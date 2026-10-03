"""Finite maneuver-library MPC prototype; no invariant terminal set or proof.

Every rollout uses ownship state plus reported traffic. Full acceleration tubes
are retained for cooperative and legacy traffic alike. Learned preferences can
rank admissible candidates but cannot edit the constraint checker or fallback.
"""
import numpy as np

from .controllers import preferred_velocity, unit, vehicle_project


def segment_distance(start, end):
    delta = end - start
    t = np.clip(-np.sum(start * delta, axis=-1) /
                np.maximum(np.sum(delta * delta, axis=-1), 1e-12), 0., 1.)
    return np.linalg.norm(start + t[..., None] * delta, axis=-1)


def volume_clearance(p, v, a, radius, cfg):
    """Minimum clearance from every face during a constant-acceleration step."""
    end = p + v * cfg.dt + .5 * a * cfg.dt ** 2
    turning = np.clip(-v / np.where(np.abs(a) > 1e-12, a, 1.), 0., cfg.dt)
    mid = p + v * turning + .5 * a * turning ** 2
    low = np.minimum(np.minimum(p, end), mid)
    high = np.maximum(np.maximum(p, end), mid)
    floors = np.array([-cfg.area / 2, -cfg.area / 2, cfg.altitude_floor])
    ceilings = np.array([cfg.area / 2, cfg.area / 2, cfg.altitude_ceiling])
    return np.minimum(np.min(low - floors, axis=-1),
                      np.min(ceilings - high, axis=-1)) - radius


def choose_candidate(feasible, collision_deficit, environment_deficit,
                     separation_deficit, cost):
    """Safety class precedes preferences. Fallback ignores learned weights.

    Deficits are accumulated squared meters over the horizon. In a failed
    library, minimize physical/environmental violations, then separation loss.
    This is diagnostic best effort, never a certified emergency maneuver.
    """
    selected = np.empty(len(cost), int)
    for row in range(len(cost)):
        if np.any(feasible[row]):
            selected[row] = np.argmin(np.where(feasible[row], cost[row], np.inf))
        else:
            selected[row] = np.lexsort((np.arange(cost.shape[1]),
                                       separation_deficit[row],
                                       collision_deficit[row] + environment_deficit[row]))[0]
    return selected


def traffic_enclosure(error, error_v, age, horizon, cfg):
    """Extend the feed's acceleration bound to include bounded wind throughout.

    The feed already encloses A*age²/2 and A*age. Its wind additions must
    cover the stale interval as well as the prediction interval, including
    the cross-term in (age + horizon)².
    """
    disturbance = .8
    return (error + error_v * horizon + .5 * cfg.advertised_acceleration_bound * horizon ** 2 +
            .5 * disturbance * (age + horizon) ** 2)


def predictive_control(cfg, world, p, v, active, snapshot, desired, policy=None, debt=None):
    pred, obs_v, error, error_v, age = snapshot
    ids = np.flatnonzero(active & world["cooperative"])
    output = desired.copy()
    n = len(p)
    stats = {"unresolved": np.zeros(n, bool), "interventions": np.zeros(n, bool),
             "feasible_candidates": np.zeros(n, int)}
    if not len(ids):
        return output, stats
    own_fixed = world["fixed"][ids]
    goals = world["goals"][ids]
    cruise = world["cruise"][ids]
    base = preferred_velocity(p[ids], goals, cruise, own_fixed, cfg)
    # Fixed library includes straight flight, vertical alternatives, turns,
    # slower/faster flight, braking, and current-velocity continuation.
    primitives = [(angle, climb) for angle in (0., -np.pi/3, np.pi/3,
                                               -2*np.pi/3, 2*np.pi/3, np.pi)
                  for climb in (0., -3., 3.)]
    targets = []
    for angle, climb in primitives:
        vv = base.copy()
        vv[:, 0] = base[:, 0] * np.cos(angle) - base[:, 1] * np.sin(angle)
        vv[:, 1] = base[:, 0] * np.sin(angle) + base[:, 1] * np.cos(angle)
        vv[:, 2] = np.clip(base[:, 2] + climb, -cfg.fixed_wing_climb_limit,
                          cfg.fixed_wing_climb_limit)
        targets.append(vv)
    targets += [base * .65, base * 1.25, np.zeros_like(base), v[ids].copy()]
    target = np.stack(targets, axis=1)
    m, k = target.shape[:2]
    q = np.repeat(p[ids, None, :], k, axis=1)
    vel = np.repeat(v[ids, None, :], k, axis=1)
    first = np.zeros_like(q)
    fixed = np.repeat(own_fixed, k)
    radius = world["radius"][ids, None]
    # Wind is bounded by 0.8 m/s²; keep it in both ownship and obstacle tubes.
    disturbance = .8
    collision_loss = np.zeros((m, k))
    environment_loss = np.zeros((m, k))
    separation_loss = np.zeros((m, k))
    effort = np.zeros((m, k))
    min_clearance = np.full((m, k), np.inf)
    done = np.zeros((m, k), bool)
    neighbor = active[None, :].repeat(m, axis=0)
    neighbor[np.arange(m), ids] = False
    steps = int(np.ceil(cfg.predictive_horizon / cfg.dt))
    for step in range(steps):
        start_t, end_t = step * cfg.dt, (step + 1) * cfg.dt
        target[:, 0, :] = preferred_velocity(q[:, 0], goals, cruise, own_fixed, cfg)
        a = vehicle_project(((target - vel) / .6).reshape(-1, 3),
                            vel.reshape(-1, 3), fixed, cfg).reshape(m, k, 3)
        a[done] = 0.
        if step == 0:
            first = a.copy()
        end = q + vel * cfg.dt + .5 * a * cfg.dt ** 2
        own_curve = np.linalg.norm(a, axis=-1) * cfg.dt ** 2 / 8
        own_error = .5 * disturbance * end_t ** 2
        # Relative segment closest approach plus curvature and time-growing
        # uncertainty conservatively bounds every point within this step.
        traffic_start = pred + obs_v * start_t
        traffic_end = pred + obs_v * end_t
        enclosure = traffic_enclosure(error, error_v, age, end_t, cfg)
        # Process in chunks to bound temporary memory at 200–500 aircraft.
        for left in range(0, n, 32):
            right = min(left + 32, n)
            r0 = q[:, :, None, :] - traffic_start[None, None, left:right, :]
            r1 = end[:, :, None, :] - traffic_end[None, None, left:right, :]
            clear = segment_distance(r0, r1) - own_curve[:, :, None]
            clear -= enclosure[None, None, left:right] + own_error
            mask = neighbor[:, None, left:right] & ~done[:, :, None]
            sep = np.where(mask, clear - cfg.separation, np.inf)
            physical = np.where(mask, clear - radius[:, :, None] -
                                world["radius"][None, None, left:right], np.inf)
            min_clearance = np.minimum(min_clearance, np.minimum(np.min(sep, axis=-1),
                                                               np.min(physical, axis=-1)))
            collision_loss += np.sum(np.minimum(physical, 0.) ** 2, axis=-1) * cfg.dt
            separation_loss += np.sum(np.minimum(sep, 0.) ** 2, axis=-1) * cfg.dt
        bound = volume_clearance(q, vel, a, radius, cfg) - own_error
        bound = np.where(done, np.inf, bound)
        min_clearance = np.minimum(min_clearance, bound)
        environment_loss += np.minimum(bound, 0.) ** 2 * cfg.dt
        for x, y, z, rad in world["obstacles"]:
            obs_clear = segment_distance(q - [x, y, z], end - [x, y, z])
            obs_clear -= rad + radius + own_curve + own_error
            obs_clear = np.where(done, np.inf, obs_clear)
            min_clearance = np.minimum(min_clearance, obs_clear)
            environment_loss += np.minimum(obs_clear, 0.) ** 2 * cfg.dt
        effort += np.sum(a * a, axis=-1) * cfg.dt
        vel += a * cfg.dt
        q = end
        final_leg = np.linalg.norm(goals - world.get("mission_goals", world["goals"])[ids], axis=-1) < 1e-9
        done |= (np.linalg.norm(q - goals[:, None], axis=-1) < cfg.goal_radius) & final_leg[:, None]
        vel[done] = 0.
    remaining = np.linalg.norm(q - goals[:, None], axis=-1)
    turn = np.sum((first - desired[ids, None, :]) ** 2, axis=-1)
    climb = np.abs(q[:, :, 2] - p[ids, None, 2])
    cost = (cfg.policy_progress_weight * remaining + cfg.policy_effort_weight * effort +
            cfg.policy_turn_weight * turn + cfg.policy_vertical_weight * climb)
    feasible = min_clearance >= 0.
    chosen = choose_candidate(feasible, collision_loss, environment_loss,
                              separation_loss, cost)
    if policy is not None:
        from .observations import observe, central_context
        observation = observe(cfg, world, ids, p, v, active, snapshot, debt)
        proposed = np.asarray(policy.choose(ids, observation, feasible, chosen.copy(),
                                           central_context(cfg, world, p, v, active)
                                           if getattr(policy, 'mode', 'inference') != 'inference' else None), dtype=int)
        if proposed.shape != chosen.shape:
            raise ValueError("Policy returned an invalid action shape")
        valid_range = (proposed >= 0) & (proposed < k)
        valid = valid_range & feasible[np.arange(m), np.clip(proposed, 0, k-1)]
        stats["proposal_rejections"] = int(np.sum(~valid & np.any(feasible, axis=1)))
        chosen = np.where(valid, proposed, chosen)
    output[ids] = first[np.arange(m), chosen]
    stats["unresolved"][ids] = ~np.any(feasible, axis=1)
    stats["feasible_candidates"][ids] = np.sum(feasible, axis=1)
    stats["interventions"][ids] = np.linalg.norm(output[ids] - desired[ids], axis=-1) > .05
    return output, stats
