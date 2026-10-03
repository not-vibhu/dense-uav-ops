# Airspace capacity assessment

Highest tested demand passing observed requirements: **not demonstrated** UAS operations/hour.
Statistically supported tested demand: **not demonstrated** UAS operations/hour.
Operationally certified capacity: **not established**.

| Profile / scenario | UAS demand/h | Occupancy limit | Runs | UAS exits/h (worst) | Manned exits/h (worst) | Peak total | Observed pass | Failure upper bound | Blocking requirements |
|---|---:|---:|---:|---:|---:|---:|---|---:|---|
| density-research / crossing | 3600 | 50 | 2 | 2820.0 | 60.0 | 34 | False | 1.0000 | backlog_growth_requirement, body_volume_exit_aircraft, collision_pairs, no_admissible_aircraft_steps, protected_volume_breach_pairs, insufficient_statistical_safety_evidence |
| density-research / crossing | 3600 | 200 | 2 | 2820.0 | 60.0 | 34 | False | 1.0000 | backlog_growth_requirement, body_volume_exit_aircraft, collision_pairs, no_admissible_aircraft_steps, protected_volume_breach_pairs, insufficient_statistical_safety_evidence |
| density-research / crossing | 10800 | 50 | 2 | 5940.0 | 60.0 | 62 | False | 1.0000 | backlog_growth_requirement, body_volume_exit_aircraft, collision_pairs, command_deadline_misses, kinematic_violation_aircraft_steps, no_admissible_aircraft_steps, occupancy_overflow_steps, protected_volume_breach_pairs, queue_wait_requirement, uas_completion_requirement, insufficient_statistical_safety_evidence |
| density-research / crossing | 10800 | 200 | 2 | 7080.0 | 60.0 | 122 | False | 1.0000 | backlog_growth_requirement, body_volume_exit_aircraft, collision_pairs, command_deadline_misses, kinematic_violation_aircraft_steps, no_admissible_aircraft_steps, protected_volume_breach_pairs, uas_completion_requirement, insufficient_statistical_safety_evidence |

- Null capacity means no positive demonstrated value; it does not establish that physical capacity is zero.
- No monotonicity assumption, binary search or interpolation between tested levels.
- Statistical bound concerns independent fixed-duration scenario runs, not failures per flight/hour.
- All supplied profiles are required; favorable scenarios cannot offset a failing profile.
- Finite windows and backlog checks do not establish long-run queue stability.
- Host timing and an explicit synthetic multiplier do not establish target hardware WCET.
- Manned traffic uses simplified bounded trajectories; wake, ATC, pilot and aircraft flight models are absent.
- Separation and surveillance thresholds are research inputs, not regulatory minima.
- No joint invariant safety proof, field validation, airworthiness or legal authorization.
