"""Offline historical validation against the retained source and checkpoints."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('evidence', type=Path)
    parser.add_argument('--flight', action='store_true', help='Recompute all signed-control physical reconstructions')
    args = parser.parse_args()
    root = args.evidence.resolve()
    checksums = json.loads((root/'checksums.json').read_text())
    for name, expected in checksums.items():
        path = (root/name).resolve()
        if not path.is_relative_to(root) or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('Missing/modified evidence: '+name)
    model = root/'graph-model.json'
    model_sha = hashlib.sha256(model.read_bytes()).hexdigest()
    source = json.loads(model.read_text())['source_sha256']
    names = ('catalog', 'guard-comparison', 'graph-comparison', 'density', 'partition-clock')
    count = 0
    with tempfile.TemporaryDirectory(prefix='dense-ops-evidence-') as directory:
        archive_root = Path(directory)
        with tarfile.open(root/'source.tar.gz') as archive:
            archive.extractall(archive_root, filter='data')
        for name in names:
            manifest = json.loads((root/name/'manifest.json').read_text())
            if manifest['source_sha256'] != source or manifest['checkpoint_sha256'] != model_sha:
                raise ValueError('Model/source provenance differs from campaign')
            subprocess.run([sys.executable, '-m', 'dense_ops', 'validate', str(root/name)], cwd=archive_root, check=True)
            count += len(manifest['configs'])
            if args.flight:
                subprocess.run([sys.executable, '-m', 'scripts.verify_flight_replay', str(root/name),
                                '--out', str(archive_root/(name+'-reconstruction.json'))], cwd=archive_root, check=True)
                actual = json.loads((archive_root/(name+'-reconstruction.json')).read_text())
                stored = json.loads((root/name/'flight-reconstruction.json').read_text())
                if actual['rows'] != stored['rows']: raise ValueError('Flight reconstruction differs')
        subprocess.run([sys.executable, '-m', 'dense_ops', 'modelcheck', '--out', str(archive_root/'protocol.json')],
                       cwd=archive_root, check=True)
        if json.loads((archive_root/'protocol.json').read_text()) != json.loads((root/'protocol.json').read_text()):
            raise ValueError('Bounded protocol exploration differs')
    assessment = json.loads((root/'assessment.json').read_text())
    if count != 196 or assessment['evaluations'] != count or assessment['source_sha256'] != source:
        raise ValueError('Assessment/grid mismatch')
    if assessment['operational_capacity'] is not None or assessment['statistically_qualified_architecture'] is not None:
        raise ValueError('Unexpected operational claim')
    print(f'{count} evaluations verified against retained source, model, grids, signatures, trusted checkpoints and checksums')


if __name__ == '__main__':
    main()
