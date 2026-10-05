# Iteration 01: initial mixed-fleet controller comparison (v0.1, `swarm_sim`)

The complete 7,680-run campaign behind `archive/docs-v0.4.1/initial-comparison.md`. Until v0.5 it existed only on the author's machine. It was added unchanged, with the run log gzip-compressed.

| File | Content |
|---|---|
| `manifest.json` | Declared grid: 24 scenarios × fleet sizes 10/50/100/200 × cooperative fractions 0/0.1/0.5/0.9/1 × 4 controllers × seeds 0, 1 (discovery) and 1001, 1002 (holdout) |
| `runs.jsonl.gz` | Every run record |
| `summary.json`, `REPORT.md`, `report.html` | Summaries as originally generated |
| `source-snapshot.tar.gz` | The `swarm_sim` source that produced the runs. Its digest equals the manifest's `source_sha256` and commit `2694bb0`. |
| `environment.txt` | Python, NumPy and platform |
| `resolution-check.json.gz` | The separate 0.05 s-step replay cited in the original decision document |

`scripts/validate_evidence.py iteration-01` checks:
- each run ID hashes its configuration;
- the runs cover exactly the declared grid;
- the summary rebuilds from the raw runs under the archived source.

**Reanalysis** ([technical report](../../docs/report/technical-report.md#2-historical-evidence-reanalysed)):
- The run-level collision indicator saturates with fleet size: direct goal flight is at 3 % of runs at 10 aircraft and 100 % at 100 and 200. Pooled rankings mostly reflect the stratum mix.
- At 50+ aircraft every barrier-filter run had a participating aircraft leave the operating volume, so its lower collision rate cannot be separated from leaving the airspace.
- No controller is shown to be safer for dense traffic.
