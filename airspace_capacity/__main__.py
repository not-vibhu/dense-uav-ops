import argparse
from dataclasses import asdict, replace
import hashlib
import json
import math
from pathlib import Path
import platform
import sys

from .profile import Profile
from .simulation import simulate
from .assessment import render, summarize


def source_digest():
    digest = hashlib.sha256()
    root = Path(__file__).resolve().parent.parent
    for package in ('airspace_capacity', 'swarm_sim'):
        for path in sorted((root/package).glob('*.py')):
            digest.update(str(path.relative_to(root)).encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description='Conditional mixed-traffic research capacity assessment')
    parser.add_argument('--profile', type=Path, help='JSON profile or {"profiles": [...]} envelope')
    parser.add_argument('--rates', nargs='+', type=float, default=[120., 360., 720.])
    parser.add_argument('--occupancy-limits', nargs='+', type=int, default=[10, 50, 100, 200])
    parser.add_argument('--seeds', nargs='+', type=int, default=[7000, 7001, 7002])
    parser.add_argument('--scenarios', nargs='+', help='Expand each supplied profile across scenarios')
    parser.add_argument('--out', type=Path, default=Path('artifacts/capacity'))
    parser.add_argument('--serve', action='store_true', help='Open the local expert configuration lab')
    parser.add_argument('--port', type=int, default=8766)
    args = parser.parse_args()
    if args.serve:
        from .server import serve
        serve(args.port, args.out)
        return
    raw = json.loads(args.profile.read_text()) if args.profile else asdict(Profile())
    profiles = [Profile(**item).validate() for item in (raw['profiles'] if 'profiles' in raw else [raw])]
    if args.scenarios:
        profiles = [replace(p, scenario=s).validate() for p in profiles for s in args.scenarios]
    try:
        summary = run_campaign(args, profiles)
    except ValueError as error:
        parser.error(str(error))
    print(render(summary))


def run_campaign(args, profiles, progress=None):
    from .assessment import identity
    if not profiles or len({identity(asdict(p)) for p in profiles}) != len(profiles):
        raise ValueError('Duplicate profiles are not allowed')
    for p in profiles:
        p.validate()
    for values in (args.rates, args.occupancy_limits, args.seeds):
        if not values or len(values) != len(set(values)):
            raise ValueError('Nonempty grid without duplicate values required')
    # Validate the complete grid before launching an expensive campaign.
    if (any(not isinstance(x, (int,float)) or isinstance(x, bool) or not math.isfinite(x) or x <= 0 for x in args.rates) or
            any(not isinstance(x,int) or isinstance(x,bool) or not 1 <= x <= 500 for x in args.occupancy_limits) or
            any(not isinstance(x,int) or isinstance(x,bool) or x < 0 for x in args.seeds)):
        raise ValueError('Invalid rates, occupancy limits or seeds')
    from .simulation import build_traffic
    for profile in profiles:
        for rate in args.rates:
            build_traffic(profile, rate, args.seeds[0])
    args.out.mkdir(parents=True, exist_ok=True)
    if any((args.out/name).exists() for name in ('manifest.json', 'runs.jsonl', 'summary.json', 'REPORT.md')):
        raise ValueError('Output already contains evidence; use a new directory')
    manifest = dict(schema='federated-swarm.airspace-capacity-campaign.v1',
                    profiles=[asdict(p) for p in profiles], rates=args.rates,
                    occupancy_limits=args.occupancy_limits, seeds=args.seeds,
                    source_sha256=source_digest(), python=sys.version, platform=platform.platform())
    (args.out/'manifest.json').write_text(json.dumps(manifest, indent=2, allow_nan=False)+'\n')
    runs = []
    total = len(profiles)*len(args.rates)*len(args.occupancy_limits)*len(args.seeds)
    with (args.out/'runs.jsonl').open('w') as output:
        for profile in profiles:
            for rate in args.rates:
                for limit in args.occupancy_limits:
                    for seed in args.seeds:
                        run = simulate(profile, rate, limit, seed)
                        output.write(json.dumps(run, allow_nan=False)+'\n')
                        output.flush()
                        runs.append(run)
                        if progress:
                            progress(len(runs), total)
                        else:
                            print(f'{len(runs)}/{total} {profile.name}/{profile.scenario} rate={rate:g} limit={limit} seed={seed}', flush=True)
    if source_digest() != manifest['source_sha256']:
        raise RuntimeError('Source changed during campaign; evidence cannot be summarized')
    summary = summarize(runs, profiles, args.rates, args.occupancy_limits, args.seeds)
    summary['source_sha256'] = manifest['source_sha256']
    summary['manifest_sha256'] = hashlib.sha256((args.out/'manifest.json').read_bytes()).hexdigest()
    summary['runs_sha256'] = hashlib.sha256((args.out/'runs.jsonl').read_bytes()).hexdigest()
    (args.out/'summary.json').write_text(json.dumps(summary, indent=2, allow_nan=False)+'\n')
    (args.out/'REPORT.md').write_text(render(summary))
    return summary


if __name__ == '__main__':
    main()
