"""Ground-truth event checks, independent of the planner's prediction formulas.

Within a step every aircraft moves with constant acceleration, so the squared
distance between two aircraft is a quartic in time. Its extrema are roots of a
cubic, which are evaluated exactly; a conservative chord bound only decides
which pairs are far enough to skip.
"""
import numpy as np


def quadratic_minimum(r, v, a, dt):
    """Minimum of ||r + v t + a t^2 / 2|| over t in [0, dt]."""
    coefficients = [0.5 * np.dot(a, a), 1.5 * np.dot(v, a), np.dot(v, v) + np.dot(r, a), np.dot(r, v)]
    times = [0., dt]
    first = next((i for i, x in enumerate(coefficients) if abs(x) > 1e-12), len(coefficients))
    if first < len(coefficients) - 1:
        for z in np.roots(coefficients[first:]):
            if abs(z.imag) < 1e-7 and 0 < z.real < dt:
                times.append(float(z.real))
    return min(np.linalg.norm(r + v * t + .5 * a * t * t) for t in times)


def swept_pairs(p, v, a, active, threshold, dt):
    """Minimum separation of every active pair during one step.

    `threshold(i, j)` returns the largest distance of interest for each pair;
    pairs whose conservative lower bound exceeds it keep that lower bound.
    Returns pair indices and distances that are exact wherever they matter.
    """
    i, j = np.triu_indices(len(p), 1)
    use = active[i] & active[j]
    i, j = i[use], j[use]
    if not len(i):
        return i, j, np.array([], float)
    r = p[i] - p[j]
    relv = v[i] - v[j]
    rela = a[i] - a[j]
    delta = relv * dt + .5 * rela * dt * dt
    frac = np.clip(-np.einsum('ij,ij->i', r, delta) / np.maximum(np.einsum('ij,ij->i', delta, delta), 1e-20), 0., 1.)
    chord = np.linalg.norm(r + frac[:, None] * delta, axis=1)
    lower = np.maximum(0., chord - np.linalg.norm(rela, axis=1) * dt * dt / 8.)
    distances = lower.copy()
    for k in np.flatnonzero(lower <= threshold(i, j)):
        distances[k] = quadratic_minimum(r[k], relv[k], rela[k], dt)
    return i, j, distances


def swept_obstacles(p, v, a, active, radii, obstacles, dt):
    hits = []
    for k, (x, y, z, radius) in enumerate(obstacles):
        center = np.array([x, y, z])
        for i in np.flatnonzero(active):
            if np.linalg.norm(p[i] - center) <= radius + radii[i] + np.linalg.norm(v[i]) * dt + 2 * dt * dt + 1:
                if quadratic_minimum(p[i] - center, v[i], a[i], dt) < radius + radii[i]:
                    hits.append((int(i), k))
    return hits


def step_extent(p, v, a, dt):
    """Per-axis bounding box of each constant-acceleration path over one step."""
    end = p + v * dt + .5 * a * dt * dt
    t = np.divide(-v, a, out=np.zeros_like(v), where=np.abs(a) > 1e-12)
    inside = (t > 0) & (t < dt)
    extremum = p + v * t + .5 * a * t * t
    low = np.where(inside, np.minimum(np.minimum(p, end), extremum), np.minimum(p, end))
    high = np.where(inside, np.maximum(np.maximum(p, end), extremum), np.maximum(p, end))
    return low, high


def outside_volume(p, v, a, low_bound, high_bound, radii, dt):
    low, high = step_extent(p, v, a, dt)
    return np.any(low - radii[:, None] < low_bound, axis=1) | np.any(high + radii[:, None] > high_bound, axis=1)
