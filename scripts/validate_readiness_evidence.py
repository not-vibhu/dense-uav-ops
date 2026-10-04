"""Offline validation of the before/after readiness study."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile


def main():
    parser=argparse.ArgumentParser();parser.add_argument('evidence',type=Path);args=parser.parse_args()
    root=args.evidence.resolve()
    for name,expected in json.loads((root/'checksums.json').read_text()).items():
        path=(root/name).resolve()
        if not path.is_relative_to(root) or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
            raise ValueError('Missing/modified paired evidence: '+name)
    assessment=json.loads((root/'assessment.json').read_text())
    if assessment['evaluations']!=24 or assessment['operational_capacity'] is not None:
        raise ValueError('Unexpected qualification/grid claim')
    for phase,key in [('before','baseline_source_sha256'),('after','source_after_sha256')]:
        manifest=json.loads((root/phase/'manifest.json').read_text())
        if manifest['source_sha256']!=assessment[key] or len(manifest['configs'])!=12:
            raise ValueError('Paired source/grid mismatch')
        with tempfile.TemporaryDirectory(prefix='dense-ops-readiness-') as directory:
            with tarfile.open(root/('source-'+phase+'.tar.gz')) as archive:
                archive.extractall(directory,filter='data')
            subprocess.run([sys.executable,'-m','dense_ops','validate',str(root/phase)],cwd=directory,check=True)
            output=Path(directory)/'flight.json'
            subprocess.run([sys.executable,'-m','scripts.verify_flight_replay',str(root/phase),'--out',str(output)],
                           cwd=directory,check=True)
            rows=json.loads(output.read_text())['rows']
            stored=json.loads((root/phase/'flight-reconstruction.json').read_text())['rows']
            if rows!=stored: raise ValueError('Paired physical replay mismatch')
        with gzip.open(root/phase/'runs.jsonl.gz','rt') as stream:runs=[json.loads(line) for line in stream]
        if any(len(items)!=12 for items in (runs,stored,assessment['results'][phase])):
            raise ValueError('Incomplete paired outcomes')
        for run,row,summary in zip(runs,stored,assessment['results'][phase]):
            expected={'experiment':run['experiment'],'metrics':run['metrics'],
                      'controlled_collision_pairs':row['collision_categories']['controlled'],
                      'controlled_breach_pairs':row['breach_categories']['controlled'],
                      'observed_requirements_pass':run['observed_requirements_pass']}
            if expected!=summary: raise ValueError('Paired assessment differs from signed outcomes')
    if json.loads((root/'graph-model.json').read_text())['source_sha256']!=assessment['source_after_sha256']:
        raise ValueError('Graph checkpoint mismatch')
    print('24 matched before/after evaluations and physical reconstructions verified against both archived sources')


if __name__=='__main__':main()
