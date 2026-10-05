# Workflows, configuration and interpreting results

## Install

Python 3.11 or newer.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .                    # simulator (NumPy only)
.venv/bin/python -m pip install -e '.[analysis]'        # + matplotlib for figures
.venv/bin/python -m pip install -e '.[learning]'        # + PyTorch for learned rankers
.venv/bin/python -m pip install -e '.[archive]'         # + cryptography to validate archived v0.4 evidence
```

DAIDALUS baseline (optional; needs git, make and a C++14 compiler). It downloads NASA DAIDALUS at a pinned revision under its own licence:

```bash
.venv/bin/python scripts/build_daidalus.py
.venv/bin/python -m dense_uav_ops daidalus-check
```

## Run one experiment

```bash
.venv/bin/python -m dense_uav_ops run --profile profiles/frontier-base.json \
  --set demand.uas_per_hour=2880 --set assumptions.traffic_acceleration_mps2=1 \
  --out artifacts/run.json --replay artifacts/run.html
```

`--set PATH=VALUE` overrides any field (values are parsed as JSON). `show` prints the fully resolved configuration without running. The replay is a self-contained HTML file: a top-down view, altitude as shade, events highlighted.

## Configure an operating domain

A profile is a JSON object that overrides any subset of the defaults below; unknown keys are rejected. Examples in [`profiles/examples/`](../profiles/examples):

| Profile | What it shows |
|---|---|
| `urban-obstacles` | larger volume, spherical building volumes; controlled aircraft route around them |
| `mixed-equipage-manned` | 50 % cooperative UAS, 5 % noncompliant, manned transits above the UAS band |
| `degraded-surveillance` | slower, lossier, less accurate reports and an 8 s outage |
| `delivery-corridor` | long two-way corridor, faster fixed-wing fleet, stronger wind, actuator lag |

### Reference (SI units)

| Section.field | Default | Meaning |
|---|---|---|
| `airspace.side_m`, `floor_m`, `ceiling_m` | 400, 30, 120 | Square volume centred on the origin |
| `airspace.obstacles` | `[]` | Spheres `[x, y, z, radius]` |
| `demand.uas_per_hour` | 720 | Offered UAS operations per hour |
| `demand.arrivals` | `poisson` | or `periodic` |
| `demand.pattern` | `crossing` | `crossing`, `corridor` (one way), `head-on` (two way) |
| `demand.entry_inset_m`, `exit_inset_m` | 15, 25 | Entry and exit portals inside the boundary |
| `demand.uas_altitude_min_m`, `max_m` | auto | UAS altitude band (default: whole volume minus margins) |
| `demand.lane_half_width_m` | auto | Lateral spread of routes |
| `demand.manned_per_hour`, `manned_altitude_m`, `manned_lateral_offset_m` | 0, 100, 0 | Manned straight transits along x |
| `demand.manned_lookahead_s` | 15 | Manned aircraft are visible to surveillance this long before entering |
| `fleet.fixed_wing_fraction` | 0.4 | Share of UAS that are fixed-wing |
| `fleet.cooperative_fraction` | 1.0 | Share equipped and participating |
| `fleet.noncompliant_fraction`, `noncompliant_acceleration_mps2` | 0, 2 | Share that wanders off route, and how hard |
| `multirotor.*` | 8 m/s cruise, 12 max, 4 m/s², 1.2 m | Envelope and body radius |
| `fixed_wing.*` | 8 cruise, 6 min, 12 max, 4 total, 2/3/2 lon/lat/vert m/s², 35°/s, 3 m/s climb, 2.5 m | Envelope and body radius |
| `manned.speed_mps`, `radius_m` | 35, 6 | Manned transit |
| `surveillance.period_s`, `latency_s`, `loss` | 1.0, 0.2, 0.03 | Report interval and delay (both multiples of `dt`), loss |
| `surveillance.position_error_m`, `velocity_error_mps`, `bias_fraction` | 1.5, 0.3, 0.6 | Declared error bounds; share of the position bound that is persistent bias |
| `surveillance.range_m` | 1000 | Coverage radius around the origin |
| `surveillance.manned_detection`, `uncooperative_detection` | 1, 1 | Probability each manned or non-cooperative aircraft is ever reported |
| `surveillance.uncooperative_error_scale` | 1 | Error-bound multiplier for non-cooperative UAS |
| `surveillance.outage_start_s`, `outage_duration_s` | 0, 0 | Feed outage |
| `environment.wind_mps2`, `wind_period_s` | 0.4, 60 | Uniform rotating wind acceleration on UAS |
| `environment.actuator_time_constant_s` | 0 | First-order actuator lag |
| `environment.command_drop_probability` | 0 | Seeded missed control updates (hold previous command) |
| `assumptions.traffic_acceleration_mps2` | 4 | **The frontier variable**: acceleration the planner assumes any other aircraft can have |
| `assumptions.own_disturbance_mps2` | 0.8 | Ownship disturbance the planner allows for |
| `assumptions.horizon_s` | 2.4 | Planning horizon |
| `controller.kind` | `predictive` | `none`, `predictive`, `daidalus`, `recurrent`, `graph` |
| `controller.*_weight` | 1, .03, .1, .1 | Planner cost preferences (they rank admissible candidates only) |
| `controller.checkpoint` | — | Learned model for `recurrent` and `graph` |
| `controller.daidalus_period_s`, `daidalus_manifest` | 1, `artifacts/daidalus/manifest.json` | DAIDALUS guidance rate and build manifest |
| `admission.occupancy_limit` | 500 | Cap on estimated airborne aircraft for controlled entries |
| `admission.entry_check` | `spacing` | `none`, `spacing`, `clearance`, `recovery` (each includes the previous) |
| `admission.spacing_horizon_s` | 1 | Straight-ahead window the entry must stay clear for (spacing rule) |
| `requirements.separation_m`, `manned_separation_m` | 10, 60 | Loss-of-separation thresholds (events, not regulations) |
| `requirements.goal_radius_m` | 3 | Arrival tolerance at exits and waypoints |
| `window.dt_s`, `warmup_s`, `measurement_s`, `drain_s` | 0.2, 60, 240, 90 | Step and windows; events and rates count only the measurement window |
| `seed` | 0 | All randomness derives from it |

## Run a campaign

A campaign spec declares a base profile, *arms* (non-Cartesian treatments), a Cartesian *grid* of dotted settings, and *seeds*:

```json
{
  "name": "my-study",
  "base_profile": "profiles/frontier-base.json",
  "base": {"surveillance": {"loss": 0.1}},
  "arms": [{"name": "A0", "set": {"assumptions.traffic_acceleration_mps2": 0}},
           {"name": "A4", "set": {"assumptions.traffic_acceleration_mps2": 4}}],
  "grid": {"demand.uas_per_hour": [720, 2880]},
  "seeds": [1, 2, 3]
}
```

```bash
.venv/bin/python -m dense_uav_ops campaign my-study.json --out experiments/my-study --workers 8
.venv/bin/python -m dense_uav_ops validate experiments/my-study --rerun 3
.venv/bin/python -m dense_uav_ops publish experiments/my-study     # gzip the log, write checksums
```

- Every declared run is written to `manifest.json` before any simulation starts.
- `runs.jsonl` is appended as runs finish, and re-running the same command resumes.
- An output directory holding a different campaign, or results from a different simulation core, is refused.
- `summary.json` and `REPORT.md` are written only when every declared run is present exactly once.
- `validate` rebuilds the summary from the raw runs, checks every run ID against its configuration and the checksums, and optionally re-simulates runs to confirm exact reproduction. Re-simulation requires the recorded simulation core.

## Interpret the metrics

Per run (`metrics` in each run record) and per cell (`summary.json`):

| Metric | Meaning | Read it with |
|---|---|---|
| `attributable_uas_los` (per controlled flight-hour) | In-flight LoS episodes with ≥ 1 controlled aircraft and no manned aircraft | The per-1000-operations version, because slow arms accumulate flight-hours |
| `entry_phase_attributable_uas_los` | The same, within one report interval of an aircraft's entry, before surveillance can report it | Equipage: mostly uncontrolled aircraft appearing next to controlled ones |
| `attributable_uas_los_per_1000_completed` | Same events per 1000 controlled operations completed in the window | Completion; it is undefined when nothing completes |
| `attributable_uas_contacts` | Body-overlap episodes, same attribution | Very few events per cell; intervals are wide |
| `all_los_per_uas_hour` | Every LoS, including between uncontrolled aircraft | Equipage: uncontrolled–uncontrolled risk is outside the system's authority |
| `uas_throughput_per_hour` | UAS exits during the window, scaled to an hour | Offered demand: throughput below demand means backlog |
| `controlled_completion_fraction` | Completed / offered controlled operations from the window cohort | Drain length |
| `mean_delay_completed_s`, `mean_delay_lower_bound_s` | Completion − (request + nominal time); the lower bound counts unfinished operations at the end of the drain | Large gaps between the two mean congestion |
| `fallback_fraction` | Controlled aircraft-steps with no admissible maneuver | The planner's assumptions: high values mean the assumption leaves no room |
| `daidalus_unresolved_fraction` | DAIDALUS decisions with no conflict-free heading | — |
| `unknown_traffic_seconds` | Airborne aircraft-seconds inside the volume with no held track | Surveillance settings |
| `interval_if_independent` | Exact Poisson interval for a pooled rate | Optimistic, because events cluster within runs; compare per-run values |
| `runs_with_attributable_uas_contact` | k / n runs, with Clopper–Pearson interval | Runs are the independent unit |

What the numbers do **not** mean:
- They are not operational collision probabilities. They are not per-flight-hour risk for real aircraft.
- They are not a capacity of any real airspace.
- With a few seeds per cell, a zero is weak evidence: zero events in *H* flight-hours bounds the rate only at about 3.7/*H* (95 %).
- Cells with different demand have different traffic. Compare arms within a cell (they share seeds and noise), and compare across demand only as a frontier.

## Train learned rankers (optional)

Learned policies rank admissible candidates only. Their training seeds are recorded and refused at evaluation.

```bash
.venv/bin/python -m dense_uav_ops train-imitation --profile profiles/frontier-base.json --set demand.uas_per_hour=1440 --out artifacts/models/imitation.json
.venv/bin/python -m dense_uav_ops train-mappo --profile profiles/frontier-base.json --set demand.uas_per_hour=1440 --initial artifacts/models/imitation.json --out artifacts/models/mappo.json
.venv/bin/python -m dense_uav_ops train-graph --profile profiles/frontier-base.json --set demand.uas_per_hour=1440 --out artifacts/models/graph.json
.venv/bin/python -m dense_uav_ops train-preferences --profile profiles/frontier-base.json --set demand.uas_per_hour=1440 --out artifacts/models/preferences.json
.venv/bin/python -m dense_uav_ops run --set controller.kind=recurrent --set controller.checkpoint=artifacts/models/mappo.json --set seed=500
```

## Validate historical evidence

```bash
.venv/bin/python scripts/validate_evidence.py          # all sets, each against its own archived source
.venv/bin/python scripts/reanalyze_history.py          # numbers cited in the technical report
```

## Tests

```bash
.venv/bin/python -m unittest discover -s tests
```

Tests check specified behaviour on constructed cases: oracle exactness, envelopes, surveillance delay and bounds, planner information boundaries and admissibility, reproducibility, campaign integrity, DAIDALUS heading logic and the learning safeguards. Passing tests does not demonstrate operational safety.
