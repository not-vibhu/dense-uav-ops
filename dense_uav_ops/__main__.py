"""Command-line interface: python -m dense_uav_ops <command> (or the `dense-uav-ops` script)."""
import argparse
import json
from pathlib import Path
import sys

from .config import Experiment, load, override


def parse_value(text):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def experiment_from(args):
    experiment = load(args.profile) if args.profile else Experiment()
    for item in args.set or []:
        if '=' not in item:
            raise ValueError(f'--set expects path=value, got {item}')
        path, value = item.split('=', 1)
        experiment = override(experiment, path, parse_value(value))
    return experiment.validate()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=1, allow_nan=False) + '\n')


def main(argv=None):
    parser = argparse.ArgumentParser(prog='dense-uav-ops', description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest='command', required=True)

    def configurable(p):
        p.add_argument('--profile', type=Path, help='JSON profile (partial overrides of the defaults)')
        p.add_argument('--set', action='append', metavar='PATH=VALUE',
                       help='override one setting, e.g. --set assumptions.traffic_acceleration_mps2=1')

    show = sub.add_parser('show', help='print the fully resolved experiment configuration')
    configurable(show)
    run = sub.add_parser('run', help='simulate one experiment')
    configurable(run)
    run.add_argument('--out', type=Path, help='write the full result JSON here')
    run.add_argument('--replay', type=Path, help='write a self-contained HTML replay here')
    camp = sub.add_parser('campaign', help='run a declared grid (resumable)')
    camp.add_argument('spec', type=Path)
    camp.add_argument('--out', type=Path, required=True)
    camp.add_argument('--workers', type=int, default=1)
    summ = sub.add_parser('summarize', help='rebuild summary.json and REPORT.md from a complete campaign')
    summ.add_argument('directory', type=Path)
    pub = sub.add_parser('publish', help='compress the run log deterministically and write checksums')
    pub.add_argument('directory', type=Path)
    val = sub.add_parser('validate', help='verify a campaign directory')
    val.add_argument('directory', type=Path)
    val.add_argument('--rerun', type=int, default=0, help='also re-simulate this many randomly chosen runs')
    rep = sub.add_parser('replay', help='render a recorded run as HTML')
    rep.add_argument('result', type=Path)
    rep.add_argument('--out', type=Path, required=True)
    daa = sub.add_parser('daidalus-check', help='run reference encounters through the DAIDALUS bridge')
    daa.add_argument('--manifest', default='artifacts/daidalus/manifest.json')
    from .learning.cli import add_commands
    add_commands(sub, configurable)
    args = parser.parse_args(argv)
    try:
        if args.command == 'show':
            print(json.dumps(experiment_from(args).to_dict(), indent=1))
        elif args.command == 'run':
            from .engine import simulate
            result = simulate(experiment_from(args), record=bool(args.replay))
            if args.out:
                write_json(args.out, result)
            if args.replay:
                from .replay import render
                args.replay.parent.mkdir(parents=True, exist_ok=True)
                args.replay.write_text(render(result))
            print(json.dumps(result['metrics'], indent=1))
        elif args.command == 'campaign':
            from .campaign import run_campaign
            if not 1 <= args.workers <= 64:
                raise ValueError('workers must be 1–64')
            summary = run_campaign(args.spec, args.out, args.workers)
            print(f"{summary['runs']} runs summarized in {args.out / 'REPORT.md'}")
        elif args.command == 'summarize':
            from .campaign import finish
            print(f"{finish(args.directory)['runs']} runs summarized")
        elif args.command == 'publish':
            from .campaign import publish
            publish(args.directory)
            print(f'{args.directory} compressed and checksummed')
        elif args.command == 'validate':
            from .campaign import validate
            print(validate(args.directory, args.rerun))
        elif args.command == 'replay':
            from .replay import render
            result = json.loads(args.result.read_text())
            if 'replay' not in result:
                raise ValueError('result has no replay; rerun with --replay or --out from `run --replay`')
            args.out.write_text(render(result))
        elif args.command == 'daidalus-check':
            from .daidalus import Bridge
            cases = [('head-on 100 m', [0, 0, 60], [0, 8, 0], [0, 100, 60], [0, -8, 0]),
                     ('crossing 80 m', [0, 0, 60], [0, 8, 0], [-60, 60, 60], [8, 0, 0]),
                     ('diverging', [0, 0, 60], [0, 8, 0], [0, -60, 60], [0, -8, 0]),
                     ('vertically separated', [0, 0, 60], [0, 8, 0], [0, 100, 100], [0, -8, 0])]
            with Bridge(args.manifest) as bridge:
                for k, (name, p0, v0, p1, v1) in enumerate(cases):
                    result = bridge.query(k, [k, 100 + k], [p0, p1], [v0, v1], 0.)
                    print(f"{name:22s} alert level {result['alerts'][0][1]}; bands {result['bands']}")
        else:
            from .learning.cli import dispatch
            dispatch(args)
    except (ValueError, FileNotFoundError) as error:
        parser.error(str(error))


if __name__ == '__main__':
    sys.exit(main())
