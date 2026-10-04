"""Freeze the complete development study, checksums, source and flight replay."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile

from dense_ops.__main__ import source_hash, validate_campaign
from scripts.verify_flight_replay import reconstruct


def write(path, document):
    path.write_text(json.dumps(document, indent=2, allow_nan=False)+'\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--artifacts', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    if any(args.out.iterdir()): raise ValueError('Evidence output must be empty')
    names = ('catalog', 'guard-comparison', 'graph-comparison', 'density', 'partition-clock')
    analysis, count = {}, 0
    for name in names:
        source = args.artifacts/'release-study'/name
        validate_campaign(source)
        shutil.copytree(source, args.out/name)
        anchors = json.loads((source/'anchors.json').read_text())
        with gzip.open(source/'runs.jsonl.gz', 'rt') as stream:
            runs = [json.loads(line) for line in stream]
        rows = [reconstruct(run, anchor) for run, anchor in zip(runs, anchors)]
        write(args.out/name/'flight-reconstruction.json', {'rows': rows,
              'scope': 'Record/plant consistency with archived continuous geometry; not surveillance-decision replay.'})
        analysis[name] = dict(runs=len(runs), passing=sum(r['observed_requirements_pass'] for r in runs),
            collision_runs=sum(r['metrics']['collision_pairs'] > 0 for r in runs),
            controlled_collision_runs=sum(r['collision_categories']['controlled'] > 0 for r in rows),
            controlled_breach_runs=sum(r['breach_categories']['controlled'] > 0 for r in rows),
            max_cooperative_completion=max(r['metrics']['completion_fraction'] for r in runs),
            peak_occupancy=max(r['metrics']['peak_occupancy'] for r in runs))
        count += len(runs)
    if count != 196: raise ValueError('Unexpected development grid size')
    model = json.loads((args.artifacts/'qualified-source-policy.json').read_text())
    if model['source_sha256'] != source_hash(): raise ValueError('Training source mismatch')
    shutil.copyfile(args.artifacts/'qualified-source-policy.json', args.out/'graph-model.json')
    shutil.copyfile(args.artifacts/'qualified-source-policy.data.json', args.out/'graph-data.json')
    for name in ('protocol.json', 'nasa.json', 'tests.log', 'replay.html', 'replay.jpg'):
        shutil.copyfile(args.artifacts/name, args.out/name)
    if '\nOK\n' not in (args.out/'tests.log').read_text(): raise ValueError('Missing passing regression evidence')
    if json.loads((args.out/'protocol.json').read_text())['violations'] != 0: raise ValueError('Protocol failure')
    replay = json.loads((args.artifacts/'release-replay.json').read_text())
    write(args.out/'individual-flight-reconstruction.json', reconstruct(replay, replay['audit']['anchor']))
    with gzip.open(args.out/'individual-replay.json.gz', 'wt') as stream:
        json.dump(replay, stream, allow_nan=False)
    shutil.copyfile(args.artifacts/'release-study/commands.json', args.out/'commands.json')
    shutil.copyfile(args.artifacts/'release-campaign.log', args.out/'campaign.log')
    env = dict(source_sha256=source_hash(), python=sys.version, platform=platform.platform(),
               dependencies=subprocess.check_output([sys.executable, '-m', 'pip', 'freeze'], text=True),
               compiler=subprocess.check_output(['c++', '--version'], text=True),
               timing_scope='Shared host, two campaign workers; development processes may share the machine. Not onboard WCET.')
    write(args.out/'environment.json', env)
    root = Path.cwd()
    files = [p for d in ('dense_ops','swarm_sim','airspace_capacity','integrations','scripts','tests','profiles','docs','.github')
             for p in (root/d).rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    files += [root/'pyproject.toml', root/'README.md', root/'LICENSE']
    with tarfile.open(args.out/'source.tar.gz', 'w:gz') as archive:
        for path in sorted(files): archive.add(path, arcname=str(path.relative_to(root)))
    write(args.out/'assessment.json', dict(evaluations=count, source_sha256=source_hash(), studies=analysis,
          operational_capacity=None, statistically_qualified_architecture=None,
          decision='Resolve recoverability, service, observation and timing blockers; no safest architecture or capacity established.'))
    write(args.out/'checksums.json', {str(p.relative_to(args.out)): hashlib.sha256(p.read_bytes()).hexdigest()
          for p in sorted(args.out.rglob('*')) if p.is_file()})
    print(json.dumps(analysis, indent=2))


if __name__ == '__main__':
    main()
