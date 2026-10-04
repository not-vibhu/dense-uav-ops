"""Paired untouched-seed evaluation of the surveillance admission correction."""
import argparse
import gzip
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile

from dense_ops.__main__ import source_hash
from scripts.verify_flight_replay import reconstruct


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if any(out.iterdir()): raise ValueError('Followup output must be empty')
    baseline = args.baseline.resolve()
    results = {}
    with tempfile.TemporaryDirectory(prefix='dense-ops-baseline-') as directory:
        archive_root = Path(directory)
        with tarfile.open(baseline/'source.tar.gz') as archive:
            archive.extractall(archive_root, filter='data')
        for label, cwd in [('before', archive_root), ('after', Path.cwd())]:
            path = out/label
            command = [sys.executable, '-m', 'dense_ops', 'campaign',
                       '--profile', 'profiles/distributed-04/mixed-mission.json', '--scenarios',
                       'stale_telemetry', 'network_outage', 'head_on', '--counts', '10',
                       '--modes', 'local', 'federated', '--guards', 'continuation', '--seeds', '8800', '8801',
                       '--workers', '2', '--out', str(path)]
            subprocess.run(command, cwd=cwd, check=True)
            subprocess.run([sys.executable, '-m', 'dense_ops', 'validate', str(path)], cwd=cwd, check=True)
            with gzip.open(path/'runs.jsonl.gz', 'rt') as stream:
                runs = [json.loads(line) for line in stream]
            anchors = json.loads((path/'anchors.json').read_text())
            rows = [reconstruct(run, anchor) for run, anchor in zip(runs, anchors)]
            (path/'flight-reconstruction.json').write_text(json.dumps({'rows': rows}, indent=2)+'\n')
            results[label] = [{'experiment': run['experiment'], 'metrics': run['metrics'],
                               'controlled_collision_pairs': row['collision_categories']['controlled'],
                               'controlled_breach_pairs': row['breach_categories']['controlled'],
                               'observed_requirements_pass': run['observed_requirements_pass']}
                              for run, row in zip(runs, rows)]
    (out/'assessment.json').write_text(json.dumps({'evaluations': 24, 'source_after_sha256': source_hash(),
        'baseline_source_sha256': json.loads((baseline/'assessment.json').read_text())['source_sha256'],
        'results': results, 'operational_capacity': None,
        'scope': 'Paired independent seeds after a defect was discovered in the 196-run development baseline. Small research comparison, not statistical safety qualification.'}, indent=2)+'\n')


if __name__ == '__main__':
    main()
