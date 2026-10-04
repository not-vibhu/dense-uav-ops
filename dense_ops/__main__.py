import argparse
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, replace
import gzip
import hashlib
import itertools
import json
from pathlib import Path
import platform
import sys
from .engine import Experiment, from_document, simulate
from .audit import verify, digest
from .worker import worker
from airspace_capacity.assessment import upper_failure_probability


def source_hash():
    root = Path(__file__).resolve().parents[1]
    h = hashlib.sha256()
    files = [p for package in ('dense_ops', 'swarm_sim', 'airspace_capacity') for p in (root/package).glob('*.py')]
    files += list((root/'integrations/daidalus').glob('*'))
    for p in sorted(files):
        h.update(str(p.relative_to(root)).encode()); h.update(p.read_bytes())
    return h.hexdigest()


def write(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')


def summarize(runs, manifest):
    keys = [(r['experiment']['scenario'], r['experiment']['drones'], r['experiment']['mode'],
             r['experiment']['guard'], r['experiment']['fault'], r['experiment']['seed']) for r in runs]
    expected = [tuple(x) for x in manifest['grid']]
    if len(keys) != len(set(keys)) or set(keys) != set(expected):
        raise ValueError('Incomplete/duplicate campaign grid')
    cells = {}
    for r in runs:
        key = tuple(r['experiment'][x] for x in ('scenario', 'drones', 'mode', 'guard', 'fault'))
        cells.setdefault(key, []).append(r)
    rows = []
    for key, group in sorted(cells.items()):
        failed = sum(not r['observed_requirements_pass'] for r in group)
        upper = upper_failure_probability(failed, len(group), .05/len(cells))
        rows.append(dict(scenario=key[0], drones=key[1], mode=key[2], guard=key[3], fault=key[4], runs=len(group),
                         passing_runs=len(group)-failed, failure_upper_95_simultaneous=upper,
                         collisions=sum(r['metrics']['collision_pairs'] > 0 for r in group),
                         worst_completion=min(r['metrics']['completion_fraction'] for r in group),
                         peak_occupancy=max(r['metrics']['peak_occupancy'] for r in group),
                         worst_command_ms=max(r['metrics']['command_max_ms'] for r in group),
                         blockers=sorted({b for r in group for b in r['blockers']})))
    return dict(source_sha256=manifest['source_sha256'], evaluations=len(runs), cells=rows,
                operational_capacity=None, statistically_qualified_architecture=None,
                probability_unit='independent fixed-duration research runs; not per-flight or per-hour',
                timing_scope=f"host fleet measurements, {manifest['workers']} concurrent workers; not onboard WCET",
                decision='No deployment ranking: compare feasibility, service and safety within matched strata.')


def campaign(args):
    base = from_document(json.loads(args.profile.read_text())) if args.profile else Experiment()
    grids = (args.scenarios, args.counts, args.modes, args.guards, args.faults, args.seeds)
    if any(not x or len(x) != len(set(x)) for x in grids):
        raise ValueError('Nonempty grids without duplicate values required')
    grid = list(itertools.product(*grids))
    if len(grid) > 10000 or not 1 <= args.workers <= 4:
        raise ValueError('Campaign exceeds bounded research workload')
    configs = [replace(base, scenario=s, drones=n, mode=m, guard=g, fault=f, seed=seed).validate()
               for s, n, m, g, f, seed in grid]
    if any('graph' in c.mode for c in configs) and not args.checkpoint:
        raise ValueError('Graph campaign requires a checkpoint')
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    if any(out.iterdir()):
        raise ValueError('Evidence output must be empty')
    manifest = dict(schema='dense-ops-campaign-v1', source_sha256=source_hash(), grid=grid, base=asdict(base),
                    configs=[asdict(c) for c in configs], workers=args.workers, python=sys.version, platform=platform.platform(),
                    checkpoint_sha256=hashlib.sha256(args.checkpoint.read_bytes()).hexdigest() if args.checkpoint else None)
    write(out/'manifest.json', manifest)
    runs, anchors = [], []
    jobs = [(c, str(args.checkpoint) if args.checkpoint else None) for c in configs]
    with ProcessPoolExecutor(max_workers=args.workers) as pool, gzip.open(out/'runs.jsonl.gz', 'wt') as stream:
        for index, result in enumerate(pool.map(worker, jobs), 1):
            audit = result['audit']
            verify(audit['events'], audit['public'], audit['anchor'])
            anchors.append(audit['anchor'])
            stream.write(json.dumps(result, allow_nan=False)+'\n'); stream.flush()
            runs.append(result)
            print(f'{index}/{len(configs)} {result["experiment"]["scenario"]} n={result["experiment"]["drones"]} '
                  f'{result["experiment"]["mode"]}/{result["experiment"]["guard"]} '
                  f'collisions={result["metrics"]["collision_pairs"]} completion={result["metrics"]["completion_fraction"]:.2f}', flush=True)
    if source_hash() != manifest['source_sha256']:
        raise ValueError('Source changed while campaign was running')
    summary = summarize(runs, manifest)
    summary['raw_sha256'] = hashlib.sha256((out/'runs.jsonl.gz').read_bytes()).hexdigest()
    write(out/'anchors.json', anchors)
    summary['anchors_sha256'] = digest(anchors)
    write(out/'summary.json', summary)
    rows = ['# Distributed assurance development assessment', '', f'{len(runs)} complete evaluations. No operational capacity established.', '',
            '| Scenario | Fleet | Architecture | Guard | Fault | Runs | Passing | Collision runs | Worst completion | Peak occupancy |',
            '|---|---:|---|---|---|---:|---:|---:|---:|---:|']
    for r in summary['cells']:
        rows.append(f'| {r["scenario"]} | {r["drones"]} | {r["mode"]} | {r["guard"]} | {r["fault"]} | {r["runs"]} | {r["passing_runs"]} | {r["collisions"]} | {r["worst_completion"]:.1%} | {r["peak_occupancy"]} |')
    rows.extend(['', summary['timing_scope'], '', summary['probability_unit'], '', summary['decision'], ''])
    (out/'REPORT.md').write_text('\n'.join(rows))


def validate_campaign(path):
    manifest = json.loads((path/'manifest.json').read_text())
    if manifest['source_sha256'] != source_hash():
        raise ValueError('Campaign source mismatch; use archived corresponding source')
    anchors = json.loads((path/'anchors.json').read_text())
    with gzip.open(path/'runs.jsonl.gz', 'rt') as stream:
        runs = [json.loads(line) for line in stream]
    if len(anchors) != len(runs):
        raise ValueError('Missing trusted anchors')
    if len(manifest['configs']) != len(runs):
        raise ValueError('Missing declared configurations')
    for run, anchor, config in zip(runs, anchors, manifest['configs']):
        if run['experiment'] != config:
            raise ValueError('Run condition differs from campaign manifest')
        if run['audit']['anchor'] != anchor:
            raise ValueError('Anchor mismatch')
        verify(run['audit']['events'], run['audit']['public'], anchor)
        start = run['audit']['events'][0]['payload']
        if start['kind'] != 'START' or start['payload']['experiment'] != config:
            raise ValueError('Run condition differs from signed start record')
        end = run['audit']['events'][-1]['payload']
        if end['kind'] != 'END' or end['payload'] != {'metrics': run['metrics'], 'blockers': run['blockers']}:
            raise ValueError('Outcome differs from signed terminal record')
    expected = summarize(runs, manifest)
    stored = json.loads((path/'summary.json').read_text())
    if any(stored[k] != v for k, v in expected.items()):
        raise ValueError('Summary mismatch')
    if stored['raw_sha256'] != hashlib.sha256((path/'runs.jsonl.gz').read_bytes()).hexdigest() or stored['anchors_sha256'] != digest(anchors):
        raise ValueError('Published evidence digest mismatch')
    print(f'{len(runs)} complete evaluations, signatures, causal chains and outcomes verified')


def main():
    parser = argparse.ArgumentParser(description='Distributed assurance and federated swarm research')
    sub = parser.add_subparsers(dest='command', required=True)
    c = sub.add_parser('campaign')
    c.add_argument('--profile', type=Path)
    c.add_argument('--counts', type=int, nargs='+', default=[10, 50])
    c.add_argument('--scenarios', nargs='+', default=['crossing', 'corridor', 'urban'])
    c.add_argument('--modes', nargs='+', default=['local', 'federated'])
    c.add_argument('--guards', nargs='+', default=['reference', 'continuation'])
    c.add_argument('--faults', nargs='+', default=['none'])
    c.add_argument('--seeds', type=int, nargs='+', default=[8100, 8101])
    c.add_argument('--checkpoint', type=Path)
    c.add_argument('--workers', type=int, default=1)
    c.add_argument('--out', type=Path, required=True)
    v = sub.add_parser('validate'); v.add_argument('directory', type=Path)
    run = sub.add_parser('run'); run.add_argument('--profile', type=Path); run.add_argument('--out', type=Path, required=True)
    run.add_argument('--checkpoint', type=Path)
    t = sub.add_parser('train-federated'); t.add_argument('--out', type=Path, required=True)
    t.add_argument('--rounds', type=int, default=3)
    n = sub.add_parser('nasa-check'); n.add_argument('--manifest', type=Path, default=Path('artifacts/nasa/manifest.json'))
    n.add_argument('--out', type=Path, required=True)
    mc=sub.add_parser('modelcheck');mc.add_argument('--out',type=Path,required=True)
    args = parser.parse_args()
    try:
        if args.command == 'campaign': campaign(args)
        elif args.command == 'validate': validate_campaign(args.directory)
        elif args.command == 'run':
            exp = from_document(json.loads(args.profile.read_text())) if args.profile else Experiment()
            from .learning import GraphPolicy
            policy = GraphPolicy(args.checkpoint, source_hash()) if args.checkpoint else None
            write(args.out, simulate(exp, policy, record=True))
        elif args.command == 'train-federated':
            from .learning import train
            if not 1 <= args.rounds <= 20: raise ValueError('Rounds must be 1–20')
            clients = [[], [], []]; validation = [[], [], []]
            for domain, area in enumerate((320., 500., 700.)):
                for seed in (9000+domain*10, 9001+domain*10):
                    simulate(Experiment(drones=10, duration=5., area=area, cooperative_fraction=1., fixed_wing_fraction=0., seed=seed), samples=clients[domain])
                simulate(Experiment(drones=10, duration=5., area=area, cooperative_fraction=1., fixed_wing_fraction=0., seed=9100+domain), samples=validation[domain])
            if any(not x for x in clients+validation): raise ValueError('Insufficient admissible training/validation data')
            history = train(clients, validation, source_hash(), [9000,9001,9010,9011,9020,9021,9100,9101,9102], args.out, rounds=args.rounds)
            write(args.out.with_suffix('.data.json'), {'clients': clients, 'validation': validation, 'history': history,
                 'scope': 'Small development dataset, three airspace domains; no convergence or safety gain established.'})
            print(history)
        elif args.command == 'nasa-check':
            from .nasa import Daidalus
            daa = Daidalus(args.manifest)
            cases = []
            for name, distance, altitude, velocity in [('head-on',800.,100.,-20.), ('separated-diverging',5000.,100.,40.),
                                                       ('vertical-separated',800.,1000.,-20.), ('close',100.,100.,-20.)]:
                output = daa.evaluate(0,[0,1],[[0,0,100],[distance,0,altitude]],[[20,0,0],[velocity,0,0]])
                cases.append({'name': name, 'result': output})
            write(args.out, {'manifest': daa.manifest, 'cases': cases,
                            'scope': 'Actual DAIDALUS DO-365B reference snapshots; thresholds not dense-UAS operational minima.'})
            print([(c['name'], c['result']['alerts']) for c in cases])
        elif args.command == 'modelcheck':
            from .modelcheck import explore
            result=explore();write(args.out,result);print(result)
    except ValueError as error:
        parser.error(str(error))


if __name__ == '__main__':
    main()
