# First mixed-traffic airspace capacity assessment

The capacity metric completed **179 published evaluations**. No operating point met the statistical evidence gate, and no operational capacity was established. A hypothetical layered corridor passed observed requirements at **120 UAS requests plus 60 manned transits/hour**, for **180 total offered operations/hour**. That passing cell contains three independent seeds and insufficient statistical evidence. It is not a certified safe limit or a demonstrated universal maximum.

The shared-airspace baseline, degraded-surveillance envelope and density cases did not demonstrate a positive capacity under their declared requirements. Null capacity does not mean physical capacity is zero.

| Campaign | Runs | Required conditions | UAS demand/hour | Occupancy admission limits | Observed passing cells |
|---|---:|---|---|---|---:|
| [Baseline](baseline/REPORT.md) | 108 | Crossing, corridor, urban obstacle, manned lateral intrusion, sensor outage, wind gust | 120, 360, 720 | 10, 50 | 0 / 36 |
| [Degraded surveillance](sensitivity/REPORT.md) | 54 | Crossing, urban, sensor outage; poorer accuracy, longer latency/loss, lower conformance/cooperation and actuator lag | 120, 360, 720 | 10, 50 | 0 / 18 |
| [Density](density/REPORT.md) | 8 | Shared crossing; 220 m square; helicopter background | 3,600, 10,800 | 50, 200 | 0 / 4 |
| [Layered corridor](layered/REPORT.md) | 9 | One-direction UAS corridor at 24–36 m, light fixed-wing manned transit at 120 m; 300 m square | 120, 360, 720 | 10 | 1 / 3 |

Each scenario cell uses seeds 7000–7002, except density uses 7000–7001. The same seeds across cells form paired comparisons, not additional independent evidence within a cell. Every complete cell and raw run is retained. The layered campaign was exercised through the final lab interface; repeated UI checks are not pooled into the statistical sample size.

These are development seeds, not an independent held-out qualification campaign. The layered profile was explored after observing shared-airspace failures. Its bounds are diagnostic calculations for the declared fixed grid, not selection-adjusted assurance across adaptive profile development. Any later qualification requires new independent validation evidence and an error budget covering the planned selection procedure.

Baseline and sensitivity use 40 s warmup, 120 s measurement and 60 s drainage. Density uses 20/60/40 s. Every profile uses dt = 0.2 s. Manned background is 60 requests/hour. The base mix has 40% fixed-wing UAS, 50% cooperation and 95% modeled behavioral conformance; sensitivity uses 20% cooperation and 70% conformance. These are hypothetical conditions, not measurements of an operational fleet. The layered example uses 100% modeled conformance while retaining 50% cooperation and 40% fixed-wing UAS.

## Findings

The baseline observed physical collisions in 32 of 108 runs and protected-distance breaches in all 108. Completing a traversal and avoiding physical contact therefore cannot substitute for the full safety gate. No passing baseline operating point was hidden by averaging scenarios.

All eight density runs observed physical collisions. At 10,800 UAS requests/hour, the achieved peak was **122 concurrent aircraft** in the occupancy-limit-200 runs. The limit-50 cases still reached peaks of 58 and 62 because uncontrolled traffic bypasses managed admission. That overflow blocks the gate and demonstrates why an admission quota alone cannot establish mixed-equipage capacity.

For the limit-200 density runs, maximum measured command times were approximately **269 and 310 ms** against a 200 ms deadline, with 221 and 306 missed ticks. Their UAS cohort completion fractions were approximately 72% and 77%, below the specified 95%. These are measurements of this executing host and prototype, not calibrated target-hardware worst-case times.

The layered corridor's 120 UAS/hour cell completed its measurement cohorts and passed observed checks across three seeds. Its worst measured total exit rate was 180 operations/hour and peak combined occupancy was two aircraft. The 360 UAS/hour cell failed maneuver feasibility in one seed. The 720 UAS/hour cell failed feasibility, body-volume, backlog or occupancy checks. Keeping altitude bands separate improved this hypothetical case without making a higher-density claim.

The layered cell's simultaneous one-sided upper modeled run-failure probability is **74.46%**, compared with its example 1% target. Its three-cell search would require at least **408 zero-failure independent runs per cell** to meet that target at 95% family-wise confidence. The baseline search would require 655 zero-failure runs per cell. These probability units refer to complete fixed-duration research runs; they are not operational failure probabilities per flight or flight-hour.

The [metric guide](../../docs/airspace-capacity.md) defines parameters, gates, units and limitations. Entry/exit buffers, landing, wake turbulence, realistic manned dynamics, ATC/human behavior, legal authorization and a joint invariant safety proof are outside the assessed model. Periodic phased demand and finite windows do not establish long-run capacity or exhaustive scenario coverage.

## Evidence and reproduction

Each campaign directory contains the exact manifest, all raw `runs.jsonl` records, a JSON summary and a readable report. The combined capacity/simulator source SHA-256 is:

```
da850e5693e083ec1378bd61b720c680a56f36fce6dcb54f7b2a4925238540da
```

`source.tar.gz` preserves the corresponding Python modules, `environment.txt` records the runtime, `tests.txt` records **67 passing tests**, `checksums.json` pins the evidence files, and `lab.png` shows the verified final interface. The existing batch simulator and pretrained models retain their previous source pin and are not reused as capacity evidence.

```bash
.venv/bin/python experiments/capacity-01/validate.py
sh experiments/capacity-01/reproduce.sh artifacts/new-capacity-reproduction
.venv/bin/python -m airspace_capacity --serve --out artifacts/capacity-lab
```

The validator reconstructs summaries from raw complete grids and verifies current source/evidence hashes. Reproduction preserves conditions and seeds; host timing and watchdog outcomes can differ. Checksums are tamper-evident only against a trusted reference, not signed or independently witnessed audit records.
