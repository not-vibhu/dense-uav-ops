# Admission, checked backups and recurrent learning

Version 0.3 implements the next development sequence. This is a research prototype, with conditional numerical checks and finite experimental evidence. It is not a flight controller or an operational safety clearance.

## Demand and routes

`--admission off` starts all requested flights. `capacity` queues participating flights until active airborne traffic is below the configured capacity. `checked` additionally requires a finite brake/turn backup to pass both numerical checkers before entry. Legacy aircraft always enter and retain their uncoordinated routes; if legacy traffic exhausts capacity, participating demand remains queued. Ties among simultaneous requests use aircraft ID. Repeatedly infeasible requests can remain unserved; no starvation bound is established.

Queued fixed-wing aircraft are abstract **pre-entry demand**, not airborne aircraft hovering at their starting coordinates. An accepted entry uses the scenario's original initial velocity and an idealized, immediately shared entry-state announcement. Pending observations with older source times cannot overwrite that announcement. This assumes cooperative entry coordination; real takeoff dynamics, communications delays at entry, and distributed entry races are not modeled.

`--routes visibility` finds static obstacle routes using inflated spherical volumes and a visibility graph. A missing route rejects the flight, including when admission is off. Route edges establish static geometric clearance only. Fixed-wing curvature and dynamic traffic are checked by the runtime maneuver planner; a feasible visibility route is not a dynamically certified flight path. Reaching an intermediate waypoint does not complete a mission. Route-rejected and never-admitted demand remain in requested participant goal-reach denominators.

## Backup scope and numerical assurance

The backup generator rolls out multirotor braking followed by hover feedback, or a finite fixed-wing turn. The first checker uses conservative chord/curvature envelopes. A second checker recomputes trajectory continuity, nominal actuator constraints, polynomial distance extrema and body/uncertainty-inflated volume bounds. It consumes the proposed path; it does not trust a `valid` flag. Both depend on the same stated point-mass plant, reported traffic, and declared uncertainty assumptions. They are ordinary floating-point programs, not theorem provers or independent flight implementations.

For multirotor hover about a center, each spatial coordinate has phase state \(x=(p-p_c,v)\), feedback \(u=-[1,1.5]x\), sampled plant matrix

\[
F=\begin{bmatrix}1-\Delta^2/2&\Delta-3\Delta^2/4\\-\Delta&1-3\Delta/2\end{bmatrix},\quad
G=\begin{bmatrix}\Delta^2/2\\\Delta\end{bmatrix},\quad
P=\begin{bmatrix}17/12&1/2\\1/2&2/3\end{bmatrix}.
\]

Let \(q=\|P^{1/2}FP^{-1/2}\|_2<1\), using a Cholesky-induced equivalent norm in code. For total 3D acceleration disturbance norm at most \(d=0.8\), a sufficient sampled invariant ellipsoid satisfies

\[
\sqrt{\rho}>\frac{d\sqrt{G^TPG}}{1-q},\qquad
V=\sum_{c=1}^3x_c^TPx_c\le\rho.
\]

The implementation reconstructs input, velocity and intersample position bounds, checks actuator/speed authority and requires the whole position envelope to fit the static environment. It also checks a conservative bound on **terminal position and velocity uncertainty** before reporting terminal membership. A nominal endpoint inside the ellipsoid is insufficient. At the default 2.4-second open-loop horizon, this robust terminal check is restrictive and may fail even for an otherwise clear brake maneuver. `--require-invariant-backup` consequently rejects many entries and every fixed-wing entry. The static ellipsoid does not establish indefinite clearance from moving traffic. Finite fixed-wing paths do not certify disturbed stall/turn envelopes or an invariant loiter set.

Checked mode revalidates an independent backup when the maneuver library fails or the synthetic update-overrun fault is injected. If no backup passes, it reports unavailability and retains diagnostic best effort (or the previous command in the overrun case). This cannot promise recursive feasibility. Admission does not verify an invariant joint continuation for all previously admitted aircraft.

## Learning implementation

Install optional training dependencies:

```bash
.venv/bin/python -m pip install -e '.[learning]'
.venv/bin/python -m swarm_sim train-imitation --episodes 8 --epochs 12 \
  --training-seed 42 --out models/imitation.json
.venv/bin/python -m swarm_sim train-mappo --episodes 8 --epochs 3 \
  --training-seed 42 --initial models/imitation.json --out models/mappo.json
```

A shared actor encodes ownship state, navigation goal, boundary distances, vehicle type and accumulated yielding burden. Attention aggregates a local star graph of the nearest eight reported traffic tracks, including age, uncertainty and capability labels. A 32-state GRU carries encounter history. The actor emits preferences over the existing 22 maneuver primitives. The deterministic checker evaluates **all active traffic**, independent of the eight-neighbor actor limit, and vetoes any out-of-mask proposal. The actor never receives the simulator's other-aircraft true state. Capability/active-track metadata is an idealized input in this harness.

Imitation collects predictive expert trajectories and trains cross-entropy only on decisions with at least one admissible candidate. Failed-library fallback decisions are never expert labels. Training uses eight-step recurrent chunks and stored hidden states at chunk boundaries. The public checkpoints are small development runs, not converged policies.

MAPPO starts from imitation, uses on-policy stochastic masked categorical actions, a shared actor and a separate centralized critic with global simulator context during training. Training uses GAE (gamma .99, lambda .95), PPO clipping .2, clipped value loss, entropy coefficient .01, gradient norm .5 and Adam at 3e-4. Empty masks have no actor objective; their fallback outcomes can still train the critic/shared representation. The configured finite episode duration is terminal, with zero continuation bootstrap. No PPO updates use holdout trajectories.

Reward combines mission progress, goal reach, time and effort with collision, obstacle, exit and separation penalties. Safety thresholds are not reward weights: the maneuver checker retains final authority. Reward penalties themselves do not establish safety, and finite masks do not imply invariant safety. Yielding burden is observed; this reward does not establish a fairness guarantee.

Checkpoints use a fixed JSON schema of finite, shape-checked tensor arrays. They contain no executable pickle objects. Loading checks the simulator source revision, stage, and any supplied SHA-256 pin. Campaigns pin checkpoint digests and reject overlap between training and evaluation seeds. Source changes require deliberate retraining. These integrity checks are not signatures or a tamper-proof tactical liability ledger; the signed/witnessed production audit protocol remains proposed in the architecture.

## Evaluation

Compare the predictive teacher with both learned policies using paired environments and separately reported requested demand, admitted demand, collisions, exits, finite-check failures, backup availability, throughput and observed computation time. Compare admission modes in separate manifests; do not pool controllers across different capacity/route settings. Add compound loss+wind, outage+legacy-turn, and actuator-lag+datum-error cases. Keep model-violating cases visible and separate.

The empirical gate requires zero recorded participant collisions, obstacle collisions, exits, kinematic violations, failed-library steps, unavailable backup steps and measured command deadline misses, plus at least 70% admission and participant goal reach. Requested demand is the denominator. A zero-collision run that simply withholds demand does not clear the gate. Deadline measurements are host/process-contention observations, not worst-case execution-time proofs. Version 0.3 timing covers telemetry ingestion, admission, route updates and tactical control including the synthetic watchdog fallback.

Research context: [predictive safety filters](https://arxiv.org/abs/1812.05506) motivate checking a backup continuation; [MAPPO](https://arxiv.org/abs/2103.01955) motivates centralized training with decentralized actor execution. Neither paper validates this implementation or provides a universal UAS safety guarantee.

[Measured results and checksums](../experiments/iteration-03/README.md) now cover 948 completed evaluations. No configuration passed the empirical gate; the learned policies did not establish consistent safety gains over the predictive teacher. Earlier evidence remains tied to its own source revisions and is not relabeled as current validation.

Backup-unavailability counters count failed check attempts. A failed-library fallback and synthetic watchdog can both check the same aircraft in one step; these counters are not unique-aircraft-step exposure denominators.
