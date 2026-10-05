"""Offered traffic: arrival times, routes, vehicle classes, equipage and behaviour.

UAS operations enter at a portal inset inside the volume boundary and leave at
an exit portal on the opposite side. Manned aircraft fly straight transits that
start outside the volume, so surveillance can see them before they enter.
"""
from dataclasses import dataclass
import numpy as np

from .vehicles import Limits, limits_for, unit

MAX_OPERATIONS = 5000


@dataclass
class Traffic:
    request: np.ndarray      # time an operation asks to enter (UAS) or crosses the boundary (manned)
    activate: np.ndarray     # time the aircraft becomes airborne in the simulation
    manned: np.ndarray
    fixed: np.ndarray        # fixed-wing UAS
    cooperative: np.ndarray  # equipped and participating
    compliant: np.ndarray    # follows its own route/commands
    controlled: np.ndarray   # cooperative & compliant UAS: the system's control authority
    start: np.ndarray
    goal: np.ndarray
    velocity: np.ndarray     # entry velocity
    cruise: np.ndarray
    radius: np.ndarray
    nominal_time: np.ndarray # straight-line traversal time at cruise
    limits: Limits

    @property
    def n(self):
        return len(self.request)


def arrival_times(rate_per_hour, stop, process, rng):
    if rate_per_hour <= 0:
        return np.array([])
    mean = 3600. / rate_per_hour
    if process == 'periodic':
        return np.arange(rng.uniform(0, mean), stop, mean)
    # Poisson process: draw enough exponential gaps to pass the stop time.
    times = np.cumsum(rng.exponential(mean, size=max(16, int(2 * stop / mean) + 16)))
    while times[-1] < stop:
        times = np.concatenate((times, times[-1] + np.cumsum(rng.exponential(mean, size=len(times)))))
    return times[times < stop]


def build(experiment):
    e, a, d, f = experiment, experiment.airspace, experiment.demand, experiment.fleet
    rng = np.random.default_rng(np.random.SeedSequence([e.seed, 101]))
    stop = e.window.warmup_s + e.window.measurement_s
    dt = e.window.dt_s
    uas = np.ceil(arrival_times(d.uas_per_hour, stop, d.arrivals, rng) / dt - 1e-9) * dt
    manned_times = np.ceil(arrival_times(d.manned_per_hour, stop, d.arrivals, rng) / dt - 1e-9) * dt
    n_uas, n_manned = len(uas), len(manned_times)
    n = n_uas + n_manned
    if n > MAX_OPERATIONS:
        raise ValueError(f'{n} scheduled operations exceed {MAX_OPERATIONS}; shorten the window or split runs')
    manned = np.arange(n) >= n_uas
    request = np.concatenate((uas, manned_times))
    fixed = (rng.random(n) < f.fixed_wing_fraction) & ~manned
    cooperative = (rng.random(n) < f.cooperative_fraction) & ~manned
    compliant = (rng.random(n) >= f.noncompliant_fraction) | manned
    radius = np.where(manned, e.manned.radius_m, np.where(fixed, e.fixed_wing.radius_m, e.multirotor.radius_m))
    cruise = np.where(manned, e.manned.speed_mps, np.where(fixed, e.fixed_wing.cruise_mps, e.multirotor.cruise_mps))
    half = a.side_m / 2
    edge, exit_edge = half - d.entry_inset_m, half - d.exit_inset_m
    width = d.lane_half_width_m
    if width is None:
        width = 20. if d.pattern in ('corridor', 'head-on') else exit_edge - 10.
    start = np.zeros((n, 3))
    goal = np.zeros((n, 3))
    for i in range(n_uas):
        r = radius[i]
        low = a.floor_m + r + 5 if d.uas_altitude_min_m is None else d.uas_altitude_min_m
        high = a.ceiling_m - r - 5 if d.uas_altitude_max_m is None else d.uas_altitude_max_m
        if d.pattern == 'crossing':
            axis, sign = int(rng.integers(2)), (1 if rng.random() < .5 else -1)
        elif d.pattern == 'corridor':
            axis, sign = 0, 1
        else:
            axis, sign = 0, (1 if rng.random() < .5 else -1)
        altitude = rng.uniform(low, high)
        lateral_in, lateral_out = rng.uniform(-width, width, size=2)
        if d.pattern != 'crossing':
            lateral_out = lateral_in
        start[i, axis], start[i, 1 - axis], start[i, 2] = -sign * edge, lateral_in, altitude
        goal[i, axis], goal[i, 1 - axis], goal[i, 2] = sign * exit_edge, lateral_out, altitude
    for i in np.flatnonzero(manned):
        start[i] = (-half - d.manned_lookahead_s * e.manned.speed_mps, d.manned_lateral_offset_m, d.manned_altitude_m)
        goal[i] = (half + 4 * e.manned.radius_m + e.requirements.manned_separation_m, d.manned_lateral_offset_m, d.manned_altitude_m)
    velocity = unit(goal - start) * cruise[:, None]
    activate = np.where(manned, request - d.manned_lookahead_s, request)
    limits = limits_for(experiment, fixed)
    # Manned aircraft are exogenous; their envelope is not projected, only checked.
    limits.acceleration[manned] = np.inf
    limits.max_speed[manned] = np.inf
    nominal = np.where(manned, np.nan, np.linalg.norm(goal - start, axis=1) / cruise)
    return Traffic(request=request, activate=activate, manned=manned, fixed=fixed, cooperative=cooperative,
                   compliant=compliant, controlled=cooperative & compliant & ~manned, start=start, goal=goal,
                   velocity=velocity, cruise=cruise, radius=radius, nominal_time=nominal, limits=limits)
