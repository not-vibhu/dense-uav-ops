"""Finite recovery maneuvers with an independent re-check, and a sampled hover lemma.

A recovery is a fixed maneuver from the current state: a multirotor brakes and
then holds position with linear feedback; a fixed-wing aircraft turns at
constant speed. `check` rolls it out over the planning horizon and tests it
against held tracks (with the planner's assumed reachable sets), obstacles and
the volume. `verify` independently recomputes the same path with exact
per-step distance extrema instead of chord bounds.

Hover lemma (static environment only). For the sampled double integrator with
zero-order-hold feedback u = -(p - c) - 1.5 v, each axis evolves as
x+ = F x + G d with x = (p - c, v). With P the continuous-time Lyapunov
solution for that feedback and q = ||P^1/2 F P^-1/2||_2 < 1, the ellipsoid
{sum_axes x^T P x <= rho} is invariant for every disturbance sequence with
3D norm <= d whenever sqrt(rho) >= d sqrt(G^T P G) / (1 - q), provided the
feedback stays unsaturated. This holds at sample instants for the stated plant
only. It says nothing about moving traffic, which a recovery excludes only for
its finite horizon. No fixed-wing invariant set is provided.
"""
import numpy as np

from .oracle import quadratic_minimum, step_extent
from .planner import enclosure, segment_distance, volume_clearance
from .vehicles import Limits, project, unit

P = np.array([[17 / 12, .5], [.5, 2 / 3]])
GAIN = np.array([1., 1.5])


def hover_certificate(dt, acceleration, max_speed, disturbance):
    F = np.array([[1 - .5 * dt ** 2, dt - .75 * dt ** 2], [-dt, 1 - 1.5 * dt]])
    G = np.array([.5 * dt ** 2, dt])
    L = np.linalg.cholesky(P).T
    contraction = float(np.linalg.norm(L @ F @ np.linalg.inv(L), 2)) + 1e-10
    if contraction >= 1:
        return {'valid': False, 'reason': 'not-contracting'}
    rho = float((disturbance * np.sqrt(G @ P @ G) / (1 - contraction)) ** 2 * 1.01)
    inv = np.linalg.inv(P)
    command = float(np.sqrt(rho * (GAIN @ inv @ GAIN)))
    speed = float(np.sqrt(rho * inv[1, 1]))
    position = float(np.sqrt(rho * inv[0, 0]))
    swept = position + speed * dt + .5 * (command + disturbance) * dt ** 2
    return {'valid': bool(command <= acceleration and speed <= max_speed), 'rho': rho, 'contraction': contraction,
            'command_bound': command, 'speed_bound': speed, 'position_bound': position,
            'swept_position_bound': swept, 'disturbance_bound': disturbance}


def _single(lim, i):
    return Limits(**{k: getattr(lim, k)[i:i + 1] for k in lim.__dataclass_fields__})


def check(experiment, world, i, p, v, snapshot, relevant, require_terminal=False):
    """Roll out and check the recovery for aircraft `i`; returns a certificate dict."""
    e = experiment
    dt = e.window.dt_s
    lim = _single(world.limits, i)
    fixed = bool(lim.fixed[0])
    radius = world.radius[i]
    own_w = e.assumptions.own_disturbance_mps2
    accel = float(lim.acceleration[0])
    low = np.array([-e.airspace.side_m / 2, -e.airspace.side_m / 2, e.airspace.floor_m])
    high = -low.copy()
    high[2] = e.airspace.ceiling_m
    sep_req = np.where(world.manned, e.requirements.manned_separation_m, e.requirements.separation_m)
    required = np.maximum(sep_req, radius + world.radius)
    q, vel = np.array(p, float), np.array(v, float)
    stop_time = np.linalg.norm(vel) / accel
    center = q + unit(vel) * np.linalg.norm(vel) ** 2 / (2 * accel)
    steps = int(np.ceil(e.assumptions.horizon_s / dt - 1e-9))
    path = []
    for step in range(steps):
        t = (step + 1) * dt
        if fixed:
            horizontal = np.linalg.norm(vel[:2])
            target = np.array([-vel[1], vel[0], 0.]) * 1.5 / max(horizontal, 1e-9)
            target[2] = -vel[2]
        elif step * dt < stop_time:
            target = -unit(vel) * accel
            if np.linalg.norm(vel) <= accel * dt:
                target = -vel / dt
        else:
            target = -(q - center) - 1.5 * vel
        a = project(target[None], vel[None], lim, dt)[0]
        end = q + vel * dt + .5 * a * dt ** 2
        own = .5 * own_w * t * t
        if volume_clearance(q, vel, a, radius, low, high, dt) - own < 0:
            return {'valid': False, 'reason': 'volume'}
        curve = np.linalg.norm(a) * dt ** 2 / 8
        for x, y, z, r in e.airspace.obstacles:
            if segment_distance(q - [x, y, z], end - [x, y, z]) - curve - own < r + radius:
                return {'valid': False, 'reason': 'obstacle'}
        others = relevant.copy()
        others[i] = False
        lower = (segment_distance(q - (snapshot.position + snapshot.velocity * (t - dt)),
                                  end - (snapshot.position + snapshot.velocity * t))
                 - curve - own - enclosure(snapshot, t, e.assumptions.traffic_acceleration_mps2))
        if np.any(lower[others] < required[others]):
            return {'valid': False, 'reason': 'traffic'}
        path.append({'position': q.tolist(), 'velocity': vel.tolist(), 'acceleration': a.tolist()})
        q, vel = end, vel + a * dt
    terminal = False
    hover = hover_certificate(dt, accel, float(lim.max_speed[0]), own_w)
    if not fixed and hover['valid']:
        phase = np.stack((q - center, vel))
        nominal = np.sqrt(float(np.einsum('ac,ab,bc->', phase, P, phase)))
        horizon = len(path) * dt
        error = np.array([.5 * own_w * horizon ** 2, own_w * horizon])
        robust = nominal + np.sqrt(float(error @ np.abs(P) @ error))
        guard = radius + hover['swept_position_bound']
        static = np.all(center - guard >= low) and np.all(center + guard <= high)
        static &= all(np.linalg.norm(center - np.array([x, y, z])) >= r + guard for x, y, z, r in e.airspace.obstacles)
        terminal = bool(robust <= np.sqrt(hover['rho']) and static)
    if require_terminal and not terminal:
        return {'valid': False, 'reason': 'no-static-terminal-set'}
    certificate = {'valid': True, 'kind': 'fixed-wing-turn' if fixed else 'multirotor-brake-hover',
                   'static_terminal': terminal, 'horizon_s': len(path) * dt, 'path': path, 'reason': 'checked'}
    if not verify(experiment, world, i, certificate, p, v, snapshot, relevant):
        return {'valid': False, 'reason': 'independent-check-failed'}
    return certificate


def verify(experiment, world, i, certificate, p, v, snapshot, relevant):
    """Second check: continuity, envelope and exact per-step distance extrema."""
    e = experiment
    dt = e.window.dt_s
    lim = _single(world.limits, i)
    path = certificate.get('path', [])
    if len(path) != int(np.ceil(e.assumptions.horizon_s / dt - 1e-9)):
        return False
    radius = world.radius[i]
    own_w = e.assumptions.own_disturbance_mps2
    low = np.array([-e.airspace.side_m / 2, -e.airspace.side_m / 2, e.airspace.floor_m])
    high = np.array([e.airspace.side_m / 2, e.airspace.side_m / 2, e.airspace.ceiling_m])
    sep_req = np.where(world.manned, e.requirements.manned_separation_m, e.requirements.separation_m)
    others = np.flatnonzero(relevant & (np.arange(len(relevant)) != i))
    q, vel = np.array(p, float), np.array(v, float)
    for step, item in enumerate(path):
        a = np.asarray(item['acceleration'], float)
        if a.shape != (3,) or not np.all(np.isfinite(a)):
            return False
        if not np.allclose(q, item['position'], atol=1e-8, rtol=0) or not np.allclose(vel, item['velocity'], atol=1e-8, rtol=0):
            return False
        nextv = vel + a * dt
        if np.linalg.norm(a) > lim.acceleration[0] + 1e-8 or np.linalg.norm(nextv) > lim.max_speed[0] + 1e-8:
            return False
        if lim.fixed[0]:
            angle = abs((np.arctan2(nextv[1], nextv[0]) - np.arctan2(vel[1], vel[0]) + np.pi) % (2 * np.pi) - np.pi)
            if (np.linalg.norm(nextv[:2]) < lim.min_speed[0] - 1e-8 or angle > lim.turn_rate[0] * dt + 1e-8
                    or abs(nextv[2]) > lim.climb[0] + 1e-8):
                return False
        t = (step + 1) * dt
        guard = radius + .5 * own_w * t * t
        lo, hi = step_extent(q[None], vel[None], a[None], dt)
        if np.any(lo[0] - guard < low) or np.any(hi[0] + guard > high):
            return False
        for x, y, z, r in e.airspace.obstacles:
            if quadratic_minimum(q - [x, y, z], vel, a, dt) < r + guard:
                return False
        reach = enclosure(snapshot, t, e.assumptions.traffic_acceleration_mps2)
        for j in others:
            minimum = quadratic_minimum(q - snapshot.position[j] - snapshot.velocity[j] * (t - dt), vel - snapshot.velocity[j], a, dt)
            if minimum < max(sep_req[j], radius + world.radius[j]) + guard - radius + reach[j]:
                return False
        q, vel = q + vel * dt + .5 * a * dt ** 2, nextv
    return True
