# Corrected predictive-policy evaluation

These are published summaries of the completed version 0.2 research comparison. They do not establish flight safety. The preference optimizer retained the default weights, and no tested controller cleared the empirical gate. Read the [decision and interpretation](../../docs/second-iteration.md) before using the rankings.

| Evidence | Scope |
|---|---|
| [Catalog manifest](catalog-manifest.json) | All 24 scenarios, 10/50 aircraft, 50/100% cooperation, six labels, two separate seeds: 1,152 runs |
| [Catalog summary](catalog-summary.json) | Discovery, holdout, modeled/out-of-bound and per-scenario descriptive metrics |
| [Catalog interactive report](catalog-report.html) | Standalone browser report; download/open locally |
| [Scale manifest](scale-manifest.json) | Crossing/overload, 100/200 aircraft, 50% cooperation, four labels, two seeds: 32 runs |
| [Scale summary](scale-summary.json) | Dense-airspace failures, timing and safety-gate outcomes |
| [Scale interactive report](scale-report.html) | Standalone browser report; download/open locally |
| [Selected preferences](../../profiles/predictive-preferences.json) | The corrected 96-evaluation training search and frozen source hash |

`evolved` and `predictive` have equal physical outcomes in all paired evaluation runs. These are two labels for the retained preference profile; their agreement is not independent replication or evidence of a learned improvement. The discovery controller was chosen before considering the holdout; no weights were tuned on the holdout.

The manifests embed and hash the profile and record the Python source hash. Each summary records a SHA-256 digest of the complete sorted raw results. Local raw results, training traces, environment metadata and source archives live under ignored `artifacts/`; those larger files are not included in this directory. The exact rerun commands and model coverage are in [policy development](../../docs/learning-policy.md). Timing depends on host and load, so freshly generated raw-result digests can differ even when physical outcomes agree.

Preliminary computations before the stale-interval wind correction are archived separately and excluded. The original 7,680-run benchmark covers a different matrix and cannot be compared directly with this aggregate.
