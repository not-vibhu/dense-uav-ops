"""Streaming traffic harness. Manned trajectories are exogenous and never negotiated.

Reuses the existing finite predictive library without changing its source pins.
The global oracle sees every aircraft, including traffic absent from the feed.
"""
from dataclasses import asdict, replace
import time
import numpy as np

from swarm_sim.config import Config
from swarm_sim.controllers import preferred_velocity, vehicle_project
from swarm_sim.oracle import quadratic_minimum, swept_pairs, swept_obstacles
from swarm_sim.predictive import predictive_control, volume_clearance
from .profile import Profile


def schedule(rate, stop, rng):
    if rate == 0:
        return np.array([], float)
    interval = 3600. / rate
    return np.arange(rng.uniform(0, interval), stop, interval)


def build_traffic(profile, rate, seed):
    rng = np.random.default_rng(np.random.SeedSequence([seed, 711]))
    stop = profile.warmup_s + profile.measurement_s
    ua = np.ceil(schedule(rate, stop, rng)/profile.dt_s)*profile.dt_s
    ma = np.ceil(schedule(profile.manned_operations_per_hour, stop, rng)/profile.dt_s)*profile.dt_s
    ua, ma = ua[ua < stop], ma[ma < stop]
    n = max(2, len(ua) + len(ma))
    if n > 500:
        raise ValueError("More than 500 scheduled operations: shorten the window or split independent runs")
    manned = np.arange(n) >= len(ua)
    manned[len(ua) + len(ma):] = False
    requested = np.full(n, np.inf)
    requested[:len(ua)] = ua
    requested[len(ua):len(ua) + len(ma)] = ma
    fixed = rng.random(n) < profile.fixed_wing_fraction
    cooperative = rng.random(n) < profile.cooperative_fraction
    compliant = rng.random(n) < profile.compliance_fraction
    cooperative[manned] = False
    compliant[manned] = True  # Class-specific bounded exogenous trajectory, not RID compliance.
    controlled = cooperative & compliant & ~manned
    fixed[manned] = True
    radius = np.where(manned, profile.manned_radius_m, np.where(fixed, profile.fixed_wing_radius_m, profile.multirotor_radius_m))
    cruise = np.where(manned, profile.manned_speed_mps, profile.drone_speed_mps)
    p = np.zeros((n, 3))
    goals = np.zeros_like(p)
    edge = profile.area_m / 2 - 25 - radius
    for i in range(n):
        axis = 0 if manned[i] or profile.scenario == "corridor" else i % 2
        direction = 1 if manned[i] or profile.scenario == "corridor" else (1 if i % 4 < 2 else -1)
        half_width = profile.area_m/5 if profile.uas_route_half_width_m is None else profile.uas_route_half_width_m
        lane = profile.manned_route_lateral_offset_m if manned[i] else rng.uniform(-half_width, half_width)
        low = profile.floor_m+radius[i]+10 if profile.uas_altitude_min_m is None else profile.uas_altitude_min_m
        high = profile.ceiling_m-radius[i]-10 if profile.uas_altitude_max_m is None else profile.uas_altitude_max_m
        altitude = profile.manned_altitude_m if manned[i] else rng.uniform(low, high)
        p[i, axis] = -direction * edge[i]
        p[i, 1-axis] = lane
        p[i, 2] = altitude
        goals[i] = p[i]
        goals[i, axis] *= -1
    direction = goals - p
    v = direction / np.maximum(np.linalg.norm(direction, axis=1, keepdims=True), 1e-9) * cruise[:, None]
    if profile.scenario == 'manned_intrusion':
        # A bounded lateral excursion changes the protected transit path while
        # retaining a reachable exit portal. No UAS command affects this script.
        transit = np.abs(goals[manned, 0]-p[manned, 0])/profile.manned_speed_mps
        pulse = np.minimum(6., transit/2)
        goals[manned, 1] += profile.manned_acceleration_bound_mps2*pulse**2/(2*np.pi)
        v[manned, 1] = 0.
    obstacles = np.array([[0., 0., 42., 20.]]) if profile.scenario == "urban" else np.empty((0, 4))
    if profile.obstacles:
        obstacles = np.concatenate((obstacles, np.array(profile.obstacles, float)))
    world = dict(position=p, velocity=v, goals=goals, mission_goals=goals.copy(),
                 fixed=fixed, cooperative=controlled, cruise=cruise,
                 radius=radius.copy(), obstacles=obstacles)
    return world, requested, manned, cooperative, compliant


class Feed:
    """Synthetic fused surveillance with sensor coverage, bounded errors and age.

    Manned observations represent external surveillance, not Remote ID. Coverage
    is a region-wide sensor at the origin. Own state remains locally available.
    No truth-initialization or entry announcements are injected into this feed.
    """
    def __init__(self, profile, n, seed):
        self.profile = profile
        self.rng = np.random.default_rng(np.random.SeedSequence([seed, 712]))
        self.p = np.zeros((n, 3))
        self.v = np.zeros_like(self.p)
        self.source = np.full(n, -np.inf)
        self.seen = np.zeros(n, bool)
        self.detectable = self.rng.random(n) < profile.manned_detection_fraction
        self.pending = []
        self.next_sample = 0.

    def update(self, t, p, v, active, manned):
        pr = self.profile
        if t + 1e-9 >= self.next_sample:
            self.next_sample += pr.telemetry_period_s
            mask = active & (np.linalg.norm(p, axis=1) <= pr.sensor_range_m)
            mask &= ~manned | self.detectable
            mask &= self.rng.random(len(p)) >= pr.telemetry_loss_fraction
            if pr.scenario == "sensor_outage" and pr.warmup_s <= t < pr.warmup_s + 10:
                mask[:] = False
            noise = self.rng.normal(size=p.shape)
            noise /= np.maximum(np.linalg.norm(noise, axis=1, keepdims=True), 1e-9)
            vn = self.rng.normal(size=v.shape)
            vn /= np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-9)
            self.pending.append((t + pr.telemetry_latency_s, t, mask,
                                 p + noise * pr.position_error_m, v + vn * pr.velocity_error_mps))
        keep = []
        for arrival, source, mask, op, ov in self.pending:
            if arrival <= t + 1e-9:
                mask = mask & (source > self.source)
                self.p[mask], self.v[mask] = op[mask], ov[mask]
                self.source[mask] = source
                self.seen[mask] = True
            else:
                keep.append((arrival, source, mask, op, ov))
        self.pending = keep

    def snapshot(self, t, acceleration):
        age = np.where(self.seen, np.maximum(0., t - self.source), 0.)
        pred = self.p + self.v * age[:, None]
        e = self.profile.position_error_m + self.profile.velocity_error_mps * age + .5 * acceleration * age**2
        ev = self.profile.velocity_error_mps + acceleration * age
        return pred, self.v.copy(), e, ev, age


def protection(profile, manned, radius, i, j):
    mixed = manned[i] | manned[j]
    return np.maximum(np.where(mixed, profile.manned_separation_m, profile.uas_separation_m), radius[i] + radius[j])


def simulate(profile: Profile, rate: float, occupancy_limit: int, seed: int):
    profile.validate()
    if not np.isfinite(rate) or rate <= 0 or isinstance(occupancy_limit, bool) or not isinstance(occupancy_limit, int) or not 1 <= occupancy_limit <= 500:
        raise ValueError("Positive demand rate and integer occupancy limit 1–500 required")
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValueError("Nonnegative integer seed required")
    world, requested, manned, cooperative, compliant = build_traffic(profile, rate, seed)
    p, v = world['position'].copy(), world['velocity'].copy()
    entry_positions = p.copy()
    initial_velocity = v.copy()
    radii = world['radius'].copy()
    # Only traffic radii for the shield are inflated. Physical oracle radii are
    # kept separate; UAS–manned protection is conservative for every UAS body.
    world['radius'][manned] = np.maximum(radii[manned], profile.manned_separation_m)
    controlled = world['cooperative']
    n = len(p)
    acceleration = max(profile.drone_acceleration_mps2, profile.manned_acceleration_bound_mps2)
    cfg = Config(controller='predictive', drones=n, area=profile.area_m,
                 altitude_floor=profile.floor_m, altitude_ceiling=profile.ceiling_m,
                 dt=profile.dt_s, cruise_speed=profile.drone_speed_mps,
                 max_speed=profile.drone_max_speed_mps, acceleration_limit=profile.drone_acceleration_mps2,
                 fixed_wing_min_speed=profile.fixed_wing_min_speed_mps,
                 fixed_wing_turn_rate_deg=profile.fixed_wing_turn_deg_s,
                 fixed_wing_climb_limit=profile.fixed_wing_climb_mps,
                 separation=profile.uas_separation_m, advertised_acceleration_bound=acceleration,
                 position_error_bound=profile.position_error_m, velocity_error_bound=profile.velocity_error_mps)
    goal_cfg = replace(cfg, controller='goal')
    active = np.zeros(n, bool)
    admitted = np.zeros(n, bool)
    completed = np.zeros(n, bool)
    admitted_time = np.full(n, np.nan)
    completed_time = np.full(n, np.nan)
    v[:] = 0.
    previous = np.zeros_like(p)
    feed = Feed(profile, n, seed)
    failure_rng = np.random.default_rng(np.random.SeedSequence([seed, 713]))
    control_failures = (failure_rng.random(n) < profile.control_failure_fraction) & ~manned
    collision_pairs, protected_pairs, obstacle_hits, volume_hits = set(), set(), set(), set()
    metrics = dict(no_admissible_aircraft_steps=0, kinematic_violation_aircraft_steps=0,
                   command_deadline_misses=0, unobserved_manned_aircraft_steps=0,
                   occupancy_overflow_steps=0, peak_total_occupancy=0, peak_uas_occupancy=0,
                   control_failure_aircraft_steps=0, endurance_exceeded_aircraft_steps=0,
                   peak_manned_occupancy=0, measured_aircraft_seconds=0.)
    times = []
    backlog_start = backlog_end = 0
    stop = profile.warmup_s + profile.measurement_s
    end_time = stop + profile.drain_s
    for step in range(round(end_time / cfg.dt)):
        t = step * cfg.dt
        if abs(t-profile.warmup_s) < 1e-7:
            backlog_start = int(np.sum((requested < profile.warmup_s) & ~completed))
        if abs(t-stop) < 1e-7:
            backlog_end = int(np.sum((requested < stop) & ~completed))
        # Last step cannot extend beyond the declared observation window.
        dt = min(cfg.dt, end_time - t)
        local_start = time.perf_counter()
        approaching = manned & ~admitted & (requested > t) & (requested <= t + profile.surveillance_lookahead_s)
        p[approaching] = entry_positions[approaching] + initial_velocity[approaching] * (t-requested[approaching, None])
        v[approaching] = initial_velocity[approaching]
        feed.update(t, p, v, active | approaching, manned)
        snapshot = feed.snapshot(t, acceleration)
        pending = np.flatnonzero((requested <= t + 1e-9) & ~admitted)
        # Traffic we do not control enters regardless of admission limits.
        for i in sorted(pending, key=lambda i: (bool(controlled[i]), requested[i], i)):
            if controlled[i]:
                if np.sum(active) >= occupancy_limit:
                    continue
                neighbors = np.flatnonzero(active & feed.seen)
                safe = True
                for j in neighbors:
                    bound = protection(profile, manned, radii, i, j)
                    e = snapshot[2][j] + snapshot[3][j] * cfg.dt + .5 * acceleration * cfg.dt**2
                    e += .4 * (snapshot[4][j] + cfg.dt)**2
                    distance = quadratic_minimum(p[i]-snapshot[0][j], initial_velocity[i]-snapshot[1][j], np.zeros(3), cfg.dt)
                    if distance < bound + e:
                        safe = False
                        break
                if not safe:
                    continue
            active[i] = admitted[i] = True
            p[i] = entry_positions[i]
            admitted_time[i] = t
            v[i] = initial_velocity[i]
        # A shared feed can report no new aircraft during its initial latency.
        # Ownship state is local; unknown external aircraft are not conjured up.
        reported_active = active & feed.seen
        target = preferred_velocity(p, world['goals'], world['cruise'], world['fixed'], goal_cfg)
        desired = vehicle_project((target - v) / .6, v, world['fixed'], goal_cfg)
        desired[manned] = 0.
        applied, stats = predictive_control(cfg, world, p, v, reported_active, snapshot, desired)
        applied[~controlled & ~manned] = desired[~controlled & ~manned]
        for i in np.flatnonzero(active & controlled & ~feed.seen):
            own_world = {**world, 'cooperative': np.arange(n) == i}
            own_active = reported_active.copy()
            own_active[i] = True
            own_applied, own_stats = predictive_control(cfg, own_world, p, v, own_active, snapshot, desired)
            applied[i] = own_applied[i]
            stats['unresolved'][i] = own_stats['unresolved'][i]
        # Noncompliance changes bounded control independently of cooperation.
        rogue = active & ~compliant & ~manned
        applied[rogue, 1] += profile.drone_acceleration_mps2 * np.sin(t + np.flatnonzero(rogue))
        applied[~manned] = vehicle_project(applied[~manned], v[~manned], world['fixed'][~manned], cfg)
        applied[manned] = 0.
        if profile.scenario == 'manned_intrusion':
            ids = np.flatnonzero(manned & active)
            transit = np.abs(world['goals'][ids, 0]-entry_positions[ids, 0])/profile.manned_speed_mps
            pulse = np.minimum(6., transit/2)
            phase = (t-admitted_time[ids]-transit/4)/pulse
            applied[ids, 1] = np.where((phase >= 0) & (phase <= 1),
                profile.manned_acceleration_bound_mps2 * np.sin(2*np.pi*phase), 0.)
        if profile.actuator_time_constant_s:
            beta = 1 - np.exp(-dt / profile.actuator_time_constant_s)
            applied[~manned] = previous[~manned] + beta * (applied[~manned] - previous[~manned])
        failed = active & control_failures & ((t-admitted_time) >= profile.control_failure_after_s)
        applied[failed] = previous[failed]
        metrics['control_failure_aircraft_steps'] += int(np.sum(failed))
        metrics['endurance_exceeded_aircraft_steps'] += int(np.sum(active & ~manned & ((t-admitted_time) > profile.flight_endurance_s)))
        command_ms = (time.perf_counter() - local_start) * 1000
        times.append(command_ms)
        missed = command_ms * profile.hardware_time_multiplier > profile.command_deadline_ms
        metrics['command_deadline_misses'] += int(missed)
        if missed:
            applied[controlled & active] = previous[controlled & active]
        previous = applied.copy()
        actual = applied.copy()
        if profile.scenario == 'wind_gust':
            actual[:, 1] += profile.wind_acceleration_mps2 * np.sin(t)
        actual[~active] = 0.
        metrics['no_admissible_aircraft_steps'] += int(np.sum(stats['unresolved'] & active))
        metrics['unobserved_manned_aircraft_steps'] += int(np.sum(active & manned & ~feed.seen))
        count = int(np.sum(active))
        metrics['peak_total_occupancy'] = max(metrics['peak_total_occupancy'], count)
        metrics['peak_uas_occupancy'] = max(metrics['peak_uas_occupancy'], int(np.sum(active & ~manned)))
        metrics['peak_manned_occupancy'] = max(metrics['peak_manned_occupancy'], int(np.sum(active & manned)))
        metrics['occupancy_overflow_steps'] += int(count > occupancy_limit)
        if profile.warmup_s <= t < stop:
            metrics['measured_aircraft_seconds'] += count * min(dt, stop - t)
        i, j, distances, _ = swept_pairs(p, v, actual, active, radii,
                                       max(profile.uas_separation_m, profile.manned_separation_m), dt)
        for a, b in zip(i[distances < radii[i]+radii[j]], j[distances < radii[i]+radii[j]]):
            collision_pairs.add((int(a), int(b)))
        protected = distances < protection(profile, manned, radii, i, j)
        protected_pairs.update((int(a), int(b)) for a, b in zip(i[protected], j[protected]))
        obstacle_hits.update(swept_obstacles(p, v, actual, active, radii, world['obstacles'], dt))
        # Body-volume clearance, including constant-acceleration extrema.
        step_cfg = replace(cfg, dt=dt)
        bad_volume = active & (volume_clearance(p, v, actual, radii, step_cfg) < -1e-8)
        volume_hits.update(int(i) for i in np.flatnonzero(bad_volume))
        new_v = v + actual * dt
        uas = active & ~manned
        violations = (np.linalg.norm(actual, axis=1) > profile.drone_acceleration_mps2 + profile.wind_acceleration_mps2 + 1e-6)
        violations |= np.linalg.norm(new_v, axis=1) > cfg.max_speed + 1e-6
        fw = world['fixed'] & uas
        angle = np.arctan2(new_v[:, 1], new_v[:, 0]) - np.arctan2(v[:, 1], v[:, 0])
        angle = np.abs((angle + np.pi) % (2*np.pi) - np.pi)
        violations |= fw & ((np.linalg.norm(new_v[:, :2], axis=1) < cfg.fixed_wing_min_speed - 1e-6) |
                            (angle > np.deg2rad(cfg.fixed_wing_turn_rate_deg) * dt + 1e-6) |
                            (np.abs(new_v[:, 2]) > cfg.fixed_wing_climb_limit + 1e-6))
        metrics['kinematic_violation_aircraft_steps'] += int(np.sum(violations & uas))
        manned_violation = ((np.linalg.norm(actual, axis=1) > profile.manned_acceleration_bound_mps2 + profile.wind_acceleration_mps2 + 1e-6) |
                            (np.linalg.norm(new_v, axis=1) > profile.manned_max_speed_mps + 1e-6) |
                            (np.linalg.norm(new_v[:, :2], axis=1) < profile.manned_min_speed_mps - 1e-6) |
                            (angle > np.deg2rad(profile.manned_turn_deg_s) * dt + 1e-6) |
                            (np.abs(new_v[:, 2]) > profile.manned_climb_mps + 1e-6))
        metrics['kinematic_violation_aircraft_steps'] += int(np.sum(manned_violation & manned & active))
        reached = np.zeros(n, bool)
        for a in np.flatnonzero(active):
            reached[a] = quadratic_minimum(p[a] - world['goals'][a], v[a], actual[a], dt) <= cfg.goal_radius
        p += v * dt + .5 * actual * dt**2
        v = new_v
        completed[reached] = True
        completed_time[reached] = t + dt
        active[reached] = False
        v[~active] = 0.
    cohort = (requested >= profile.warmup_s) & (requested < stop)
    exits = completed & (completed_time >= profile.warmup_s) & (completed_time < stop)
    ua_cohort, ma_cohort = cohort & ~manned, cohort & manned
    waits = np.where(admitted, admitted_time - requested, end_time - requested)
    metrics.update(collision_pairs=len(collision_pairs), protected_volume_breach_pairs=len(protected_pairs),
                   uas_manned_breach_pairs=sum(bool(manned[a] or manned[b]) for a, b in protected_pairs),
                   obstacle_collision_pairs=len(obstacle_hits), body_volume_exit_aircraft=len(volume_hits),
                   uas_requested=int(np.sum(ua_cohort)), manned_requested=int(np.sum(ma_cohort)),
                   uas_cohort_completed=int(np.sum(ua_cohort & completed)),
                   manned_cohort_completed=int(np.sum(ma_cohort & completed)),
                   uas_completion_fraction=float(np.mean(completed[ua_cohort])) if np.any(ua_cohort) else None,
                   manned_completion_fraction=float(np.mean(completed[ma_cohort])) if np.any(ma_cohort) else None,
                   uas_admission_fraction=float(np.mean(admitted[ua_cohort])) if np.any(ua_cohort) else None,
                   p95_uas_wait_s=float(np.percentile(waits[ua_cohort], 95)) if np.any(ua_cohort) else None,
                   uas_completed_per_hour=float(np.sum(exits & ~manned) * 3600 / profile.measurement_s),
                   manned_completed_per_hour=float(np.sum(exits & manned) * 3600 / profile.measurement_s),
                   average_total_occupancy=metrics['measured_aircraft_seconds']/profile.measurement_s,
                   backlog_growth=backlog_end-backlog_start,
                   unfinished_aircraft=int(np.sum(np.isfinite(requested) & ~completed)),
                   command_p99_ms=float(np.percentile(times, 99)), command_max_ms=float(max(times)),
                   estimated_target_command_max_ms=float(max(times)*profile.hardware_time_multiplier),
                   cooperative_uas=int(np.sum(cooperative & ~manned & np.isfinite(requested))),
                   compliant_uas=int(np.sum(compliant & ~manned & np.isfinite(requested))),
                   controlled_uas=int(np.sum(controlled & np.isfinite(requested))))
    return dict(profile=asdict(profile), uas_demand_per_hour=rate, occupancy_limit=occupancy_limit,
                seed=seed, metrics=metrics)
