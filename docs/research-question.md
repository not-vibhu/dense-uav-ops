# Research question, definitions and evidence requirements

## The question

> For a declared operating domain — airspace geometry, offered traffic and its mix, vehicle envelopes, surveillance quality — how much traffic can be served at a stated level of collision and separation risk, and how does that depend on what each aircraft assumes about the others, on surveillance, on equipage and on the avoidance method?

This is a question about a **frontier**: the set of achievable (service, risk) pairs. Controllers, coordination protocols and learned policies are *treatments* that move a configuration on or toward that frontier. None of them is evaluated in isolation.

### Why this framing

The earlier iterations of this project (v0.1–v0.4, retained under [`experiments/`](../experiments/README.md)) compared controllers and declared that none "cleared a safety gate". Reanalysis shows the dominant cause was not any controller: every planner assumed that every other aircraft could accelerate toward it at the full 4 m/s². Over a 2.4 s look-ahead with 0.5 s-old reports, that turns each neighbour into a protected sphere of about 33 m radius. As density grew, the maneuver library had no admissible option on roughly 15 % of controlled aircraft-steps at 10 aircraft, 46 % at 50 and 90 % at 200 (see the [technical report](report/technical-report.md)). No tuning or learning can create admissible maneuvers in that situation, and none did. The assumption, not the controller, set the density limit, and that assumption deserves to be the variable under study.

### The long-term ambition, stated as a hypothesis

The motivating ambition is a free, open, evidence-backed safety policy for aerial robotics that could eventually inform standards. This project treats that as a hypothesis with explicit preconditions, not as a goal it has reached:

- **H-policy:** for some class of operating domains, there exist assumption regimes (what aircraft may assume about each other, backed by what aircraft must then guarantee) that deliver materially more capacity than worst-case separation at an acceptable, *estimable* risk.
- It is falsified for a domain if, at every tested regime, either the risk estimate exceeds the target or the service requirement fails.
- It cannot be confirmed by this simulator alone. Confirmation needs the higher evidence levels below.

## Definitions

These definitions are what the code and reports mean by each term. They are deliberately narrower than everyday usage.

### Events

| Term | Definition in this project |
|---|---|
| **Contact** | Two aircraft bodies (spheres of declared radius) overlap at any instant within a step, checked exactly for constant-acceleration motion. A stand-in for a mid-air collision; there is no impact model. |
| **Loss of separation (LoS)** | Two aircraft come closer than the declared protection distance (default 10 m UAS–UAS, 60 m UAS–manned). Counted once per episode, when the pair enters the condition. A research threshold, not a regulatory well-clear definition. |
| **Attributable** | The event involves at least one *controlled* aircraft (equipped, participating and compliant). Events between aircraft the system does not control (legacy UAS, noncompliant UAS, manned aircraft) are reported separately as airspace-level risk. |
| **Entry phase** | An event within one report interval (period + latency + one step) of either aircraft entering the volume. In that interval surveillance cannot yet have reported the newcomer, so no avoidance method can react. Entry-phase events are reported separately from in-flight events. |
| **Fallback** | A controlled aircraft's planner found no admissible maneuver and used a best-effort command. Counted per aircraft-step; never called safe. |

### Risk metric

The primary risk metric is **attributable in-flight events per controlled flight-hour** inside a fixed measurement window, with the run as the independent replicate. Two alternatives were rejected:

- *Fraction of runs with at least one event* saturates with fleet size: direct goal flight goes from 3 % of runs at 10 aircraft to 100 % at 100 and 200 in the iteration-01 data. Pooled across fleet sizes, it mostly measures which fleet sizes were included.
- *Events per encounter* needs a validated encounter definition and encounter-rate model. That is the standard approach for detect-and-avoid assessment (risk ratios on encounter sets, e.g. ASTM F3442 for small UAS against crewed aircraft), and it is on the roadmap.

Simulated contacts are not mid-air collisions. Converting them to collision probabilities needs a validated vehicle and encounter model plus a P(collision | contact-geometry) term.

### "Safest"

There is no defensible "safest controller" in the abstract. Safety depends on the operating domain and the service delivered, and every result has sampling uncertainty. The narrowest defensible statement is:

> Within the declared domain and model, configuration X had a lower attributable event rate than Y at matched served throughput, and the uncertainty intervals do not overlap.

Even that is a statement about the model. This repository reports frontiers and per-cell estimates, and does not rank controllers as "safest".

### "Airspace capacity"

> The highest offered demand (operations per hour) at which, for the declared domain, (i) the upper confidence bound on the attributable event rate is below a stated target, and (ii) service requirements hold: completion, delay, and no growing backlog over the window.

Capacity is conditional on the domain, the assumption regime, the requirements and the tested grid. It is never extrapolated beyond tested demand levels, and a failing lower level is not rescued by a passing higher one. Occupancy (aircraft airborne at once) is reported separately; it relates to throughput through the residence time (Little's law), which itself grows with delay. Short windows cannot show long-run stability.

### "Proven"

Reserved for mathematical statements with explicit assumptions. This repository contains two such statements, both conditional and both limited to the model plant:

1. **Enclosure soundness (planner).** If every other aircraft's true acceleration, including wind, stays within the assumed bound *A*, and reports stay within their declared position and velocity error bounds, then any admissible candidate keeps the declared separation from every *held* track over the planning horizon. This holds up to the ownship disturbance bound and the per-step chord-and-curvature screening, which is conservative. It says nothing about untracked aircraft, fallbacks or beyond the horizon. Receding-horizon admissibility is not recursive feasibility.
2. **Hover invariance (recovery).** For the sampled double integrator with the stated feedback and an acceleration disturbance of norm at most *d*, a computed ellipsoid is invariant at sample instants, provided the feedback stays unsaturated (see [`recovery.py`](../dense_uav_ops/recovery.py)). This applies to a static environment only.

Simulation outcomes are *observed*, not proven. Passing unit tests shows that the implementation behaves as specified on the tested cases. Zero observed events in N runs bounds a rate statistically; it does not prove the event impossible.

### "Standard"

Standards are consensus documents produced by standards bodies, for example ASTM F38, RTCA SC-228, EUROCAE WG-105 and ISO/TC 20/SC 16. Relevant existing documents include:
- ASTM F3411 (Remote ID);
- ASTM F3548 (USS strategic coordination);
- ASTM F3442/F3442M (detect-and-avoid performance for small UAS against crewed aircraft), which uses risk ratios validated by encounter modelling.

This project cannot write a standard. At most it can supply:
- an open, reproducible evaluation method;
- configurable scenario sets;
- frontier evidence that a committee could examine.

Its UAS–UAS separation thresholds are research inputs. We are not aware of an agreed UAS–UAS tactical well-clear definition comparable to the UAS–crewed-aircraft one, which is itself a reason to treat thresholds as variables.

## Evidence ladder

Every claim in this repository is labelled by the highest level it has reached.

| Level | Name | What it means here | Status |
|---|---|---|---|
| 0 | Implemented | Code exists and runs. | All listed features |
| 1 | Tested behaviour | Unit and integration tests check specified behaviour on constructed cases. | Engine, planner, surveillance, campaign tooling |
| 2 | Simulation evidence | Pre-declared design, independent seeds, complete grids, uncertainty reported, under the declared model. | frontier-01 and frontier-02 (pilots, 3 seeds per cell); historical sets with caveats |
| 3 | Model validation | Planner and plant assumptions checked against higher-fidelity simulation (e.g. PX4 SITL) or hardware-in-the-loop; model-mismatch experiments. | Not started |
| 4 | Flight evidence | Instrumented flights with independent truth, at conservative densities. | Not started |
| 5 | Operational evidence | Encounter models and risk estimates from real traffic data; independent replication. | Not started |
| — | Conditional mathematics | Statements proved under explicit assumptions (above). | Two statements, model plant only |

Standards-relevant claims would need levels 3–5 together with rare-event estimation. To show an event rate below *r* per flight-hour with zero observed events needs about 3/*r* independent flight-hours (more when events cluster). That is about 30,000 flight-hours for *r* = 10⁻⁴, and naive simulation cannot reach the rates relevant to crewed aviation. Importance sampling on validated encounter models, the method used in detect-and-avoid standards work, is the realistic route.

## References

- ASTM F3442 — Standard Specification for Detect and Avoid System Performance Requirements: <https://store.astm.org/f3442-25.html>
- Weinert et al., *Well-Clear Recommendation for Small Unmanned Aircraft Systems Based on Unmitigated Collision Risk*, J. Air Transportation (2018): <https://www.researchgate.net/publication/326921896>
- MIT Lincoln Laboratory, *Uncorrelated Encounter Model of the National Airspace System*: <https://www.ll.mit.edu/r-d/publications/uncorrelated-encounter-model-national-airspace-system-version-10>
- *A Review of Detect and Avoid Standards for Unmanned Aircraft Systems*, Aerospace 12(4):344 (2025): <https://www.mdpi.com/2226-4310/12/4/344>
- ASTM F3411 (Remote ID) and F3548 (USS interoperability) scope pages: <https://store.astm.org/f3411-22a.html>, <https://store.astm.org/f3548-21.html>
