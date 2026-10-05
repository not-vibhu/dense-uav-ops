# Archive: v0.1–v0.4.1 code and documents

Version 0.5 replaced three overlapping simulators with one engine. This directory keeps the retired material so earlier results stay inspectable and reproducible. Nothing here is maintained.

## Contents

| Item | What it is |
|---|---|
| [`dense-uav-ops-v0.4.1-source.tar.gz`](dense-uav-ops-v0.4.1-source.tar.gz) | The full source tree at commit `dddfc00` (v0.4.1). It contains `swarm_sim`, `airspace_capacity`, `dense_ops`, scripts, profiles, tests and docs, but not `experiments/` or `models/`, which remain in the repository. Created with `git archive`. |
| [`docs-v0.4.1/`](docs-v0.4.1) | The v0.4.1 README and documents: architecture, protocol, safety case, verification plan, simulation guide, iteration decisions, capacity metric, NASA study, sources. |

The trained v0.3 checkpoints moved to [`experiments/iteration-03/models/`](../experiments/iteration-03/models) beside the evidence that used them.

## Why each part was retired

| Retired | Reason | Where its ideas went |
|---|---|---|
| Three simulators (`swarm_sim`, `airspace_capacity`, `dense_ops`) | Shared one plant but used different defaults, metrics and gates, so their results could not be compared. Each was frozen by a source checksum asserted in a test, so it could not be improved. | One engine, [`dense_uav_ops`](../dense_uav_ops). Historical evidence is validated against the archived source, not the current code. |
| Host wall-clock time feeding back into outcomes (`airspace_capacity`, `dense_ops`) | Results depended on laptop load and could not be reproduced elsewhere. | Timing faults are a seeded model parameter. Compute cost is reported separately. |
| Barrier, repulsion and negotiation-emulation controllers | The barrier filter was a finite projection rather than a solved robust program, and evidence showed its lower collision rate came with near-universal volume exits at 50+ aircraft. Negotiation was an emulation without a protocol. | The maneuver-library planner and DAIDALUS as baselines. Coordination returns as an assumption-contract experiment ([roadmap](../docs/roadmap.md)). |
| Signed audit journal, certificate negotiator and bounded protocol exploration (`dense_ops/audit.py`, `federation.py`, `modelcheck.py`) | Working and tested, but orthogonal to the safety–capacity question and not connected to control. The "model check" enumerated 624 cases in Python, not a model checker. | Kept here for reuse as a possible transport for coordination contracts. |
| Two local browser labs | Two web UIs to maintain for exploratory use. | A static HTML replay generated from any run (`dense-uav-ops run --replay`). |
| Production-architecture documents (architecture, protocol, safety case, verification plan) | Careful prose, but describes F3411/F3548/Flight Blender integration, Merkle logs and an optimisation-based shield that do not exist in code, mixed with implemented features. | The research question, model and roadmap documents state what exists. These documents remain useful design background. |
| Run-level pass/fail gates with zero tolerance on per-step counters | Near-certain to fail in any non-trivial run (e.g. any one-step unseen aircraft), so "all runs failed" carried little information. | Rates with exposure, intervals and attribution. |

## Running archived code

```bash
mkdir -p /tmp/v041 && tar -xzf archive/dense-uav-ops-v0.4.1-source.tar.gz -C /tmp/v041
cd /tmp/v041/dense-uav-ops-v0.4.1
python3 -m venv .venv && .venv/bin/python -m pip install 'numpy>=2,<3' 'cryptography>=43,<48' 'torch>=2.6,<3'
.venv/bin/python -m unittest discover -s tests
```

Each historical evidence set also carries the exact source that produced it, and [`scripts/validate_evidence.py`](../scripts/validate_evidence.py) validates every set against that source. The v0.4.1 documents link to `../experiments/...` and to each other with their original relative paths; inside `docs-v0.4.1/` the links between documents still work, but links to `experiments/` need one more `../`.
