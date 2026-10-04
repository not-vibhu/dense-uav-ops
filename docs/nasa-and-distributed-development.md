# NASA foundations and distributed development, version 0.4.1

This release adds an executable research layer in `dense_ops`. The v0.3 simulator, learned models and capacity assessments remain frozen. The new layer measures decentralized observation and control, asynchronous federated intent exchange, recovery feasibility and offline federated learning. It does not establish an operational safety envelope.

## What NASA supplies

**DAIDALUS** evaluates each ownship against traffic: well-clear detection, escalating alerts and maneuver guidance. Guidance can use instantaneous or kinematic ownship motion. Its heading, horizontal-speed, vertical-speed and altitude bands classify maneuver ranges; recovery guidance addresses existing well-clear loss. Guidance assumes non-maneuvering traffic, and alerts assume non-maneuvering ownship and traffic. The application must align and preprocess observations. The mathematical core has PVS specifications and verification; that assurance does not automatically cover our telemetry, Python integration or vehicle. See the [NASA reference manual](https://nasa.github.io/daidalus/).

**ICAROUS** arranges onboard autonomy around cFS messaging. TrafficMonitor uses DAIDALUS, GeofenceMonitor checks containment, Cognition prioritizes triggers and handlers, TrajectoryManager creates alternatives, Guidance follows paths, and Merger coordinates intersection scheduling. TargetTracker supports observation processing. Commands reach an external autopilot through interfaces such as MAVLink. This decomposition separates mission decisions, monitoring and flight execution. See the [NASA documentation](https://nasa.github.io/icarous/) and [pinned module source](https://github.com/nasa/icarous/tree/4a3bcf443e516c713c775bd6d32b8184d57c4ea2/Modules).

Our design inference is to use these components as independently assessable foundations, while adding robust uncertainty enclosures and distributed agreement checks for dense, maneuvering mixed traffic. DAIDALUS well-clear guidance is distinct from a control barrier or a joint invariant collision-avoidance proof.

The first 196-run release is retained as a v0.4.0 development baseline. It exposed a cold-start admission defect under two-second telemetry delay. Version 0.4.1 now requires a delivered observation frame whose upper source age, including the declared clock bound, is within `max_surveillance_age` before admission. The default one second is an explicit research assumption, not an aviation minimum. Empty live frames can establish receiver readiness in this synthetic model; they do not prove complete RF coverage. Deferred requests are signed and remain in the service denominator. Airborne aircraft still require fresh geometric checks and checked recovery, and the gate does not solve missed traffic or future recovery infeasibility.

## Actual integration and licensing

`scripts/build_daidalus.py` builds official C++ DAIDALUS at `1c7b58e5525d5cca91cbbf4a8b7337a488243769`, then links our original MIT bridge. The manifest pins the source revision, bridge, binary and configuration digests. No NASA source or binary is committed or relicensed. Both NASA projects retain their NASA Open Source Agreement; inspect upstream terms before redistribution.

The Python adapter supplies SI ENU states with unique IDs and returns real alerts, horizontal-direction bands and left/right resolutions. The selected upstream `DO_365B_no_SUM.conf` is a reference configuration, not a proposed dense-UAS separation standard. Hard error bounds are not converted into Gaussian standard deviations. Four native reference encounters exercise approach, diverging separation, vertical separation and close proximity.

The adapter is currently a **snapshot comparison tool**, outside the tactical actuator path. Each invocation creates a fresh object and has no persistent hysteresis history. Horizontal speed, vertical speed and altitude output adapters, sustained-ownship sessions, encounter-file interoperability and ICAROUS cFS/SITL integration remain work to complete. We studied ICAROUS; we did not run or embed its complete flight stack.

## Research information and authority boundaries

Each participating ownship receives a separate observation store. There is no truth-initialized common tactical track table. Source timestamps, clock-error bounds, independent packet losses, receiver range, bias, outages and persistent stale hypotheses affect its forecasts. The truth oracle evaluates outcomes separately. Own state and vehicle metadata are idealized, and the RF model is synthetic.

The new engine inherits these source-pinned v0.3 plant defaults. They are research assumptions, not approved operating limits:

| Parameter | Implemented default |
|---|---|
| UAS altitude range | 12–116 m in the model's common local datum |
| UAS cruise / maximum speed | 8 / 12 m/s |
| UAS acceleration authority | 4 m/s² |
| Fixed-wing minimum horizontal speed / nominal turn / climb | 6 m/s / 35°/s / 3 m/s |
| UAS / manned protection distance | 10 / 60 m, 3D spherical distance |
| Multirotor / fixed-wing / manned collision radius | 1.2 / 2.5 / 6 m |
| Manned transit speed / altitude | 35 m/s / 90 m |
| Reported position / velocity error bounds | 1.5 m / 0.3 m/s |
| Synthetic report period | 0.5 s |
| Local own-position tube seed | 0.1 m; own measured state is otherwise idealized |
| Current profile disturbance / control step / planning horizon | 0.4 m/s² / 0.2 s / 4 s |

`Experiment` configures the declared fleet, geometry, equipage, manned count, links, clock bound, range, duration, disturbance, freshness and host deadline. Arbitrary per-vehicle hardware/compliance calibration is still provided by the original capacity research model, not fully integrated into this new engine. Actual aircraft require airspeed, attitude/bank, tracking and navigation models beyond these point-mass defaults.

Regional brokers exchange signed, delayed intents through bounded directed queues. They retain separate reservation books; partition and asymmetric delivery can leave replicas inconsistent. An ownship still checks physical traffic with the original hard uncertainty bounds, even if a neighbor advertises a preferred path. The entry book is regional infrastructure shared by its members; the implementation is not a leaderless admission protocol.

The simulated entry-limit check uses the truth-state active fleet count. The published grids keep that limit above observed occupancy, but this shortcut matters for other configurations: a deployable admission service must estimate occupancy from surveillance and reservations, account for unseen traffic, and preserve every existing recovery. Independent tactical observation stores do not make the entire simulation admission process decentralized.

`Negotiator` separately implements exact-membership signed acceptance certificates, finite execution windows, monotonic epochs, overlapping-promise exclusion and local veto. The bounded protocol explorer checks 624 cases with 2–4 participants, partial delivery, competing brokers, expiry and veto. Its certificate protocol is **not yet connected to the engine's actuator path**. The engine uses asynchronous signed intents and conservative reservation checks. The `partial_commit` engine scenario exercises asymmetric intent delivery; it is not a multi-party commit execution test.

Remote ID ingestion, InterUSS/OpenUTM interfaces, pilot response and surveillance authentication remain proposed production interfaces. Broadcast-only and manned traffic are exogenous; our controller cannot guarantee avoidance between two aircraft that it cannot control.

## Recovery-preserving controller

The sampled research plant is

\[
p_{k+1}=p_k+\Delta t v_k+\tfrac12\Delta t^2(u_k+d_k),\qquad
v_{k+1}=v_k+\Delta t(u_k+d_k),\quad \|d_k\|_2\le d_{\max}.
\]

Multirotor recovery uses `u = -(p-c) - 1.5 v`, after an optional one-tick maneuver prefix. For each spatial axis, the closed-loop error transition is

\[
F=\begin{bmatrix}1-\Delta t^2/2&\Delta t-3\Delta t^2/4\\-\Delta t&1-3\Delta t/2\end{bmatrix},\quad
G=\begin{bmatrix}\Delta t^2/2\\\Delta t\end{bmatrix}.
\]

Support-function sums of `F^j G` enclose the position, velocity and feedback-command errors from bounded 3D disturbances. Commands must remain unsaturated within the declared acceleration and speed limits. A separate polynomial-extrema checker evaluates continuous trajectory slabs against traffic, spherical obstacle volumes and containment; it does not sample only endpoints or truncate to the nearest eight neighbors. A conservative broad phase removes provably irrelevant pairs.

For a static terminal set, the implementation uses

\[
P=\begin{bmatrix}17/12&1/2\\1/2&2/3\end{bmatrix},\quad
\|[p-c,v]\|_P\le r.
\]

It requires `q r + d_max sqrt(GᵀPG) <= r`, where `q = ||P^(1/2) F P^(-1/2)||₂`, checks endpoint membership including uncertainty, and verifies input, speed, containment and obstacle bounds. The numerical calculation assumes exact arithmetic apart from its explicit tolerances; it is not an interval-arithmetic or PVS proof. The trusted tube generator supplies the enclosures; the geometric checker does not independently rederive every support sum.

**Static hover invariance is not invariant separation from future moving traffic.** Traffic clearance is a renewable finite-horizon condition. Fixed-wing alternatives are finite nominal turns with uncertainty enclosures, not robust invariant loiter sets. Fixed-wing speed floors and heading changes are evaluated at samples; the model does not certify continuous airspeed, instantaneous turn rate or bank limits. Wind-disturbed trajectories are checked by the outcome oracle within those sampled constraints rather than claimed as a complete robust flight-envelope proof.

A retained recovery can execute only while unexpired, enclosing the measured state, and passing fresh traffic/environment checks. An unavailable recovery becomes `LOSS_OF_GUARANTEE`; a zero command is not labeled safe. The simulated watchdog uses recoveries that existed before a late tick. Actual fallback checking still runs in the Python process; isolated real-time execution and target-hardware WCET are outstanding.

## Graph policy and federated learning

An attention-pooled graph ranker sees every reported neighbor and scores a variable list of independently checked continuations. It never changes separation, uncertainty or vehicle limits. Invalid model indices and model failures fall back to the deterministic checked choice. Source-pinned finite JSON tensors avoid executable checkpoint deserialization.

Training is offline federated imitation across three simulated airspace domains. Each client trains locally from the same round base; the aggregator clips weighted parameter deltas. The standalone aggregator has no signed round/epoch attestation and should not be treated as a network-facing stale-update detector. A round is accepted only if imitation loss does not worsen in any independent tuning domain. Training and tuning seeds are excluded from subsequent evaluation. The study records the data and every round.

This is not a new graph-MAPPO implementation, Byzantine-tolerant aggregation, or a demonstration of safety improvement. The existing recurrent imitation/MAPPO pipeline remains available in v0.3. Subsequent constrained RL must improve mission progress and intervention rates on independent encounters without relaxing the deterministic checker. Background reading: [predictive safety filtering](https://arxiv.org/abs/1812.05506), [GCBF+](https://arxiv.org/abs/2401.14554), and [FedAvg](https://proceedings.mlr.press/v54/mcmahan17a.html).

## Audit evidence

Ed25519 signatures identify record authors; a causal SHA-256 chain and actor sequences detect edits, deletions, reordering and forks relative to a trusted signed checkpoint and public-key registry digest. `APPLY` records describe controls after overrides. Individual replay files also retain plan bodies and visualization frames. Campaign logs retain signed actions and outcomes, but not every observation and plan body needed to reconstruct all feasibility decisions.

`scripts/verify_flight_replay.py` reconstructs simulated motion from the signed applied controls and the archived exogenous plant, then reconciles collision, protection, obstacle, containment, vehicle-envelope and completion counts. It also distinguishes events involving controlled aircraft from wholly exogenous events. It reuses the archived continuous geometric oracle; this is record/plant consistency checking rather than an independent implementation of all geometry or a replay of surveillance decisions.

The simulator creates separate witness keys in the same process. Production requires independent witnesses, external checkpoint retention, protected long-term keys and authenticated clocks. These are tamper-evident records, not tamper-proof storage. They support investigation of declared intent and deviation; they cannot prove sensor truth or determine legal liability.

## Running and reviewing

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[learning]'
.venv/bin/python scripts/build_daidalus.py
.venv/bin/python -m dense_ops nasa-check --out artifacts/nasa-reference.json
.venv/bin/python -m dense_ops modelcheck --out artifacts/protocol.json
.venv/bin/python -m dense_ops run --profile profiles/distributed-04/mixed-mission.json --out artifacts/mission.json
.venv/bin/python -m scripts.render_distributed_replay artifacts/mission.json --out artifacts/replay.html
.venv/bin/python -m dense_ops train-federated --out artifacts/graph.json --rounds 3
.venv/bin/python -m scripts.run_distributed_study --checkpoint artifacts/graph.json --out artifacts/study
.venv/bin/python -m dense_ops validate artifacts/study/catalog
.venv/bin/python -m scripts.verify_flight_replay artifacts/study/catalog --out artifacts/catalog-flight-replay.json
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m scripts.validate_distributed_evidence experiments/distributed-04
```

The development study declares 196 evaluations: all 27 catalog scenarios, matched guard and policy comparisons, 50/100/200/500-aircraft stress tests, and compound partition/clock/outage/deadline/wind conditions. The published instance uses retained v0.4.0 source; rerunning these commands uses the current version. The admission correction has a separate 24-run before/after comparison on seeds 8800/8801, which were not used to discover the defect. Fleet timing is measured on a shared host with two workers; it is not onboard latency certification. Eight-second density windows assess stress, not mission completion. Mission windows last 36 seconds. Failures and queued demand remain in the denominator. Confidence bounds apply to independent fixed-duration runs with simultaneous cell correction, not per-hour accident risk.

The interactive `swarm_sim` and `airspace_capacity` labs remain v0.3. The new engine is available through `dense-ops`; its batch-fleet density is not operations/hour. The existing capacity metric is preserved, and no v0.4 capacity qualification is asserted.

## Next acceptance sequence

| Stage | Required work | Evidence required before advancing |
|---|---|---|
| Recoverable mixed-fleet motion | Verified fixed-wing loiter/escape sets, track retirement, obstacle routes, structured crossing slots | Robust actuator envelopes, continuous separation, completed requested missions and demonstrated recovery under fresh threats |
| Federated execution | Connect multi-party certificates to scheduled maneuver bundles, broker handoff and local watchdogs | End-to-end partial-delivery/partition tests; unbounded protocol specification and model proof; independent local veto |
| Capacity integration | Continuous arrivals, joint admission preserving every recovery, configurable hardware/accuracy/compliance and manned encounter classes | Conditional operations/hour with service, surveillance, containment, timing and statistically supported risk gates |
| Learned optimization | Stronger graph actor/critic, constrained offline RL, adversarial validation and gated federated updates | Improvement over matched deterministic baselines on untouched seeds and distributions; no degraded safety gate |
| Flight confidence | DAIDALUS persistent sessions, ICAROUS SITL, PX4/ArduPilot HIL, measured sensors and vehicle dynamics | Independent encounter replay, target-hardware latency, externally witnessed audit, assurance review and staged flight tests |

The existing fixed-wing, service and surveillance failures must be resolved before maximizing traffic density or claiming a safest architecture. A short collision-free simulation cannot establish either claim.
