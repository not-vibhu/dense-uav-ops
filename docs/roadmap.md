# Roadmap

Ordered by the value of the evidence each step produces. Every step has an exit criterion, the evidence needed before building on it. Nothing here is a commitment to a date.

## 0. What the pilot changed

frontier-01 and frontier-02 found the worst-case assumption dominated by constant-velocity prediction with fast replanning. Measured deviations over the replanning interval were about 1 m, well inside the separation margin. That result rests on idealizations, and steps 1 and 3 must test them before anything else:
- smooth maneuvers;
- fresh reports;
- exact own state;
- no tracking error.

The specific threats to test first:
1. Abrupt and adversarial maneuvers, such as sudden 4 m/s² turns toward ownship.
2. Long report ages (2–5 s) and outages.
3. Ownship navigation and tracking error (model mismatch).
4. A *verified* recovery in place of the best-effort fallback, which might change the conservative arm's risk.

## 1. Frontier campaign at decision-grade sample sizes (next)

frontier-01 is a pilot: 3 seeds per cell, about 1–15 controlled flight-hours per cell, one geometry. Its job is to show the frontier's shape and size this campaign.

- **Design.**
  - Same arms, plus assumed acceleration 0.5 and 3 m/s², a 4.8 s horizon and a 3 s horizon.
  - The four threats in step 0 as factors: abrupt-maneuver intruders, report age, ownship error, and the fallback type (best effort versus verified recovery).
  - Demand on a finer grid around where service collapses.
  - Latency 0.2 / 1.0 / 2.0 s; cooperative fraction 1.0 / 0.5 / 0.2.
  - At least 20 seeds per cell. Set the number by the target interval width: to separate rates of 1 and 2 events per flight-hour at 95 %, a cell needs roughly 30–50 controlled flight-hours.
  - A second geometry (`head-on` corridor) as a replication domain.
- **Analysis declared in advance.** Primary metric: attributable UAS LoS per 1000 completed operations and per flight-hour. Report cluster-bootstrap intervals over seeds. Show frontiers per facet. Hold out one geometry for confirmation.
- **Compute.** frontier-01's 360 runs took 36 minutes on 8 cores. A 20-seed campaign is about 7× that: run it unattended with `--workers`, or split across machines by arm (the campaign resumes and refuses mixed sources).
- **Exit criterion.** Frontier curves whose ordering is stable across seeds and across both geometries, or a documented failure to replicate.

## 2. Coordination as an assumption contract

The evidence so far says the information model limits density more than the avoidance algorithm does. Coordination matters if it makes optimistic assumptions *true*.

- **Implement a contract regime.**
  - Controlled aircraft broadcast their chosen plan through the feed, with the same delay and loss as reports.
  - They commit to stay within a deviation bound of it until the next broadcast.
  - Others predict cooperating traffic along the broadcast plan with that bound, and keep worst-case or constant-velocity sets for everyone else.
- **Measure** frontier shift against assumption-only regimes, and contract violations under faults (lost broadcasts, lag, wind, command drops).
- **Exit criterion.** A measured frontier gain at matched risk, with violation rates reported and the failure behaviour characterised. Treat the earlier signed-certificate protocol (archived) as one possible transport for this, not as the contribution.

## 3. Richer dynamics and model mismatch

- **Separate the planner's model from the plant.**
  - Plant: per-vehicle second-order tracking with lag, saturation and overshoot, fitted to logs.
  - Planner: the current point mass.
  - Report how admissibility and events change.
- **Fit envelopes** (tracking error, turn and climb performance, navigation error) from PX4 and ArduPilot software-in-the-loop (SITL), then from flight logs.
- **Add an ownship navigation-error model**, and replace sinusoidal wind with spatially varying stochastic fields.
- **Exit criterion.** The frontier's qualitative ordering survives realistic mismatch, or the conditions under which it does not are documented.

## 4. Simulator integration

- **Gazebo with PX4 SITL** for a small number of encounters, using a thin adapter that sends this project's planner commands as velocity or acceleration setpoints and reads back states. Use it to validate the envelopes in step 3, not for parameter sweeps; it is orders of magnitude slower than the point-mass engine.
- **NVIDIA Isaac Sim** only if perception (camera or radar detect-and-avoid) becomes a research variable. It adds no value for kinematic separation studies.
- Keep the fast engine as the sweep workhorse. Validate it against higher fidelity on sampled cells (paired runs, same seeds and initial conditions).

## 5. Encounter models and rare-event estimation

- Build or adopt encounter models for low-altitude traffic. Candidates: the MIT Lincoln Laboratory uncorrelated encounter models, Remote ID or ADS-B datasets where available.
- Move from per-flight-hour rates to per-encounter risk ratios, the metric used in detect-and-avoid standards work. Use importance sampling to reach small probabilities.
- **Exit criterion.** Risk-ratio estimates with intervals for each regime on validated encounter sets.

## 6. Assurance

- **Machine-check the planner's enclosure-soundness argument and the hover lemma.** Candidates: a proof assistant, or interval arithmetic over the implementation. Add sampled-data and floating-point margins.
- **Add a runtime monitor** that flags violations of the assumed acceleration bound, using observed track residuals. That turns an *assumption* into a *monitored condition* with a defined response.
- **Recovery for fixed-wing aircraft** (loiter or escape sets), which today have finite-horizon turns only.
- **Exit criterion.** Each guarantee stated with assumptions that are monitored at run time, and a measured response when they fail.

## 7. Toward a policy and standards (hypothesis)

Only after steps 1–5. If a regime shows a robust frontier gain under validated models:
- write it as a candidate *operating rule*: what aircraft may assume, what they must guarantee, and the monitoring that backs it;
- publish the evidence package;
- seek review from people who work on ASTM F38 and RTCA SC-228 detect-and-avoid and UTM standards.

This project's output would be evidence and a method, not the standard.

## Housekeeping

- Continuous integration runs the tests and validates every retained evidence set against its archived source. Keep both green.
- New campaigns go in new `experiments/<name>/` directories with a pre-registered design section, followed by a `publish` step. Never overwrite a published set; supersede it with a new one and say why.
