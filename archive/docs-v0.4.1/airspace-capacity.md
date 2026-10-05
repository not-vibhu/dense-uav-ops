# Conditional airspace capacity

This is a configurable research metric for Civil Aviation and Public Safety experts. An assessment identifies the largest **tested offered demand** that satisfies the declared safety, service, surveillance and timing requirements under a specified traffic and operating profile. It also reports measured throughput and concurrent occupancy separately. It does not calculate a universal or certified safe aircraft count.

## Definition and units

Let θ contain the volume, routes, obstacles, fleet capabilities, compliance, cooperation, surveillance, weather, hardware timing and background manned demand. Let R contain acceptance requirements. For offered UAS rate λ and managed admission limit L, simulate each required scenario independently across declared random seeds:

\[
\widehat C_{\mathrm{UAS}}(\Theta,R)
=\max_{(\lambda,L)\in G}\{\lambda:\ \text{every required profile meets }R\}.
\]

G is the explicit tested grid. Capacity is conditional on the supplied profiles Θ, controller and experiment window. There is no monotonicity assumption: a passing high rate does not qualify an untested or failing lower rate. Every cell remains visible. An empty passing set is reported as **not demonstrated**, never as proof of zero physical capacity.

This first capacity implementation evaluates the existing deterministic predictive maneuver library. It does not evaluate the imitation/MAPPO actors or requalify their batch results. Controller improvements should be evaluated against this metric on independent operating profiles and seeds before using any resulting capacity increase.

| Output | Meaning |
|---|---|
| UAS offered operations/hour | Scheduled new drone mission requests; an operation is one traversal, not one control update |
| Total offered operations/hour | UAS demand plus the profile's scheduled manned demand |
| Observed exits/hour | Completed exits inside the measurement window × 3600 / measurement seconds, separately for UAS, manned and their total |
| Concurrent occupancy | Peak actual airborne UAS, manned and combined counts; average total count is integrated aircraft-seconds / measurement seconds |
| Admission limit | Total occupancy threshold used to withhold **controlled UAS** entry; other traffic can enter and exceed it |
| Cohort completion | Fraction of all mission requests originating in the measurement window completed by the end of the drain window |
| Queue wait | Request-to-admission delay; unadmitted requests retain their full observed waiting time |
| Backlog growth | Outstanding requests at measurement end minus outstanding requests at measurement start, including airborne unfinished missions |

The per-profile output includes the highest passing total offered demand including manned traffic. The multi-profile envelope reports the common UAS demand supported under **every** declared background condition. When manned demand differs between profiles, there is no single background-independent total capacity number. A supported observed peak is an achieved concurrency value at a tested passing operating point, not a proven maximum concurrent count.

In a stable long-run system, Little's law relates average occupancy, served arrival rate and residence time. This harness does not use that relation to invent capacity from a fleet count. It simulates arrivals explicitly and checks backlog and service.

## Configurable inputs

| Group | Implemented conditions | Effect |
|---|---|---|
| Operating airspace | Square horizontal extent, volume altitude bounds, UAS altitude band/route width, manned lateral offset, scenario routes, spherical obstacles | Determines traversal time, crossing geometry, planned segregation and available maneuvering space |
| Drone capabilities | Multirotor/fixed-wing mixture, cruise/max/min speed, acceleration, turn/climb limits, body radii, endurance | Limits feasible maneuvers and detects capability or endurance violations |
| Compliance | Probability a UAS conforms to the modeled goal-following or accepted-control behavior | Nonconforming UAS introduce bounded lateral changes independently of negotiation capability |
| Cooperation | Probability a UAS can participate in the controlled fleet | Only cooperative **and** conforming UAS accept the predictive controller and entry queue |
| Manned background | Demand rate, helicopter or light fixed-wing class label, speed limits, acceleration/turn/climb envelope, body radius, altitude, protection distance | Protected exogenous trajectories occupy the same airspace and reduce available service |
| Surveillance | Position/velocity error bounds, refresh period, latency, loss, range, manned detection fraction, pre-entry surveillance lookahead | Determines available tracks and their age-growing uncertainty tubes |
| Aircraft hardware | Actuator time constant, per-mission control failure probability/time | Applies delayed or held inputs; failure exposure and resulting kinematic errors are visible |
| Compute hardware | Executing-host timings, named target profile, explicit timing multiplier, command deadline | Applies a held-command watchdog on missed deadlines; multiplier is a synthetic sensitivity assumption |
| Weather | Bounded wind acceleration, applied in the wind-gust scenario | Disturbs trajectories; existing predictive enclosure permits at most 0.8 m/s² |
| Requirements | Protection distances, cohort completion, queue wait, backlog growth, modeled run failure probability and confidence | Defines the passing envelope and evidence strength |

“Compliance” here is a modeled behavioral conformance parameter. It does not establish legal compliance, airworthiness, Remote ID conformance or authenticated intent. Cooperation is sampled independently and does not reduce other aircraft's disturbance bounds. The profile's class labels and bounds are assumed known; the harness does not estimate aircraft type from Remote ID.

A manned aircraft is **never controlled, negotiated with or delayed by UAS admission**. Its observations represent an external fused surveillance channel, which could eventually ingest radar, ADS-B, optical or other surveillance. They are not Remote ID observations. No universal ADS-B equipage is assumed. The current model uses common conservative position/velocity bounds and one synthetic shared regional refresh/latency channel. It is not an RF receiver, ASTM, ADS-B or sensor coverage conformance test.

The protection distance for a pair is at least the physical body-radius sum; a pair involving manned traffic additionally uses the configured manned distance. The independent oracle checks minimum relative distance through each constant-acceleration step, along with obstacles and body-volume clearance. The predictive library conservatively inflates reported manned traffic by the protection distance. These are spherical research thresholds, not DAIDALUS well-clear logic or jurisdictional separation minima. They do not model wake turbulence.

## Gates and evidence

An observed passing run requires all of the following:

- No physical collisions, protected-distance breaches, obstacle collisions or body-volume exits for **any traffic**, including legacy–legacy and UAS–manned pairs.
- No unresolved predictive maneuver library, kinematic violation, control failure exposure or endurance exceedance.
- No missed command deadline, unobserved airborne manned step or total occupancy overflow.
- Nonempty measurement demand cohorts, UAS and manned completion at the specified threshold, queue wait within its limit and acceptable backlog growth.
- Full modeled manned detection coverage when manned demand is present. A lucky run with an incomplete-detection profile cannot pass this assumption gate.

Hardware time includes surveillance update, admission, goal control, predictive selection and actuator/watchdog preparation. It excludes ground-truth oracle checks, trajectory integration, reporting and source loading. The host measurement multiplied by a target factor is **not calibrated worst-case execution time**. Run evidence records Python, OS, source hash and exact inputs. Timing under host load can change outcomes through the watchdog.

The statistical gate treats a complete fixed-duration independent scenario run as one Bernoulli trial. A failure is any safety-counter event, including lost surveillance, timing and occupancy authority. Aircraft and time steps in the same run are dependent and are not counted as independent evidence. For k failures in n runs, the one-sided exact Clopper–Pearson upper bound is calculated from the binomial CDF. For zero failures:

\[
p_{\mathrm{upper}}=1-\alpha_{\mathrm{cell}}^{1/n},\qquad
\alpha_{\mathrm{cell}}=\frac{1-\text{confidence}}{\text{number of tested cells}}.
\]

The Bonferroni allocation protects simultaneous selection across the full grid. Paired seeds across cells are permitted; independence is assumed within each cell. Every profile and every replicate must still meet the hard/service gates. A single zero-failure cell needs **299 independent runs** to put its upper modeled run-failure probability below 1% at 95% confidence. Multiple tested cells require more. This is not a failure probability per flight or flight-hour and is not an aviation target level of safety. Do not translate the example 1% per research run into an operational safety criterion.

The report therefore separates:

1. Highest tested demand passing observed requirements.
2. Highest tested demand passing the additional statistical requirements.
3. Operationally certified capacity, always **not established** by this implementation.

Source and evidence hashes expose changes when compared against trusted copies. They are tamper-evident checksums, not signed, independently witnessed or tamper-proof evidence. The tactical audit architecture still requires those production mechanisms.

## Run the expert lab or CLI

```bash
.venv/bin/python -m airspace_capacity --serve --out artifacts/capacity-lab
# Open http://127.0.0.1:8766

.venv/bin/python -m airspace_capacity \
  --profile profiles/capacity-research.json \
  --scenarios crossing corridor urban manned_intrusion sensor_outage wind_gust \
  --rates 120 360 720 --occupancy-limits 10 50 100 200 \
  --seeds 7000 7001 7002 --out artifacts/my-capacity-study
```

Editable installation also exposes `airspace-capacity`. The lab provides essential condition/requirement fields plus full profile JSON, progress, a requirement-level results table and JSON export. Results are saved locally; the server binds only to loopback. Set additional fields, including obstacles, endurance, physical radii, manned class and hardware failures, through the full JSON editor. “Apply JSON to fields” synchronizes its essential values; visible fields take precedence at assessment time.

Use `uas_altitude_min_m`, `uas_altitude_max_m` and `uas_route_half_width_m` to represent planned drone altitude bands and route distributions, and `manned_route_lateral_offset_m` for the background transit. Null UAS values select the default body-cleared altitude distribution and route width. `profiles/capacity-layered-corridor.json` is a separate hypothetical layered corridor with low-altitude drones and a light fixed-wing manned transit above them. Its separation is an input assumption; it is not an authorized corridor design.

To compare multiple operating conditions as one required envelope, use `{"profiles": [<profile>, <profile>, ...]}` in a CLI profile file. Give profiles meaningful names and retain every required condition. No profile can be omitted merely because it fails. Distinct output directories preserve earlier evidence. Interrupted campaigns retain raw completed rows but cannot produce a complete passing summary.

The default low rates are software/research examples; occupancy limits of 100 or 200 do not force 100 or 200 aircraft to appear. Raise offered rates and inspect the **actual peak occupancy** to exercise density. `profiles/capacity-density.json` supports 3,600 and 10,800 UAS requests/hour over a short window. Each run is limited to 500 total scheduled operations; split larger studies into independent scenario runs instead of silently dropping traffic.

Files are `manifest.json`, `runs.jsonl`, `summary.json` and `REPORT.md`. All supplied profiles, seeds and grid cells must be present exactly once. Summaries reject missing, duplicated or unexpected runs. Source changes during a campaign invalidate summarization. The new package leaves the existing `swarm_sim` source and pretrained checkpoints pinned to their previous source; those batch experiments are not reused as mixed-manned capacity evidence.

## Model boundaries and calibration

Arrivals are periodic streams with independently randomized phases, rounded up to control steps. They are not a Poisson or bursty demand model; unusually low rates may yield no measurement cohort and cannot qualify capacity in a short window. Warmup, measurement and drain windows must align with the simulation step. Manned demand continues through the measurement window, then all arrival streams stop for drainage. Service is calculated against measurement-origin cohorts; exit rates count every exit occurring during measurement, including warmup-origin flights.

Entry and exit points are abstract portals inset inside the outer volume. Manned pre-entry trajectories are sensed with bounded noisy measurements within the configured lookahead/range. Pre-entry and post-exit conflict risk, holding areas, takeoff/landing, emergency landing, terrain/geodetic datum errors, wreckage, RF interference, human workload, ATC clearance and aircraft aerodynamics are not assessed. Completed missions disappear at their portal. Diagnostics continue after collisions. Sphere obstacles and simplified wind do not constitute a realistic urban or emergency-response digital twin.

The inherited finite maneuver library has no verified joint invariant backup or infinite-horizon traffic guarantee. Admission tests only an immediate reported-traffic conflict screen; it does not prove recursive feasibility. Actuator lag and held commands can invalidate forecast controls, so their effects are measured and rejected when requirements fail. The simulator does not validate the declared acceleration bounds against real aircraft. One profile contains one manned class; assess different class conditions separately or extend the traffic model before claiming a simultaneous multi-class mixture.

For an operational prediction, experts must first supply measured surveillance integrity/coverage, representative traffic and emergency demand, validated aircraft and disturbance envelopes, hardware benchmarks, applicable jurisdiction and approved separation/risk criteria. Then extend and validate demand bursts, entry/exit areas, route and landing capacity, outages, multiple manned classes, wake and human/ATC behavior. Validate independently on new seeds and field/hardware data after policy/model selection; the current family-wise bounds do not protect repeated adaptation using the same evidence. A finite-window backlog check is not proof of long-run queue stability or exhaustive scenario coverage.

## Primary references

NASA lists a throughput-based low-altitude capacity study alongside conformance-monitoring and target-risk research in its [sUAS research publications](https://www.nasa.gov/ames/aviationsystems/publications/suas/). This implementation's precise gate definitions and statistical unit are our research design, not a NASA-endorsed metric.

The [FAA/NextGen UTM ConOps v2.0](https://www.nasa.gov/wp-content/uploads/2024/04/2020-03-faa-nextgen-utm-conops-v2-508-1.pdf) discusses strategic/tactical services and surveillance quality/coverage. It provides integration context; it does not validate these numerical inputs.

For US Part 107 context, the FAA identifies [yielding right of way and avoiding manned aircraft](https://www.faa.gov/uas/commercial_operators). The harness's manned priority is a research policy; applicable operational rules and any airspace authorization must be supplied for the intended jurisdiction and operation.
