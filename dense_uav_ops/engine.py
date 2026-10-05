"""Simulation loop for one experiment.

Information boundaries:
- Controlled aircraft know their own state exactly (idealized navigation) and
  see other aircraft only through the shared surveillance feed.
- The oracle sees true states and is the only source of outcome events.
- Host compute time is measured and reported separately; it never changes a
  simulated outcome, so results are identical across machines and loads.

Event accounting: a loss of separation (LoS) or contact is counted once per
episode (when a pair enters the condition) and only while the measurement
window is open. Each event is attributed by who was involved, so risk that the
system could have acted on (at least one controlled aircraft) is reported
separately from airspace-wide risk.
"""
from dataclasses import dataclass
import time as clock
import numpy as np

from . import __version__
from .oracle import outside_volume, quadratic_minimum, swept_obstacles, swept_pairs
from .planner import plan, segment_distance
from .routes import Routes
from .surveillance import Feed, Snapshot
from .traffic import build
from .vehicles import Limits, preferred_velocity, project, violations

CATEGORIES = ('cc', 'cu', 'uu', 'cm', 'um', 'mm')
ATTRIBUTABLE = ('cc', 'cu', 'cm')


@dataclass
class World:
    """Static per-aircraft attributes plus the current route waypoint, shared with planners."""
    limits: Limits
    radius: np.ndarray
    cruise: np.ndarray
    manned: np.ndarray
    fixed: np.ndarray
    controlled: np.ndarray
    waypoint: np.ndarray
    final_leg: np.ndarray
    goal: np.ndarray
    burden: np.ndarray
    airborne: np.ndarray  # truth; only training critics may read it, never planners or actors


def category(controlled, manned, i, j):
    def kind(x):
        return 'm' if manned[x] else ('c' if controlled[x] else 'u')
    pair = ''.join(sorted(kind(i) + kind(j)))
    return {'cc': 'cc', 'cu': 'cu', 'uu': 'uu', 'cm': 'cm', 'mu': 'um', 'mm': 'mm'}[pair]


def load_policy(experiment):
    kind = experiment.controller.kind
    if kind == 'recurrent':
        from .learning.recurrent import load_policy as load
    elif kind == 'graph':
        from .learning.graph import load_policy as load
    else:
        return None
    return load(experiment.controller.checkpoint)


def simulate(experiment, policy=None, record=False):
    e = experiment.validate()
    started = clock.perf_counter()
    traffic = build(e)
    n = traffic.n
    dt = e.window.dt_s
    controller = e.controller.kind
    if policy is None and controller in ('recurrent', 'graph'):
        policy = load_policy(e)
    if policy is not None and e.seed in getattr(policy, 'training_seeds', ()):
        raise ValueError('evaluation seed was used to train this policy')
    routes = Routes(e, traffic)
    world = World(limits=traffic.limits, radius=traffic.radius, cruise=traffic.cruise, manned=traffic.manned,
                  fixed=traffic.fixed, controlled=traffic.controlled, waypoint=routes.waypoints(),
                  final_leg=routes.final(), goal=traffic.goal, burden=np.zeros(n),
                  airborne=np.zeros(n, bool))
    feed = Feed(e, traffic)
    if policy is not None:
        policy.reset(n)
    guidance = None
    if controller == 'daidalus':
        from .daidalus import Bridge, Guidance
        guidance = Guidance(e, Bridge(e.controller.daidalus_manifest))
    drop_rng = np.random.default_rng(np.random.SeedSequence([e.seed, 301]))
    wander_rng = np.random.default_rng(np.random.SeedSequence([e.seed, 302]))
    low = np.array([-e.airspace.side_m / 2, -e.airspace.side_m / 2, e.airspace.floor_m])
    high = np.array([e.airspace.side_m / 2, e.airspace.side_m / 2, e.airspace.ceiling_m])
    window_start = e.window.warmup_s
    window_end = window_start + e.window.measurement_s
    total_steps = int(round((window_end + e.window.drain_s) / dt))

    p = traffic.start.copy()
    v = np.zeros((n, 3))
    airborne = np.zeros(n, bool)
    admitted = np.zeros(n, bool)
    completed = np.zeros(n, bool)
    admit_time = np.full(n, np.nan)
    complete_time = np.full(n, np.nan)
    previous = np.zeros((n, 3))
    wander = np.zeros((n, 3))
    just_finished = []
    in_los, in_contact, in_obstacle, outside = set(), set(), set(), set()
    # Events within one report interval of an aircraft's entry happen before surveillance can have
    # reported it; they are counted separately ('entry' phase) from in-flight events.
    entry_window = e.surveillance.period_s + e.surveillance.latency_s + dt
    events = {phase: {name: {c: 0 for c in CATEGORIES} for name in ('los', 'contact')} for phase in ('flight', 'entry')}
    counters = dict(obstacle_contacts_controlled=0, obstacle_contacts_uncontrolled=0, volume_exits_controlled=0,
                    volume_exits_uncontrolled=0, kinematic_violation_steps=0, controlled_steps=0,
                    fallback_steps=0, entry_denials=0, dropped_commands=0, unknown_traffic_seconds=0.,
                    controlled_seconds=0., uncontrolled_seconds=0., manned_seconds=0., uas_occupancy_seconds=0.,
                    peak_uas_occupancy=0, minimum_separation_m=np.inf)
    event_log, frames = [], []
    backlog_start = backlog_end = None
    compute_seconds = 0.
    record_every = max(1, int(round(.4 / dt)))

    def in_window(t):
        return window_start - 1e-9 <= t < window_end - 1e-9

    def threshold(i, j):
        mixed = traffic.manned[i] | traffic.manned[j]
        return np.maximum(np.where(mixed, e.requirements.manned_separation_m, e.requirements.separation_m),
                          traffic.radius[i] + traffic.radius[j])

    for step in range(total_steps):
        t = step * dt
        if abs(t - window_start) < 1e-9:
            backlog_start = int(np.sum(~traffic.manned & (traffic.request < t) & ~completed))
        if abs(t - window_end) < 1e-9:
            backlog_end = int(np.sum(~traffic.manned & (traffic.request < t) & ~completed))
        # Uncontrolled UAS and manned traffic enter when they ask to; nothing holds them.
        enter = ~airborne & ~completed & ~traffic.controlled & (traffic.activate <= t + 1e-9)
        airborne |= enter
        admitted |= enter
        admit_time[enter & np.isnan(admit_time)] = t
        v[enter] = traffic.velocity[enter]
        feed.update(t, p, v, airborne, just_finished)
        just_finished = []
        snapshot = feed.snapshot(t)
        compute_start = clock.perf_counter()

        # Admission of controlled operations, first come first served, every step. The admission
        # service knows its own clearances: controlled aircraft it admitted but that surveillance has not
        # reported yet are added to its picture as dead-reckoned tracks from their entry state.
        pending = np.flatnonzero(traffic.controlled & ~admitted & ~routes.rejected & (traffic.request <= t + 1e-9))
        if len(pending):
            picture = own_fleet_picture(e, snapshot, airborne & traffic.controlled, admit_time, traffic, t)
            estimated = int(np.sum(picture.known))
            for i in sorted(pending, key=lambda x: (traffic.request[x], x)):
                if estimated >= e.admission.occupancy_limit:
                    break
                if not entry_allowed(e, world, i, traffic, picture):
                    counters['entry_denials'] += 1
                    continue
                airborne[i] = admitted[i] = True
                admit_time[i] = t
                p[i], v[i] = traffic.start[i], traffic.velocity[i]
                picture = own_fleet_picture(e, picture, airborne & traffic.controlled, admit_time, traffic, t)
                estimated += 1

        # Commands.
        world.waypoint, world.final_leg, world.airborne = routes.waypoints(), routes.final(), airborne.copy()
        applied = np.zeros((n, 3))
        uas = airborne & ~traffic.manned
        nominal = np.zeros((n, 3))
        if np.any(uas):
            ids = np.flatnonzero(uas)
            want = preferred_velocity(p[ids], world.waypoint[ids], traffic.cruise[ids], traffic.limits.take(ids))
            nominal[ids] = project((want - v[ids]) / .6, v[ids], traffic.limits.take(ids), dt)
        applied[uas] = nominal[uas]
        rogue = uas & ~traffic.compliant
        if np.any(rogue) and e.fleet.noncompliant_acceleration_mps2 > 0:
            # Bounded random lateral wandering, independent of equipage.
            wander[rogue] = .9 * wander[rogue] + wander_rng.normal(size=(int(rogue.sum()), 3)) * e.fleet.noncompliant_acceleration_mps2 * .5
            wander[:, 2] = 0.
            norm = np.linalg.norm(wander, axis=1, keepdims=True)
            wander *= np.minimum(1., e.fleet.noncompliant_acceleration_mps2 / np.maximum(norm, 1e-9))
            ids = np.flatnonzero(rogue)
            applied[ids] = project(applied[ids] + wander[ids], v[ids], traffic.limits.take(ids), dt)
        ctrl = np.flatnonzero(airborne & traffic.controlled)
        if len(ctrl) and controller in ('predictive', 'recurrent', 'graph'):
            observation = policy.observe(e, world, ctrl, p, v, snapshot) if policy is not None else None
            result = plan(e, world, ctrl, p, v, snapshot, nominal, policy, observation)
            applied[ctrl] = result.command
            if in_window(t):
                counters['fallback_steps'] += int(np.sum(result.fallback))
        elif len(ctrl) and controller == 'daidalus':
            want = preferred_velocity(p[ctrl], world.waypoint[ctrl], traffic.cruise[ctrl], traffic.limits.take(ctrl))
            applied[ctrl] = guidance.commands(t, world, ctrl, p, v, snapshot, want)
        if e.environment.command_drop_probability > 0:
            dropped = drop_rng.random(n) < e.environment.command_drop_probability  # drawn every step: aligned streams
            drop = ctrl[dropped[ctrl]]
            applied[drop] = previous[drop]
            counters['dropped_commands'] += len(drop)
        if len(ctrl):
            world.burden[ctrl] += np.linalg.norm(applied[ctrl] - nominal[ctrl], axis=1) * dt
            if in_window(t):
                counters['controlled_steps'] += len(ctrl)
        if e.environment.actuator_time_constant_s > 0:
            beta = 1 - np.exp(-dt / e.environment.actuator_time_constant_s)
            applied[uas] = previous[uas] + beta * (applied[uas] - previous[uas])
        compute_seconds += clock.perf_counter() - compute_start
        previous = applied.copy()

        # True motion: wind acts on UAS; manned transits are scripted straight lines.
        phase = 2 * np.pi * t / e.environment.wind_period_s
        actual = applied.copy()
        actual[uas] += e.environment.wind_mps2 * np.array([np.cos(phase), np.sin(phase), 0.])
        actual[~airborne] = 0.

        # Oracle events.
        ii, jj, distance = swept_pairs(p, v, actual, airborne, threshold, dt)
        if len(distance):
            counters['minimum_separation_m'] = min(counters['minimum_separation_m'], float(distance.min()))
        contact = distance < traffic.radius[ii] + traffic.radius[jj]
        los = distance < threshold(ii, jj)
        now_los = {(int(a), int(b)) for a, b in zip(ii[los], jj[los])}
        now_contact = {(int(a), int(b)) for a, b in zip(ii[contact], jj[contact])}
        for name, now, before in (('los', now_los, in_los), ('contact', now_contact, in_contact)):
            for a, b in now - before:
                if in_window(t):
                    cat = category(traffic.controlled, traffic.manned, a, b)
                    phase = 'entry' if min(t - admit_time[a], t - admit_time[b]) < entry_window - 1e-9 else 'flight'
                    events[phase][name][cat] += 1
                    if len(event_log) < 2000:
                        event_log.append({'time': round(t, 3), 'type': name, 'pair': [a, b], 'category': cat, 'phase': phase})
        in_los, in_contact = now_los, now_contact
        hits = set(swept_obstacles(p, v, actual, uas, traffic.radius, e.airspace.obstacles, dt))
        for i, k in hits - in_obstacle:
            if in_window(t):
                counters['obstacle_contacts_controlled' if traffic.controlled[i] else 'obstacle_contacts_uncontrolled'] += 1
        in_obstacle = hits
        out = set(np.flatnonzero(uas & outside_volume(p, v, actual, low, high, traffic.radius, dt)).tolist())
        for i in out - outside:
            if in_window(t):
                counters['volume_exits_controlled' if traffic.controlled[i] else 'volume_exits_uncontrolled'] += 1
        outside = out

        # Exposure inside the measurement window.
        if in_window(t):
            inside = airborne & np.all((p[:, :2] >= low[:2]) & (p[:, :2] <= high[:2]), axis=1)
            counters['controlled_seconds'] += dt * int(np.sum(airborne & traffic.controlled))
            counters['uncontrolled_seconds'] += dt * int(np.sum(uas & ~traffic.controlled))
            counters['manned_seconds'] += dt * int(np.sum(inside & traffic.manned))
            occupancy = int(np.sum(uas))
            counters['uas_occupancy_seconds'] += dt * occupancy
            counters['peak_uas_occupancy'] = max(counters['peak_uas_occupancy'], occupancy)
            counters['unknown_traffic_seconds'] += dt * int(np.sum(inside & ~snapshot.known))

        if policy is not None and hasattr(policy, 'transition'):
            policy.transition(training_reward(e, traffic, world, p, v, actual, applied, ctrl, ii, jj, contact, los,
                                              hits, out, dt), step == total_steps - 1)

        # Integrate, check envelopes, detect arrivals.
        new_v = v + actual * dt
        if in_window(t):
            # Commanded motion must respect the envelope; wind-induced deviations are not violations.
            ids = np.flatnonzero(uas)
            bad = violations(applied[ids], v[ids], v[ids] + applied[ids] * dt, traffic.limits.take(ids), dt)
            counters['kinematic_violation_steps'] += int(np.sum(bad))
        reached = np.zeros(n, bool)
        for i in np.flatnonzero(uas & world.final_leg):
            reached[i] = quadratic_minimum(p[i] - world.waypoint[i], v[i], actual[i], dt) <= e.requirements.goal_radius_m
        reached |= airborne & traffic.manned & (p[:, 0] >= traffic.goal[:, 0])
        p[airborne] += v[airborne] * dt + .5 * actual[airborne] * dt ** 2
        v[airborne] = new_v[airborne]
        routes.advance(p, airborne & traffic.controlled)
        completed |= reached
        complete_time[reached] = t + dt
        airborne &= ~reached
        v[~airborne] = 0.
        just_finished = np.flatnonzero(reached).tolist()
        if record and step % record_every == 0:
            frames.append({'t': round(t + dt, 3), 'p': np.round(p[airborne], 1).tolist(),
                           'id': np.flatnonzero(airborne).tolist()})
    if guidance is not None:
        guidance.bridge.close()

    metrics = summarize_run(e, traffic, events, counters, admitted, completed, admit_time, complete_time,
                            backlog_start, backlog_end, routes.rejected)
    if controller not in ('predictive', 'recurrent', 'graph'):
        metrics['fallback_steps'] = metrics['fallback_fraction'] = None  # no maneuver library to fail
    if guidance is not None:
        metrics['daidalus_guidance'] = dict(guidance.counts)
        decisions = sum(guidance.counts.values())
        metrics['daidalus_unresolved_fraction'] = ((guidance.counts['recovery'] + guidance.counts['none']) / decisions
                                                   if decisions else None)
        metrics['daidalus_alerted_aircraft'] = sum(level > 0 for level in guidance.max_alert.values())
    result = {'run_id': e.run_id(), 'version': __version__, 'experiment': e.to_dict(), 'metrics': metrics,
              'events': event_log, 'policy_sha256': getattr(policy, 'checkpoint_sha256', None),
              'compute': {'wall_seconds': clock.perf_counter() - started, 'control_seconds': compute_seconds,
                          'control_ms_per_controlled_step': 1000 * compute_seconds / max(1, counters['controlled_steps']),
                          'note': 'Host measurement of the centralized simulation; not onboard latency. Never fed back into outcomes.'}}
    if record:
        result['replay'] = {'dt': dt, 'frames': frames, 'radius': traffic.radius.tolist(),
                            'controlled': traffic.controlled.astype(int).tolist(),
                            'manned': traffic.manned.astype(int).tolist(), 'fixed': traffic.fixed.astype(int).tolist(),
                            'obstacles': [list(o) for o in e.airspace.obstacles],
                            'bounds': [low.tolist(), high.tolist()], 'events': event_log}
    return result


def own_fleet_picture(e, snapshot, controlled_airborne, admit_time, traffic, t):
    """Snapshot plus controlled aircraft admitted too recently for surveillance to have reported them."""
    recent = (t - admit_time) <= e.surveillance.period_s + e.surveillance.latency_s + e.window.dt_s + 1e-9
    missing = controlled_airborne & ~snapshot.known & recent
    if not np.any(missing):
        return snapshot
    picture = Snapshot(*(x.copy() for x in (snapshot.position, snapshot.velocity, snapshot.position_error,
                                            snapshot.velocity_error, snapshot.age, snapshot.known)))
    age = t - admit_time[missing]
    picture.position[missing] = traffic.start[missing] + traffic.velocity[missing] * age[:, None]
    picture.velocity[missing] = traffic.velocity[missing]
    picture.age[missing] = age
    picture.known[missing] = True
    return picture


def entry_allowed(e, world, i, traffic, picture):
    """Entry rules, each including the previous one.

    'spacing': over the next `admission.spacing_horizon_s`, the entrant flying straight at its entry
    velocity stays clear by the required distance of every known aircraft's constant-velocity
    prediction, inflated by declared report errors and the *physical* UAS acceleration bound (so the
    rule does not depend on the planner's assumed traffic acceleration). 'clearance': the planner also
    has an admissible maneuver at entry. 'recovery': a checked recovery maneuver also exists.
    'none': no rule (ablation only).
    """
    check = e.admission.entry_check
    if check == 'none':
        return True
    others = picture.known.copy()
    others[i] = False
    sep = np.where(world.manned, e.requirements.manned_separation_m, e.requirements.separation_m)
    need = np.maximum(sep, traffic.radius[i] + traffic.radius)
    horizon = e.admission.spacing_horizon_s
    physical = max(e.multirotor.acceleration_mps2, e.fixed_wing.acceleration_mps2)
    elapsed = picture.age + horizon
    error = picture.position_error + picture.velocity_error * elapsed + .5 * physical * elapsed ** 2
    start = picture.position - traffic.start[i]
    relative = picture.velocity - traffic.velocity[i]
    gap = segment_distance(start, start + relative * horizon) - error
    if np.any(gap[others] < need[others]):
        return False
    if check == 'spacing':
        return True
    p = np.array(traffic.start)
    v = np.zeros_like(p)
    v[i] = traffic.velocity[i]
    if check == 'clearance':
        result = plan(e, world, np.array([i]), p, v, picture, np.zeros_like(p))
        return bool(result.feasible.any())
    from .recovery import check as recovery_check
    return recovery_check(e, world, i, p[i], v[i], picture, picture.known)['valid']


def summarize_run(e, traffic, events, counters, admitted, completed, admit_time, complete_time,
                  backlog_start, backlog_end, rejected):
    start, end = e.window.warmup_s, e.window.warmup_s + e.window.measurement_s
    hours = lambda seconds: seconds / 3600.
    cohort = ~traffic.manned & (traffic.request >= start - 1e-9) & (traffic.request < end - 1e-9)
    controlled_cohort = cohort & traffic.controlled
    finished_in_window = completed & (complete_time > start) & (complete_time <= end + 1e-9)
    horizon_end = end + e.window.drain_s
    # Service delay of an operation: completion time minus (request time + nominal traversal time), so it
    # includes any wait for entry. Unfinished operations are censored at the end of the drain window and
    # contribute a lower bound.
    finish = np.where(completed, complete_time, horizon_end)
    delay = finish - traffic.request - traffic.nominal_time
    done_delays = delay[controlled_cohort & completed]
    censored = np.maximum(delay[controlled_cohort & ~completed], 0.)  # an unfinished operation is at least on time
    wait = np.where(admitted, admit_time, horizon_end) - traffic.request
    flight, entry = events['flight'], events['entry']
    attributable_los = sum(flight['los'][c] for c in ATTRIBUTABLE)
    attributable_contact = sum(flight['contact'][c] for c in ATTRIBUTABLE)
    uas_seconds = counters['controlled_seconds'] + counters['uncontrolled_seconds']
    mean = lambda x: float(np.mean(x)) if len(x) else None
    p95 = lambda x: float(np.percentile(x, 95)) if len(x) else None
    return {
        'offered_uas': int(cohort.sum()),
        'offered_controlled': int(controlled_cohort.sum()),
        'offered_manned': int(np.sum(traffic.manned & (traffic.request >= start) & (traffic.request < end))),
        'admitted_controlled': int(np.sum(controlled_cohort & admitted)),
        'route_rejected_controlled': int(np.sum(controlled_cohort & rejected)),
        'completed_controlled': int(np.sum(controlled_cohort & completed)),
        'controlled_completion_fraction': mean(completed[controlled_cohort]),
        'uncontrolled_completion_fraction': mean(completed[cohort & ~traffic.controlled]),
        'uas_throughput_per_hour': float(np.sum(finished_in_window & ~traffic.manned)) / hours(e.window.measurement_s),
        'controlled_throughput_per_hour': float(np.sum(finished_in_window & traffic.controlled)) / hours(e.window.measurement_s),
        'mean_delay_s': mean(done_delays),
        'p95_delay_s': p95(done_delays),
        'controlled_delays_s': [round(float(x), 3) for x in done_delays],
        'controlled_censored_delays_s': [round(float(x), 3) for x in censored],
        'controlled_completed_in_window': int(np.sum(finished_in_window & traffic.controlled)),
        'mean_entry_wait_s': mean(wait[controlled_cohort]),
        'p95_entry_wait_s': p95(wait[controlled_cohort]),
        'backlog_growth': None if backlog_start is None or backlog_end is None else backlog_end - backlog_start,
        'mean_uas_occupancy': counters['uas_occupancy_seconds'] / e.window.measurement_s,
        'peak_uas_occupancy': counters['peak_uas_occupancy'],
        'controlled_flight_hours': hours(counters['controlled_seconds']),
        'uas_flight_hours': hours(uas_seconds),
        'manned_flight_hours': hours(counters['manned_seconds']),
        'los_events': flight['los'],
        'contact_events': flight['contact'],
        'entry_los_events': entry['los'],
        'entry_contact_events': entry['contact'],
        'attributable_los': attributable_los,
        'attributable_contacts': attributable_contact,
        'attributable_uas_los': flight['los']['cc'] + flight['los']['cu'],
        'attributable_uas_contacts': flight['contact']['cc'] + flight['contact']['cu'],
        'entry_attributable_uas_los': entry['los']['cc'] + entry['los']['cu'],
        'entry_attributable_uas_contacts': entry['contact']['cc'] + entry['contact']['cu'],
        'all_los': sum(flight['los'].values()) + sum(entry['los'].values()),
        'all_contacts': sum(flight['contact'].values()) + sum(entry['contact'].values()),
        'obstacle_contacts_controlled': counters['obstacle_contacts_controlled'],
        'obstacle_contacts_uncontrolled': counters['obstacle_contacts_uncontrolled'],
        'volume_exits_controlled': counters['volume_exits_controlled'],
        'volume_exits_uncontrolled': counters['volume_exits_uncontrolled'],
        'kinematic_violation_steps': counters['kinematic_violation_steps'],
        'controlled_steps': counters['controlled_steps'],
        'fallback_steps': counters['fallback_steps'],
        'fallback_fraction': counters['fallback_steps'] / counters['controlled_steps'] if counters['controlled_steps'] else None,
        'entry_denials': counters['entry_denials'],
        'dropped_commands': counters['dropped_commands'],
        'unknown_traffic_seconds': counters['unknown_traffic_seconds'],
        'minimum_separation_m': None if not np.isfinite(counters['minimum_separation_m']) else counters['minimum_separation_m'],
    }


def training_reward(e, traffic, world, p, v, actual, applied, ctrl, ii, jj, contact, los, hits, out, dt):
    """Per-aircraft shaping reward for learning only; it is not a safety measure."""
    n = len(p)
    reward = np.zeros(n)
    if not len(ctrl):
        return reward
    goal = world.waypoint[ctrl]
    new_p = p[ctrl] + v[ctrl] * dt + .5 * actual[ctrl] * dt ** 2
    progress = np.linalg.norm(p[ctrl] - goal, axis=1) - np.linalg.norm(new_p - goal, axis=1)
    reward[ctrl] = progress / traffic.cruise[ctrl] - .02 * dt - .001 * np.sum(applied[ctrl] ** 2, axis=1) * dt
    reward[ctrl] += 5. * ((np.linalg.norm(new_p - goal, axis=1) < e.requirements.goal_radius_m) & world.final_leg[ctrl])
    penalty = np.zeros(n)
    np.add.at(penalty, ii[contact], 20.)
    np.add.at(penalty, jj[contact], 20.)
    np.add.at(penalty, ii[los], .2 * dt)
    np.add.at(penalty, jj[los], .2 * dt)
    for i, _ in hits:
        penalty[i] += 20.
    for i in out:
        penalty[i] += 5.
    return reward - penalty
