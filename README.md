# Federated swarm

An open-source architecture for real-time tactical deconfliction of dense, low-altitude UAS traffic using Network and Direct Remote ID observations. Cooperative aircraft negotiate efficient maneuvers; broadcast-only aircraft are modeled as independently moving obstacles. Every participating aircraft retains local authority to reject an unsafe maneuver.

**Status:** architecture and runnable research simulator, dated 3 October 2026. The simulator compares mixed multirotor/fixed-wing traffic and records measured simulation outcomes. Aircraft dynamics, telemetry, controller thresholds and timing remain unvalidated operational assumptions; there is no certified flight implementation.

The core design is a federated USS discovery layer, regional telemetry fusion, a bounded maneuver-negotiation protocol, and an onboard deterministic safety controller. Safety depends on observed traffic, bounded uncertainty, sufficient maneuver authority, and continued controller feasibility. Adoption by every aircraft is unnecessary; collision freedom for two aircraft that neither participate nor respond cannot be guaranteed by this system. Remote ID alone cannot guarantee detection or truthful position reports.

## Run the simulation lab

From this repository directory:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install 'numpy>=2.0,<3'
.venv/bin/python -m swarm_sim serve
```

Open [the local simulation lab](http://127.0.0.1:8765). Choose a scenario, 10–500 aircraft, cooperative/fixed-wing proportions and controller, then run and replay the encounter. The simulator uses 3D constant-acceleration motion and a continuous swept collision checker; the display interpolates recorded frames.

Run the full comparison, including all 27 catalog scenarios and holdout seeds:

```bash
.venv/bin/python -m swarm_sim compare --out artifacts/predictive-campaign
.venv/bin/python -m unittest discover -s tests -v
```

The current default matrix is 10,800 runs: fleet sizes 10/50/100/200, five cooperation fractions, five controllers, and four seeds split between discovery and holdout. The original four-controller campaign contained 7,680 runs and remains preserved separately. Outputs include every run, a manifest, rankings and an interactive report. Failed safety gates prevent a deployment recommendation. See the [simulation guide](docs/simulation.md) for model coverage, ranking and repeatable commands.

The new `predictive` controller evaluates vehicle-feasible maneuver rollouts against reported traffic uncertainty, obstacles and volume boundaries. `evolved` uses the same checker with preferences learned through cross-entropy search. Both explicitly count failed maneuver libraries; neither has a proven joint invariant traffic backup. See the [policy development guide](docs/learning-policy.md) for training, independent evaluation and the path toward shielded reinforcement learning.

```bash
.venv/bin/python -m swarm_sim learn --out artifacts/policy-search/preferences.json
.venv/bin/python -m swarm_sim run --controller evolved \
  --policy profiles/predictive-preferences.json --drones 100 \
  --seed 3001 --out artifacts/evolved-replay.json
```

## Next development sequence: learning with admission

The recurrent actor selects among checked maneuver primitives. The critic uses global simulator state only during training. Queue and route rejection are reported against requested demand; a zero-collision outcome with withheld traffic cannot pass the empirical gate.

```bash
.venv/bin/python -m pip install -e '.[learning]'
.venv/bin/python -m swarm_sim train-imitation --epochs 12 --out models/imitation.json
.venv/bin/python -m swarm_sim train-mappo --initial models/imitation.json --out models/mappo.json
.venv/bin/python -m swarm_sim run --controller mappo --checkpoint models/mappo.json \
  --admission checked --admission-limit 40 --routes visibility --drones 50 --seed 6000
```

The [948-run development decision](experiments/iteration-03/README.md) found no empirical gate pass or consistent learning gain. Checked admission reduced observed density-test collisions while withholding/delaying demand; goal reach and timing remain inadequate.

See [the implementation and assurance scope](docs/third-iteration.md) before interpreting a backup certificate or comparing the learned policies. The default finite horizon does not establish a robust terminal hover for every multirotor, and fixed-wing backups remain finite-horizon turns.

## Documents

| Document | Contents |
|---|---|
| [Architecture](docs/architecture.md) | Standards, topology, algorithms, deterministic bounds, and audit design |
| [Negotiation protocol](docs/protocol.md) | Messages, deadlines, partial delivery, ownership, and degraded operation |
| [Safety case](docs/safety-case.md) | Equations, assumptions, detection range example, and proof obligations |
| [Verification plan](docs/verification.md) | Formal modeling, simulation, hardware tests, and acceptance evidence |
| [Sources and integration pins](docs/sources.md) | Primary references and locally inspected upstream revisions |
| [Simulation profile](profiles/simulation-example.json) | Explicitly unvalidated example parameters |
| [Simulation guide](docs/simulation.md) | Running, replaying and comparing the implemented research models |
| [Initial comparison decision](docs/initial-comparison.md) | Observed results from the completed 7,680-run mixed-fleet campaign |
| [Policy development](docs/learning-policy.md) | Predictive planning, evolutionary optimization and the proposed shielded MARL design |
| [Admission and recurrent learning](docs/third-iteration.md) | Implemented pipeline, mathematical bounds, training and evaluation scope |
| [Predictive iteration decision](docs/second-iteration.md) | Independent catalog results, learning outcome, limitations and next safety work |

Read the architecture first, then the safety case before implementing adapters or controllers. ASTM conformance tests and tactical safety validation are separate acceptance gates.

## Proposed implementation boundaries

- `rid-adapter`: F3411 service discovery and observation ingestion.
- `direct-rid-gateway`: OpenDroneID decoder and receiver provenance.
- `track-fusion`: timestamp handling, association, hard uncertainty sets, and sensor health.
- `tactical-broker`: conflict neighborhoods, signed proposals, fairness, and bounded rounds.
- `aircraft-agent`: local planning, proposal verification, and controller interface.
- `safety-kernel`: robust reachability, control barriers, watchdog, and backup controller.
- `audit-recorder` and `audit-verifier`: signed evidence, witnessed checkpoints, and replay.

These are proposed production services. The `swarm_sim` package implements an exploratory deterministic harness, synthetic telemetry, heuristic/barrier controllers, negotiation emulation, a predictive maneuver library and evolutionary preference optimization. Version 0.3 also implements pre-entry admission, static obstacle routing, independently checked finite backups, a limited static multirotor hover bound, recurrent imitation and masked MAPPO training. It does not implement the full signed production protocol, exact QP/ORCA, DAIDALUS integration or a flight-validated invariant mixed-fleet safety controller.

## License

The repository is licensed under the [MIT License](LICENSE). Third-party standards and software retain their own licenses. ASTM text is not redistributed; an implementation must obtain the applicable standard and independently establish its compliance.
