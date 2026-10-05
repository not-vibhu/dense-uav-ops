# Mixed fleet safety comparison

Completed **7680 / 7680** reproducible runs. Fleet sizes: [10, 50, 100, 200]; cooperative fractions: [0, 0.1, 0.5, 0.9, 1]; fixed-wing fraction: 0.4. Every catalog scenario was evaluated only if listed in the manifest.

Discovery choice: **barrier**. Stable on holdout: **False**. Empirical safety gate passed: **False**.

The gate requires zero participating-aircraft collisions, zero obstacle collisions, zero volume exits, zero unresolved filter steps, zero vehicle-limit violations, and at least 70% participating goal reach on holdout. A gate pass would still be a finite-suite result, not a flight safety proof.

## Holdout results

| Controller | Collision runs | Obstacle runs | Volume exit runs | Separation exposure | Goal reach | Unresolved filter steps |
|---|---:|---:|---:|---:|---:|---:|
| negotiated | 39.1% | 7.6% | 82.4% | 0.02% | 26.4% | 6284244 |
| barrier | 39.3% | 7.4% | 82.4% | 0.02% | 26.2% | 6283900 |
| repulsion | 62.6% | 9.5% | 57.6% | 0.08% | 97.7% | 0 |
| goal | 73.2% | 10.8% | 6.0% | 0.18% | 99.3% | 0 |

Collision run rates count encounters involving at least one equipped participant. Legacy–legacy collision pairs are published separately and are not attributed to control authority the system does not have. Zero-cooperation runs are included in raw results but excluded from controller ranking.

Separation exposure is the fraction of active participating pair-time steps whose continuous swept trajectory crossed the 10 m boundary. A touched step counts its entire duration, so this is an upper step-based exposure measure. Collision thresholds use the sum of physical radii. Minimum distance away from threat thresholds is a conservative chord lower bound.

## Interpretation

**No configuration cleared the safety gate.** The discovery choice is a lower-risk research candidate under the published lexicographic ordering, not a deployment recommendation. Inspect failed scenarios and unresolved constraints; lower demand, better sensing, route redesign and admission control may be required.

## Coverage and provenance

Discovery seeds: [0, 1]; holdout seeds: [1001, 1002]. Step: 0.2 s; encounter duration: 36 s. Source SHA-256: `a7037124a2ea7b9b8d89160d7a60be07f46adc9f0f828b66dab082e3fdc5ccf9`.

The simulator uses a common synthetic regional feed, approximate finite-projection barriers, idealized mixed point-mass dynamics and absorbing goals. It does not implement authenticated ASTM messaging, an exact ORCA or QP solver, verified backup invariance, RF propagation, impact/wreckage physics, or aircraft aerodynamic certification. Intentional out-of-bounds faults are separated in summary.json. No MARL policy is trained in this release.

See manifest.json, runs.jsonl, results.json and summary.json for every configuration and outcome. Reported timing is measured on this host, includes Python overhead, and cannot establish an onboard real-time deadline.

Goal reach is a kinematic diagnostic fraction; paths continue after collisions without impact physics. It is not a successful real mission-completion rate.
