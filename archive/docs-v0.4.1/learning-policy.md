# Improving safety before training complex policies

This document records the version 0.2 implementation and subsequent design proposal. Version 0.3 now implements recurrent imitation, masked MAPPO and independently checked finite backups; see [the current implementation and assurance limits](third-iteration.md). Statements below about unimplemented neural training or backup controllers refer to version 0.2.

The original experiments exposed three problems: encounters with insufficient maneuver room, a finite-projection barrier solver that often returned unresolved constraints, and maneuvers that left the operating volume. Learning a higher reward in those conditions does not establish a safe controller. The next policy must account for trajectories, vehicle type, available escape space and source uncertainty before optimizing flight efficiency.

Version 0.2 adds a predictive maneuver-library controller and an evolutionary optimizer of its preferences. It is a working research iteration, not a certified safety filter. The previous 7,680-run results and computation source remain preserved under `artifacts/full-campaign`; a new source revision always uses a new campaign directory.

## Implemented predictive controller

Every equipped aircraft evaluates 22 candidate velocity targets: straight and turned headings, climb/descent alternatives, lower/higher speed, braking and continued velocity. Rollouts use the existing multirotor/fixed-wing acceleration, minimum-speed, turn and climb projections at each 0.2 s step over a nominal 2.4 s horizon. A fixed-wing braking target still obeys its horizontal minimum speed; it does not assume hovering.

The controller has its own idealized navigation state, a shared reported traffic snapshot and known static obstacles. It cannot access other aircraft's true positions or velocities. Cooperative promises do not reduce intruder acceleration bounds. Other aircraft are predicted at reported velocity with expanding uncertainty balls:

\[
E_j(\tau)=e_j+e_{v,j}\tau+\tfrac12 A_j\tau^2+
\tfrac12(0.8)(\mathrm{age}_j+\tau)^2.
\]

The feed's observation-age uncertainty for \(A_j\) is already included in \(e_j,e_{v,j}\). The added wind term covers both the stale source interval and future prediction, including their cross-term. Ownship predicted positions also carry a \(0.8\,\mathrm{m/s^2}\) bounded-disturbance enclosure. For each step, the minimum distance of relative straight segments is reduced by the ownship curvature bound \(\|a\|\Delta t^2/8\) and uncertainty. This conservatively screens the continuous nominal path within each segment. Obstacle spheres include aircraft body radius; volume faces use the extrema of the quadratic motion, including between-endpoint excursions.

A candidate is admissible only if every checked step clears separation, body/obstacle and volume margins. When there are admissible candidates, positive preference weights select among them:

\[
J_\theta = \theta_p\|p_H-g\|+
\theta_e\sum_k\|a_k\|^2\Delta t+
\theta_t\|a_0-a_{\rm nominal}\|^2+
\theta_z|z_H-z_0|.
\]

When the library has no admissible candidate, an independent deterministic best-effort rule minimizes accumulated squared physical/volume/obstacle deficits, then separation deficits. Learned weights cannot change this fallback. Every such decision increments `predictive_no_admissible_drone_steps`, which prevents an empirical safety-gate pass. A failed library does not prove that all physically possible controls are infeasible.

The horizon has no invariant terminal set, admission guarantee or independently verified emergency controller. Receding-horizon feasibility is not recursive feasibility. Nearby aircraft may mutually react; fresh observations update their tubes but do not remove the need for verified backups. Absorbing goals, shared reception and other simulation limitations still apply.

## Implemented policy optimization

The `learn` command uses the cross-entropy method: sample log-space preference weights, evaluate complete seeded episodes, retain elite candidates and update the sampling distribution. It is gradient-free evolutionary optimization, not PPO, a neural network or multi-agent reinforcement learning.

Only the four allowlisted positive scalar preferences can be loaded from a JSON profile. Profiles cannot alter separation, telemetry bounds, vehicle limits, horizon checks or failed-library fallback. Training fitness ranks collision-run rate, obstacle-run rate, volume-exit rate and normalized failed-library steps before separation exposure, goal reach and effort. A collision cannot be exchanged for faster travel through a weighted reward.

The initial saved profile uses 96 evaluations: six candidates, two generations, four scenarios, two training seeds, ten aircraft, 50% cooperation and 40% fixed-wing. This intentionally small first search is not sufficient to establish generalization. Training seeds 20/21 are separated from controller-selection seed 2000 and holdout seed 3000. The new comparison includes default `predictive` and learned `evolved` as separate controllers, with identical traffic and observation seeds. Never tune this profile after inspecting its holdout to preserve that holdout's purpose.

```bash
.venv/bin/python -m swarm_sim learn \
  --scenarios head_on crossing overtaking urban --counts 10 \
  --train-seeds 20 21 --population 6 --generations 2 --workers 4 \
  --out artifacts/policy-search/preferences.json

.venv/bin/python -m swarm_sim compare \
  --scenarios all --counts 10 50 --fractions 0.5 1 \
  --controllers goal repulsion barrier negotiated predictive evolved \
  --policy profiles/predictive-preferences.json \
  --discovery-seeds 2000 --holdout-seeds 3000 --workers 6 \
  --out artifacts/predictive-catalog

.venv/bin/python -m swarm_sim compare \
  --scenarios crossing overload --counts 100 200 --fractions 0.5 \
  --controllers goal negotiated predictive evolved \
  --policy profiles/predictive-preferences.json \
  --discovery-seeds 2000 --holdout-seeds 3000 --workers 6 \
  --out artifacts/predictive-scale
```

The catalog command covers 1,152 runs over every named scenario at 10/50 aircraft. The separate scale command covers 32 runs at 100/200 aircraft in crossing and overload cases with 50% cooperation. Preliminary training and a broader incomplete matrix were archived with their source under `artifacts/pre-age-correction` after the stale-interval wind enclosure was corrected. None of those preliminary rows is included in the corrected evaluation. The split makes the tested domain explicit while exposing the substantial runtime cost at 200 aircraft.

The preference profile is embedded in each manifest and hashed; each run records the actual preference values. Baseline controllers and the default predictive controller do not receive the learned preferences. Generated training traces retain each candidate, fitness and constituent simulation result. They remain local under ignored `artifacts/`.

## Next reinforcement-learning architecture

Use centralized training with decentralized execution: a shared recurrent actor sees ownship state, aircraft class, goal, source age, uncertainty, yielding debt and an order-invariant encoding of nearby reported traffic. A graph or attention encoder can handle variable fleet size; a recurrent belief state represents missing/delayed observations. A centralized critic may see simulator truth during training, while actor execution must never depend on it. This is a partially observed multi-agent problem with legacy drones modeled as exogenous agents.

Begin with imitation of feasible predictive decisions, then fine-tune a MAPPO baseline. The actor should propose a maneuver/waypoint or score admissible candidates at a slower planning rate. A separate fast safety kernel checks every proposed action, controls bounded-input tracking, rejects missing deadlines and invokes a verified vehicle-specific backup. For a fixed-wing aircraft, that backup might be a validated turning/climbing reachable tube; for a multirotor, a certified braking/holding tube. Neither is implemented here.

Train efficiency and fairness after enforcing admissibility. An appropriate nominal reward can penalize travel time, energy, detour, maneuver changes, accumulated yield disparity and safety-filter intervention. Record costs for collisions, obstacle strikes, exits and unresolved decisions separately. A constrained MDP's bound on expected cost does not imply trajectory-wise collision freedom, and a large negative collision reward cannot replace the kernel.

Use curricula from sparse pure multirotor traffic to mixed aircraft, legacy fractions, congestion and combined faults. Randomize vehicle limits, latency, loss, bounded bias, gusts, intruder behavior and receiver coverage within explicit ranges. Keep adversarial out-of-bound tests separate but visible. Safety assumptions may not be relaxed by a learned uncertainty model; calibrated statistical predictions and hard enclosing bounds have different claims.

Before accepting learned gains, evaluate default planner, imitation policy and learned policy under the same independently checked shield. Include an unshielded ablation only in simulation, record raw proposals and overrides, and verify that the actor has no truth-state leak. Partition training, development and final holdout by seeds, geometry variants, fleet size, aircraft dynamics and compound faults. Evaluate worst strata, collision/exit events, failed-library rate, shield interventions, effort, fairness, goal reach, latency and persistent gridlock. Require several independent training seeds; a single neural checkpoint is insufficient evidence.

## Capacity and verification work

For the next substantial safety improvement, add entry/admission and route management that retains a feasible escape tube, plus a solver/checker and terminal backup pair with independently established sampled-data bounds. Capacity rejection must be reported as rejected demand rather than successful flight. Run a separate comparison with and without admission so lowering exposure cannot masquerade as a better tactical policy.

The current dense-volume benchmark deliberately grants control only to cooperative aircraft. Legacy–legacy collisions remain outside that authority. A protocol cannot guarantee their mutual collision freedom, and Remote ID coverage alone is insufficient for assured detection. More learning cannot repair absent observations, physically impossible maneuvers or an unsafe operating domain.

## Research sources

- [Wabersich and Zeilinger: predictive safety filtering](https://arxiv.org/abs/1812.05506) develops a model-based filter around a learning controller, including uncertainty and constrained planning. Its safety assumptions and design conditions must be discharged by an implementation; our finite library does not inherit the paper's guarantee.
- [Yuan et al.: safe-control-gym](https://arxiv.org/abs/2109.06325) provides a benchmark approach for comparing model-based and learned control with explicit constraints and injected disturbances.
- [Yu et al.: MAPPO](https://arxiv.org/abs/2103.01955) supports PPO as a cooperative multi-agent baseline. Its game benchmarks do not establish UAS safety or performance in mixed-equipage flight.
