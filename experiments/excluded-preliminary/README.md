# Excluded preliminary runs

Development runs that the v0.2–v0.4 documents described as "archived locally and excluded". They are published here so that what was excluded, and why, can be inspected. **Never pool them with any results.** `inventory.json` lists every file in `excluded-preliminary.tar.gz` with its SHA-256.

| Path in archive | Excluded because |
|---|---|
| `pre-age-correction/` | Preference search and catalog runs before the stale-report wind enclosure was corrected (v0.2) |
| `incomplete-before-identity-fix/` | Partial campaign abandoned after a run-identity defect (v0.2) |
| `pre-inference-isolation/` | v0.3 campaigns before the learned actor was isolated from training-only state |
| `pre-report-update/` | v0.3 campaigns before report and accounting updates |
| `capacity-preliminary/` | Capacity campaigns before route controls and export verification (v0.3) |
| `neural-smoke/` | Smoke-test checkpoints for the v0.3 learning pipeline |
| `predictive-development.json`, `predictive-scale-development.json`, `iteration-03-smoke.json` | Development diagnostics |
| `frontier-01-stopped/` | First execution of frontier-01 (v0.5), stopped at 240 of 360 runs when a second review found entry-phase defects; see `experiments/frontier-01/README.md` |

Reasons for the v0.2–v0.4 items come from those versions' documents and archive names; their underlying defects were not independently re-verified for this release.
