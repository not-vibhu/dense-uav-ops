# Surveillance-readiness correction, v0.4.1

This 24-evaluation followup preserves both source versions and uses paired seeds 8800/8801, separate from the seeds that exposed the admission defect. Each phase has 12 runs: three scenarios, local/federated modes, two seeds, 10 mixed UAS and one exogenous manned aircraft. Both phases failed the full operational requirements in every run; no capacity or safest architecture is established.

Previously, warmup elapsed before two-second-delayed telemetry arrived, allowing admission without usable traffic input. The correction requires a delivered frame with an upper source age within configurable `max_surveillance_age`, including the declared clock error. The default one second is a research condition. A fresh frame is necessary for readiness, not proof of complete coverage, truthful reports or recursively feasible airborne recovery.

| Scenario, four runs per phase | Controlled requests | Admitted before → after | Completed before → after | Runs with controlled separation breaches before → after |
|---|---:|---:|---:|---:|
| Two-second stale telemetry | 20 | 20 → 0 | 14 → 0 | 4 → 0 |
| Feed outage | 20 | 16 → 16 | 0 → 0 | 0 → 0 |
| Head-on nominal links | 20 | 14 → 14 | 0 → 0 | 2 → 2 |

Neither phase recorded a controlled-aircraft collision on these paired seeds. The stale-telemetry correction removed controlled exposure by holding all 20 requests; the service loss remains a failure. This is a regression fix with a demonstrated admission tradeoff, not evidence of safe high-density throughput. Head-on breaches and recovery/service failures remain unresolved.

`DEFER_ENTRY` records the missing/stale readiness condition. The regression suite has 98 passing tests, including a known-defect seed that now admits no cooperative aircraft under two-second delay, delivered empty-frame readiness, stale-frame rejection and clock-bound checks. [tests.log](tests.log) preserves that run. The separate [196-run baseline](../distributed-04/README.md) includes all 27 catalog scenarios and larger-fleet stress tests; those results describe the earlier version, not a full catalog qualification of v0.4.1.

[assessment.json](assessment.json), each phase's signed compressed runs, manifests, summaries, checkpoints and flight reconstructions retain the complete comparison. `source-before.tar.gz` and `source-after.tar.gz` allow validation after future implementation changes. The after-phase graph checkpoint was retrained and pinned to the corrected source; it was not used for these local/federated evaluations. Its synthetic training data and round history are retained, and no learning safety gain is claimed.

```bash
.venv/bin/python -m scripts.validate_readiness_evidence experiments/readiness-04
.venv/bin/python -m scripts.run_readiness_followup --baseline experiments/distributed-04 --out artifacts/readiness-reproduction
```

The retained model describes point-mass vehicles with idealized own state and metadata, synthetic telemetry, finite-horizon traffic checking and finite fixed-wing turns. It excludes real RF coverage, authenticated navigation truth, wake, pilot/ATC behavior, landing/impact dynamics and target-hardware WCET. Signed reconstruction checks declared controls against that plant; it does not validate real aircraft truth. Prioritize robust fixed-wing escape/loiter, structured crossing routes and complete federated certificate execution before expanding RL or claiming operational capacity.
