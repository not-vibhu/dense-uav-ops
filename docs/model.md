# Model, assumptions and limits of transfer

This page describes what `dense_uav_ops` simulates, what it idealizes, and how plausibly each part transfers to physical aircraft. Code references are to [`dense_uav_ops/`](../dense_uav_ops).

## Architecture

```
profile (JSON) ──► config.Experiment ──► traffic.build ──► engine.simulate ──► run result (JSON)
                                             │                 │
                         surveillance.Feed ◄─┘                 ├─ planner.plan        (maneuver library)
                         (delayed, lossy,                      ├─ daidalus.Guidance   (NASA DAIDALUS bridge)
                          bounded-error reports)               ├─ learning.*          (optional ranking of admissible candidates)
                                                               ├─ recovery.check      (finite recovery + hover lemma; entry rule)
                                                               └─ oracle.*            (true-state event checks)
campaign.run_campaign ── declared grid ──► runs.jsonl ──► summary.json / REPORT.md ──► validate / publish
```

There is one engine. The v0.1–v0.4 simulators (`swarm_sim`, `airspace_capacity`, `dense_ops`) are archived; see [`archive/`](../archive/README.md).

## Information boundaries

| Who | Knows | Does not know |
|---|---|---|
| Controlled aircraft (planner, DAIDALUS, learned actor) | Its own exact position and velocity; reports from the shared feed; static class labels (radius, manned, fixed-wing, controlled) | Other aircraft's true states; untracked aircraft; other aircraft's intentions or plans |
| Admission service | The feed, plus the entry states of aircraft it has itself admitted and that are not yet reported | True states |
| Oracle | True states | — (it only scores outcomes) |
| Training critics | A global truth summary | — (never used at execution) |

Host compute time is measured but never changes a simulated outcome, so results are identical across machines and loads. Control-loop timing faults are modelled explicitly instead, as a seeded `environment.command_drop_probability`.

## Components

**Vehicles** ([`vehicles.py`](../dense_uav_ops/vehicles.py)). Point masses with acceleration held constant over each 0.2 s step.
- *Multirotors* have a total acceleration bound (4 m/s²) and a speed bound (12 m/s).
- *Fixed-wing UAS* also have a minimum horizontal speed (6 m/s), separate longitudinal, lateral and vertical acceleration bounds, a 35°/s turn-rate bound and a 3 m/s climb bound.
- *Manned aircraft* fly scripted straight transits.

There is no attitude, thrust, aerodynamics, battery or autopilot model, and commanded accelerations are achieved exactly (optionally with a first-order actuator lag).

**Traffic** ([`traffic.py`](../dense_uav_ops/traffic.py)). Poisson (or periodic) arrivals at an offered rate. Routes are `crossing` (random entry on any side, exit on the opposite side), `corridor` (one direction) or `head-on` (two opposing directions). Altitudes are uniform within a band, and flight is level. Equipage (`cooperative`) and behaviour (`compliant`) are drawn independently: only cooperative and compliant UAS are *controlled*. Noncompliant UAS add bounded random lateral acceleration to their route.

**Surveillance** ([`surveillance.py`](../dense_uav_ops/surveillance.py)). A single regional feed:
- reports every `period_s`;
- delivered `latency_s` later, quantized to the step;
- each report independently lost with probability `loss`;
- position error made of a persistent per-aircraft bias plus bounded noise, together within a declared bound; velocity error likewise bounded;
- a range limit and outage windows;
- separate detection probabilities for manned and non-cooperative UAS.

Tracks are dropped on an end-of-operation notice (which can itself be lost) or after 10 s without a report. There are no RF propagation, no ASTM F3411 message encoding, no receiver geometry, no false tracks and no association errors.

**Planner** ([`planner.py`](../dense_uav_ops/planner.py)). It runs every step for every controlled aircraft:
1. Roll out 22 candidate velocity targets over `assumptions.horizon_s` through the aircraft's own envelope.
2. Keep the candidates whose swept path clears, at every step:
   - every held track's assumed reachable ball, which grows as `e_p + e_v·(τ+t) + ½·A·(τ+t)²`;
   - the obstacles;
   - the volume.

   Ownship disturbance and per-step curvature are included in the clearance.
3. Pick the lowest-cost admissible candidate. The cost is deviation from nominal progress, effort, turn and climb.
4. If none is admissible, use a best-effort fallback and count it.

A conservative broad phase skips tracks that provably cannot interfere; a test confirms identical decisions with and without it. The planner does not coordinate with other aircraft and does not know their plans.

**DAIDALUS baseline** ([`daidalus.py`](../dense_uav_ops/daidalus.py), [`integrations/daidalus/`](../integrations/daidalus)). It works as follows:
- Every `daidalus_period_s` (1 s), each controlled aircraft sends its own state and its tracks within 400 m to NASA DAIDALUS. DAIDALUS assumes non-maneuvering traffic.
- The aircraft steers to the conflict-free horizontal heading nearest its desired heading, or a recovery heading if none is free, and holds it until the next update.
- Thresholds come from the research configuration [`small-uas-research.conf`](../integrations/daidalus/small-uas-research.conf) (15 m / 10 m / 3 s tau-modified well-clear). That is not a published standard.
- Only horizontal resolutions are used.

**Entry rules** ([`engine.py`](../dense_uav_ops/engine.py)). Controlled operations queue first-come-first-served and are checked every step:
- `spacing` (default): for the next 1 s the entrant's straight path must stay clear of known traffic and of the system's own recent admissions. The check allows for report errors and the physical acceleration bound, so it does not depend on the planner's assumptions;
- `clearance`: additionally, an admissible maneuver must exist;
- `recovery`: additionally, a checked recovery maneuver must exist;
- `occupancy_limit` caps the surveillance-estimated airborne count.

Uncontrolled and manned traffic enter regardless.

**Oracle and events** ([`oracle.py`](../dense_uav_ops/oracle.py)). Exact minimum distance between constant-acceleration paths within each step. A contact is an overlap of body spheres. A loss of separation (LoS) is a breach of the protection distance: 10 m UAS–UAS or 60 m with manned traffic. Both are counted once per episode, attributed by involvement (controlled / uncontrolled UAS / manned), and counted only inside the measurement window. Events within one report interval of either aircraft's entry form a separate *entry phase*, because surveillance cannot have reported the newcomer yet. Volume exits use the body sphere.

**Learning** ([`learning/`](../dense_uav_ops/learning)). Three optional rankers of *admissible* planner candidates, built on PyTorch:
- a recurrent attention actor trained by imitation then masked MAPPO;
- an attention graph ranker trained by offline federated imitation across airspace "domains";
- cross-entropy search over the four cost weights.

None can make an inadmissible candidate admissible or change thresholds, assumptions or the fallback.

## What the planner's assumption means

`assumptions.traffic_acceleration_mps2` (A) is a *belief*, deliberately decoupled from the true vehicle authority (4 m/s²):

- **A ≥ true relative acceleration** (A = 4 here): admissible candidates are separation-safe over the horizon against every held track (see "Enclosure soundness" in [research-question.md](research-question.md#proven)). The price is large protected volumes: about 33 m radius at 2.4 s horizon and 0.5 s report age.
- **A < true** (A = 0 is a constant-velocity assumption, as in DAIDALUS): protected volumes stay small. Separation is guaranteed only if neighbours do not maneuver hard within the horizon, and controlled neighbours do maneuver. Uncooperative traffic flying straight satisfies the assumption.

There is a third regime between these: cooperating aircraft *promise* bounded deviation from a shared plan, so others may assume less. It is not implemented here; it is the main coordination experiment on the [roadmap](roadmap.md).

## Plausibility of transfer to physical aircraft

| Model element | Idealization | Effect on results | What would establish transfer |
|---|---|---|---|
| Ownship navigation | Exact | Understates ownship uncertainty; real GNSS/INS error adds metres | Navigation-error model calibrated from flight logs; run with ownship error |
| Plant = planner model | The planner predicts its own motion with the true plant | No model mismatch; real autopilots track with lag and overshoot | PX4/ArduPilot SITL tracking-error envelopes; mismatch experiments |
| Fixed-wing kinematics | Point mass, turn-rate cap, no bank dynamics or stall model | Turns and speed changes are optimistic | Envelope from a 6-DOF or SITL fixed-wing model |
| Wind | Uniform, sinusoidal, bounded | Cancels in relative motion; no gusts or shear | Spatially varying stochastic wind fields |
| Surveillance | One feed; bounded errors; universal reporting by default | Optimistic coverage and integrity; no false or missing association | RF and receiver models; Remote ID field data; non-cooperative sensors |
| Other aircraft's behaviour | Straight-line routes or bounded random wander | Real traffic has structure (corridors, pads, loiter) | Encounter models from recorded traffic |
| Events | Sphere overlap / threshold breach | No collision consequence model | P(collision \| geometry), consequence models |
| Timing | Instantaneous decisions every 0.2 s | Real compute, comms and actuation delays are larger and variable | Measured on target hardware (HIL) |
| Scale | Single 400 m cell | No handoff, terrain, buildings beyond spheres | Multi-cell domains; terrain and obstacle data |

**Bottom line.** Today the *qualitative* frontier result is the most plausible part to transfer: worst-case assumptions trade service for risk, and optimistic ones trade risk for service. It follows from geometry rather than from fine dynamics. The *numbers* (rates, demand levels, delays) should not be expected to transfer. The most useful next fidelity step is to calibrate tracking and navigation error envelopes against SITL and flight logs, then keep this fast engine for large sweeps (see [roadmap](roadmap.md)). Photorealistic simulators matter for perception, which this project does not model.
