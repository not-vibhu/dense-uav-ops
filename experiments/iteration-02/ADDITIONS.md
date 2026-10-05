# Added in v0.5

The original `README.md` in this directory (kept unchanged) says the raw results and source archives were kept only locally. They were added in v0.5, unchanged apart from gzip compression:

| File | Content |
|---|---|
| `catalog-runs.jsonl.gz`, `scale-runs.jsonl.gz` | Every run record of the 1,152-run catalog and the 32-run scale campaigns |
| `source-snapshot.tar.gz` | The `swarm_sim` source both campaigns ran (digest equals each manifest's `source_sha256`) |
| `environment.txt` | Python, NumPy and platform |
| `preferences.json`, `preferences.training.json.gz` | The selected preference profile (equal to the one embedded in both manifests) and its 96-evaluation training trace |
| `checksums.json` | SHA-256 of every file in this directory |

`scripts/validate_evidence.py iteration-02` rebuilds both summaries from the raw runs under the archived source and checks the preference pin. Its links to `../../docs/...` now resolve under `archive/docs-v0.4.1/`.
