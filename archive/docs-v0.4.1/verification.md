# Verification and acceptance plan

This is the production evidence plan. The current research harness implements a subset of these scenarios and produces finite simulation benchmarks; see the [simulation guide](simulation.md) and generated campaign reports for implemented coverage. No flight trials or formal safety proofs have been completed.

## Claim to evidence mapping

| Claim | Method | Acceptance evidence |
|---|---|---|
| F3411/F3548 adapter interoperability | Pinned InterUSS qualifier and applicable OpenUTM scenarios against independent peer USSs | Versioned configuration, requirements mapping and passing artifacts for the deployed profile; no tactical claim inferred. |
| No unsafe reliance on negotiation | TLA+ or equivalent finite-state model of loss, duplication, reorder, partition, double leaders and expiry | Invariant: execution requires local safety authorization; a partial certificate delivery never creates required reciprocity. |
| No conflicting local promises | Formal reservation state machine with overlapping conflicts | One active accepted trajectory for any overlapping interval; supersession requires a safe transition. |
| Physical collision boundary | Robust HOCBF/reachability analysis for certified aircraft and environment models | Initial-set, sampled-data, uncertainty-update, solver error, multi-obstacle feasibility and actuator-tracking obligations discharged. |
| Continuous candidate separation | Interval or continuous swept-volume checker | Every accepted trajectory slab and backup transition excludes protected occupancy; no endpoint-only checking. |
| Timely sensing and control | Measured sensor age/clock bounds, real-time scheduling analysis and fault injection | All claimed bounds supported on the intended hardware; any miss invokes a still-valid backup before its validity expires. |
| Legacy independence | Mixed-equipage simulations and controlled encounters | Safety assumptions never require a legacy acknowledgment, reciprocal maneuver or pilot reaction. |
| Fairness policy compliance | Deterministic replay of cost, credentials and burden accounting | Selected bundle matches the published policy; quantify disparity, starvation and overload separately. |
| Audit integrity | Signature, sequence-chain, Merkle inclusion/consistency and witness tests | Modified retained events rejected, equivocation detected when independent views meet, missing data reported rather than inferred. |
| Reproducible incidents | Archived raw messages, enclosures, models, software and timing | An independent verifier reconstructs candidate validation and control authorization with bounded timing ambiguity. |

The proposed formal protocol model proves logical properties under specified assumptions. It does not prove RF coverage or aircraft dynamics. Likewise, simulation and a passing standards suite cannot replace the safety-kernel proof and measured integration bounds.

## Simulation campaign

Use a reproducible simulator with recorded seeds, full physical ground truth, actual acceleration/jerk constraints, terrain, receiver geometry, source/reception timestamps and independent communication queues. The oracle checks continuous or conservatively enclosed minimum physical separation independently of the planner. Avoid validating a controller with a checker that repeats its own potentially faulty approximation.

| Dimension | Required cases |
|---|---|
| Equipage | Cooperative fraction 0%, 10%, 50%, 90% and 100%; one equipped ownship among legacy traffic; two legacy drones conflicting independently. |
| Geometry | Head-on, crossing, overtaking, merging corridors, opposing corridor entry, vertical encounters, blocked escape, boundary handoff and urban occlusion. |
| Density | Below validated capacity, at capacity, and overload with dynamically arriving legacy traffic; measure backup feasibility throughout. |
| Dynamics | Multirotor and fixed-wing models separately; acceleration envelope extremes, wind, payload, battery and tracking lag. |
| Observations | Quantized RID, burst loss, stale/wrapped/future timestamps, velocity unavailable, GNSS bias, correlated errors, vertical-datum mismatch and conflicting identity associations. |
| Radio/network | Receiver blind spots, scan gaps, RF contention, upstream outages, asymmetry, delay spikes, reordering, duplicated and withheld certificates. |
| Other traffic | Unannounced turns within bounds, stopping, continuing straight, bound violations and physically undetected entrants. |
| Software/control | Planner/solver overrun, numeric failure, autopilot mode change, hardware reset, reservation conflict, double broker and lost backup validity. |
| Evidence | Forged priority, rotated identity, compromised key, dropped event, deleted payload, log fork, clock rollback and offline recorder filling. |

Zero cooperative participants evaluates sensing/admission and documents the absence of control authority over legacy aircraft; it cannot be reported as guaranteed collision avoidance for them. Faults outside the bounded domain should cause explicit loss-of-guarantee reporting. Count these separately from successful prevention and within-domain failures.

Compare three baselines with identical sensing and physical assumptions: deterministic unilateral planning, the same planner with negotiation, and optional MARL ranking with the same shield. Include a reciprocity heuristic in simulation to expose its failure with legacy traffic. Baseline comparisons must not weaken the uncertainty envelope for the proposed method.

## Proposed timing targets

These budgets apply to the example simulation profile and require measurement and worst-case analysis before operation:

| Loop | Proposed budget | Required interpretation |
|---|---|---|
| Safety command cycle | 20 ms / 50 Hz | Includes local state snapshot, robust solve, independent residual check and command publication. |
| Nominal decision epoch | 100 ms / 10 Hz | Up to 20 ms snapshot/proposal preparation, 60 ms negotiation, 15 ms final validation and 5 ms publication. |
| Negotiation | At most 60 ms and two rounds | Deadline expiry returns to unilateral operation; no latency guarantee inferred from a transport protocol. |
| Prediction | 5 s | Must cover validated escape and communication-loss continuation; extend horizon or restrict operation if it does not. |
| Track freshness trigger | 0.5 s age upper bound | Triggers degradation and enlargement; does not change the actual observation rate or delete a threat. |
| Audit checkpoint | Proposed 1 s cadence when connected | Durability and witness availability are measured separately; no effect on the safety tick. |

Choose internal safety-process sub-budgets after hardware profiling. Report median, p95, p99, worst observed latency, deadline misses and analytically supported worst-case limits. A p99 budget leaves outliers and therefore cannot alone support deterministic invariance. Account separately for remote source age and local computation.

Benchmark traffic levels of 100, 500 and 1,000 tracks per regional node, and 10, 30 and 60 relevant tracks per aircraft as **stress-test points**, not promised supported capacities. Dense graphs can approach quadratic edge count; report edges, uncertainty size and solver constraints as well as track count. A safety kernel that exceeds validated capacity must trigger the capacity/fallback policy before losing its deadline; it cannot discard excess threats.

## Outcomes to publish

- Minimum physical center/body separation and applicable well-clear losses, with oracle ground truth.
- Hard constraint violations, infeasible controls, proof-assumption failures, and successful/failed backup transitions.
- Observation-age distributions, coverage gaps, classification/association failures and actual sensor-detection range.
- Negotiation success, expiry, shield overrides, control latency and missed-deadline response.
- Mission completion, delay, energy, throughput, worst waiting time and operator-normalized cumulative burden by priority class.
- Audit completeness, signature verification results, receipt latency, detected equivocation and unavailable payloads.

Publish seeds, hardware/software/profile hashes, provenance and all exclusions. Zero observed collisions is a result for the tested sample, not proof of universal collision freedom. State the experiment's sample size and dependence assumptions when calculating statistical uncertainty.

## Hardware and controlled-flight gates

First run software-in-the-loop with realistic autopilot interfaces. Then run hardware-in-the-loop for actuator lag, worst-case scheduling, receiver contention, key operations and watchdog takeover. Exercise partial delivery and disconnected operation before flight.

Controlled trials require independently measured position truth, a surveyed operating region, validated contingency volumes, the applicable permissions and supervision, and safety limits derived from the tested vehicle/coverage combination. Tighten density only when real sensing and maneuver envelopes permit it. A remote operator display or pilot notification without a validated response bound cannot replace onboard avoidance.

## Open-source implementation sequence

1. Define canonical telemetry/enclosure messages and write read-only RID/direct-receiver adapters pinned to tested standards versions.
2. Build a deterministic simulation and independent collision oracle; reproduce unilateral legacy encounters before negotiation.
3. Implement the safety kernel and backup controller for one explicit vehicle/environment profile; discharge its proof obligations.
4. Implement bounded negotiation, local reservations, fairness and audit replay; model-check the protocol fault cases.
5. Qualify standards interoperability and integrate the tactical sidecar without putting USS storage/polling on control deadlines.
6. Measure hardware timing, fault responses and coverage; complete controlled trials at conservative density.
7. Evaluate MARL candidate ranking against the deterministic baseline under the unchanged shield and hard assumptions.

Runtime code should expose stable, open message schemas, signed profile manifests and a replay format; use the repository's MIT license for original project code. Keep privileged signing material, personal telemetry and licensed ASTM documents out of public fixtures. Distribute synthetic audit fixtures and failure scenarios so independent operators can test compatibility without exposing real flights.
