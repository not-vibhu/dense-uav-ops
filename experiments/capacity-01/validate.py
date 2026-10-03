"""Rebuild public summaries from complete raw evidence and verify source pins."""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from airspace_capacity.__main__ import source_digest
from airspace_capacity.profile import Profile
from airspace_capacity.assessment import summarize


def validate():
    current = source_digest()
    total = 0
    for name in ('baseline', 'sensitivity', 'density', 'layered'):
        directory = Path(__file__).parent/name
        manifest_bytes = (directory/'manifest.json').read_bytes()
        manifest = json.loads(manifest_bytes)
        raw = (directory/'runs.jsonl').read_bytes()
        runs = [json.loads(line) for line in raw.splitlines()]
        profiles = [Profile(**p).validate() for p in manifest['profiles']]
        assert manifest['source_sha256'] == current, f'{name}: source mismatch'
        calculated = summarize(runs, profiles, manifest['rates'], manifest['occupancy_limits'], manifest['seeds'])
        calculated.update(source_sha256=current,
                          manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
                          runs_sha256=hashlib.sha256(raw).hexdigest())
        saved = json.loads((directory/'summary.json').read_text())
        assert calculated == saved, f'{name}: summary mismatch'
        total += len(runs)
        print(f'{name}: {len(runs)} exact raw rows and summary verified')
    checksums = json.loads((Path(__file__).parent/'checksums.json').read_text())
    for relative, digest in checksums.items():
        assert hashlib.sha256((Path(__file__).parent/relative).read_bytes()).hexdigest() == digest, relative
    print(f'{total} mixed-traffic evaluations verified; source {current}')


if __name__ == '__main__':
    validate()
