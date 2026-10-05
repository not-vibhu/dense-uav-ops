# frontier-01: pilot sweep of the safety–capacity frontier

**Status:** pilot simulation evidence (evidence level 2 in [the definitions](../../docs/research-question.md#evidence-ladder)): 3 seeds per cell, one airspace geometry, one model. It is designed to show the *shape* of the frontier and to size the larger campaign, not to estimate rates precisely.

The design below was written before the campaign was run. Results are in a separate section added afterwards.

## Design (fixed before execution)

**Question.** In a 400 m × 400 m × 90 m volume with Poisson crossing traffic, how do attributable risk and service change with:
- what controlled aircraft assume about other aircraft's acceleration;
- offered demand;
- surveillance latency;
- the share of equipped, cooperating aircraft?

How do the no-avoidance and DAIDALUS baselines compare?

**Fixed conditions** ([`profiles/frontier-base.json`](../../profiles/frontier-base.json)):
- 40 % fixed-wing UAS; cruise 8 m/s; true acceleration authority 4 m/s².
- Wind 0.4 m/s².
- 1 Hz regional surveillance with 3 % loss and declared error bounds of 1.5 m / 0.3 m/s.
- 10 m separation threshold, 2.4 s planning horizon.
- Entry spacing rule only, with no occupancy limit.
- Windows: 60 s warm-up, 240 s measurement, 90 s drain; 0.2 s step.
- No manned traffic, no obstacles, every UAS compliant.
- Non-cooperative UAS are reported exactly like cooperative ones. This models universal broadcast Remote ID and is an optimistic surveillance assumption.

**Arms** ([`spec.json`](spec.json)):

| Arm | Controlled aircraft | Assumed traffic acceleration |
|---|---|---|
| `none` | fly their route, no avoidance | — |
| `predictive-A0/1/2/4` | maneuver-library planner | 0, 1, 2, 4 m/s² |
| `daidalus` | NASA DAIDALUS horizontal-direction bands, research small-UAS thresholds | constant velocity (DAIDALUS's own model) |

**Grid:** offered UAS demand 360, 720, 1440, 2880, 5760 operations/hour × surveillance latency 0.2 s, 1.0 s × cooperative fraction 1.0, 0.5 × seeds 11, 12, 13. That makes 6 arms × 20 conditions × 3 seeds = **360 runs**. All arms in a condition share seeds, traffic and surveillance noise (common random numbers).

**Truth model relevant to the question.**
- Uncooperative UAS fly their routes at near-constant velocity.
- Controlled aircraft maneuver at up to 4 m/s².
- A uniform wind of up to 0.4 m/s² acts on all UAS and cancels in relative motion.

So A = 4 covers every aircraft's true relative acceleration. A = 0 is violated whenever a controlled neighbour maneuvers.

**Outcomes.** Primary: attributable UAS losses of separation (involving at least one controlled aircraft) per controlled flight-hour, and per 1000 controlled operations completed in the window. Secondary:
- attributable contacts;
- UAS throughput;
- controlled completion fraction;
- mean delay (completed, and the censored lower bound);
- fallback fraction (planner arms);
- DAIDALUS unresolved fraction;
- airspace-level event rates.

**Analysis plan.**
1. For each latency × equipage facet, plot each arm's frontier across demand: risk (per 1000 completed operations) against controlled throughput, with delay and completion alongside.
2. Report per-cell pooled estimates with exact Poisson intervals that assume independent events (optimistic), and per-run values.
3. Do not declare a "safest" arm. Describe dominance only where intervals separate at comparable throughput.
4. Illustrate the capacity definition with an example requirement: attributable UAS contacts upper bound < 1 per controlled flight-hour, completion ≥ 0.95, mean delay lower bound ≤ 30 s. Report whether any tested demand meets it. With about 1–15 controlled flight-hours per cell, the contact bound alone is weak, and the report must say so.

**Expectations, stated before the final run.** A calibration run on an earlier build (before the fixes listed below; not reported as evidence) showed the worst-case arm congesting at 5760/h, with low completion, long delays and more events than the constant-velocity arm. We therefore expect:
- (E1) at low demand, risk decreases as A increases;
- (E2) at high demand, A = 4 congests, so service collapses and its risk advantage shrinks or reverses;
- (E3) `none` has much higher attributable risk at every demand;
- (E4) DAIDALUS gives service close to `none` with intermediate risk.

**Fixes made before this run after an independent code review:**
- entries could start inside loss of separation; fixed with the spacing rule and own-fleet awareness;
- exits coincided with opposite entry planes;
- delay averaged only finished flights; now censored;
- non-cooperative surveillance was not configurable;
- latency quantization;
- a profile-merge bug;
- surveillance random streams diverged across arms.

These are in the commit history and tests (`tests/test_engine.py::ReviewRegressionTests`).

**Amendment before the final execution.** A first execution was stopped at 240 of 360 runs. A second review found two defects affecting events at aircraft entry:
- *The entry-spacing rule ignored braking.* It dead-reckoned recently admitted aircraft at their entry velocity and had no acceleration term. Entrants could therefore be placed close behind slowed aircraft, which mostly affected the A = 4 arm.
- *Unseen recent entrants.* Uncontrolled aircraft that had entered within the last report interval were not yet visible, so controlled entries could land on them, and they could spawn onto controlled aircraft.

The changes were motivated by the review's defect findings. They were not blind: partial outcomes of the stopped execution (the `none`, A = 0 and A = 1 arms) had been viewed, and a 12-run check of the fixes was run at 5760/h with shorter windows (seed 11; those runs are not part of this grid). Changes:
- The spacing rule now requires the entrant's straight path to stay clear for 1 s. The check includes report errors and the *physical* 4 m/s² bound, so it does not depend on A.
- Events within one report interval (period + latency + one step) of either aircraft's entry are counted as an **entry phase**, separately from in-flight events.
- The **primary outcome is in-flight** attributable UAS LoS. Entry-phase events are reported alongside.
- Minor fixes: command-drop draws every step, step-multiple validation of surveillance timing, and a pooled DAIDALUS unresolved fraction.

The stopped partial run is retained under [`../excluded-preliminary/`](../excluded-preliminary/README.md) and is not pooled with these results.

## Reproduce

```bash
.venv/bin/python scripts/build_daidalus.py                    # the DAIDALUS arm needs the bridge
.venv/bin/python -m dense_uav_ops campaign experiments/frontier-01/spec.json --out experiments/frontier-01 --workers 8
.venv/bin/python -m dense_uav_ops validate experiments/frontier-01 --rerun 5
```

The campaign resumes if interrupted. Outcomes are independent of host speed and worker count; only the reported compute times change.

## Results (added after execution)

360 of 360 runs completed. `dense-uav-ops validate experiments/frontier-01 --rerun 5` verifies completeness, configuration hashes, the summary and checksums, and reproduces five randomly chosen runs exactly. Interpretation, figures and per-cell tables are in [section 4.1 of the technical report](../../docs/report/technical-report.md#41-frontier-01-assumed-acceleration-across-demand-latency-and-equipage).

In brief:
- **Constant-velocity planner (A = 0).** 13 in-flight attributable losses of separation and no contacts in 89 controlled flight-hours, full completion, at most 1.5 s mean delay.
- **Worst-case planner (A = 4).**
  - It bought no measurable risk reduction.
  - It congested from 1440–2880/h: completion as low as 0.05, mean delay up to 159 s, fallback up to 85 %.
  - It had the most contacts of any planner arm (6 in flight, 5 at entry).
- **DAIDALUS.** Service almost unchanged, intermediate risk.
- **No avoidance.** 3,307 losses of separation and 440 contacts.

Against the expectations: E1 was untestable (zero events at low demand); E2, E3 and E4 were supported. No cell is an operational capacity.
