"""Ground-truth checker independent of controller prediction/barrier formulas."""
import numpy as np


def quadratic_minimum(r, v, a, dt):
    """Exact extrema candidates for ||r + v t + 0.5 a t²|| on a step."""
    coefficients = [0.5 * np.dot(a, a), 1.5 * np.dot(v, a),
                    np.dot(v, v) + np.dot(r, a), np.dot(r, v)]
    times = [0., dt]
    first = next((i for i, x in enumerate(coefficients) if abs(x) > 1e-12), len(coefficients))
    if first < len(coefficients) - 1:
        for z in np.roots(coefficients[first:]):
            if abs(z.imag) < 1e-7 and 0 < z.real < dt:
                times.append(float(z.real))
    return min(np.linalg.norm(r + v * t + .5 * a * t * t) for t in times)


def swept_pairs(p, v, a, active, radii, separation, dt):
    """Conservative chord bound screens pairs; exact cubic resolves all threats."""
    i, j = np.triu_indices(len(p), 1)
    use = active[i] & active[j]
    i, j = i[use], j[use]
    if not len(i):
        return i, j, np.array([], float), np.inf
    r = p[i] - p[j]
    relv = v[i] - v[j]
    rela = a[i] - a[j]
    delta = relv * dt + .5 * rela * dt * dt
    frac = np.clip(-np.einsum("ij,ij->i", r, delta) /
                   np.maximum(np.einsum("ij,ij->i", delta, delta), 1e-20), 0., 1.)
    chord = np.linalg.norm(r + frac[:, None] * delta, axis=1)
    lower = np.maximum(0., chord - np.linalg.norm(rela, axis=1) * dt * dt / 8.)
    # Anything possibly near a threshold gets an exact minimum calculation.
    threshold = np.maximum(separation, radii[i] + radii[j])
    nearby = lower <= threshold
    distances = lower.copy()
    for k in np.flatnonzero(nearby):
        distances[k] = quadratic_minimum(r[k], relv[k], rela[k], dt)
    # Global minimum is a conservative lower bound if its pair was not refined.
    return i, j, distances, float(np.min(distances))


def swept_obstacles(p, v, a, active, radii, obstacles, dt):
    events = []
    for k, (x, y, z, radius) in enumerate(obstacles):
        center = np.array([x, y, z])
        for i in np.flatnonzero(active):
            if np.linalg.norm(p[i] - center) <= radius + radii[i] + np.linalg.norm(v[i]) * dt + 2:
                if quadratic_minimum(p[i] - center, v[i], a[i], dt) < radius + radii[i]:
                    events.append((int(i), k))
    return events


def outside_volume(p, v, a, cfg, dt):
    lower = np.minimum(p, p + v * dt + .5 * a * dt * dt)
    upper = np.maximum(p, p + v * dt + .5 * a * dt * dt)
    t = np.divide(-v, a, out=np.zeros_like(v), where=np.abs(a) > 1e-12)
    inside = (t > 0) & (t < dt)
    extremum = p + v * t + .5 * a * t * t
    lower = np.where(inside, np.minimum(lower, extremum), lower)
    upper = np.where(inside, np.maximum(upper, extremum), upper)
    return (np.any(lower[:, :2] < -cfg.area / 2, axis=1) |
            np.any(upper[:, :2] > cfg.area / 2, axis=1) |
            (lower[:, 2] < cfg.altitude_floor) | (upper[:, 2] > cfg.altitude_ceiling))
