import numpy as np


def unit(x):
    return x / np.maximum(np.linalg.norm(x, axis=-1, keepdims=True), 1e-9)


def vehicle_project(a, v, fixed, cfg):
    """Project into the simplified mixed-vehicle input set, including stall floor."""
    a = a.copy()
    norm = np.linalg.norm(a, axis=1)
    a *= np.minimum(1., cfg.acceleration_limit / np.maximum(norm, 1e-9))[:, None]
    # Multirotor: speed ball. Its projection preserves the acceleration ball.
    nextv = v + a * cfg.dt
    nextv *= np.minimum(1., cfg.max_speed / np.maximum(np.linalg.norm(nextv, axis=1), 1e-9))[:, None]
    a = (nextv - v) / cfg.dt
    ids = np.flatnonzero(fixed)
    if len(ids):
        hv = v[ids, :2]
        speed = np.linalg.norm(hv, axis=1)
        forward = unit(hv)
        lateral = np.column_stack((-forward[:, 1], forward[:, 0]))
        longitudinal_a = np.clip(np.sum(a[ids, :2] * forward, axis=1), -2., 2.)
        longitudinal_a = np.maximum(longitudinal_a, (cfg.fixed_wing_min_speed - speed) / cfg.dt)
        lat_a = np.clip(np.sum(a[ids, :2] * lateral, axis=1), -3., 3.)
        turn_bound = np.maximum(speed + longitudinal_a * cfg.dt, cfg.fixed_wing_min_speed)
        turn_bound *= np.tan(np.deg2rad(cfg.fixed_wing_turn_rate_deg) * cfg.dt) / cfg.dt
        lat_a = np.clip(lat_a, -turn_bound, turn_bound)
        vertical_a = np.clip(a[ids, 2], -2., 2.)
        vertical_a = np.clip(vertical_a,
                             (-cfg.fixed_wing_climb_limit - v[ids, 2]) / cfg.dt,
                             (cfg.fixed_wing_climb_limit - v[ids, 2]) / cfg.dt)
        aa = np.column_stack((forward * longitudinal_a[:, None] + lateral * lat_a[:, None], vertical_a))
        aa *= np.minimum(1., cfg.acceleration_limit / np.maximum(np.linalg.norm(aa, axis=1), 1e-9))[:, None]
        nv = v[ids] + aa * cfg.dt
        # Bound total speed without violating forward minimum speed.
        horizontal_max = np.sqrt(np.maximum(cfg.max_speed ** 2 - nv[:, 2] ** 2, cfg.fixed_wing_min_speed ** 2))
        hs = np.linalg.norm(nv[:, :2], axis=1)
        nv[:, :2] *= np.minimum(1., horizontal_max / np.maximum(hs, 1e-9))[:, None]
        a[ids] = (nv - v[ids]) / cfg.dt
    return a


def preferred_velocity(p, goals, cruise, fixed, cfg):
    diff = goals - p
    distance = np.linalg.norm(diff, axis=1)
    speed = np.minimum(cruise, np.sqrt(2 * cfg.acceleration_limit * distance))
    speed[fixed] = np.maximum(speed[fixed], cfg.fixed_wing_min_speed)
    return unit(diff) * speed[:, None]


def nominal(cfg, world, p, v, active, snapshot, debt, time):
    pred, obs_v, error, error_v, age = snapshot
    wanted = preferred_velocity(p, world["goals"], world["cruise"], world["fixed"], cfg)
    base = (wanted - v) / .8
    stats = {"negotiations": 0, "partial_certificates": 0}
    if cfg.controller == "goal":
        return vehicle_project(base, v, world["fixed"], cfg), stats
    r = p[:, None, :] - pred[None, :, :]
    distances = np.linalg.norm(r, axis=2)
    neighbor = active[:, None] & active[None, :]
    np.fill_diagonal(neighbor, False)
    relv = v[:, None, :] - obs_v[None, :, :]
    t = np.clip(-np.sum(r * relv, axis=2) / np.maximum(np.sum(relv ** 2, axis=2), 1e-9), 0., 3.)
    cpa = np.linalg.norm(r + relv * t[..., None], axis=2)
    danger = neighbor & (cpa < cfg.separation + 5) & (distances < 65)
    # All controllers use the same available reported traffic, never truth of others.
    weight = np.maximum(0., (28. - distances) / 28.) * neighbor
    weight += .7 * danger * np.maximum(0., (3. - t) / 3.)
    push = np.sum(unit(r) * weight[..., None], axis=1)
    base += 3. * push
    for x, y, z, rad in world["obstacles"]:
        diff = p - [x, y, z]
        dist = np.linalg.norm(diff, axis=1)
        base += unit(diff) * (5 * np.clip((rad + 18 - dist) / 18, 0., 2.))[:, None]
    if cfg.controller == "negotiated":
        coop = world["cooperative"]
        joint = danger & coop[:, None] & coop[None, :]
        # Greater accumulated yielding burden wins priority. Ties are stable.
        score = debt + np.arange(len(p)) * 1e-6
        yield_to = joint & (score[:, None] < score[None, :])
        will_yield = np.any(yield_to, axis=1)
        stats["negotiations"] = int(np.sum(np.triu(joint, 1)))
        if world["scenario"].fault == "partial":
            received = (np.arange(len(p)) + int(time / .6)) % 3 != 0
            stats["partial_certificates"] = int(np.sum(will_yield & ~received))
            will_yield &= received
        # Broker-emulated proposals: a climb/descent alternative and speed adjustment.
        # The safety filter remains unilateral and never halves the intruder bound.
        up = np.where(p[:, 2] < (cfg.altitude_floor + cfg.altitude_ceiling) / 2, 1., -1.)
        base[:, 2] += will_yield * up * 2.
        base[:, :2] -= unit(v[:, :2]) * will_yield[:, None] * 1.5
    return vehicle_project(base, v, world["fixed"], cfg), stats


def barrier_filter(cfg, world, p, v, active, snapshot, desired):
    """Finite projection approximation of robust affine HOCBF inequalities.

    Not an exact QP or a verified sampled-data controller. Residuals are always
    returned, including after vehicle projection; infeasibility is not hidden.
    """
    pred, obs_v, error, error_v, age = snapshot
    n = len(p)
    r = p[:, None, :] - pred[None, :, :]
    w = v[:, None, :] - obs_v[None, :, :]
    nr, nw = np.linalg.norm(r, axis=2), np.linalg.norm(w, axis=2)
    e, ev = error[None, :], error_v[None, :]
    k = cfg.barrier_gain
    # Conservative intersample spatial margin; not a complete invariance proof.
    radius = cfg.separation + cfg.max_speed * cfg.dt + cfg.acceleration_limit * cfg.dt ** 2
    aa = 2 * r
    rr = np.maximum(nr - e, 0.)
    rw_lower = np.sum(r * w, axis=2) - nr * ev - e * (nw + ev)
    b = (2 * e * cfg.acceleration_limit +
         2 * (nr + e) * (cfg.advertised_acceleration_bound + .8) -
         2 * np.maximum(nw - ev, 0.) ** 2 - 4 * k * rw_lower - k * k * (rr ** 2 - radius ** 2))
    mask = active[:, None] & active[None, :]
    np.fill_diagonal(mask, False)
    b = np.where(mask, b, -1e15)
    invalid_initial = np.any(mask & ((rr < radius) | (2 * rw_lower + k * (rr ** 2 - radius ** 2) < 0)), axis=1)
    # Static obstacle barrier uses zero obstacle velocity/acceleration.
    for x, y, z, rad in world["obstacles"]:
        diff = p - [x, y, z]
        h = np.sum(diff ** 2, axis=1) - (rad + world["radius"] + cfg.max_speed * cfg.dt) ** 2
        bb = -2 * np.sum(v * v, axis=1) - 4 * k * np.sum(diff * v, axis=1) - k * k * h
        aa = np.concatenate((aa, (2 * diff)[:, None, :]), axis=1)
        b = np.concatenate((b, np.where(active, bb, -1e15)[:, None]), axis=1)
    # Six operating-volume halfspaces, with actual second-order dynamics.
    directions = np.array([[1., 0., 0.], [-1., 0., 0.], [0., 1., 0.], [0., -1., 0.], [0., 0., 1.], [0., 0., -1.]])
    offsets = np.array([cfg.area/2, cfg.area/2, cfg.area/2, cfg.area/2, -cfg.altitude_floor, cfg.altitude_ceiling])
    h = p @ directions.T + offsets[None, :] - world["radius"][:, None]
    bb = -2*k*(v @ directions.T) - k*k*h + .8
    aa = np.concatenate((aa, np.broadcast_to(directions, (n, 6, 3))), axis=1)
    b = np.concatenate((b, np.where(active[:, None], bb, -1e15)), axis=1)
    u = desired.copy()
    ids = np.arange(n)
    for _ in range(cfg.projection_iterations):
        violation = b - np.einsum("ijk,ik->ij", aa, u)
        worst = np.argmax(violation, axis=1)
        amount = np.maximum(violation[ids, worst], 0.)
        if np.max(amount[active], initial=0) < 1e-6:
            break
        normal = aa[ids, worst]
        u += normal * (amount / np.maximum(np.sum(normal * normal, axis=1), 1e-12))[:, None]
        u = vehicle_project(u, v, world["fixed"], cfg)
    residual = np.max(b - np.einsum("ijk,ik->ij", aa, u), axis=1)
    return u, {"residual": residual, "invalid_initial": invalid_initial,
               "interventions": np.linalg.norm(u - desired, axis=1) > .05}
