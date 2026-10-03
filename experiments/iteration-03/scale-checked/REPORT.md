# Mixed fleet safety comparison

Completed **24 / 24** reproducible runs. Fleet sizes: [100, 200]; cooperative fractions: [0.5]; fixed-wing fraction: 0.4. Every catalog scenario was evaluated only if listed in the manifest.

Discovery choice: **mappo**. Stable on holdout: **False**. Empirical safety gate passed: **False**.

The gate requires zero participating-aircraft collisions, zero obstacle collisions, zero volume exits, zero unresolved barrier steps or failed predictive libraries, zero vehicle-limit violations, zero unavailable-backup steps, zero observed command deadline misses, at least 70% admission and at least 70% participating goal reach on holdout. Requested demand is the denominator. A gate pass would still be a finite-suite result, not a flight safety proof.

## Holdout results

| Controller | Collision runs | Obstacle runs | Volume exit runs | Separation exposure | Goal reach | Unresolved control steps |
|---|---:|---:|---:|---:|---:|---:|
| imitation | 0.0% | 0.0% | 0.0% | 0.00% | 23.8% | 4257 |
| mappo | 0.0% | 0.0% | 0.0% | 0.00% | 23.2% | 4399 |
| predictive | 0.0% | 0.0% | 25.0% | 0.00% | 27.0% | 4621 |

## Service and backup availability

Admission: checked; capacity: 120; routes: visibility.

| Controller | Admitted / requested | Queued | Route rejected | Backup unavailable steps | Deadline-miss runs | Mean fleet p99 ms |
|---|---:|---:|---:|---:|---:|---:|
| imitation | 78.5% | 73 | 0 | 4247 | 4 | 359.40 |
| mappo | 79.5% | 74 | 0 | 4390 | 4 | 328.81 |
| predictive | 79.8% | 72 | 0 | 4605 | 4 | 335.87 |

Collision run rates count encounters involving at least one equipped participant. Legacy–legacy collision pairs are published separately and are not attributed to control authority the system does not have. Zero-cooperation runs are included in raw results but excluded from controller ranking.

Separation exposure is the fraction of active participating pair-time steps whose continuous swept trajectory crossed the 10 m boundary. A touched step counts its entire duration, so this is an upper step-based exposure measure. Collision thresholds use the sum of physical radii. Minimum distance away from threat thresholds is a conservative chord lower bound.

## Interpretation

**No configuration cleared the safety gate.** The discovery choice is a lower-risk research candidate under the published lexicographic ordering, not a deployment recommendation. Inspect failed scenarios and unresolved constraints; lower demand, better sensing, route redesign and admission control may be required.

## Coverage and provenance

Discovery seeds: [5000]; holdout seeds: [6000]. Step: 0.2 s; encounter duration: 36.0 s. Source SHA-256: `454b8cdae5ed609fa46bcc6e4908c4675f5adefc04e1d759d867fb8e436d953e`.

The simulator uses a common synthetic regional feed, approximate finite-projection barriers, idealized mixed point-mass dynamics and absorbing goals. It does not implement authenticated ASTM messaging, an exact ORCA or QP solver, joint invariant traffic safety, RF propagation, impact/wreckage physics, or aircraft aerodynamic certification. Intentional out-of-bounds faults are separated in summary.json. Optional recurrent imitation and masked MAPPO policies are trained separately and pinned in the manifest when evaluated. Admission and static routes report unserved demand. Checked backups cover finite traffic envelopes; the limited static hover bound is not a mixed-fleet invariance proof. Goal reach includes diagnostic trajectories continuing after collisions and is not a successful real mission rate.

See manifest.json, runs.jsonl, results.json and summary.json for every configuration and outcome. Reported timing is measured on this host, includes Python overhead, and cannot establish an onboard real-time deadline.
