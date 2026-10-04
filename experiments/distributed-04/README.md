# Distributed development baseline, v0.4.0

The complete 196-evaluation grid establishes no operational capacity and selects no safest architecture. All 196 runs failed at least one safety, service, surveillance, feasibility or timing requirement. This is a frozen development baseline preceding the v0.4.1 surveillance-readiness correction, not a qualification of the current source.

| Study | Runs | Runs with collisions | Runs with controlled-aircraft collisions | Runs with controlled-aircraft separation breaches | Peak occupancy |
|---|---:|---:|---:|---:|---:|
| All 27 catalog scenarios | 108 | 4 | 2 | 8 | 11 |
| Matched guard comparison | 32 | 0 | 0 | 4 | 10 |
| Graph-policy comparison | 32 | 4 | 0 | 4 | 10 |
| 50/100/200/500 UAS stress | 16 | 6 | 0 | 0 | 274 |
| Compound partition/clock/faults | 8 | 2 | 0 | 2 | 10 |

The reconstructed categories distinguish an event involving at least one controlled aircraft from an event involving only exogenous traffic. Manned involvement is recorded separately and can overlap either category. A global protection failure still fails the gate even if the participating aircraft were uninvolved. No controlled collision in a stress window cannot establish mission safety or capacity.

Some conditions recur across the catalog and matched-comparison studies. These are 196 evaluations, not 196 distinct independent environments. Seed-matched comparisons share conditions deliberately; confidence bounds are computed within each study's cells and are not pooled across repeated conditions.

In the matched guard comparison, the reference completed 16 of 80 controlled requests and had four runs with controlled separation breaches. Checked continuations completed 0 of 80 and had none of those breaches. Neither passed the full gate. The observation describes a safety/service tradeoff; it does not establish statistical dominance.

In the graph comparison, each architecture completed 2 of 40 controlled requests and had one run with a controlled separation breach. The four collision runs involved exogenous traffic. The attention graph and federated training provide executable research capabilities; this grid shows no observed aggregate service or safety gain over deterministic ranking. Across three offline domains, tuning loss declined from approximately 2.14–2.16 to 1.62–1.67 after three accepted rounds. Tuning loss is not a safety metric, and tuning seeds are excluded from evaluation.

The catalog's controlled collisions occurred with two-second telemetry delay: admission proceeded before usable observation frames arrived. The [readiness followup](../readiness-04/README.md) addresses that defect with a source-age gate and independent paired evaluation. Other unresolved blockers include absent or stale traffic, fixed-wing recovery feasibility, containment, actuator assumptions, deadline misses, and incomplete requested missions.

Native DAIDALUS was built at the pin in [nasa.json](nasa.json). Its four reference snapshots returned alert levels 3, 0, 0 and 3. The upstream DO-365B configuration is used for comparison, not dense-UAS operating minima. ICAROUS source informed the architecture; a complete ICAROUS runtime was not executed. [protocol.json](protocol.json) records 624 bounded protocol cases without a violated assertion, not an unbounded proof or a continuous-flight guarantee.

Inspect [assessment.json](assessment.json), each study's manifest/summary/report, compressed signed runs and `flight-reconstruction.json`. The latter reconstructs the archived simulation plant from signed applied controls and reconciles physical outcomes using the same continuous geometry definitions. It does not reconstruct every observation or feasibility decision. Public registries and signed checkpoints are retained separately. The simulated witness runs in the same process; independent external witnesses remain required for production.

[graph-model.json](graph-model.json) is source-pinned to this baseline; [graph-data.json](graph-data.json) retains the synthetic training and tuning samples. [source.tar.gz](source.tar.gz) retains the corresponding implementation and scripts. [environment.json](environment.json) records dependencies, compiler and platform. Fleet timings came from a shared host with two campaign workers and other development activity; they are not onboard WCET. Eight-second density windows assess stress, while mission and fault windows last 36 seconds.

```bash
# From the repository, using the existing virtual environment:
.venv/bin/python -m scripts.validate_distributed_evidence experiments/distributed-04
# Optional complete physical-flight reconstruction from retained source:
.venv/bin/python -m scripts.validate_distributed_evidence experiments/distributed-04 --flight
# Recreate the declared grid using current code and a newly trained checkpoint:
.venv/bin/python -m dense_ops train-federated --out artifacts/reproduction-04/model.json --rounds 3
.venv/bin/python -m scripts.run_distributed_study --checkpoint artifacts/reproduction-04/model.json --out artifacts/reproduction-04/study
```

Reproducing the historical version requires extracting its source archive and using the recorded environment. Ephemeral signing keys and host timings prevent byte-identical newly generated logs. Earlier incomplete development runs were abandoned after a process-launch defect and unused-reference-work timing flaw; they were not included in this source-frozen grid.

The [offline replay](replay.html) and [screenshot](replay.jpg) show one baseline crossing encounter, its incomplete missions and failed requirements. The new engine is a CLI research layer; the original interactive labs and continuous-arrival capacity estimator remain v0.3. Next priorities are robust fixed-wing escape/loiter sets, structured routes, end-to-end certificate execution, validated surveillance and hardware, and continuous-arrival capacity integration.
