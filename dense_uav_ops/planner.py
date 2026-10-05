"""Finite maneuver-library planner with an explicit model of other aircraft.

Each controlled aircraft rolls out 22 candidate velocity targets over a short
horizon using its own envelope, and keeps the candidates whose swept path stays
clear of every held track's *assumed* reachable set, the obstacles and the
volume. A candidate that is clear for the whole horizon is called admissible.

The assumed reachable set of a track reported with age `tau` is a ball around
its constant-velocity prediction with radius

    e_p + e_v (tau + t) + A (tau + t)^2 / 2

where `e_p`, `e_v` are the declared report error bounds and `A` is
`assumptions.traffic_acceleration_mps2`. Admissibility guarantees separation
over the horizon only if the true traffic acceleration (including wind) stays
within `A`, reports stay within their declared bounds, and the ownship
disturbance stays within `assumptions.own_disturbance_mps2`. There is no
terminal set: receding-horizon admissibility is not recursive feasibility.
When no candidate is admissible, a best-effort fallback minimises predicted
violation; it is counted, never called safe.
"""
import numpy as np

from .vehicles import preferred_velocity, project

PRIMITIVES = [(angle, climb) for angle in (0., -np.pi / 3, np.pi / 3, -2 * np.pi / 3, 2 * np.pi / 3, np.pi)
              for climb in (0., -3., 3.)]
ACTIONS = len(PRIMITIVES) + 4  # plus slower, faster, brake and hold-velocity


def dot(a, b):
    return np.einsum('...i,...i->...', a, b)


def segment_distance(start, end):
    """Distance from the origin to the segment start→end (per row, any leading shape)."""
    delta = end - start
    t = np.clip(-dot(start, delta) / np.maximum(dot(delta, delta), 1e-12), 0., 1.)
    closest = start + t[..., None] * delta
    return np.sqrt(dot(closest, closest))


def enclosure(snapshot, elapsed, acceleration):
    """Radius of the assumed reachable ball of each track `elapsed` seconds after now."""
    total = snapshot.age + elapsed
    return snapshot.position_error + snapshot.velocity_error * total + .5 * acceleration * total ** 2


def volume_clearance(p, v, a, radius, low, high, dt):
    end = p + v * dt + .5 * a * dt ** 2
    turning = np.clip(-v / np.where(np.abs(a) > 1e-12, a, 1.), 0., dt)
    mid = p + v * turning + .5 * a * turning ** 2
    lo = np.minimum(np.minimum(p, end), mid)
    hi = np.maximum(np.maximum(p, end), mid)
    return np.minimum(np.min(lo - low, axis=-1), np.min(high - hi, axis=-1)) - radius


def choose(feasible, physical_deficit, separation_deficit, cost):
    """Lowest cost admissible candidate; otherwise least predicted violation.

    The fallback ignores preference weights and learned scores entirely.
    """
    selected = np.empty(len(cost), int)
    for row in range(len(cost)):
        if np.any(feasible[row]):
            selected[row] = np.argmin(np.where(feasible[row], cost[row], np.inf))
        else:
            selected[row] = np.lexsort((np.arange(cost.shape[1]), separation_deficit[row], physical_deficit[row]))[0]
    return selected


class Plan:
    """Per-step planning result for the aircraft in `ids`."""
    def __init__(self, ids, command, feasible, clearance, remaining, effort, chosen, fallback):
        self.ids, self.command, self.feasible, self.clearance = ids, command, feasible, clearance
        self.remaining, self.effort, self.chosen, self.fallback = remaining, effort, chosen, fallback


def plan(experiment, world, ids, p, v, snapshot, desired, policy=None, observation=None, cull=True):
    """Plan for controlled aircraft `ids` from their own (idealized) state and the shared snapshot."""
    e = experiment
    dt = e.window.dt_s
    traffic_a = e.assumptions.traffic_acceleration_mps2
    own_w = e.assumptions.own_disturbance_mps2
    m = len(ids)
    lim = world.limits.take(ids)
    goals = world.waypoint[ids]
    cruise = world.cruise[ids]
    base = preferred_velocity(p[ids], goals, cruise, lim)
    targets = []
    for angle, climb in PRIMITIVES:
        vv = base.copy()
        vv[:, 0] = base[:, 0] * np.cos(angle) - base[:, 1] * np.sin(angle)
        vv[:, 1] = base[:, 0] * np.sin(angle) + base[:, 1] * np.cos(angle)
        vv[:, 2] = base[:, 2] + climb
        targets.append(vv)
    targets += [base * .65, base * 1.25, np.zeros_like(base), v[ids].copy()]
    target = np.stack(targets, axis=1)
    k = target.shape[1]
    q = np.repeat(p[ids, None, :], k, axis=1)
    vel = np.repeat(v[ids, None, :], k, axis=1)
    lim_k = lim.repeat(k)
    radius = world.radius[ids, None]
    low = np.array([-e.airspace.side_m / 2, -e.airspace.side_m / 2, e.airspace.floor_m])
    high = np.array([e.airspace.side_m / 2, e.airspace.side_m / 2, e.airspace.ceiling_m])
    steps = int(np.ceil(e.assumptions.horizon_s / dt - 1e-9))
    horizon = steps * dt
    sep_req = np.where(world.manned, e.requirements.manned_separation_m, e.requirements.separation_m)
    # Tracks each aircraft must respect: every held track except itself.
    relevant = np.repeat(snapshot.known[None, :], m, axis=0)
    relevant[np.arange(m), ids] = False
    if cull:
        # Conservative broad phase. A track is skipped only if, by the triangle inequality, it stays
        # beyond its required distance from every candidate for the whole horizon. Skipped tracks can
        # never make a candidate inadmissible or add to a deficit, so admissibility is unchanged.
        start_gap = np.linalg.norm(p[ids][:, None, :] - snapshot.position[None, :, :], axis=-1)
        reach_end = enclosure(snapshot, horizon, traffic_a)
        need = np.maximum(sep_req[None, :], world.radius[ids, None] + world.radius[None, :])
        bound = ((lim.max_speed[:, None] + np.linalg.norm(snapshot.velocity, axis=1)[None, :]) * horizon
                 + lim.acceleration[:, None] * dt ** 2 / 8 + reach_end[None, :] + .5 * own_w * horizon ** 2 + need + 1.)
        relevant &= start_gap <= bound
    width = max(1, int(relevant.sum(axis=1).max(initial=0)))
    neighbors = np.zeros((m, width), int)
    present = np.zeros((m, width), bool)
    for row in range(m):
        found = np.flatnonzero(relevant[row])
        neighbors[row, :len(found)] = found
        present[row, :len(found)] = True
    nbr_radius = world.radius[neighbors][:, None, :]
    nbr_need = np.maximum(sep_req[neighbors][:, None, :], radius[:, :, None] + nbr_radius)
    physical = np.zeros((m, k))
    separation = np.zeros((m, k))
    clearance = np.full((m, k), np.inf)
    effort = np.zeros((m, k))
    done = np.zeros((m, k), bool)
    first = None
    final = world.final_leg[ids]
    for step in range(steps):
        t0, t1 = step * dt, (step + 1) * dt
        target[:, 0, :] = preferred_velocity(q[:, 0], goals, cruise, lim)
        a = project(((target - vel) / .6).reshape(-1, 3), vel.reshape(-1, 3), lim_k, dt).reshape(m, k, 3)
        a[done] = 0.
        if first is None:
            first = a.copy()
        end = q + vel * dt + .5 * a * dt ** 2
        curve = np.sqrt(dot(a, a)) * dt ** 2 / 8
        own = .5 * own_w * t1 ** 2
        traffic_start = snapshot.position[neighbors] + snapshot.velocity[neighbors] * t0
        traffic_end = snapshot.position[neighbors] + snapshot.velocity[neighbors] * t1
        reach = enclosure(snapshot, t1, traffic_a)[neighbors]
        mask = present[:, None, :] & ~done[:, :, None]
        if mask.any():
            r0 = q[:, :, None, :] - traffic_start[:, None, :, :]
            r1 = end[:, :, None, :] - traffic_end[:, None, :, :]
            clear = segment_distance(r0, r1) - curve[:, :, None] - reach[:, None, :] - own
            sep_margin = np.where(mask, clear - nbr_need, np.inf)
            body_margin = np.where(mask, clear - radius[:, :, None] - nbr_radius, np.inf)
            clearance = np.minimum(clearance, np.min(sep_margin, axis=-1))
            physical += np.sum(np.minimum(body_margin, 0.) ** 2, axis=-1) * dt
            separation += np.sum(np.minimum(sep_margin, 0.) ** 2, axis=-1) * dt
        bound = np.where(done, np.inf, volume_clearance(q, vel, a, radius, low, high, dt) - own)
        clearance = np.minimum(clearance, bound)
        physical += np.minimum(bound, 0.) ** 2 * dt
        for x, y, z, r in e.airspace.obstacles:
            c = segment_distance(q - [x, y, z], end - [x, y, z]) - r - radius - curve - own
            c = np.where(done, np.inf, c)
            clearance = np.minimum(clearance, c)
            physical += np.minimum(c, 0.) ** 2 * dt
        effort += dot(a, a) * dt
        vel = vel + a * dt
        q = end
        done |= (np.linalg.norm(q - goals[:, None], axis=-1) < e.requirements.goal_radius_m) & final[:, None]
        vel[done] = 0.
    remaining = np.linalg.norm(q - goals[:, None], axis=-1)
    # Deviation from the nominal plan (candidate 0) in either direction: being early is
    # not rewarded, so aircraft fly their nominal speed unless traffic requires otherwise.
    lag = np.abs(remaining - remaining[:, :1])
    turn = np.sum((first - desired[ids, None, :]) ** 2, axis=-1)
    climb = np.abs(q[:, :, 2] - p[ids, None, 2])
    c = e.controller
    cost = c.progress_weight * lag + c.effort_weight * effort + c.turn_weight * turn + c.vertical_weight * climb
    feasible = clearance >= 0.
    chosen = choose(feasible, physical, separation, cost)
    if policy is not None:
        proposed = np.asarray(policy.choose(ids, feasible, chosen.copy(), clearance, remaining, effort, observation), dtype=int)
        if proposed.shape != chosen.shape:
            raise ValueError('policy returned an invalid action shape')
        valid = (proposed >= 0) & (proposed < k)
        valid &= feasible[np.arange(m), np.clip(proposed, 0, k - 1)]
        # A learned proposal can only pick among admissible candidates.
        chosen = np.where(valid, proposed, chosen)
    fallback = ~np.any(feasible, axis=1)
    return Plan(ids, first[np.arange(m), chosen], feasible, clearance, remaining, effort, chosen, fallback)
