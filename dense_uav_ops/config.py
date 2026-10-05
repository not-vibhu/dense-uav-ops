"""Experiment configuration: one nested, JSON-serializable description of a run.

Every quantity is SI. Defaults describe a hypothetical research setting, not an
approved operating profile. Profiles are JSON objects that override any subset
of these fields; unknown keys are rejected so a typo cannot silently fall back
to a default.
"""
from dataclasses import asdict, dataclass, field, fields, is_dataclass, replace
import hashlib
import json
import math


@dataclass(frozen=True)
class Airspace:
    """Square operating volume centred on the origin; obstacles are spheres."""
    side_m: float = 400.
    floor_m: float = 30.
    ceiling_m: float = 120.
    obstacles: tuple = ()  # ((x, y, z, radius), ...)


@dataclass(frozen=True)
class Demand:
    """Offered traffic. An operation is one traversal from an entry to an exit."""
    uas_per_hour: float = 720.
    arrivals: str = 'poisson'          # 'poisson' or 'periodic'
    pattern: str = 'crossing'          # 'crossing', 'corridor' or 'head-on'
    entry_inset_m: float = 15.
    exit_inset_m: float = 25.          # exits sit inside the opposite entry plane, so leaving and entering aircraft do not coincide
    uas_altitude_min_m: float | None = None
    uas_altitude_max_m: float | None = None
    lane_half_width_m: float | None = None
    manned_per_hour: float = 0.
    manned_altitude_m: float = 100.
    manned_lateral_offset_m: float = 0.
    manned_lookahead_s: float = 15.    # surveillance sees manned traffic before it enters


@dataclass(frozen=True)
class Fleet:
    """Traffic mix. Equipage (cooperative) and behaviour (compliant) are independent."""
    fixed_wing_fraction: float = .4
    cooperative_fraction: float = 1.
    noncompliant_fraction: float = 0.
    noncompliant_acceleration_mps2: float = 2.


@dataclass(frozen=True)
class Multirotor:
    cruise_mps: float = 8.
    max_speed_mps: float = 12.
    acceleration_mps2: float = 4.
    radius_m: float = 1.2


@dataclass(frozen=True)
class FixedWing:
    cruise_mps: float = 8.
    min_speed_mps: float = 6.
    max_speed_mps: float = 12.
    acceleration_mps2: float = 4.
    longitudinal_mps2: float = 2.
    lateral_mps2: float = 3.
    vertical_mps2: float = 2.
    turn_rate_dps: float = 35.
    climb_mps: float = 3.
    radius_m: float = 2.5


@dataclass(frozen=True)
class Manned:
    """Exogenous straight transits; never controlled, delayed or negotiated with."""
    speed_mps: float = 35.
    radius_m: float = 6.


@dataclass(frozen=True)
class Surveillance:
    """One shared regional feed (e.g. network Remote ID plus fused sensors)."""
    period_s: float = 1.
    latency_s: float = .2              # delivery is quantized to the step; use multiples of dt
    loss: float = .03
    position_error_m: float = 1.5      # declared hard bound on report error
    velocity_error_mps: float = .3
    bias_fraction: float = .6          # share of the position bound that is a persistent per-aircraft bias
    range_m: float = 1000.
    manned_detection: float = 1.       # probability a manned aircraft is ever reported
    uncooperative_detection: float = 1.     # probability a non-cooperative UAS is ever reported (1 = all broadcast Remote ID)
    uncooperative_error_scale: float = 1.   # multiplies the declared error bounds of non-cooperative UAS reports
    outage_start_s: float = 0.
    outage_duration_s: float = 0.


@dataclass(frozen=True)
class Environment:
    """True disturbances and faults. The planner does not see these directly."""
    wind_mps2: float = .4
    wind_period_s: float = 60.
    actuator_time_constant_s: float = 0.
    command_drop_probability: float = 0.   # seeded stand-in for missed control updates


@dataclass(frozen=True)
class Assumptions:
    """What the planner assumes about the world. This is the frontier variable.

    `traffic_acceleration_mps2` bounds how hard any other aircraft is assumed to
    be able to accelerate (including wind). It is deliberately independent of the
    vehicles' true authority so that optimistic and conservative beliefs can be
    compared against the same true traffic.
    """
    traffic_acceleration_mps2: float = 4.
    own_disturbance_mps2: float = .8
    horizon_s: float = 2.4


@dataclass(frozen=True)
class Controller:
    kind: str = 'predictive'   # 'none', 'predictive', 'daidalus', 'recurrent', 'graph'
    progress_weight: float = 1.
    effort_weight: float = .03
    turn_weight: float = .1
    vertical_weight: float = .1
    checkpoint: str = ''
    daidalus_period_s: float = 1.
    daidalus_manifest: str = 'artifacts/daidalus/manifest.json'


@dataclass(frozen=True)
class Admission:
    occupancy_limit: int = 500         # on surveillance-estimated airborne count
    entry_check: str = 'spacing'       # 'none', 'spacing', 'clearance' or 'recovery' (each includes the previous, except 'none')
    spacing_horizon_s: float = 1.      # straight-ahead window the entry point must stay clear for


@dataclass(frozen=True)
class Requirements:
    """Measurement thresholds. They define events, not regulatory minima."""
    separation_m: float = 10.
    manned_separation_m: float = 60.
    goal_radius_m: float = 3.


@dataclass(frozen=True)
class Window:
    dt_s: float = .2
    warmup_s: float = 60.
    measurement_s: float = 240.
    drain_s: float = 90.


@dataclass(frozen=True)
class Experiment:
    name: str = 'default'
    seed: int = 0
    airspace: Airspace = field(default_factory=Airspace)
    demand: Demand = field(default_factory=Demand)
    fleet: Fleet = field(default_factory=Fleet)
    multirotor: Multirotor = field(default_factory=Multirotor)
    fixed_wing: FixedWing = field(default_factory=FixedWing)
    manned: Manned = field(default_factory=Manned)
    surveillance: Surveillance = field(default_factory=Surveillance)
    environment: Environment = field(default_factory=Environment)
    assumptions: Assumptions = field(default_factory=Assumptions)
    controller: Controller = field(default_factory=Controller)
    admission: Admission = field(default_factory=Admission)
    requirements: Requirements = field(default_factory=Requirements)
    window: Window = field(default_factory=Window)

    def to_dict(self):
        return asdict(self)

    def run_id(self):
        return hashlib.sha256(canonical(self.to_dict())).hexdigest()[:16]

    def validate(self):
        a, d, f, mr, fw, s = self.airspace, self.demand, self.fleet, self.multirotor, self.fixed_wing, self.surveillance
        e, asm, c, adm, r, w = self.environment, self.assumptions, self.controller, self.admission, self.requirements, self.window
        for path, value in _leaves(self):
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError(f'{path} must be finite')
        if type(self.seed) is not int or self.seed < 0:
            raise ValueError('seed must be a nonnegative integer')
        if a.side_m < 100 or a.ceiling_m - a.floor_m < 20 or a.floor_m < 0:
            raise ValueError('airspace too small for the route generator')
        for obstacle in a.obstacles:
            if len(obstacle) != 4 or obstacle[3] <= 0 or not all(math.isfinite(x) for x in obstacle):
                raise ValueError('obstacles must be finite (x, y, z, radius) spheres')
        if d.uas_per_hour <= 0 or d.manned_per_hour < 0 or d.arrivals not in ('poisson', 'periodic'):
            raise ValueError('demand must be positive with a known arrival process')
        if d.pattern not in ('crossing', 'corridor', 'head-on'):
            raise ValueError('unknown route pattern')
        if not 0 <= d.entry_inset_m < d.exit_inset_m < a.side_m / 4 or d.manned_lookahead_s < 0:
            raise ValueError('need 0 <= entry inset < exit inset < side/4 and a nonnegative manned lookahead')
        if not a.floor_m < d.manned_altitude_m < a.ceiling_m + 500:
            raise ValueError('manned altitude must lie above the floor')
        for name in ('fixed_wing_fraction', 'cooperative_fraction', 'noncompliant_fraction'):
            if not 0 <= getattr(f, name) <= 1:
                raise ValueError(f'fleet.{name} must lie in [0, 1]')
        if f.noncompliant_acceleration_mps2 < 0:
            raise ValueError('noncompliant acceleration must be nonnegative')
        if not 0 < mr.cruise_mps <= mr.max_speed_mps or mr.acceleration_mps2 <= 0 or mr.radius_m <= 0:
            raise ValueError('invalid multirotor envelope')
        if (not 0 < fw.min_speed_mps <= fw.cruise_mps <= fw.max_speed_mps or fw.acceleration_mps2 <= 0
                or min(fw.longitudinal_mps2, fw.lateral_mps2, fw.vertical_mps2, fw.turn_rate_dps, fw.climb_mps, fw.radius_m) <= 0):
            raise ValueError('invalid fixed-wing envelope')
        if self.manned.speed_mps <= 0 or self.manned.radius_m <= 0:
            raise ValueError('invalid manned aircraft')
        if s.period_s < w.dt_s or s.latency_s < 0 or not 0 <= s.loss <= 1 or s.range_m <= 0:
            raise ValueError('invalid surveillance timing, loss or range')
        if (s.position_error_m < 0 or s.velocity_error_mps < 0 or not 0 <= s.bias_fraction <= 1
                or not 0 <= s.manned_detection <= 1 or not 0 <= s.uncooperative_detection <= 1 or s.uncooperative_error_scale < 1):
            raise ValueError('invalid surveillance error model')
        if s.outage_start_s < 0 or s.outage_duration_s < 0:
            raise ValueError('invalid surveillance outage')
        if e.wind_mps2 < 0 or e.wind_period_s <= 0 or e.actuator_time_constant_s < 0 or not 0 <= e.command_drop_probability <= 1:
            raise ValueError('invalid environment')
        if asm.traffic_acceleration_mps2 < 0 or asm.own_disturbance_mps2 < 0 or not w.dt_s <= asm.horizon_s <= 10:
            raise ValueError('invalid planner assumptions')
        if c.kind not in ('none', 'predictive', 'daidalus', 'recurrent', 'graph'):
            raise ValueError('unknown controller kind')
        if min(c.progress_weight, c.effort_weight, c.turn_weight, c.vertical_weight) <= 0:
            raise ValueError('preference weights must be positive')
        if c.kind in ('recurrent', 'graph') and not c.checkpoint:
            raise ValueError('learned controllers require a checkpoint')
        if c.daidalus_period_s < w.dt_s:
            raise ValueError('DAIDALUS guidance period must be at least one step')
        if type(adm.occupancy_limit) is not int or not 1 <= adm.occupancy_limit <= 2000:
            raise ValueError('occupancy limit must be an integer in [1, 2000]')
        if adm.entry_check not in ('none', 'spacing', 'clearance', 'recovery') or not 0 <= adm.spacing_horizon_s <= 10:
            raise ValueError('unknown entry check or invalid spacing horizon')
        if r.separation_m <= 0 or r.manned_separation_m <= 0 or r.goal_radius_m <= 0:
            raise ValueError('requirements must be positive')
        if not .02 <= w.dt_s <= .5 or w.warmup_s < 0 or w.measurement_s <= 0 or w.drain_s < 0:
            raise ValueError('invalid time window')
        for value in (w.warmup_s, w.measurement_s, w.drain_s, s.period_s, s.latency_s, c.daidalus_period_s):
            if abs(value / w.dt_s - round(value / w.dt_s)) > 1e-7:
                raise ValueError('windows, surveillance period and latency, and the DAIDALUS period must be multiples of dt')
        return self


SECTIONS = {f.name: f.type for f in fields(Experiment) if f.name not in ('name', 'seed')}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def _leaves(obj, prefix=''):
    for f in fields(obj):
        value = getattr(obj, f.name)
        path = f'{prefix}{f.name}'
        if is_dataclass(value):
            yield from _leaves(value, path + '.')
        else:
            yield path, value


def from_dict(document, base=None):
    """Merge a (possibly partial) nested document over `base` or the defaults."""
    base = base or Experiment()
    if not isinstance(document, dict):
        raise ValueError('profile must be a JSON object')
    unknown = set(document) - {f.name for f in fields(Experiment)}
    if unknown:
        raise ValueError('unknown profile keys: ' + ', '.join(sorted(unknown)))
    changes = {}
    for key, value in document.items():
        current = getattr(base, key)
        if is_dataclass(current):
            if not isinstance(value, dict):
                raise ValueError(f'{key} must be an object')
            extra = set(value) - {f.name for f in fields(current)}
            if extra:
                raise ValueError(f'unknown {key} keys: ' + ', '.join(sorted(extra)))
            if 'obstacles' in value:
                value = {**value, 'obstacles': tuple(tuple(float(x) for x in o) for o in value['obstacles'])}
            changes[key] = replace(current, **value)
        else:
            changes[key] = value
    return replace(base, **changes)


def override(experiment, path, value):
    """Return a copy with one dotted field replaced, e.g. 'assumptions.horizon_s'."""
    parts = path.split('.')
    if len(parts) == 1:
        return from_dict({parts[0]: value}, experiment)
    if len(parts) != 2 or parts[0] not in SECTIONS:
        raise ValueError(f'unknown setting {path}')
    return from_dict({parts[0]: {parts[1]: value}}, experiment)


def load(path):
    from pathlib import Path
    return from_dict(json.loads(Path(path).read_text()))
