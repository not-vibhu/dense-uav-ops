# Airspace capacity assessment

Highest tested demand passing observed requirements: **not demonstrated** UAS operations/hour.
Statistically supported tested demand: **not demonstrated** UAS operations/hour.
Operationally certified capacity: **not established**.

| Profile / scenario | UAS demand/h | Occupancy limit | Runs | UAS exits/h (worst) | Manned exits/h (worst) | Peak total | Observed pass | Failure upper bound | Blocking requirements |
|---|---:|---:|---:|---:|---:|---:|---|---:|---|
| baseline-research / crossing | 120 | 10 | 3 | 120.0 | 60.0 | 2 | False | 1.0000 | no_admissible_aircraft_steps, protected_volume_breach_pairs, insufficient_statistical_safety_evidence |
| baseline-research / crossing | 120 | 50 | 3 | 120.0 | 60.0 | 2 | False | 1.0000 | no_admissible_aircraft_steps, protected_volume_breach_pairs, insufficient_statistical_safety_evidence |
| baseline-research / crossing | 360 | 10 | 3 | 330.0 | 60.0 | 5 | False | 1.0000 | collision_pairs, no_admissible_aircraft_steps, protected_volume_breach_pairs, insufficient_statistical_safety_evidence |
| baseline-research / crossing | 360 | 50 | 3 | 330.0 | 60.0 | 5 | False | 1.0000 | collision_pairs, no_admissible_aircraft_steps, protected_volume_breach_pairs, insufficient_statistical_safety_evidence |
| baseline-research / crossing | 720 | 10 | 3 | 690.0 | 60.0 | 10 | False | 1.0000 | body_volume_exit_aircraft, collision_pairs, no_admissible_aircraft_steps, protected_volume_breach_pairs, insufficient_statistical_safety_evidence |
| baseline-research / crossing | 720 | 50 | 3 | 690.0 | 60.0 | 10 | False | 1.0000 | body_volume_exit_aircraft, collision_pairs, no_admissible_aircraft_steps, protected_volume_breach_pairs, insufficient_statistical_safety_evidence |
| baseline-research / corridor | 120 | 10 | 3 | 120.0 | 60.0 | 2 | False | 1.0000 | no_admissible_aircraft_steps, protected_volume_breach_pairs, insufficient_statistical_safety_evidence |
| baseline-research / corridor | 120 | 50 | 3 | 120.0 | 60.0 | 2 | False | 1.0000 | no_admissible_aircraft_steps, protected_volume_breach_pairs, insufficient_statistical_safety_evidence |
| baseline-research / corridor | 360 | 10 | 3 | 330.0 | 60.0 | 5 | False | 1.0000 | collision_pairs, no_admissible_aircraft_steps, protected_volume_breach_pairs, insufficient_statistical_safety_evidence |
| baseline-research / corridor | 360 | 50 | 3 | 330.0 | 60.0 | 5 | False | 1.0000 | collision_pairs, no_admissible_aircraft_steps, protected_volume_breach_pairs, insufficient_statistical_safety_evidence |
| baseline-research / corridor | 720 | 10 | 3 | 660.0 | 60.0 | 8 | False | 1.0000 | body_volume_exit_aircraft, no_admissible_aircraft_steps, protected_volume_breach_pairs, insufficient_statistical_safety_evidence |
| baseline-research / corridor | 720 | 50 | 3 | 660.0 | 60.0 | 8 | False | 1.0000 | body_volume_exit_aircraft, no_admissible_aircraft_steps, protected_volume_breach_pairs, insufficient_statistical_safety_evidence |
| baseline-research / urban | 120 | 10 | 3 | 120.0 | 60.0 | 2 | False | 1.0000 | no_admissible_aircraft_steps, obstacle_collision_pairs, protected_volume_breach_pairs, insufficient_statistical_safety_evidence |
| baseline-research / urban | 120 | 50 | 3 | 120.0 | 60.0 | 2 | False | 1.0000 | no_admissible_aircraft_steps, obstacle_collision_pairs, protected_volume_breach_pairs, insufficient_statistical_safety_evidence |
| baseline-research / urban | 360 | 10 | 3 | 330.0 | 60.0 | 5 | False | 1.0000 | collision_pairs, no_admissible_aircraft_steps, obstacle_collision_pairs, protected_volume_breach_pairs, insufficient_statistical_safety_evidence |
| baseline-research / urban | 360 | 50 | 3 | 330.0 | 60.0 | 5 | False | 1.0000 | collision_pairs, no_admissible_aircraft_steps, obstacle_collision_pairs, protected_volume_breach_pairs, insufficient_statistical_safety_evidence |
| baseline-research / urban | 720 | 10 | 3 | 690.0 | 60.0 | 10 | False | 1.0000 | body_volume_exit_aircraft, collision_pairs, no_admissible_aircraft_steps, obstacle_collision_pairs, protected_volume_breach_pairs, insufficient_statistical_safety_evidence |
| baseline-research / urban | 720 | 50 | 3 | 690.0 | 60.0 | 11 | False | 1.0000 | body_volume_exit_aircraft, collision_pairs, no_admissible_aircraft_steps, obstacle_collision_pairs, protected_volume_breach_pairs, insufficient_statistical_safety_evidence |
| baseline-research / manned_intrusion | 120 | 10 | 3 | 120.0 | 60.0 | 2 | False | 1.0000 | no_admissible_aircraft_steps, protected_volume_breach_pairs, insufficient_statistical_safety_evidence |
| baseline-research / manned_intrusion | 120 | 50 | 3 | 120.0 | 60.0 | 2 | False | 1.0000 | no_admissible_aircraft_steps, protected_volume_breach_pairs, insufficient_statistical_safety_evidence |
| baseline-research / manned_intrusion | 360 | 10 | 3 | 330.0 | 60.0 | 5 | False | 1.0000 | collision_pairs, no_admissible_aircraft_steps, protected_volume_breach_pairs, insufficient_statistical_safety_evidence |
| baseline-research / manned_intrusion | 360 | 50 | 3 | 330.0 | 60.0 | 5 | False | 1.0000 | collision_pairs, no_admissible_aircraft_steps, protected_volume_breach_pairs, insufficient_statistical_safety_evidence |
| baseline-research / manned_intrusion | 720 | 10 | 3 | 690.0 | 60.0 | 10 | False | 1.0000 | body_volume_exit_aircraft, collision_pairs, no_admissible_aircraft_steps, protected_volume_breach_pairs, insufficient_statistical_safety_evidence |
| baseline-research / manned_intrusion | 720 | 50 | 3 | 690.0 | 60.0 | 10 | False | 1.0000 | body_volume_exit_aircraft, collision_pairs, no_admissible_aircraft_steps, protected_volume_breach_pairs, insufficient_statistical_safety_evidence |
| baseline-research / sensor_outage | 120 | 10 | 3 | 120.0 | 60.0 | 2 | False | 1.0000 | no_admissible_aircraft_steps, protected_volume_breach_pairs, insufficient_statistical_safety_evidence |
| baseline-research / sensor_outage | 120 | 50 | 3 | 120.0 | 60.0 | 2 | False | 1.0000 | no_admissible_aircraft_steps, protected_volume_breach_pairs, insufficient_statistical_safety_evidence |
| baseline-research / sensor_outage | 360 | 10 | 3 | 330.0 | 60.0 | 5 | False | 1.0000 | body_volume_exit_aircraft, collision_pairs, no_admissible_aircraft_steps, protected_volume_breach_pairs, insufficient_statistical_safety_evidence |
| baseline-research / sensor_outage | 360 | 50 | 3 | 330.0 | 60.0 | 5 | False | 1.0000 | body_volume_exit_aircraft, collision_pairs, no_admissible_aircraft_steps, protected_volume_breach_pairs, insufficient_statistical_safety_evidence |
| baseline-research / sensor_outage | 720 | 10 | 3 | 690.0 | 60.0 | 10 | False | 1.0000 | body_volume_exit_aircraft, collision_pairs, no_admissible_aircraft_steps, protected_volume_breach_pairs, insufficient_statistical_safety_evidence |
| baseline-research / sensor_outage | 720 | 50 | 3 | 690.0 | 60.0 | 10 | False | 1.0000 | body_volume_exit_aircraft, collision_pairs, no_admissible_aircraft_steps, protected_volume_breach_pairs, insufficient_statistical_safety_evidence |
| baseline-research / wind_gust | 120 | 10 | 3 | 120.0 | 60.0 | 2 | False | 1.0000 | kinematic_violation_aircraft_steps, no_admissible_aircraft_steps, protected_volume_breach_pairs, insufficient_statistical_safety_evidence |
| baseline-research / wind_gust | 120 | 50 | 3 | 120.0 | 60.0 | 2 | False | 1.0000 | kinematic_violation_aircraft_steps, no_admissible_aircraft_steps, protected_volume_breach_pairs, insufficient_statistical_safety_evidence |
| baseline-research / wind_gust | 360 | 10 | 3 | 330.0 | 60.0 | 5 | False | 1.0000 | body_volume_exit_aircraft, collision_pairs, kinematic_violation_aircraft_steps, no_admissible_aircraft_steps, protected_volume_breach_pairs, insufficient_statistical_safety_evidence |
| baseline-research / wind_gust | 360 | 50 | 3 | 330.0 | 60.0 | 5 | False | 1.0000 | body_volume_exit_aircraft, collision_pairs, kinematic_violation_aircraft_steps, no_admissible_aircraft_steps, protected_volume_breach_pairs, insufficient_statistical_safety_evidence |
| baseline-research / wind_gust | 720 | 10 | 3 | 690.0 | 60.0 | 9 | False | 1.0000 | collision_pairs, kinematic_violation_aircraft_steps, no_admissible_aircraft_steps, protected_volume_breach_pairs, insufficient_statistical_safety_evidence |
| baseline-research / wind_gust | 720 | 50 | 3 | 690.0 | 60.0 | 9 | False | 1.0000 | collision_pairs, kinematic_violation_aircraft_steps, no_admissible_aircraft_steps, protected_volume_breach_pairs, insufficient_statistical_safety_evidence |

- Null capacity means no positive demonstrated value; it does not establish that physical capacity is zero.
- No monotonicity assumption, binary search or interpolation between tested levels.
- Statistical bound concerns independent fixed-duration scenario runs, not failures per flight/hour.
- All supplied profiles are required; favorable scenarios cannot offset a failing profile.
- Finite windows and backlog checks do not establish long-run queue stability.
- Host timing and an explicit synthetic multiplier do not establish target hardware WCET.
- Manned traffic uses simplified bounded trajectories; wake, ATC, pilot and aircraft flight models are absent.
- Separation and surveillance thresholds are research inputs, not regulatory minima.
- No joint invariant safety proof, field validation, airworthiness or legal authorization.
