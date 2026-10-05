"""Point-mass vehicle envelopes for multirotor and fixed-wing UAS.

Acceleration is held constant over each step. Multirotors are bounded by a
total acceleration and speed. Fixed-wing aircraft additionally keep a minimum
horizontal speed and are bounded in longitudinal, lateral and vertical
acceleration, turn rate and climb rate. These are kinematic envelopes, not
aerodynamic, attitude or autopilot models.
"""
from dataclasses import dataclass
import numpy as np


def unit(x):
    return x / np.maximum(np.linalg.norm(x, axis=-1, keepdims=True), 1e-9)


@dataclass
class Limits:
    """Per-aircraft envelope arrays (length n)."""
    fixed: np.ndarray
    acceleration: np.ndarray
    max_speed: np.ndarray
    min_speed: np.ndarray
    longitudinal: np.ndarray
    lateral: np.ndarray
    vertical: np.ndarray
    turn_rate: np.ndarray   # rad/s
    climb: np.ndarray

    def take(self, ids):
        return Limits(**{k: getattr(self, k)[ids] for k in self.__dataclass_fields__})

    def repeat(self, k):
        return Limits(**{name: np.repeat(getattr(self, name), k) for name in self.__dataclass_fields__})


def limits_for(experiment, fixed):
    """Envelope arrays for a fleet given its fixed-wing mask."""
    mr, fw = experiment.multirotor, experiment.fixed_wing
    pick = lambda a, b: np.where(fixed, float(b), float(a))
    inf = np.inf
    return Limits(fixed=fixed.copy(),
                  acceleration=pick(mr.acceleration_mps2, fw.acceleration_mps2),
                  max_speed=pick(mr.max_speed_mps, fw.max_speed_mps),
                  min_speed=pick(0., fw.min_speed_mps),
                  longitudinal=pick(inf, fw.longitudinal_mps2),
                  lateral=pick(inf, fw.lateral_mps2),
                  vertical=pick(inf, fw.vertical_mps2),
                  turn_rate=pick(inf, np.deg2rad(fw.turn_rate_dps)),
                  climb=pick(inf, fw.climb_mps))


def project(a, v, lim, dt):
    """Project desired accelerations into each aircraft's envelope for one step."""
    a = np.array(a, float)
    norm = np.linalg.norm(a, axis=1)
    a *= np.minimum(1., lim.acceleration / np.maximum(norm, 1e-9))[:, None]
    nextv = v + a * dt
    nextv *= np.minimum(1., lim.max_speed / np.maximum(np.linalg.norm(nextv, axis=1), 1e-9))[:, None]
    a = (nextv - v) / dt
    ids = np.flatnonzero(lim.fixed)
    if len(ids):
        hv = v[ids, :2]
        speed = np.linalg.norm(hv, axis=1)
        forward = unit(hv)
        lateral = np.column_stack((-forward[:, 1], forward[:, 0]))
        lon_a = np.clip(np.sum(a[ids, :2] * forward, axis=1), -lim.longitudinal[ids], lim.longitudinal[ids])
        lon_a = np.maximum(lon_a, (lim.min_speed[ids] - speed) / dt)
        lat_a = np.clip(np.sum(a[ids, :2] * lateral, axis=1), -lim.lateral[ids], lim.lateral[ids])
        turn = np.maximum(speed + lon_a * dt, lim.min_speed[ids]) * np.tan(lim.turn_rate[ids] * dt) / dt
        lat_a = np.clip(lat_a, -turn, turn)
        climb = lim.climb[ids]
        ver_a = np.clip(a[ids, 2], -lim.vertical[ids], lim.vertical[ids])
        ver_a = np.clip(ver_a, (-climb - v[ids, 2]) / dt, (climb - v[ids, 2]) / dt)
        aa = np.column_stack((forward * lon_a[:, None] + lateral * lat_a[:, None], ver_a))
        aa *= np.minimum(1., lim.acceleration[ids] / np.maximum(np.linalg.norm(aa, axis=1), 1e-9))[:, None]
        nv = v[ids] + aa * dt
        horizontal_max = np.sqrt(np.maximum(lim.max_speed[ids] ** 2 - nv[:, 2] ** 2, lim.min_speed[ids] ** 2))
        hs = np.linalg.norm(nv[:, :2], axis=1)
        nv[:, :2] *= np.minimum(1., horizontal_max / np.maximum(hs, 1e-9))[:, None]
        a[ids] = (nv - v[ids]) / dt
    return a


def preferred_velocity(p, goals, cruise, lim):
    """Goal-directed velocity that can still brake to a stop (or minimum speed) at the goal."""
    diff = goals - p
    distance = np.linalg.norm(diff, axis=1)
    speed = np.minimum(cruise, np.sqrt(2 * lim.acceleration * distance))
    speed = np.maximum(speed, lim.min_speed)
    return unit(diff) * speed[:, None]


def violations(a, v, new_v, lim, dt, tolerance=1e-6, disturbance=0.):
    """Envelope violations of applied acceleration and resulting velocity (counted, never hidden)."""
    bad = np.linalg.norm(a, axis=1) > lim.acceleration + disturbance + tolerance
    bad |= np.linalg.norm(new_v, axis=1) > lim.max_speed + tolerance
    ids = np.flatnonzero(lim.fixed)
    if len(ids):
        angle = np.arctan2(new_v[ids, 1], new_v[ids, 0]) - np.arctan2(v[ids, 1], v[ids, 0])
        angle = np.abs((angle + np.pi) % (2 * np.pi) - np.pi)
        bad[ids] |= ((np.linalg.norm(new_v[ids, :2], axis=1) < lim.min_speed[ids] - tolerance) |
                     (angle > lim.turn_rate[ids] * dt + tolerance) |
                     (np.abs(new_v[ids, 2]) > lim.climb[ids] + tolerance))
    return bad
