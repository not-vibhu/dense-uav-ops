"""Validate every retained evidence set against the source that produced it.

Historical evidence is never checked against the current package. Each set's
archived source is extracted to a temporary directory and imported from there,
so the maintained code can change without invalidating historical results.

Usage:
    python scripts/validate_evidence.py            # all sets
    python scripts/validate_evidence.py iteration-03 capacity-01
    python scripts/validate_evidence.py --flight   # also re-run signed-control flight reconstructions (slow)
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENTS = ROOT / 'experiments'


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check_checksums(directory):
    listing = json.loads((directory / 'checksums.json').read_text())
    for name, expected in listing.items():
        path = (directory / name).resolve()
        if not path.is_relative_to(directory.resolve()) or not path.is_file():
            raise ValueError(f'{directory.name}: missing {name}')
        if sha256(path) != expected:
            raise ValueError(f'{directory.name}: modified {name}')
    return len(listing)


def extract(archive, destination):
    """Extract our own source archives, skipping macOS AppleDouble entries."""
    with tarfile.open(archive) as tar:
        members = [m for m in tar.getmembers()
                   if not Path(m.name).name.startswith('._') and Path(m.name).name != '.DS_Store']
        tar.extractall(destination, members=members, filter='data')


def run_archived(code, cwd, *arguments):
    result = subprocess.run([sys.executable, '-c', code, *map(str, arguments)], cwd=cwd,
                            capture_output=True, text=True)
    if result.returncode:
        raise ValueError(result.stderr.strip()[-2000:])
    return result.stdout.strip()


# Runs inside an extracted swarm_sim snapshot. Checks the declared grid, the
# configuration hash behind every run ID and the published summary.
SWARM_CAMPAIGN = r'''
import gzip, itertools, json, sys
from pathlib import Path
from swarm_sim.analysis import summarize
from swarm_sim.config import Config
from swarm_sim.engine import config_id
manifest_path, runs_path, summary_path = map(Path, sys.argv[1:4])
manifest = json.loads(manifest_path.read_text())
raw = gzip.decompress(runs_path.read_bytes()).decode()
runs = json.loads(raw) if raw.lstrip().startswith('[') else [json.loads(l) for l in raw.splitlines() if l.strip()]
runs.sort(key=lambda r: r['run_id'])
ids = [r['run_id'] for r in runs]
assert len(runs) == manifest['expected_runs'] == len(set(ids)), 'missing or duplicate runs'
for run in runs:
    assert config_id(Config(**run['config'])) == run['run_id'], 'run ID does not hash its configuration'
cells = {(r['config']['scenario'], r['config']['drones'], r['config']['cooperative_fraction'],
          r['config']['controller'], r['config']['seed']) for r in runs}
expected = set(itertools.product(manifest['scenarios'], manifest['counts'], manifest['fractions'],
                                 manifest['controllers'], manifest['discovery_seeds'] + manifest['holdout_seeds']))
assert cells == expected, 'runs do not cover exactly the declared grid'
for run in runs:
    c = run['config']
    assert c['fixed_wing_fraction'] == manifest['fixed_wing_fraction'] and c['duration'] == manifest['duration_s'] and c['dt'] == manifest['dt_s']
    for key in ('admission', 'admission_limit', 'routes', 'require_invariant_backup'):
        if key in manifest:
            assert c[key] == manifest[key], key
saved = json.loads(summary_path.read_text())
rebuilt = summarize(runs, manifest)
for key in ('results_sha256', 'ranking_discovery', 'ranking_holdout', 'passed_empirical_gate', 'selected_on_discovery'):
    assert rebuilt[key] == saved[key], 'summary differs: ' + key
print(len(runs))
'''

SWARM_SOURCE_HASH = r'''
import hashlib
from pathlib import Path
digest = hashlib.sha256()
for p in sorted(Path('swarm_sim').glob('*.py')):
    digest.update(p.name.encode()); digest.update(p.read_bytes())
print(digest.hexdigest())
'''


def swarm_campaign(source_archive, manifest, runs, summary):
    """Validate one swarm_sim campaign against its archived source; returns run count."""
    with tempfile.TemporaryDirectory(prefix='evidence-') as temp:
        extract(source_archive, temp)
        recorded = json.loads(Path(manifest).read_text())['source_sha256']
        actual = run_archived(SWARM_SOURCE_HASH, temp)
        if actual != recorded:
            raise ValueError(f'archived source {actual[:12]} differs from manifest {recorded[:12]}')
        return int(run_archived(SWARM_CAMPAIGN, temp, Path(manifest).resolve(), Path(runs).resolve(),
                                Path(summary).resolve()))


def iteration_01(flight):
    d = EXPERIMENTS / 'iteration-01'
    check_checksums(d)
    n = swarm_campaign(d / 'source-snapshot.tar.gz', d / 'manifest.json', d / 'runs.jsonl.gz', d / 'summary.json')
    return f'{n} runs, grid and summary rebuilt from archived source'


def iteration_02(flight):
    d = EXPERIMENTS / 'iteration-02'
    check_checksums(d)
    profile = json.loads((d / 'preferences.json').read_text())
    digest = hashlib.sha256(json.dumps(profile, sort_keys=True, allow_nan=False).encode()).hexdigest()
    total = 0
    for name in ('catalog', 'scale'):
        manifest = json.loads((d / f'{name}-manifest.json').read_text())
        if manifest['policy_sha256'] != digest or manifest['policy_profile'] != profile:
            raise ValueError(f'{name}: preference profile differs from manifest pin')
        total += swarm_campaign(d / 'source-snapshot.tar.gz', d / f'{name}-manifest.json',
                                d / f'{name}-runs.jsonl.gz', d / f'{name}-summary.json')
    return f'{total} runs in two campaigns; preference profile pin verified'


def iteration_03(flight):
    d = EXPERIMENTS / 'iteration-03'
    check_checksums(d)
    total = 0
    models = {('imitation', 'models/imitation.json'), ('mappo', 'models/mappo.json'),
              ('imitation', 'models/seed-43/imitation.json'), ('mappo', 'models/seed-43/mappo.json')}
    digests = {sha256(d / path): stage for stage, path in models}
    for campaign in sorted(p.parent for p in d.glob('*/manifest.json')):
        manifest = json.loads((campaign / 'manifest.json').read_text())
        for stage, pin in manifest.get('neural_checkpoints', {}).items():
            if digests.get(pin['checkpoint_sha256']) != stage:
                raise ValueError(f'{campaign.name}: no retained {stage} checkpoint matches the evaluated pin')
        total += swarm_campaign(d / 'simulator-source.tar.gz', campaign / 'manifest.json',
                                campaign / 'runs.json.gz', campaign / 'summary.json')
    if total != 948:
        raise ValueError(f'expected 948 evaluations, found {total}')
    return f'{total} runs in 8 campaigns; checkpoint pins match retained models'


CAPACITY = r'''
import hashlib, json, sys
from pathlib import Path
from airspace_capacity.assessment import summarize
from airspace_capacity.profile import Profile
digest = hashlib.sha256()
for package in ('airspace_capacity', 'swarm_sim'):
    for path in sorted(Path(package).glob('*.py')):
        digest.update(str(path).encode()); digest.update(path.read_bytes())
source = digest.hexdigest()
total = 0
for d in map(Path, sys.argv[1:]):
    manifest_bytes = (d/'manifest.json').read_bytes(); manifest = json.loads(manifest_bytes)
    assert manifest['source_sha256'] == source, d.name + ': archived source differs from manifest'
    raw = (d/'runs.jsonl').read_bytes(); runs = [json.loads(l) for l in raw.splitlines()]
    profiles = [Profile(**p).validate() for p in manifest['profiles']]
    rebuilt = summarize(runs, profiles, manifest['rates'], manifest['occupancy_limits'], manifest['seeds'])
    rebuilt.update(source_sha256=source, manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
                   runs_sha256=hashlib.sha256(raw).hexdigest())
    assert rebuilt == json.loads((d/'summary.json').read_text()), d.name + ': summary differs'
    total += len(runs)
print(total)
'''


def capacity_01(flight):
    d = EXPERIMENTS / 'capacity-01'
    check_checksums(d)
    with tempfile.TemporaryDirectory(prefix='evidence-') as temp:
        extract(d / 'source.tar.gz', temp)
        n = run_archived(CAPACITY, temp, *[(d / name).resolve() for name in ('baseline', 'sensitivity', 'density', 'layered')])
    return f'{n} runs; four summaries rebuilt from archived source'


def archived_validator(directory, archive, module, flight):
    """distributed-04 and readiness-04 ship their own validators inside their source archives."""
    with tempfile.TemporaryDirectory(prefix='evidence-') as temp:
        extract(directory / archive, temp)
        command = [sys.executable, '-m', module, str(directory.resolve())]
        if flight and module.endswith('distributed_evidence'):
            command.append('--flight')
        result = subprocess.run(command, cwd=temp, capture_output=True, text=True)
        if result.returncode:
            raise ValueError(result.stderr.strip()[-2000:])
        return result.stdout.strip().splitlines()[-1]


def distributed_04(flight):
    return archived_validator(EXPERIMENTS / 'distributed-04', 'source.tar.gz',
                              'scripts.validate_distributed_evidence', flight)


def readiness_04(flight):
    return archived_validator(EXPERIMENTS / 'readiness-04', 'source-after.tar.gz',
                              'scripts.validate_readiness_evidence', flight)


def excluded_preliminary(flight):
    d = EXPERIMENTS / 'excluded-preliminary'
    check_checksums(d)
    inventory = json.loads((d / 'inventory.json').read_text())
    found = {}
    with tarfile.open(d / 'excluded-preliminary.tar.gz') as tar:
        for member in tar.getmembers():
            if member.isfile():
                found[member.name] = hashlib.sha256(tar.extractfile(member).read()).hexdigest()
    if found != inventory:
        raise ValueError('archive contents differ from inventory')
    return f'{len(found)} excluded files match their inventory (never pooled with results)'


def frontier(name):
    def check(flight):
        result = subprocess.run([sys.executable, '-m', 'dense_uav_ops', 'validate', str(EXPERIMENTS / name)],
                                cwd=ROOT, capture_output=True, text=True)
        if result.returncode:
            raise ValueError(result.stderr.strip()[-2000:])
        return result.stdout.strip().splitlines()[-1]
    return check


SETS = {'iteration-01': iteration_01, 'iteration-02': iteration_02, 'iteration-03': iteration_03,
        'capacity-01': capacity_01, 'distributed-04': distributed_04, 'readiness-04': readiness_04,
        'excluded-preliminary': excluded_preliminary}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('sets', nargs='*', help='Evidence sets to validate (default: all)')
    parser.add_argument('--flight', action='store_true', help='Also recompute signed-control flight reconstructions')
    args = parser.parse_args()
    available = dict(SETS)
    for manifest in sorted(EXPERIMENTS.glob('frontier-*/manifest.json')):
        available[manifest.parent.name] = frontier(manifest.parent.name)
    names = args.sets or list(available)
    unknown = set(names) - set(available)
    if unknown:
        parser.error('Unknown evidence set: ' + ', '.join(sorted(unknown)))
    failed = False
    for name in names:
        try:
            print(f'{name}: OK - {available[name](args.flight)}', flush=True)
        except Exception as error:  # Report every set, then fail.
            failed = True
            print(f'{name}: FAILED - {error}', flush=True)
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
