# Mixed fleet simulation and controller comparison

The implementation is a reproducible research harness, with a browser replay and a batch comparison CLI. It tests 10–500 aircraft in a 220 × 220 m operating volume, altitudes 12–116 m, and an adjustable mixture of multirotors and fixed-wing aircraft. The current default campaign destination is `artifacts/predictive-campaign`; the original completed campaign remains under `artifacts/full-campaign`. Generated recordings are excluded from Git.

Runtime defaults are defined in `swarm_sim/config.py`. The earlier `profiles/simulation-example.json` records production-design assumptions and incomplete proof inputs; it is not loaded as the simulator configuration. In particular, the batch experiment uses a 0.2 s step while the production design proposes a 0.02 s safety period. Resolution checks can reduce the simulation step without establishing a hardware deadline.

Spawn capacity depends on geometry: a large one-sided overtaking formation may exceed the separated entry slots even below the generic 500-aircraft input limit. Such a configuration must be rejected rather than fabricating a feasible start. The published default comparison tests 10–200 aircraft in every catalog geometry.

## Vehicle and sensing model

Position and velocity evolve under constant acceleration within each step. Nominal cruise is 8 m/s, maximum speed is 12 m/s, and commanded acceleration is bounded by 4 m/s². Multirotors can slow or stop. Fixed-wing aircraft require at least 6 m/s horizontal airspeed, a maximum 35°/s horizontal turn rate, a 3 m/s climb/descent rate, and narrower longitudinal/lateral/vertical acceleration limits. These are illustrative motion limits, not manufacturer aerodynamic data. Goal regions are absorbing exits: reaching one removes the aircraft from the encounter; landing and approach assurance remain outside this model.

The synthetic regional observation feed publishes at 2 Hz with a 150 ms nominal delay, 3% nominal packet loss, bounded position/velocity error, and persistent per-aircraft position bias. True positions of other aircraft are available only to the dynamics and independent collision oracle. Controllers receive predicted reported states and uncertainty growth based on source age. Ownship navigation state is idealized. All controllers in a paired block receive the same traffic, noise, equipage and source samples.

This release does not encode actual ASTM packets or emulate RF propagation. It does not model independent onboard sensors, observer-specific reception, validated time synchronization, aerodynamic stall/bank envelopes, impact/wreckage behavior or wake effects. Conservative spherical building volumes approximate obstacles. A collision is recorded and diagnostic trajectories continue; later outcomes in that run are not post-impact physical predictions.

## Controllers

| CLI name | Implemented behavior |
|---|---|
| `goal` | Direct goal tracking within vehicle limits; cooperative equipment has no avoidance benefit. |
| `repulsion` | Distance and closest-approach repulsion from reported traffic and static obstacles. |
| `barrier` | The same nominal avoidance, filtered with conservative affine higher-order barrier inequalities and full intruder acceleration bounds. |
| `negotiated` | Barrier filtering plus emulated cooperative priority/yield proposals based on cumulative maneuver burden. Missing certificates revert to unilateral nominal behavior. |
| `predictive` | A 22-maneuver, 2.4 s library with vehicle-limit rollouts and conservative swept uncertainty, obstacle and boundary checks; default preferences. |
| `evolved` | The same predictive checker and fallback, with four preferences loaded from an evolutionary-search JSON profile. |

All broadcast-only aircraft keep their goal-following legacy controller, regardless of selected controller. There is no implicit reciprocal avoidance from them. Negotiation is an emulation of proposals and partial receipt, not an implementation of the signed state machine or an optimization theorem. It uses vertical alternatives and speed adjustments; the shield does not reduce the intruder acceleration envelope for a cooperative promise.

The barrier solver uses bounded iterative projection, followed by projection into vehicle limits. It is neither an exact QP nor a formally verified sampled-data controller. Every remaining constraint residual is counted as an unresolved filter step; a failed residual is not called a safe maneuver. Initial barrier-domain violations are counted separately. The `solver_overrun` scenario holds a prior command to demonstrate the risk of a missing certified backup. None of these mechanisms establishes the production architecture's formal guarantee.

Predictive controllers explicitly count `predictive_no_admissible_drone_steps` whenever their library has no candidate clearing all horizon checks. Their independent best-effort fallback is not certified. The finite library has no invariant terminal set or recursive-feasibility guarantee. Loaded preferences cannot change hard thresholds or uncertainty bounds. See [policy development](learning-policy.md) for equations, learning commands and limitations.

## Scenario catalog and exclusions

The default `all` catalog contains 27 cases:

- Geometry and demand: head-on, crossing, overtaking, merge, opposing corridor, vertical crossing, urban building volumes, blocked escape and overload.
- Traffic and communications: boundary handoff, sudden legacy turn, stopped legacy multirotors, packet loss, stale telemetry, network outage and sensor occlusion.
- Integrity and control stress: GNSS bias, altitude-datum error, identity ambiguity, wind gust, actuator lag, acceleration-bound violation, solver overrun and partial certificate receipt.

The synthetic identity-ambiguity case retains two possible associations separated by 8 m using an enclosing uncertainty ball. It does not implement a real RID identity-association protocol.

Each named scenario isolates one geometry/fault combination. `all` means this published finite catalog, not every possible real-world situation or every cross-product of faults. Independent RF channels, wrapped timestamp decoding, missing velocity, pilot takeover, broker split brain, forged priority, cryptographic audit attacks and deadline-certified hardware backups remain production verification requirements; they are not silently represented as covered by an unrelated case.

GNSS bias, datum errors, actuator lag, acceleration violations and solver overruns intentionally exceed the modeled safety assumptions. Reports show both the whole suite and the subset within modeled fault bounds. An experiment classified as within modeled bounds still may start outside the robust barrier viability set; those violations are recorded and prevent a proof claim. Overload deliberately compresses initially separated demand; no universal admission or escape feasibility is asserted.

## Run and replay

Use Python 3.11+ and NumPy 2.x from this source checkout:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install 'numpy>=2.0,<3'
.venv/bin/python -m swarm_sim scenarios
.venv/bin/python -m swarm_sim serve --port 8765
```

Open `http://127.0.0.1:8765`. The local server binds only to loopback. Its replay controls show positions, cooperative status and vehicle class, with collision markers and evidence summaries. The default replay displays 100 aircraft, 40% fixed-wing and 50% cooperation. Simulation step is adjustable down to 0.02 s; display-frame sampling is independent of the collision checker.

For a saved single-run replay:

```bash
.venv/bin/python -m swarm_sim run \
  --scenario crossing --controller negotiated --drones 200 \
  --cooperative 0.5 --fixed-wing 0.4 --seed 1001 \
  --duration 36 --dt 0.1 --out artifacts/replay.json
```

The web UI saves its own replay to `artifacts/replays/<run_id>.json`. Within the same frozen source revision, identical configurations have identical IDs and physical results; wall time and host timing vary. Run IDs hash configuration rather than software: retain source/campaign provenance when archiving replays across revisions.

## Compare every catalog scenario

```bash
.venv/bin/python -m swarm_sim compare \
  --scenarios all --counts 10 50 100 200 \
  --fractions 0 0.1 0.5 0.9 1 --fixed-wing 0.4 \
  --discovery-seeds 0 1 --holdout-seeds 1001 1002 \
  --duration 36 --dt 0.2 --workers 4 \
  --out artifacts/predictive-campaign
```

This now runs 10,800 configurations with five default controllers. Add `--controllers goal repulsion barrier negotiated` to select the original four baselines, but use a new output directory for the changed source revision. To include the learned sixth controller, explicitly add `evolved` and `--policy profiles/predictive-preferences.json`; training and evaluation seeds must be disjoint. Each discovery and holdout block compares every controller with the same initial conditions and observations. Completed runs are flushed to `runs.jsonl`, and restarting the identical command resumes the same manifest. A changed manifest or source hash requires a new output directory. Do not edit simulator code during a campaign. A failed worker makes the campaign fail explicitly rather than omitting its result.

Smaller initial checks can select scenario names and counts. For stronger sampling, use additional disjoint seeds and rerun into a new output directory. Increase the fixed-wing fraction to 1 for a pure fixed-wing sensitivity check and to 0 for a multirotor-only check. Recheck the selected profile with smaller time steps and longer encounter durations; thresholds and rankings can be timestep- and horizon-sensitive.

## Safety ranking and decision rule

Rank controllers lexicographically by participating-aircraft collision-run rate, obstacle-collision-run rate, operating-volume-exit rate, worst scenario/count/cooperation collision rate, separation exposure, then mission completion. The ordering is published before the campaign and applies identically to all controllers. This avoids a weighted objective that could trade a collision for shorter travel time.

Choose the discovery winner before consulting holdout outcomes. Report its holdout performance, whether the ordering remained stable, and every failed scenario. The empirical gate requires zero participant collisions, zero obstacle collisions, zero volume exits, zero unresolved barrier steps or failed predictive libraries, zero vehicle-limit violations, and at least 70% participant goal reach in holdout. Only filtered or predictive controllers can pass the gate. A finite-suite pass still cannot authorize flight or establish universal safety.

If the gate fails, the answer is **no configuration cleared the gate**. The lowest-risk tested controller can still be identified as a research candidate, but it must not be labeled the safest operational system. Repeating a collision-prone setup with more seeds does not cure insufficient sensing, infeasible maneuvers or overloaded geometry. Route changes, independently validated sensing, admission control and a verified backup controller are separate design changes requiring new comparisons.

Collision pairs are separated into equipped–equipped, equipped–legacy and legacy–legacy. Zero-cooperation runs remain in raw results and are excluded from controller ranking because none of the controllers has control authority there. Completion remains visible so indefinite holding is not rewarded as an acceptable operational outcome.

The raw fields `completion_fraction` and `participant_completion_fraction` measure **kinematic goal reach**, including diagnostic paths that continue after a collision. They are not successful real mission-completion rates. The UI labels this measure Goal reach. The empirical gate first requires zero participant collisions, obstacle strikes and volume exits before considering its 70% goal-reach threshold. A passing gate would still concern this finite idealized model.

The oracle screens all active pairs using a conservative curved-path/chord bound, then evaluates the cubic stationary points of squared distance for every possible threshold crossing. Physical collision thresholds are sums of vehicle radii; the operational separation threshold is 10 m. The global minimum reported away from thresholds is a conservative lower bound. Separation exposure counts a full pair-time step when its swept path touches the threshold, so it is a step-based upper exposure measure, not exact violation duration.

## Outputs and tests

Each campaign writes `manifest.json`, `runs.jsonl`, `results.json`, `summary.json`, `REPORT.md` and a standalone `report.html`. The report provides whole-suite, bounded-fault, out-of-bounds-fault and per-scenario holdout views. The lab's comparison table loads completed campaign summaries.

Run the automated checks with:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

The tests cover continuous crossing detection, accelerated distance extrema, between-step boundary exits, inactive objects, vehicle limits, explicit filter infeasibility, aged/stale telemetry, seeded repeatability, unchanged legacy behavior, collision-category accounting, all catalog scenarios, initial mixed-fleet speed limits and failed-gate handling. Passing these tests validates those implemented behaviors; it does not discharge the formal production safety case.

Version 0.3 adds compound `loss_wind`, `outage_turn` and `lag_datum` scenarios, pre-entry admission, visibility routes, finite backup checking, and optional recurrent learning. See [the new pipeline](third-iteration.md) for training and assurance scope. Default comparisons still use the five non-neural baselines; neural controllers require pinned checkpoints and disjoint evaluation seeds.
