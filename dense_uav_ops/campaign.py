"""Declared experiment grids: run, resume, summarize and validate.

A campaign specification names a base profile, a list of arms (non-Cartesian
treatments such as controller and assumption settings), a Cartesian grid of
conditions and the seeds. Every declared run is recorded in the manifest before
any simulation starts; a summary is only produced when every declared run is
present exactly once, so failed or unfavourable runs cannot drop out.
"""
from concurrent.futures import ProcessPoolExecutor, as_completed
import gzip
import hashlib
import itertools
import json
from pathlib import Path
import platform
import random
import sys

import numpy as np

from . import __version__
from .config import canonical, from_dict, override
from .engine import CATEGORIES, simulate
from .stats import clopper_pearson, rate

PACKAGE = Path(__file__).resolve().parent
CORE = ('config.py', 'vehicles.py', 'oracle.py', 'traffic.py', 'surveillance.py', 'planner.py', 'recovery.py',
        'routes.py', 'daidalus.py', 'engine.py')


def source_digest(files=None):
    """SHA-256 over the simulation core (or given files) and the DAIDALUS bridge/configuration."""
    digest = hashlib.sha256()
    paths = [PACKAGE / f for f in files] if files else sorted(PACKAGE.rglob('*.py'))
    paths += sorted((PACKAGE.parent / 'integrations' / 'daidalus').glob('*'))
    for path in paths:
        digest.update(str(path.relative_to(PACKAGE.parent)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def expand(spec, root=Path('.')):
    """Declared runs as (cell key, Experiment) pairs, in a stable order."""
    experiment = from_dict(json.loads((root / spec['base_profile']).read_text())) if 'base_profile' in spec else from_dict({})
    experiment = from_dict(spec.get('base', {}), experiment)  # section-level merge over the profile
    arms = spec.get('arms') or [{'name': 'base', 'set': {}}]
    names = [arm['name'] for arm in arms]
    if len(set(names)) != len(names):
        raise ValueError('arm names must be unique')
    grid = spec.get('grid', {})
    axes = list(grid)
    for axis, values in grid.items():
        if not values or len(values) != len(set(map(json.dumps, values))):
            raise ValueError(f'grid axis {axis} must be nonempty without duplicates')
    seeds = spec['seeds']
    if not seeds or len(seeds) != len(set(seeds)):
        raise ValueError('seeds must be nonempty and distinct')
    runs = []
    for arm in arms:
        armed = experiment
        for path, value in arm.get('set', {}).items():
            armed = override(armed, path, value)
        armed = override(armed, 'name', arm['name'])
        for point in itertools.product(*(grid[a] for a in axes)):
            cell = armed
            for axis, value in zip(axes, point):
                cell = override(cell, axis, value)
            key = {'arm': arm['name'], **dict(zip(axes, point))}
            for seed in seeds:
                runs.append((key, override(cell, 'seed', seed).validate()))
    ids = [e.run_id() for _, e in runs]
    if len(ids) != len(set(ids)):
        raise ValueError('two declared runs have identical configurations')
    return runs


def _run(document):
    from .config import from_dict
    return simulate(from_dict(document))


def deterministic(run):
    """The part of a run that must reproduce exactly: everything except host timing (JSON-normalized)."""
    return json.loads(json.dumps({k: v for k, v in run.items() if k != 'compute'}, allow_nan=False))


def run_campaign(spec_path, out, workers=1, root=Path('.')):
    spec_path, out = Path(spec_path), Path(out)
    spec = json.loads(spec_path.read_text())
    runs = expand(spec, root)
    manifest = {'schema': 'dense-uav-ops-campaign-v1', 'name': spec.get('name', spec_path.stem), 'spec': spec,
                'runs': [{'run_id': e.run_id(), 'cell': key, 'experiment': e.to_dict()} for key, e in runs],
                'version': __version__, 'core_sha256': source_digest(CORE), 'source_sha256': source_digest(),
                'python': sys.version.split()[0], 'numpy': np.__version__, 'platform': platform.platform()}
    manifest = json.loads(json.dumps(manifest, allow_nan=False))  # compare in the form it is stored
    out.mkdir(parents=True, exist_ok=True)
    manifest_path = out / 'manifest.json'
    if manifest_path.exists():
        previous = json.loads(manifest_path.read_text())
        if previous['runs'] != manifest['runs'] or previous['core_sha256'] != manifest['core_sha256']:
            raise ValueError('output holds a different campaign or simulation core; use a new directory')
    else:
        manifest_path.write_text(json.dumps(manifest, indent=1) + '\n')
    log = out / 'runs.jsonl'
    done = {}
    if log.exists():
        for line in log.read_text().splitlines():
            if line.strip():
                row = json.loads(line)
                done[row['run_id']] = row
    pending = [e for _, e in runs if e.run_id() not in done]
    print(f'{len(runs)} declared runs, {len(pending)} pending, {workers} workers', flush=True)
    with log.open('a') as stream, ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_run, e.to_dict()): e for e in pending}
        for count, future in enumerate(as_completed(futures), 1):
            result = future.result()  # a failed run fails the campaign; nothing is skipped silently
            stream.write(json.dumps(result, allow_nan=False) + '\n')
            stream.flush()
            done[result['run_id']] = result
            if count % 10 == 0 or count == len(pending):
                print(f'{count}/{len(pending)} complete', flush=True)
    return finish(out)


def load_runs(out):
    out = Path(out)
    if (out / 'runs.jsonl.gz').exists():
        text = gzip.decompress((out / 'runs.jsonl.gz').read_bytes()).decode()
    else:
        text = (out / 'runs.jsonl').read_text()
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def finish(out):
    out = Path(out)
    manifest = json.loads((out / 'manifest.json').read_text())
    runs = load_runs(out)
    summary = summarize(manifest, runs)
    (out / 'summary.json').write_text(json.dumps(summary, indent=1, allow_nan=False) + '\n')
    (out / 'REPORT.md').write_text(report(summary))
    return summary


def summarize(manifest, runs):
    declared = {r['run_id']: r for r in manifest['runs']}
    seen = [r['run_id'] for r in runs]
    if len(seen) != len(set(seen)) or set(seen) != set(declared):
        missing = len(set(declared) - set(seen))
        raise ValueError(f'campaign incomplete or inconsistent: {missing} missing, {len(seen) - len(set(seen))} duplicated')
    by_id = {r['run_id']: r for r in runs}
    cells = {}
    for entry in manifest['runs']:
        run = by_id[entry['run_id']]
        if run['experiment'] != entry['experiment']:
            raise ValueError(f'run {entry["run_id"]} differs from its declared configuration')
        cells.setdefault(json.dumps(entry['cell'], sort_keys=True), []).append(run)
    rows = [summarize_cell(json.loads(key), group) for key, group in cells.items()]
    ordered = sorted(runs, key=lambda r: r['run_id'])
    digest = hashlib.sha256(b''.join(canonical(deterministic(r)) for r in ordered)).hexdigest()
    return {'schema': 'dense-uav-ops-summary-v1', 'name': manifest['name'], 'runs': len(runs),
            'outcomes_sha256': digest, 'core_sha256': manifest['core_sha256'], 'cells': rows,
            'units': {'rates': 'events per flight-hour inside the measurement window',
                      'run': 'one fixed-duration simulation; the independent replicate',
                      'interval_if_independent': 'exact Poisson interval assuming independent events; optimistic when events cluster within runs'}}


def summarize_cell(cell, group):
    """Pool a cell's runs. Events and exposure are summed; operations are pooled, not run means averaged."""
    m = [r['metrics'] for r in group]
    total = lambda key: sum(x[key] for x in m)
    controlled_hours = total('controlled_flight_hours')
    uas_hours = total('uas_flight_hours')
    per_run = lambda key, hours: [x[key] / x[hours] if x[hours] > 0 else None for x in m]
    values = lambda key: [x[key] for x in m if x[key] is not None]
    mean = lambda xs: float(np.mean(xs)) if len(xs) else None
    done = [d for x in m for d in x['controlled_delays_s']]
    censored = [d for x in m for d in x['controlled_censored_delays_s']]
    operations = len(done) + len(censored)
    completed_window = total('controlled_completed_in_window')
    per_thousand = lambda events: 1000. * events / completed_window if completed_window else None
    contact_runs = sum(x['attributable_uas_contacts'] > 0 for x in m)
    steps = total('controlled_steps')
    fallback = [x['fallback_steps'] for x in m]
    measurement = group[0]['experiment']['window']['measurement_s']
    return {
        'cell': cell, 'runs': len(group), 'seeds': sorted(r['experiment']['seed'] for r in group),
        'offered_uas_per_hour': mean([x['offered_uas'] * 3600 / measurement for x in m]),
        'mean_uas_occupancy': mean(values('mean_uas_occupancy')),
        'peak_uas_occupancy': max(x['peak_uas_occupancy'] for x in m),
        'uas_throughput_per_hour': mean(values('uas_throughput_per_hour')),
        'controlled_throughput_per_hour': mean(values('controlled_throughput_per_hour')),
        'controlled_operations': operations,
        'controlled_completion_fraction': len(done) / operations if operations else None,
        'mean_delay_completed_s': mean(done),
        'p95_delay_completed_s': float(np.percentile(done, 95)) if done else None,
        'mean_delay_lower_bound_s': mean(done + censored),
        'mean_entry_wait_s': mean(values('mean_entry_wait_s')),
        'backlog_growth_max': max((x['backlog_growth'] for x in m if x['backlog_growth'] is not None), default=None),
        'controlled_flight_hours': controlled_hours,
        'controlled_completed_in_window': completed_window,
        'attributable_uas_los': rate(total('attributable_uas_los'), controlled_hours),
        'attributable_uas_contacts': rate(total('attributable_uas_contacts'), controlled_hours),
        'attributable_uas_los_per_1000_completed': per_thousand(total('attributable_uas_los')),
        'attributable_uas_contacts_per_1000_completed': per_thousand(total('attributable_uas_contacts')),
        'attributable_los': rate(total('attributable_los'), controlled_hours),
        'attributable_contacts': rate(total('attributable_contacts'), controlled_hours),
        'all_los_per_uas_hour': rate(total('all_los'), uas_hours),
        'all_contacts_per_uas_hour': rate(total('all_contacts'), uas_hours),
        'los_by_category': {c: sum(x['los_events'][c] for x in m) for c in CATEGORIES},
        'contacts_by_category': {c: sum(x['contact_events'][c] for x in m) for c in CATEGORIES},
        'entry_phase_attributable_uas_los': total('entry_attributable_uas_los'),
        'entry_phase_attributable_uas_contacts': total('entry_attributable_uas_contacts'),
        'entry_phase_los_by_category': {c: sum(x['entry_los_events'][c] for x in m) for c in CATEGORIES},
        'per_run_attributable_uas_los_per_hour': per_run('attributable_uas_los', 'controlled_flight_hours'),
        'runs_with_attributable_uas_contact': [contact_runs, len(group), list(clopper_pearson(contact_runs, len(group)))],
        'fallback_fraction': (sum(fallback) / steps if steps else None) if None not in fallback else None,
        'daidalus_unresolved_fraction': unresolved(m),
        'obstacle_contacts_controlled': total('obstacle_contacts_controlled'),
        'volume_exits_controlled': total('volume_exits_controlled'),
        'kinematic_violation_steps': total('kinematic_violation_steps'),
        'unknown_traffic_seconds': total('unknown_traffic_seconds'),
        'entry_denials': total('entry_denials'),
        'minimum_separation_m': min((x['minimum_separation_m'] for x in m if x['minimum_separation_m'] is not None), default=None),
        'mean_control_ms_per_controlled_step': mean([r['compute']['control_ms_per_controlled_step'] for r in group]),
    }


def unresolved(metrics):
    """DAIDALUS decisions without a conflict-free heading, pooled over runs (weighted by decisions)."""
    counts = [x['daidalus_guidance'] for x in metrics if 'daidalus_guidance' in x]
    decisions = sum(sum(c.values()) for c in counts)
    return sum(c['recovery'] + c['none'] for c in counts) / decisions if decisions else None


def report(summary):
    fmt = lambda x, spec='.2f': '—' if x is None else format(x, spec)
    rows = [f"# Campaign {summary['name']}", '',
            f"{summary['runs']} runs. Outcome digest `{summary['outcomes_sha256'][:16]}`; simulation core `{summary['core_sha256'][:16]}`.",
            '', 'Attributable UAS events involve at least one controlled aircraft and no manned aircraft and occur in flight, i.e. not within one '
            'report interval of either aircraft entering (entry-phase events are listed separately in summary.json); rates are per controlled flight-hour '
            'in the measurement window, and per 1000 controlled operations completed in that window. Delay is completion minus '
            '(request + nominal traversal time), with unfinished operations counted at the end of the drain window (a lower bound). '
            'Intervals in summary.json assume independent events and are optimistic; per-run values are listed there too.', '']
    conditions = list(summary['cells'][0]['cell'])
    rows.append('| ' + ' | '.join(conditions) + ' | runs | mean occupancy | throughput/h | completion | mean delay s (lower bound) | fallback | attributable UAS LoS/h (events) | per 1000 ops | contacts (events) |')
    rows.append('|' + '---|' * (len(conditions) + 9))
    for c in summary['cells']:
        los, contact = c['attributable_uas_los'], c['attributable_uas_contacts']
        rows.append('| ' + ' | '.join(str(c['cell'][k]) for k in conditions) +
                    f" | {c['runs']} | {fmt(c['mean_uas_occupancy'], '.1f')} | {fmt(c['uas_throughput_per_hour'], '.0f')}"
                    f" | {fmt(c['controlled_completion_fraction'])} | {fmt(c['mean_delay_lower_bound_s'], '.1f')} | {fmt(c['fallback_fraction'], '.3f')}"
                    f" | {fmt(los['per_hour'], '.2f')} ({los['events']}) | {fmt(c['attributable_uas_los_per_1000_completed'], '.1f')}"
                    f" | {contact['events']} |")
    rows += ['', 'No cell is an operational capacity or safety qualification. See docs/research-question.md for definitions.', '']
    return '\n'.join(rows)


def publish(out):
    """Compress the run log deterministically (sorted by run ID) and write checksums."""
    out = Path(out)
    runs = sorted(load_runs(out), key=lambda r: r['run_id'])
    text = ''.join(json.dumps(r, sort_keys=True, allow_nan=False) + '\n' for r in runs)
    (out / 'runs.jsonl.gz').write_bytes(gzip.compress(text.encode(), mtime=0))
    if (out / 'runs.jsonl').exists():
        (out / 'runs.jsonl').unlink()
    checksums = {str(p.relative_to(out)): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in sorted(out.rglob('*')) if p.is_file() and p.name != 'checksums.json'}
    (out / 'checksums.json').write_text(json.dumps(checksums, indent=1) + '\n')


def validate(out, rerun=0, seed=0):
    """Check completeness, configuration hashes, summary and checksums; optionally re-simulate runs."""
    out = Path(out)
    manifest = json.loads((out / 'manifest.json').read_text())
    if (out / 'checksums.json').exists():
        for name, expected in json.loads((out / 'checksums.json').read_text()).items():
            if hashlib.sha256((out / name).read_bytes()).hexdigest() != expected:
                raise ValueError(f'modified evidence file: {name}')
    runs = load_runs(out)
    for run in runs:
        if from_dict(run['experiment']).run_id() != run['run_id']:
            raise ValueError(f'run {run["run_id"]} does not hash its configuration')
    rebuilt = summarize(manifest, runs)
    saved = json.loads((out / 'summary.json').read_text())
    if rebuilt != saved:
        raise ValueError('summary differs from the one rebuilt from raw runs')
    message = f"{len(runs)} declared runs present once; configurations, summary{' and checksums' if (out / 'checksums.json').exists() else ''} verified"
    if rerun:
        if source_digest(CORE) != manifest['core_sha256']:
            raise ValueError('re-simulation needs the recorded simulation core; extract the archived source')
        chosen = random.Random(seed).sample(runs, min(rerun, len(runs)))
        for run in chosen:
            again = _run(run['experiment'])
            if deterministic(again) != deterministic(run):
                raise ValueError(f'run {run["run_id"]} did not reproduce exactly')
        message += f'; {len(chosen)} runs re-simulated identically'
    return message
