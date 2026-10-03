from dataclasses import asdict, dataclass
import math


CONTROLLERS = ("goal", "repulsion", "barrier", "negotiated")


@dataclass(frozen=True)
class Config:
    scenario: str = "crossing"
    controller: str = "negotiated"
    drones: int = 50
    cooperative_fraction: float = 0.5
    fixed_wing_fraction: float = 0.4
    seed: int = 0
    duration: float = 36.0
    dt: float = 0.2
    area: float = 220.0
    altitude_floor: float = 12.0
    altitude_ceiling: float = 116.0
    cruise_speed: float = 8.0
    fixed_wing_min_speed: float = 6.0
    max_speed: float = 12.0
    acceleration_limit: float = 4.0
    fixed_wing_turn_rate_deg: float = 35.0
    fixed_wing_climb_limit: float = 3.0
    separation: float = 10.0
    position_error_bound: float = 1.5
    velocity_error_bound: float = 0.3
    advertised_acceleration_bound: float = 4.0
    telemetry_period: float = 0.5
    barrier_gain: float = 0.8
    projection_iterations: int = 12
    goal_radius: float = 3.0
    replay_period: float = 0.4

    def validate(self):
        from .scenarios import SCENARIOS
        if self.scenario not in SCENARIOS or self.controller not in CONTROLLERS:
            raise ValueError("Unknown scenario or controller")
        if not 2 <= self.drones <= 500:
            raise ValueError("Drones must be between 2 and 500")
        if not isinstance(self.seed, int) or self.seed < 0:
            raise ValueError("Seed must be a nonnegative integer")
        if not all(math.isfinite(v) for v in asdict(self).values() if isinstance(v, float)):
            raise ValueError("Configuration contains a nonfinite value")
        if not 0 <= self.cooperative_fraction <= 1 or not 0 <= self.fixed_wing_fraction <= 1:
            raise ValueError("Equipage fractions must lie between 0 and 1")
        if not 0.02 <= self.dt <= 0.5 or not 1 <= self.duration <= 180:
            raise ValueError("dt must be 0.02–0.5 s and duration 1–180 s")
        if self.fixed_wing_min_speed <= 0 or self.fixed_wing_min_speed > self.cruise_speed:
            raise ValueError("Invalid fixed-wing speed bounds")
        if self.max_speed < self.cruise_speed or self.acceleration_limit <= 0:
            raise ValueError("Invalid speed/acceleration limits")
        if self.separation <= 0 or self.area <= 30 or self.altitude_ceiling <= self.altitude_floor:
            raise ValueError("Invalid operating volume or separation")
        if self.telemetry_period <= 0 or self.replay_period <= 0:
            raise ValueError("Invalid telemetry/replay period")
        if self.projection_iterations < 1 or self.position_error_bound < 0 or self.velocity_error_bound < 0:
            raise ValueError("Invalid filter/enclosure settings")
        return self
