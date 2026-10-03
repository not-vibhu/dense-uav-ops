from dataclasses import asdict, replace
import hashlib
import json
import time as clock
import numpy as np

from .config import Config
from .controllers import nominal, barrier_filter, vehicle_project
from .oracle import swept_pairs, swept_obstacles, outside_volume
from .scenarios import build_world
from .telemetry import Telemetry
from .predictive import predictive_control
from .routes import Routes
from .admission import Admission
from .backup import check_backup, first_backup_command


def config_id(cfg):
    return hashlib.sha256(json.dumps(asdict(cfg), sort_keys=True).encode()).hexdigest()[:16]


def simulate(cfg: Config, record=False, policy=None):
    cfg.validate()
    if cfg.controller in ('imitation','mappo') and policy is None:
        from .learning import checkpoint_digest
        if not cfg.checkpoint_sha256:
            cfg=replace(cfg,checkpoint_sha256=checkpoint_digest(cfg.checkpoint))
    started = clock.perf_counter()
    world = build_world(cfg)
    p, v = world["position"].copy(), world["velocity"].copy()
    n = cfg.drones
    coop, fixed = world["cooperative"], world["fixed"]
    routes = Routes(cfg, world)
    world["mission_goals"] = routes.mission_goals
    admission = Admission(cfg, world, routes)
    active = admission.admitted.copy()
    initial_active = active.copy()
    v[~active] = 0.
    world["velocity"] = v.copy()
    if cfg.controller in ("imitation", "mappo") and policy is None:
        from .learning import load_actor
        policy = load_actor(cfg.checkpoint, cfg.checkpoint_sha256, cfg.controller)
    if policy is not None:
        policy.reset(n)
    completed = np.zeros(n, bool)
    debt = np.zeros(n)
    paths = np.zeros(n)
    energy = np.zeros(n)
    telemetry = Telemetry(cfg, world)
    previous = np.zeros_like(p)
    min_distance = np.inf
    collision_pairs, separation_pairs, obstacle_hits, boundary_hits = set(), set(), set(), set()
    collision_ee, collision_el, collision_ll = set(), set(), set()
    events, frames = [], []
    counters = {"filter_infeasible_drone_steps": 0, "filter_invalid_initial_drone_steps": 0,
                "shield_interventions": 0, "negotiations": 0, "partial_certificates": 0,
                "stale_drone_steps": 0, "separation_pair_step_seconds": 0.,
                "participating_separation_pair_step_seconds": 0., "participating_pair_seconds": 0.,
                "solver_overrun_drone_steps": 0, "kinematic_violation_drone_steps": 0,
                "predictive_no_admissible_drone_steps": 0,
                "checked_backup_activations": 0, "backup_unavailable_drone_steps": 0,
                "learned_proposal_rejections": 0, "active_aircraft_seconds": 0.}
    command_times = []
    next_replay = 0.
    first_participant_collision = None
    arrivals = np.full(n, np.nan)
    initial_p = p.copy()
    fault = world["scenario"].fault
    faults = set(fault.split("+"))

    def event(kind, t, **data):
        if len(events) < (1000 if record else 12):
            events.append({"time": round(t, 4), "type": kind, **data})

    for step in range(round(cfg.duration / cfg.dt)):
        t = step * cfg.dt
        if not np.any(active) and not np.any(admission.queued):
            break
        local_start = clock.perf_counter()
        telemetry.step(t, p, v)
        snapshot = telemetry.snapshot(t)
        for aircraft in admission.release(t, p, v, active, snapshot, telemetry):
            event("admission", t, aircraft=aircraft)
        snapshot = telemetry.snapshot(t)
        routes.update(p, active, world)
        counters["active_aircraft_seconds"] += int(np.sum(active)) * cfg.dt
        counters["stale_drone_steps"] += int(np.sum(active & (snapshot[-1] > .5)))
        wanted, negotiation = nominal(cfg, world, p, v, active, snapshot, debt, t)
        counters["negotiations"] += negotiation["negotiations"]
        counters["partial_certificates"] += negotiation["partial_certificates"]
        applied = wanted.copy()
        if cfg.controller in ("barrier", "negotiated") and np.any(coop & active):
            safe, stats = barrier_filter(cfg, world, p, v, active, snapshot, wanted)
            applied[coop] = safe[coop]
            counters["filter_infeasible_drone_steps"] += int(np.sum(coop & active & (stats["residual"] > 1e-3)))
            counters["filter_invalid_initial_drone_steps"] += int(np.sum(coop & active & stats["invalid_initial"]))
            counters["shield_interventions"] += int(np.sum(coop & active & stats["interventions"]))
        if cfg.controller in ("predictive", "evolved", "imitation", "mappo") and np.any(coop & active):
            applied, stats = predictive_control(cfg, world, p, v, active, snapshot, wanted, policy, debt)
            counters["learned_proposal_rejections"] += stats.get("proposal_rejections", 0)
            if cfg.admission == "checked":
                for i in np.flatnonzero(stats["unresolved"]):
                    certificate = check_backup(cfg, world, int(i), p[i], v[i], active, snapshot)
                    if certificate["valid"]:
                        applied[i] = first_backup_command(certificate)
                        counters["checked_backup_activations"] += 1
                    else:
                        counters["backup_unavailable_drone_steps"] += 1
            counters["predictive_no_admissible_drone_steps"] += int(np.sum(stats["unresolved"]))
            counters["shield_interventions"] += int(np.sum(stats["interventions"]))
        # Legacy aircraft always fly their uncoordinated goal route.
        legacy_goal = Config(**{**asdict(cfg), "controller": "goal"})
        uncooperative, _ = nominal(legacy_goal, world, p, v, active, snapshot, debt, t)
        applied[~coop] = uncooperative[~coop]
        if faults & {"turn", "intruder"} and 7 <= t <= 10:
            selected = (~coop) & (np.arange(n) % 4 == 0)
            applied[selected, 1] += 3. if "turn" in faults else 9.
            if "turn" in faults:
                applied = vehicle_project(applied, v, fixed, cfg)
        if "stop" in faults and 7 <= t <= 14:
            selected = (~coop) & (~fixed)
            applied[selected] = vehicle_project(-v, v, fixed, cfg)[selected]
        if "overrun" in faults and step % 7 == 0:
            applied[coop] = previous[coop]
            if cfg.admission == 'checked':
                for i in np.flatnonzero(coop & active):
                    certificate=check_backup(cfg,world,int(i),p[i],v[i],active,snapshot)
                    if certificate['valid']:
                        applied[i]=first_backup_command(certificate)
                        counters['checked_backup_activations']+=1
                    else:
                        counters['backup_unavailable_drone_steps']+=1
            counters["solver_overrun_drone_steps"] += int(np.sum(coop & active))
        if "lag" in faults:
            applied = .6 * previous + .4 * applied
        command_times.append(clock.perf_counter() - local_start)
        actual = applied.copy()
        if "wind" in faults and 9 <= t <= 17:
            actual[:, 1] += .7 * np.sin(t)
        actual[~active] = 0.
        previous = applied.copy()
        ii, jj, distances, step_min = swept_pairs(p, v, actual, active, world["radius"], cfg.separation, cfg.dt)
        min_distance = min(min_distance, step_min)
        collision = distances < world["radius"][ii] + world["radius"][jj]
        breach = distances < cfg.separation
        participating = coop[ii] | coop[jj]
        counters["separation_pair_step_seconds"] += int(np.sum(breach)) * cfg.dt
        counters["participating_separation_pair_step_seconds"] += int(np.sum(breach & participating)) * cfg.dt
        counters["participating_pair_seconds"] += int(np.sum(participating)) * cfg.dt
        for i, j in zip(ii[breach], jj[breach]):
            separation_pairs.add((int(i), int(j)))
        for i, j, d in zip(ii[collision], jj[collision], distances[collision]):
            pair = (int(i), int(j))
            if pair not in collision_pairs:
                event("physical_collision", t, aircraft=list(pair), minimum_m=round(float(d), 4))
            collision_pairs.add(pair)
            if coop[i] and coop[j]:
                collision_ee.add(pair)
            elif coop[i] or coop[j]:
                collision_el.add(pair)
            else:
                collision_ll.add(pair)
            if (coop[i] or coop[j]) and first_participant_collision is None:
                first_participant_collision = t
        for i, obstacle in swept_obstacles(p, v, actual, active, world["radius"], world["obstacles"], cfg.dt):
            if (i, obstacle) not in obstacle_hits:
                event("obstacle_collision", t, aircraft=i, obstacle=obstacle)
            obstacle_hits.add((i, obstacle))
        outside = outside_volume(p, v, actual, cfg, cfg.dt) & active
        for i in np.flatnonzero(outside):
            if int(i) not in boundary_hits:
                event("volume_exit", t, aircraft=int(i))
            boundary_hits.add(int(i))
        new_p = p + v * cfg.dt + .5 * actual * cfg.dt ** 2
        new_v = v + actual * cfg.dt
        fids = np.flatnonzero(fixed & active)
        violations = np.linalg.norm(actual, axis=1) > cfg.acceleration_limit + (.8 if "wind" in faults else 1e-6)
        violations |= np.linalg.norm(new_v, axis=1) > cfg.max_speed + 1e-6
        if len(fids):
            angle = np.arctan2(new_v[fids, 1], new_v[fids, 0]) - np.arctan2(v[fids, 1], v[fids, 0])
            angle = np.abs((angle + np.pi) % (2*np.pi) - np.pi)
            violations[fids] |= ((np.linalg.norm(new_v[fids, :2], axis=1) < cfg.fixed_wing_min_speed - 1e-6) |
                                 (angle > np.deg2rad(cfg.fixed_wing_turn_rate_deg) * cfg.dt + 1e-6) |
                                 (np.abs(new_v[fids, 2]) > cfg.fixed_wing_climb_limit + 1e-6))
        counters["kinematic_violation_drone_steps"] += int(np.sum(violations & active))
        paths += np.linalg.norm(new_p - p, axis=1) * active
        energy += np.sum(actual ** 2, axis=1) * cfg.dt * active
        debt += np.linalg.norm(applied - uncooperative, axis=1) * cfg.dt * coop * active
        reached = (np.linalg.norm(new_p - routes.mission_goals, axis=1) < cfg.goal_radius) & active
        if policy is not None:
            reward = ((np.linalg.norm(p - routes.mission_goals, axis=1) -
                       np.linalg.norm(new_p - routes.mission_goals, axis=1)) / cfg.cruise_speed)
            reward -= .02 * cfg.dt + .001 * np.sum(applied**2, axis=1) * cfg.dt
            reward += 5. * reached
            penalties = np.zeros(n)
            np.add.at(penalties, ii[collision], 20.)
            np.add.at(penalties, jj[collision], 20.)
            np.add.at(penalties, ii[breach], .2 * cfg.dt)
            np.add.at(penalties, jj[breach], .2 * cfg.dt)
            for i, _ in swept_obstacles(p, v, actual, active, world["radius"], world["obstacles"], cfg.dt):
                penalties[i] += 20.
            penalties += 5. * outside
            policy.transition(reward - penalties, reached | (step == round(cfg.duration / cfg.dt) - 1))
        completed |= reached
        arrivals[reached] = t + cfg.dt
        p, v = new_p, new_v
        active[reached] = False
        v[~active] = 0.
        if record and (t + 1e-8 >= next_replay or not np.any(active)):
            frames.append({"time": round(t + cfg.dt, 4), "positions": np.round(p, 2).tolist(),
                           "active": active.astype(int).tolist()})
            next_replay += cfg.replay_period
    participated = len(collision_ee) + len(collision_el)
    participating_obstacle = sum(bool(coop[i]) for i, _ in obstacle_hits)
    participating_exit = sum(bool(coop[i]) for i in boundary_hits)
    straight = np.linalg.norm(routes.mission_goals - initial_p, axis=1)
    progress = np.clip((straight - np.linalg.norm(routes.mission_goals - p, axis=1)) / np.maximum(straight, 1e-9), -1, 1)
    waiting = admission.release_time[coop & admission.admitted]
    metrics = {**counters,
               "participant_admitted_aircraft": int(np.sum(coop & admission.admitted)),
               "participant_admission_fraction": float(np.mean(admission.admitted[coop])) if np.any(coop) else None,
               "queued_aircraft": int(np.sum(admission.queued)), "route_rejected_aircraft": int(np.sum(admission.rejected)),
               "admission_checks": admission.checks, "admission_denial_attempts": admission.denials,
               "mean_admission_wait_s": float(np.mean(waiting)) if len(waiting) else None,
               "p95_admission_wait_s": float(np.percentile(waiting,95)) if len(waiting) else None,
               "unserved_queue_wait_s": cfg.duration if np.any(admission.queued) else 0.,
               "participant_completed_aircraft": int(np.sum(completed & coop)),
               "participant_throughput_per_minute": float(np.sum(completed & coop) * 60 / cfg.duration),
               "entry_static_hover_certificates": sum(bool(c.get("static_invariant_terminal")) for c in admission.certificates.values()), "collision_pairs": len(collision_pairs), "collision_pairs_ee": len(collision_ee),
               "collision_pairs_el": len(collision_el), "collision_pairs_ll": len(collision_ll),
               "participant_collision_pairs": participated,
               "obstacle_collision_pairs": len(obstacle_hits), "participant_obstacle_collisions": participating_obstacle,
               "volume_exit_aircraft": len(boundary_hits), "participant_volume_exits": participating_exit,
               "separation_pairs": len(separation_pairs),
               "minimum_distance_lower_bound_m": None if not np.isfinite(min_distance) else float(min_distance),
               "completion_fraction": float(np.mean(completed)),
               "participant_completion_fraction": float(np.mean(completed[coop])) if np.any(coop) else None,
               "mean_progress_fraction": float(np.mean(progress)),
               "participant_progress_fraction": float(np.mean(progress[coop])) if np.any(coop) else None,
               "path_length_m": float(np.sum(paths)), "control_effort_proxy": float(np.sum(energy)),
               "mean_arrival_time_s": float(np.nanmean(arrivals)) if np.any(completed) else None,
               "first_participant_collision_s": first_participant_collision,
               "command_p99_ms": float(np.percentile(command_times, 99) * 1000) if command_times else 0.,
               "command_max_ms": float(max(command_times, default=0) * 1000),
               "wall_seconds": clock.perf_counter() - started,
               "cooperative_aircraft": int(np.sum(coop)), "fixed_wing_aircraft": int(np.sum(fixed)),
               "telemetry_delivered": telemetry.delivered, "telemetry_dropped": telemetry.dropped}
    result = {"run_id": config_id(cfg), "config": asdict(cfg), "metrics": metrics,
              "domain": world["scenario"].domain, "events": events,
              "limitations": ["Exploratory point-mass dynamics; no flight certification",
                              "Finite projection barrier solver reports unresolved residuals",
                              "Synthetic shared regional RID feed, not an ASTM/RF conformance test",
                              "Goals are absorbing exits; landing and wreckage physics are absent",
                              "After a collision, diagnostic trajectories continue without impact physics",
                              "Admission is abstract pre-entry demand with idealized entry-state announcements",
                              "Checked backups exclude traffic only for their finite horizon; static hover bound is model-specific"]}
    if record:
        result["replay"] = {"initial_positions": np.round(initial_p, 2).tolist(),
                            "initial_active": initial_active.astype(int).tolist(),
                            "goals": np.round(routes.mission_goals, 2).tolist(),
                            "fixed_wing": fixed.astype(int).tolist(), "cooperative": coop.astype(int).tolist(),
                            "radii": world["radius"].tolist(), "obstacles": world["obstacles"].tolist(),
                            "frames": frames}
    return result
