# Airspace capacity assessment

Highest tested demand passing observed requirements: **120** UAS operations/hour.
Statistically supported tested demand: **not demonstrated** UAS operations/hour.
Operationally certified capacity: **not established**.

| Profile / scenario | UAS demand/h | Occupancy limit | Runs | UAS exits/h (worst) | Manned exits/h (worst) | Peak total | Observed pass | Failure upper bound | Blocking requirements |
|---|---:|---:|---:|---:|---:|---:|---|---:|---|
| layered-corridor-research / corridor | 120 | 10 | 3 | 120.0 | 60.0 | 2 | True | 0.7446 | insufficient_statistical_safety_evidence |
| layered-corridor-research / corridor | 360 | 10 | 3 | 330.0 | 60.0 | 5 | False | 0.9235 | no_admissible_aircraft_steps, insufficient_statistical_safety_evidence |
| layered-corridor-research / corridor | 720 | 10 | 3 | 600.0 | 60.0 | 11 | False | 1.0000 | backlog_growth_requirement, body_volume_exit_aircraft, no_admissible_aircraft_steps, occupancy_overflow_steps, insufficient_statistical_safety_evidence |

- Null capacity means no positive demonstrated value; it does not establish that physical capacity is zero.
- No monotonicity assumption, binary search or interpolation between tested levels.
- Statistical bound concerns independent fixed-duration scenario runs, not failures per flight/hour.
- All supplied profiles are required; favorable scenarios cannot offset a failing profile.
- Finite windows and backlog checks do not establish long-run queue stability.
- Host timing and an explicit synthetic multiplier do not establish target hardware WCET.
- Manned traffic uses simplified bounded trajectories; wake, ATC, pilot and aircraft flight models are absent.
- Separation and surveillance thresholds are research inputs, not regulatory minima.
- No joint invariant safety proof, field validation, airworthiness or legal authorization.
