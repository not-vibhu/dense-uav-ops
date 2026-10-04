"""Retain both source versions and a complete paired admission comparison."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tarfile
from dense_ops.__main__ import source_hash


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--artifacts',type=Path,required=True)
    parser.add_argument('--baseline',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    args.out.mkdir(parents=True,exist_ok=True)
    if any(args.out.iterdir()): raise ValueError('Evidence output must be empty')
    study=args.artifacts/'readiness-followup'
    assessment=json.loads((study/'assessment.json').read_text())
    if assessment['source_after_sha256']!=source_hash(): raise ValueError('Followup source mismatch')
    if any(len(assessment['results'][phase])!=12 for phase in ('before','after')):
        raise ValueError('Incomplete paired assessment')
    for before,after in zip(assessment['results']['before'],assessment['results']['after']):
        left=before['experiment'];right=dict(after['experiment']);right.pop('max_surveillance_age')
        if left!=right: raise ValueError('Nonmatched encounter conditions')
    for phase in ('before','after'): shutil.copytree(study/phase,args.out/phase)
    shutil.copyfile(study/'assessment.json',args.out/'assessment.json')
    shutil.copyfile(args.baseline/'source.tar.gz',args.out/'source-before.tar.gz')
    for source,target in [('readiness-tests.log','tests.log'),('readiness-campaign.log','campaign.log'),
                          ('readiness-graph.json','graph-model.json'),('readiness-graph.data.json','graph-data.json')]:
        shutil.copyfile(args.artifacts/source,args.out/target)
    model=json.loads((args.out/'graph-model.json').read_text())
    if model['source_sha256']!=source_hash(): raise ValueError('New graph model/source mismatch')
    if '\nOK\n' not in (args.out/'tests.log').read_text(): raise ValueError('No passing regression evidence')
    root=Path.cwd()
    files=[p for d in ('dense_ops','swarm_sim','airspace_capacity','integrations','scripts','tests','profiles','docs','.github')
           for p in (root/d).rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    files += [root/'pyproject.toml',root/'README.md',root/'LICENSE']
    with tarfile.open(args.out/'source-after.tar.gz','w:gz') as archive:
        for p in sorted(files): archive.add(p,arcname=str(p.relative_to(root)))
    checks={str(p.relative_to(args.out)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(args.out.rglob('*')) if p.is_file()}
    (args.out/'checksums.json').write_text(json.dumps(checks,indent=2)+'\n')
    print('24 matched evaluations retained with both source versions, reconstructions, retrained graph and regression evidence')


if __name__=='__main__':main()
