# Predictive policy iteration: evidence and decision

Version 0.2 adds a finite predictive maneuver library and cross-entropy preference optimization. It improves boundary behavior and goal reach in the 10/50-aircraft holdout catalog, but does not establish a consistently lower collision rate or a safe operating configuration. The optimizer retained the default preferences to numerical precision; there is no demonstrated learning benefit from the initial search.

## Training and evaluation separation

The corrected optimizer ran 96 training evaluations on head-on, crossing, overtaking and urban encounters, with ten aircraft, 50% cooperation, 40% fixed-wing, training seeds 20/21, six samples and two generations. Its best candidate was the default preference vector. Training fitness ranks safety outcomes before efficiency.

The complete catalog comparison has **1,152 runs**: all 24 named scenarios, aircraft counts 10/50, cooperation 50/100%, six controller labels, 40% fixed-wing and separate discovery/holdout seeds 2000/3000. Each encounter runs 36 s at a 0.2 s step. There are 96 holdout runs per controller label. `predictive` and `evolved` have identical physical metrics in every paired run; their equal results do not represent independent evidence or an optimization gain.

## Whole-catalog holdout outcomes

| Controller | Participant collision runs | Participant obstacle runs | Participant exit runs | Participant goal reach |
|---|---:|---:|---:|---:|
| Predictive, default or retained preferences | 6.25% | 5.21% | 36.46% | 67.92% |
| Barrier | 6.25% | 8.33% | 76.04% | 45.71% |
| Negotiation + barrier | 7.29% | 8.33% | 76.04% | 45.96% |
| Heuristic repulsion | 37.50% | 12.50% | 39.58% | 98.58% |
| Direct goal tracking | 48.96% | 12.50% | 8.33% | 98.88% |

These rates count scenario runs with at least one equipped aircraft involved in the event; they are not individual-aircraft collision probabilities. Goal reach is the kinematic diagnostic already defined in the simulator, including paths continuing after collisions. The new suite differs from the original 7,680-run count/cooperation/seed matrix, so its percentages cannot be compared directly with that older aggregate.

The predictive planner recorded 109,336 failed-library drone-steps on holdout, while the barrier recorded 205,916 unresolved projection steps. Those counters have different mechanisms and are not interchangeable estimates of feasible-control failure. Both prevent acceptance. The predictive planner has no recursively feasible terminal backup; its fallback is best effort.

Within modeled fault cases, predictive collision runs were 3.95%, compared with 5.26% for the barrier and 6.58% for negotiation. In out-of-bound cases, predictive collision runs were 15%, compared with 10% for either barrier variant. These subsets are descriptive and do not establish a universal dominance claim.

Discovery selected negotiation: its collision-run rate was 4.17%, compared with 14.58% for predictive. The ordering changed on holdout. A single held-out seed per stratum is insufficient to establish stable generalization or a population confidence claim. No policy was tuned using the holdout.

## Separate 100/200-aircraft stress tests

The scale comparison completed **32 runs**: crossing/overload, 100/200 aircraft, 50% cooperation, 40% fixed-wing, four controller labels and discovery/holdout seeds 2000/3000. Its four holdout encounters per controller are a small stress check, not coverage of all 24 scenarios at those fleet sizes.

| Controller | Participant collision runs | Participant exit runs | Participant goal reach |
|---|---:|---:|---:|
| Predictive, default or retained preferences | 50% | 100% | 26.5% |
| Negotiation + barrier | 75% | 100% | 3.5% |
| Direct goal tracking | 100% | 0% | 100% |

In the 100-aircraft holdout crossing and overload cases, predictive recorded zero participant collision pairs, but still had two/six participant exits and thousands of failed-library steps. At 200 aircraft, predictive recorded three/seven participant collision pairs and twenty/eleven participant exits. These failures prevent selecting a safe dense operating domain.

The 200-aircraft predictive holdout cases measured roughly 606–667 ms for the 99th-percentile **whole-fleet command computation** on this host while six campaign workers were active. That exceeds the simulation's 200 ms step and does not establish an onboard deadline. Hardware contention and centralized Python overhead affect these values; per-aircraft distributed execution would require separate measurements. Neither timing nor safety is ready for flight use.

## Decision

Keep the predictive controller as an additional research baseline. It offers a useful way to explore feasible maneuver alternatives, boundary preservation and improved goal reach. Keep barrier and negotiation baselines: the evidence does not support replacing them with a universally safer policy. **No tested configuration clears the empirical safety gate.**

The next safety work should add feasible admission/routes, an independently checked solver and a vehicle-specific invariant backup. Measure rejection, delay and served demand explicitly so refusing flights cannot masquerade as better tactical avoidance. Optimize neighbor lookup and kernel implementation using provably conservative threat screening before claiming a real-time deadline. Finite-horizon scores cannot repair missing coverage or physical infeasibility.

After those controls exist, add imitation and recurrent MAPPO with a graph/attention traffic encoder, local observations at execution and a centralized training critic. Keep the actor's proposal behind the independent shield; evaluate unshielded proposals only in simulation. Train on varied dynamics, fleet sizes, legacy fractions and compound faults, then use new independent holdouts and multiple training seeds. The full proposal and implemented optimizer are documented in [policy development](learning-policy.md).

## Evidence

The corrected outputs are under `artifacts/predictive-catalog` and `artifacts/predictive-scale`. Together they contain 1,184 completed evaluation runs; the separate corrected training trace contains 96 evaluations. The source hash is recorded in the manifests and trained profile; each raw results checksum is in `summary.json`. Preliminary computations before the stale-wind enclosure correction are archived separately under `artifacts/pre-age-correction` and excluded from these comparisons. Published manifests, summaries and static reports are under [the iteration evidence directory](../experiments/iteration-02/README.md); complete raw results and source snapshots remain local.

Twenty-seven automated tests passed, including between-frame collision/volume checks, isolation from other aircraft's truth state, unchanged legacy behavior, preference-independent fallback, blocked selection of unsafe candidates and stale-plus-future wind enclosures. The browser executed the corrected learned-profile replay without console errors. These checks validate implemented behavior and accounting, not flight safety.
