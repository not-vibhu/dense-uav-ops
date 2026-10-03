from dataclasses import asdict, dataclass
import math


@dataclass(frozen=True)
class Profile:
    name: str = "mixed-urban-research"
    scenario: str = "crossing"
    area_m: float = 300.
    floor_m: float = 12.
    ceiling_m: float = 116.
    uas_altitude_min_m: float | None = None
    uas_altitude_max_m: float | None = None
    uas_route_half_width_m: float | None = None
    manned_route_lateral_offset_m: float = 0.
    fixed_wing_fraction: float = .4
    cooperative_fraction: float = .5
    compliance_fraction: float = .95
    drone_speed_mps: float = 8.
    drone_max_speed_mps: float = 12.
    drone_acceleration_mps2: float = 4.
    multirotor_radius_m: float = 1.2
    fixed_wing_radius_m: float = 2.5
    flight_endurance_s: float = 900.
    fixed_wing_min_speed_mps: float = 6.
    fixed_wing_turn_deg_s: float = 35.
    fixed_wing_climb_mps: float = 3.
    uas_separation_m: float = 10.
    manned_operations_per_hour: float = 60.
    manned_kind: str = "helicopter"
    manned_speed_mps: float = 35.
    manned_max_speed_mps: float = 60.
    manned_min_speed_mps: float = 0.
    manned_turn_deg_s: float = 15.
    manned_climb_mps: float = 5.
    manned_radius_m: float = 6.
    manned_acceleration_bound_mps2: float = 3.
    manned_altitude_m: float = 80.
    manned_separation_m: float = 60.
    position_error_m: float = 1.5
    velocity_error_mps: float = .3
    telemetry_period_s: float = .5
    telemetry_latency_s: float = .15
    telemetry_loss_fraction: float = .03
    manned_detection_fraction: float = 1.
    sensor_range_m: float = 600.
    surveillance_lookahead_s: float = 10.
    wind_acceleration_mps2: float = .4
    actuator_time_constant_s: float = 0.
    control_failure_fraction: float = 0.
    control_failure_after_s: float = 5.
    obstacles: tuple = ()
    hardware_name: str = "executing-host-unvalidated"
    hardware_time_multiplier: float = 1.
    command_deadline_ms: float = 200.
    warmup_s: float = 40.
    measurement_s: float = 120.
    drain_s: float = 60.
    dt_s: float = .2
    minimum_completion_fraction: float = .95
    maximum_p95_wait_s: float = 10.
    maximum_backlog_growth: int = 2
    failure_probability_per_run: float = .01
    confidence: float = .95

    def validate(self):
        for key, value in asdict(self).items():
            if isinstance(value, (int, float)) and (isinstance(value, bool) or not math.isfinite(value)):
                raise ValueError(f"Nonfinite or boolean numeric parameter: {key}")
        for key in ("fixed_wing_fraction", "cooperative_fraction", "compliance_fraction",
                    "telemetry_loss_fraction", "manned_detection_fraction", "minimum_completion_fraction", "control_failure_fraction"):
            if not 0 <= getattr(self, key) <= 1:
                raise ValueError(f"{key} must be in [0,1]")
        positive = ("area_m", "drone_speed_mps", "drone_max_speed_mps", "drone_acceleration_mps2",
                    "fixed_wing_min_speed_mps", "fixed_wing_turn_deg_s", "fixed_wing_climb_mps",
                    "multirotor_radius_m", "fixed_wing_radius_m", "flight_endurance_s",
                    "uas_separation_m", "manned_speed_mps", "manned_max_speed_mps", "manned_turn_deg_s",
                    "manned_climb_mps", "manned_radius_m", "manned_separation_m",
                    "telemetry_period_s", "sensor_range_m", "hardware_time_multiplier",
                    "command_deadline_ms", "measurement_s", "drain_s")
        if any(getattr(self, key) <= 0 for key in positive):
            raise ValueError("Positive profile parameter required")
        nonnegative = ("position_error_m", "velocity_error_mps", "telemetry_latency_s",
                       "manned_acceleration_bound_mps2", "wind_acceleration_mps2",
                       "actuator_time_constant_s", "warmup_s", "maximum_p95_wait_s", "manned_operations_per_hour",
                       "surveillance_lookahead_s", "manned_min_speed_mps", "control_failure_after_s")
        if any(getattr(self, key) < 0 for key in nonnegative):
            raise ValueError("Negative profile parameter")
        if self.area_m <= 100 or self.ceiling_m - self.floor_m <= 25:
            raise ValueError("Volume too small for this route generator")
        if not self.floor_m + self.manned_radius_m < self.manned_altitude_m < self.ceiling_m - self.manned_radius_m:
            raise ValueError("Manned route must fit inside the volume")
        if not .02 <= self.dt_s <= .5 or self.command_deadline_ms > self.dt_s * 1000:
            raise ValueError("Invalid step or command deadline exceeding the control period")
        if self.telemetry_period_s < self.dt_s:
            raise ValueError("Surveillance period cannot be shorter than the simulation step")
        if any(abs(value/self.dt_s-round(value/self.dt_s)) > 1e-7 for value in (self.warmup_s, self.measurement_s, self.drain_s)):
            raise ValueError("Observation windows must be integer multiples of the simulation step")
        if not 0 < self.failure_probability_per_run < 1 or not 0 < self.confidence < 1:
            raise ValueError("Probability and confidence must be strictly between zero and one")
        if not isinstance(self.maximum_backlog_growth, int) or self.maximum_backlog_growth < 0:
            raise ValueError("Backlog growth allowance must be a nonnegative integer")
        if self.wind_acceleration_mps2 > .8:
            raise ValueError("Existing predictive enclosure covers at most 0.8 m/s² wind")
        if self.manned_kind not in ("helicopter", "light-fixed-wing"):
            raise ValueError("Unsupported manned aircraft class")
        if self.scenario not in ("crossing", "corridor", "urban", "manned_intrusion", "sensor_outage", "wind_gust"):
            raise ValueError("Unknown capacity scenario")
        if not 0 < self.fixed_wing_min_speed_mps <= self.drone_speed_mps <= self.drone_max_speed_mps:
            raise ValueError("Invalid drone airspeed bounds")
        if self.fixed_wing_climb_mps > self.drone_max_speed_mps:
            raise ValueError("Invalid drone climb limit")
        if not self.manned_min_speed_mps <= self.manned_speed_mps <= self.manned_max_speed_mps:
            raise ValueError("Invalid manned speed bounds")
        if max(self.multirotor_radius_m, self.fixed_wing_radius_m, self.manned_radius_m) >= min(self.area_m/2-25, (self.ceiling_m-self.floor_m)/2-10):
            raise ValueError("Aircraft bodies do not fit inside the operating volume")
        radius = max(self.multirotor_radius_m, self.fixed_wing_radius_m)
        low = self.floor_m+radius+10 if self.uas_altitude_min_m is None else self.uas_altitude_min_m
        high = self.ceiling_m-radius-10 if self.uas_altitude_max_m is None else self.uas_altitude_max_m
        if not self.floor_m+radius < low <= high < self.ceiling_m-radius:
            raise ValueError("UAS altitude band must fit inside the volume with body clearance")
        if self.uas_route_half_width_m is not None and not 0 <= self.uas_route_half_width_m < self.area_m/2-radius:
            raise ValueError("Invalid UAS route half-width")
        if abs(self.manned_route_lateral_offset_m) >= self.area_m/2-self.manned_radius_m:
            raise ValueError("Manned route offset must fit inside the volume")
        for obstacle in self.obstacles:
            if len(obstacle) != 4 or not all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) for x in obstacle) or obstacle[3] <= 0:
                raise ValueError("Obstacles must be finite [x,y,z,radius] spheres with positive radius")
        return self
