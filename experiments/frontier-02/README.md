# frontier-02: stress test with traffic that violates optimistic assumptions

**Status:** pilot simulation evidence: 3 seeds per cell, one geometry. This experiment was designed **after** seeing frontier-01's results, to test the most obvious threat to them. It is a follow-up, not a confirmatory replication.

## Why

In frontier-01 the planner assuming constant-velocity traffic (A = 0) had the lowest in-flight attributable risk at almost no service cost. In that experiment every uncontrolled UAS flew a straight route, which *satisfies* a constant-velocity assumption. Only controlled neighbours, which replan every 0.2 s, ever deviated. frontier-02 asks whether that advantage survives traffic that genuinely maneuvers unpredictably.

## Design (written before execution)

**Base.** [`profiles/frontier-base.json`](../../profiles/frontier-base.json) with every UAS equipped (`cooperative_fraction` 1.0), so the only uncontrolled aircraft are **noncompliant** UAS. These follow their route plus a bounded random lateral acceleration: a first-order random process, capped at `noncompliant_acceleration_mps2`, and projected into the vehicle envelope (4 m/s² total).

**Arms.** As in frontier-01: `none`, `predictive-A0/1/2/4` and `daidalus`.

**Grid.**
- Offered demand: 1440, 2880 operations/hour.
- Noncompliant fraction: 0.1, 0.3.
- Noncompliant lateral acceleration cap: 1.5, 3.0 m/s².
- Seeds 21, 22, 23 (disjoint from frontier-01).
- 6 × 2 × 2 × 2 × 3 = **144 runs**. Latency 0.2 s.

**Which assumptions are violated.** A wandering aircraft's lateral acceleration can reach the cap (plus route-following):
- a 1.5 m/s² cap violates A = 0 and A = 1;
- a 3.0 m/s² cap also violates A = 2;
- A = 4 covers both.

**Outcomes.** As frontier-01. Primary: in-flight attributable UAS LoS per 1000 completed controlled operations, and per controlled flight-hour. Attributable events here are controlled–noncompliant ('cu') or controlled–controlled ('cc'). Contacts, completion, delay and fallback are reported alongside.

**Expectations.**
- (S1) Risk for A = 0 and A = 1 rises relative to frontier-01 cells at the same demand, and rises with the wander cap and noncompliant fraction.
- (S2) A = 4's in-flight risk stays low at 1440/h, with the congestion costs seen in frontier-01.
- (S3) If the A = 0 advantage in frontier-01 came from predictable traffic, the ordering of A = 0 and A = 4 on risk reverses at the high wander cap, at least at 1440/h.
- (S4) DAIDALUS, which also assumes constant velocity, behaves like A = 0 on risk.

Any of these can fail; results are reported as observed.

## Reproduce

```bash
.venv/bin/python -m dense_uav_ops campaign experiments/frontier-02/spec.json --out experiments/frontier-02 --workers 8
.venv/bin/python -m dense_uav_ops validate experiments/frontier-02 --rerun 3
```

## Results (added after execution)

144 of 144 runs completed and validate; three re-simulations reproduced exactly. With 10–30 % of traffic wandering at up to 3 m/s², the constant-velocity planner had 3 in-flight attributable losses of separation and no contacts in 38 controlled flight-hours; A = 4 had 8 and a delay of up to 16.7 s. S1 and S3 were **not supported**, S2 was supported, and S4 was not (DAIDALUS had 32). A measurement of actual deviations from constant-velocity prediction (95th percentile 0.8–1.3 m over the 1.2 s replanning interval) explains the result within this model. See [sections 4.2–4.3 of the technical report](../../docs/report/technical-report.md#42-frontier-02-traffic-that-violates-the-optimistic-assumptions). Untested threats include abrupt or adversarial maneuvers, long report ages and ownship tracking error.
