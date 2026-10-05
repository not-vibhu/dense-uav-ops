# Evidence index

Every set here is retained unchanged and validated against the source that produced it:

```bash
.venv/bin/python scripts/validate_evidence.py
```

Historical sets (v0.1–v0.4.1) were produced by code now in [`archive/`](../archive/README.md). Their own README files are part of their checksummed record and are left as written. Links in them to `../../docs/...` now resolve under `archive/docs-v0.4.1/`. Their claims should be read with the reanalysis in the [technical report](../docs/report/technical-report.md), which corrects or qualifies several of them.

| Set | Produced by | Runs | What it supports | What it does not support |
|---|---|---:|---|---|
| [`frontier-01`](frontier-01/README.md) | v0.5 engine | 360 | Shape of the safety–service frontier across assumed traffic acceleration, demand, latency and equipage in one geometry: worst-case assumptions congest without lowering attributable risk; constant-velocity prediction with fast replanning gave the best observed frontier | Precise rates (3 seeds per cell); other geometries; any real-world rate or capacity |
| [`frontier-02`](frontier-02/README.md) | v0.5 engine | 144 | The frontier-01 ordering survives traffic that wanders at up to 3 m/s² (violating constant-velocity assumptions); measured deviations over the replanning interval stay within the separation margin | Abrupt or adversarial maneuvers; long report ages; model mismatch; designed after seeing frontier-01 |
| [`iteration-01`](iteration-01/README.md) | `swarm_sim` v0.1 | 7,680 | Unmanaged traffic collides often at density; barrier-filter variants reduce run-level collisions while leaving the volume | Controller ranking (run-level indicator saturates; exits confounded with density); safety of any controller |
| [`iteration-02`](iteration-02/README.md) | `swarm_sim` v0.2 | 1,184 | The maneuver library preserves the volume better than the barrier filter; the preference search found no improvement on the default weights | Learning gains; stable rankings (one holdout seed per stratum) |
| [`iteration-03`](iteration-03/README.md) | `swarm_sim` v0.3 | 948 | Imitation/MAPPO pipelines run; no consistent gain over the planner they imitate; failed-library fraction rises steeply with fleet size under worst-case assumptions | Any learned safety improvement; admission effects at matched service |
| [`capacity-01`](capacity-01/README.md) | `airspace_capacity` v0.3 | 179 | With 50 % uncontrolled UAS and a manned transit crossing the whole UAS altitude band, protected-distance breaches occur in every shared-airspace run (516 of 526 breach pairs involve the manned aircraft) | A capacity of the coordination system (failures are dominated by traffic it does not control); timing results (host load affected outcomes) |
| [`distributed-04`](distributed-04/README.md) | `dense_ops` v0.4.0 | 196 | Per-aircraft surveillance stores, signed records and DAIDALUS integration ran end to end | "All runs failed" as a safety finding: density windows (8 s) were shorter than any traversal (≥ 18.5 s), and zero-tolerance per-step gates failed nearly every run |
| [`readiness-04`](readiness-04/README.md) | `dense_ops` v0.4.0 → v0.4.1 | 24 | Requiring a fresh surveillance frame before entry removed controlled exposure under 2 s telemetry delay by holding all 20 requests | Any safety improvement at equal service |
| [`excluded-preliminary`](excluded-preliminary/README.md) | development builds | — | Transparency: runs excluded from the sets above, with reasons | Anything; never pool with results |

Each `frontier-*` set records its full specification, the simulation-core digest, and every run's configuration and outcomes. `dense-uav-ops validate <dir> --rerun N` re-simulates runs and requires exact reproduction.
