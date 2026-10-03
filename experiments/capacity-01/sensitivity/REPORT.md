# Airspace capacity assessment

Highest tested demand passing observed requirements: **not demonstrated** UAS operations/hour.
Statistically supported tested demand: **not demonstrated** UAS operations/hour.
Operationally certified capacity: **not established**.

| Profile / scenario | UAS demand/h | Occupancy limit | Runs | UAS exits/h (worst) | Manned exits/h (worst) | Peak total | Observed pass | Failure upper bound | Blocking requirements |
|---|---:|---:|---:|---:|---:|---:|---|---:|---|
| degraded-surveillance / crossing | 120 | 10 | 3 | 120.0 | 60.0 | 3 | False | 1.0000 | body_volume_exit_aircraft, kinematic_violation_aircraft_steps, protected_volume_breach_pairs, insufficient_statistical_safety_evidence |
| degraded-surveillance / crossing | 120 | 50 | 3 | 120.0 | 60.0 | 3 | False | 1.0000 | body_volume_exit_aircraft, kinematic_violation_aircraft_steps, protected_volume_breach_pairs, insufficient_statistical_safety_evidence |
| degraded-surveillance / crossing | 360 | 10 | 3 | 330.0 | 60.0 | 5 | False | 1.0000 | body_volume_exit_aircraft, collision_pairs, kinematic_violation_aircraft_steps, no_admissible_aircraft_steps, protected_volume_breach_pairs, insufficient_statistical_safety_evidence |
| degraded-surveillance / crossing | 360 | 50 | 3 | 330.0 | 60.0 | 5 | False | 1.0000 | body_volume_exit_aircraft, collision_pairs, kinematic_violation_aircraft_steps, no_admissible_aircraft_steps, protected_volume_breach_pairs, insufficient_statistical_safety_evidence |
| degraded-surveillance / crossing | 720 | 10 | 3 | 630.0 | 60.0 | 10 | False | 1.0000 | backlog_growth_requirement, body_volume_exit_aircraft, collision_pairs, kinematic_violation_aircraft_steps, no_admissible_aircraft_steps, protected_volume_breach_pairs, insufficient_statistical_safety_evidence |
| degraded-surveillance / crossing | 720 | 50 | 3 | 630.0 | 60.0 | 10 | False | 1.0000 | backlog_growth_requirement, body_volume_exit_aircraft, collision_pairs, kinematic_violation_aircraft_steps, no_admissible_aircraft_steps, protected_volume_breach_pairs, insufficient_statistical_safety_evidence |
| degraded-surveillance / urban | 120 | 10 | 3 | 120.0 | 60.0 | 3 | False | 1.0000 | body_volume_exit_aircraft, kinematic_violation_aircraft_steps, obstacle_collision_pairs, protected_volume_breach_pairs, insufficient_statistical_safety_evidence |
| degraded-surveillance / urban | 120 | 50 | 3 | 120.0 | 60.0 | 3 | False | 1.0000 | body_volume_exit_aircraft, kinematic_violation_aircraft_steps, obstacle_collision_pairs, protected_volume_breach_pairs, insufficient_statistical_safety_evidence |
| degraded-surveillance / urban | 360 | 10 | 3 | 330.0 | 60.0 | 5 | False | 1.0000 | body_volume_exit_aircraft, collision_pairs, kinematic_violation_aircraft_steps, no_admissible_aircraft_steps, obstacle_collision_pairs, protected_volume_breach_pairs, insufficient_statistical_safety_evidence |
| degraded-surveillance / urban | 360 | 50 | 3 | 330.0 | 60.0 | 5 | False | 1.0000 | body_volume_exit_aircraft, collision_pairs, kinematic_violation_aircraft_steps, no_admissible_aircraft_steps, obstacle_collision_pairs, protected_volume_breach_pairs, insufficient_statistical_safety_evidence |
| degraded-surveillance / urban | 720 | 10 | 3 | 630.0 | 60.0 | 10 | False | 1.0000 | backlog_growth_requirement, body_volume_exit_aircraft, collision_pairs, kinematic_violation_aircraft_steps, no_admissible_aircraft_steps, obstacle_collision_pairs, protected_volume_breach_pairs, insufficient_statistical_safety_evidence |
| degraded-surveillance / urban | 720 | 50 | 3 | 630.0 | 60.0 | 10 | False | 1.0000 | backlog_growth_requirement, body_volume_exit_aircraft, collision_pairs, kinematic_violation_aircraft_steps, no_admissible_aircraft_steps, obstacle_collision_pairs, protected_volume_breach_pairs, insufficient_statistical_safety_evidence |
| degraded-surveillance / sensor_outage | 120 | 10 | 3 | 120.0 | 60.0 | 3 | False | 1.0000 | body_volume_exit_aircraft, kinematic_violation_aircraft_steps, protected_volume_breach_pairs, insufficient_statistical_safety_evidence |
| degraded-surveillance / sensor_outage | 120 | 50 | 3 | 120.0 | 60.0 | 3 | False | 1.0000 | body_volume_exit_aircraft, kinematic_violation_aircraft_steps, protected_volume_breach_pairs, insufficient_statistical_safety_evidence |
| degraded-surveillance / sensor_outage | 360 | 10 | 3 | 330.0 | 60.0 | 6 | False | 1.0000 | body_volume_exit_aircraft, collision_pairs, kinematic_violation_aircraft_steps, no_admissible_aircraft_steps, protected_volume_breach_pairs, insufficient_statistical_safety_evidence |
| degraded-surveillance / sensor_outage | 360 | 50 | 3 | 330.0 | 60.0 | 6 | False | 1.0000 | body_volume_exit_aircraft, collision_pairs, kinematic_violation_aircraft_steps, no_admissible_aircraft_steps, protected_volume_breach_pairs, insufficient_statistical_safety_evidence |
| degraded-surveillance / sensor_outage | 720 | 10 | 3 | 630.0 | 60.0 | 10 | False | 1.0000 | backlog_growth_requirement, body_volume_exit_aircraft, collision_pairs, kinematic_violation_aircraft_steps, no_admissible_aircraft_steps, protected_volume_breach_pairs, insufficient_statistical_safety_evidence |
| degraded-surveillance / sensor_outage | 720 | 50 | 3 | 630.0 | 60.0 | 10 | False | 1.0000 | backlog_growth_requirement, body_volume_exit_aircraft, collision_pairs, kinematic_violation_aircraft_steps, no_admissible_aircraft_steps, protected_volume_breach_pairs, insufficient_statistical_safety_evidence |

- Null capacity means no positive demonstrated value; it does not establish that physical capacity is zero.
- No monotonicity assumption, binary search or interpolation between tested levels.
- Statistical bound concerns independent fixed-duration scenario runs, not failures per flight/hour.
- All supplied profiles are required; favorable scenarios cannot offset a failing profile.
- Finite windows and backlog checks do not establish long-run queue stability.
- Host timing and an explicit synthetic multiplier do not establish target hardware WCET.
- Manned traffic uses simplified bounded trajectories; wake, ATC, pilot and aircraft flight models are absent.
- Separation and surveillance thresholds are research inputs, not regulatory minima.
- No joint invariant safety proof, field validation, airworthiness or legal authorization.
