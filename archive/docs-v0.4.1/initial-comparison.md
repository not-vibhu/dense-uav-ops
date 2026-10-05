# Initial mixed fleet comparison decision

The first campaign completed all **7,680** planned runs. **No tested configuration clears the empirical safety gate.** The barrier-based prototypes reduce observed participating-aircraft collision runs, but frequently leave the operating volume, report unresolved constraints, and fail to reach their goals. They are research candidates rather than acceptable operating configurations.

## Experiment scope

The matrix covered all 24 scenarios in the published catalog, fleet sizes 10/50/100/200, cooperative fractions 0/10/50/90/100%, four controllers and four disjoint seeds. Fixed-wing fraction was 40%. Each encounter ran for 36 s with a 0.2 s integration/control step. Discovery used seeds 0 and 1; holdout used 1001 and 1002.

Every controller received the same initial traffic and synthetic observations within a paired block. There were 768 participating-aircraft holdout runs per controller. Zero-cooperation runs remained in the raw data and were excluded from controller selection. Intentionally out-of-bounds faults are included in the conservative whole-suite comparison and also reported separately.

## Observed holdout outcomes

| Prototype | Runs with participant collision | Runs with participant volume exit | Participant goal reach | Unresolved filter drone-steps |
|---|---:|---:|---:|---:|
| Negotiation plus barrier | 39.1% | 82.4% | 26.4% | 6,284,244 |
| Barrier | 39.3% | 82.4% | 26.2% | 6,283,900 |
| Heuristic repulsion | 62.6% | 57.6% | 97.7% | Not applicable |
| Direct goal flight | 73.2% | 6.0% | 99.3% | Not applicable |

Collision percentages are fractions of scenario runs involving at least one equipped aircraft, not percentages of individual aircraft. Goal reach is a kinematic diagnostic measure: trajectories continue after collision without impact physics, so it does not represent successful real missions. An unfiltered baseline's zero filter-residual counter does not provide a safety certificate.

Negotiation plus barrier had 300 collision-positive holdout runs, versus 302 for the barrier alone and 562 for direct flight. The two barrier variants are practically close in this suite: negotiation avoided a collision-positive result in 30 paired blocks where the barrier variant had one, while the barrier variant avoided one in 28 blocks where negotiation had one. The remaining 710 paired blocks agreed. Discovery selected the barrier alone, so the identity of the lowest-risk prototype did not remain stable on holdout. These correlated scenario blocks do not establish a population significance claim.

## Decision and required changes

Continue investigating the **barrier-based family**, and keep both variants as comparison baselines. Do not select one as a safe configuration for unrestricted dense mixed traffic. Its lower collision rate does not offset its unacceptable volume exits, unresolved constraints and low goal reach. The comparison evaluates these implementations; it does not establish that the underlying CBF framework is intrinsically inferior or that negotiation never helps.

The next design iteration needs capacity/admission and route constraints that preserve feasible escape paths, a solver with independently checked feasibility, a backup controller appropriate for fixed-wing and multirotor motion, and validated sensing/tracking bounds. These are architectural requirements exposed by the experiment, not features already implemented in this release. Parameter tuning alone cannot repair an encounter with no safe feasible action.

Do not reduce hard separation, truncate traffic or silently drop failed scenarios to improve the score. Repeat the fixed catalog after each substantive change with new disjoint holdout seeds, and qualify the altered operating domain explicitly.

## Resolution check and provenance

A separate 100-aircraft crossing replay at a 0.05 s step also recorded one participating collision, unresolved constraints and volume exits. It confirms that this failure is not removed merely by finer sampling; it does not establish timestep convergence for every scenario. The complete matrix uses the 0.2 s step recorded in its manifest.

Generated evidence lives under `artifacts/full-campaign`: `manifest.json`, `runs.jsonl`, `results.json`, `summary.json`, `REPORT.md`, `report.html`, `environment.txt` and `source-snapshot.tar.gz`. The validated matrix has 7,680 unique configurations, exactly 320 per scenario, with no missing or duplicate planned runs. The source snapshot and checksum preserve the computation revision. Reviewed report labels clarify goal reach; the raw metrics remain unchanged.

The simulator passed 16 automated checks for implemented dynamics, sensing and collision accounting. Browser verification covered actual simulation execution, replay advancement, an error-free console and input rejection. The Python wheel includes the browser assets. These checks establish functionality of the research harness, not formal flight safety.
