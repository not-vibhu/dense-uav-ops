# dense-uav-ops

A research simulator for the **safety–capacity frontier** of dense, low-altitude UAS traffic with mixed equipage: how much traffic can be served at a stated level of separation risk, and how that depends on what aircraft assume about each other, on surveillance quality, on equipage and on the avoidance method.

**Status (v0.5.0).** Research software with simulation evidence under stated assumptions. It is not a flight system, an operational safety case or a capacity estimate for any real airspace. See [what the evidence does and does not support](#what-the-evidence-supports).

## Why this question

Earlier versions (v0.1–v0.4, preserved in [`experiments/`](experiments/README.md) and [`archive/`](archive/README.md)) compared avoidance controllers and found that none "cleared the safety gate". Reanalysis shows the controller was not the main limit. Every planner assumed every other aircraft could accelerate toward it at full authority. Over the planning horizon that turns each neighbour into a protected sphere about 30 m in radius, and dense traffic leaves no room ([figure](docs/report/figures/enclosure-radius.png)). Optimistic assumptions keep the airspace usable but are violated whenever neighbours maneuver. The project now studies that trade-off directly.

## Quick start

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[analysis]'
.venv/bin/python -m dense_uav_ops run --set demand.uas_per_hour=2880 --replay artifacts/replay.html
.venv/bin/python -m unittest discover -s tests
```

Optional: `pip install -e '.[learning]'` for learned rankers, and `python scripts/build_daidalus.py` for the NASA DAIDALUS baseline (downloads DAIDALUS under its own licence).

## What it models

- **Airspace**: a configurable volume with spherical obstacles.
- **Traffic**: Poisson demand on crossing, corridor or head-on routes, a multirotor/fixed-wing mix, and optional manned transits.
- **Who is controlled**: equipped, cooperating and compliant UAS are *controlled*. Everything else is traffic the system cannot command.
- **Surveillance**: a delayed, lossy feed with bounded errors, coverage and outages. Controlled aircraft see each other only through it.
- **Avoidance methods** (selectable per run):
  - none;
  - a maneuver-library planner with an explicit **assumed traffic acceleration**, the frontier variable;
  - NASA DAIDALUS direction bands;
  - learned rankers, which may only choose among maneuvers the planner already accepts.
- **Outcomes**: exact loss-of-separation and contact events, attributed to the system or to the airspace at large, plus throughput, completion, delay and fallback.

Outcomes are deterministic for a given configuration and platform, and independent of host speed; across platforms they agree to floating-point rounding (see the model notes). Details and idealizations: [docs/model.md](docs/model.md).

## Documents

| Document | Contents |
|---|---|
| [Research question and definitions](docs/research-question.md) | The question; what "safest", "capacity", "proven" and "standard" mean here; the evidence ladder |
| [Model and transfer](docs/model.md) | Architecture, information boundaries, assumptions, plausibility of transfer to aircraft |
| [Usage](docs/usage.md) | Install, configure operating domains, run campaigns, interpret metrics, train learned rankers |
| [Technical report](docs/report/technical-report.md) | Methods, frontier-01 results, reanalysis of v0.1–v0.4 evidence, threats to validity |
| [Roadmap](docs/roadmap.md) | Larger campaigns, coordination contracts, dynamics and simulator integration, assurance |
| [Evidence index](experiments/README.md) | Every retained evidence set: what it supports and what it does not |
| [Archive](archive/README.md) | Retired v0.1–v0.4 code and documents, and why each part was retired |

## What the evidence supports

**Pilot findings** (frontier-01, 360 runs; frontier-02, 144 runs; one 400 m cell; 3 seeds per cell). These hold *in this model*:

- Worst-case assumptions about other aircraft (4 m/s²) did not lower attributable risk. Above 1440–2880 operations/hour they congested the airspace: completion as low as 5 %, delays up to minutes. Their unverified fallback maneuvers then caused more contacts than any other planner setting.
- A planner that assumes constant-velocity traffic and replans every 0.2 s gave the best observed frontier: 13 in-flight attributable losses of separation and no contacts in 89 controlled flight-hours, with negligible delay. Traffic wandering at up to 3 m/s² did not change that.
- The measured reason: over the replanning interval, neighbours departed from constant-velocity prediction by about 1 m (95th percentile). The worst-case model inflates them by up to 16 m over the whole horizon.

See the [technical report](docs/report/technical-report.md#4-results).

| Claim | Level |
|---|---|
| The simulator, planner, surveillance model, campaign tooling and DAIDALUS bridge work as specified on tested cases | Implemented and tested (58 tests) |
| The frontier findings above | Pilot simulation evidence under stated idealizations: exact ownship state, no tracking error, smooth maneuvers, fresh reports |
| Admissible maneuvers keep separation over the horizon *if* traffic stays within the assumed acceleration and reports within declared bounds | Conditional mathematical statement about the model |
| Any real-world collision rate, airspace capacity or "safest" controller | **Not established** |

## Credits and licences

Author: Vibhu Tripathi. Cite with [CITATION.cff](CITATION.cff).

Original code and documents are MIT-licensed ([LICENSE](LICENSE)). NASA DAIDALUS is fetched separately under the NASA Open Source Agreement and is not redistributed. Third-party terms are listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
