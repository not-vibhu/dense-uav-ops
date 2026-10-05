"""Reanalyze the retained v0.1–v0.4 evidence for the technical report.

Reads only committed files under experiments/ and writes docs/report/data/history.json.
Every number the report cites about historical runs is computed here, so it can
be checked and recomputed. Validate the inputs first with scripts/validate_evidence.py.

Usage: python scripts/reanalyze_history.py
"""
from collections import Counter, defaultdict
import gzip
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
E = ROOT / 'experiments'


def jsonl_gz(path):
    return [json.loads(line) for line in gzip.decompress(path.read_bytes()).decode().splitlines() if line.strip()]


def rate(xs):
    return sum(xs) / len(xs) if xs else None


def iteration_01():
    """Run-level collision indicator: saturation with fleet size and association with volume exits."""
    runs = [r for r in jsonl_gz(E / 'iteration-01/runs.jsonl.gz')
            if r['config']['seed'] >= 1000 and r['metrics']['cooperative_aircraft'] > 0]
    by_size, by_exit = defaultdict(dict), {}
    for controller in ('goal', 'repulsion', 'barrier', 'negotiated'):
        group = [r for r in runs if r['config']['controller'] == controller]
        hit = lambda r: r['metrics']['participant_collision_pairs'] > 0
        for size in (10, 50, 100, 200):
            sized = [r for r in group if r['config']['drones'] == size]
            by_size[controller][size] = {'runs': len(sized), 'collision_run_rate': rate([hit(r) for r in sized])}
        exited = [r for r in group if r['metrics']['participant_volume_exits'] > 0]
        stayed = [r for r in group if r['metrics']['participant_volume_exits'] == 0]
        by_exit[controller] = {'runs': len(group), 'collision_run_rate': rate([hit(r) for r in group]),
                               'runs_with_exit': len(exited), 'collision_rate_with_exit': rate([hit(r) for r in exited]),
                               'runs_without_exit': len(stayed), 'collision_rate_without_exit': rate([hit(r) for r in stayed]),
                               'by_size_without_exit': {s: rate([hit(r) for r in stayed if r['config']['drones'] == s])
                                                        for s in (10, 50, 100, 200)}}
    return {'holdout_participating_runs': len(runs), 'collision_run_rate_by_fleet_size': by_size,
            'collision_vs_volume_exit': by_exit}


def iteration_03():
    """Failed-library (no admissible maneuver) fraction of the predictive teacher versus fleet size."""
    out = {}
    for campaign in ('off', 'checked', 'scale-off', 'scale-checked'):
        runs = json.loads(gzip.decompress((E / f'iteration-03/{campaign}/runs.json.gz').read_bytes()))
        rows = defaultdict(lambda: Counter())
        for r in runs:
            c, m = r['config'], r['metrics']
            if c['controller'] != 'predictive':
                continue
            row = rows[c['drones']]
            # Cooperative aircraft-steps are approximated from all-aircraft active time times the cooperative share.
            row['steps'] += m['active_aircraft_seconds'] / c['dt'] * m['cooperative_aircraft'] / c['drones']
            row['failed'] += m['predictive_no_admissible_drone_steps']
            row['runs'] += 1
            row['collision_runs'] += m['participant_collision_pairs'] > 0
            row['goal_reach'] += m['participant_completion_fraction']
        out[campaign] = {size: {'runs': row['runs'], 'failed_library_fraction': row['failed'] / row['steps'],
                                'collision_run_rate': row['collision_runs'] / row['runs'],
                                'goal_reach': row['goal_reach'] / row['runs']} for size, row in sorted(rows.items())}
    return {'note': 'Denominator approximates cooperative aircraft-steps; 2.4 s horizon, assumed traffic acceleration 4 m/s^2.',
            'predictive_by_fleet_size': out}


def capacity_01():
    """Who breached the protected distance, host-timing feedback, and why the shared baseline cannot pass."""
    out = {}
    for campaign in ('baseline', 'sensitivity', 'density', 'layered'):
        runs = [json.loads(l) for l in (E / f'capacity-01/{campaign}/runs.jsonl').read_text().splitlines()]
        m = [r['metrics'] for r in runs]
        out[campaign] = {'runs': len(runs),
                         'runs_with_collision': sum(x['collision_pairs'] > 0 for x in m),
                         'runs_with_protected_breach': sum(x['protected_volume_breach_pairs'] > 0 for x in m),
                         'breach_pairs': sum(x['protected_volume_breach_pairs'] for x in m),
                         'uas_manned_breach_pairs': sum(x['uas_manned_breach_pairs'] for x in m),
                         'runs_with_host_deadline_miss': sum(x['command_deadline_misses'] > 0 for x in m),
                         'peak_total_occupancy': max(x['peak_total_occupancy'] for x in m)}
    profile = json.loads((E / 'capacity-01/baseline/manifest.json').read_text())['profiles'][0]
    radius = max(profile['multirotor_radius_m'], profile['fixed_wing_radius_m'])
    band = [profile['floor_m'] + radius + 10, profile['ceiling_m'] - radius - 10]
    manned_sphere = [profile['manned_altitude_m'] - profile['manned_separation_m'],
                     profile['manned_altitude_m'] + profile['manned_separation_m']]
    return {'by_campaign': out, 'default_uas_altitude_band_m': band, 'manned_protection_altitudes_m': manned_sphere,
            'controlled_fraction_expected': profile['cooperative_fraction'] * profile['compliance_fraction']}


def distributed_04():
    """Blocker frequencies; density windows too short for any traversal to finish."""
    out = {}
    for study in ('catalog', 'guard-comparison', 'graph-comparison', 'density', 'partition-clock'):
        runs = jsonl_gz(E / f'distributed-04/{study}/runs.jsonl.gz')
        blockers = Counter(b for r in runs for b in r['blockers'])
        windows = sorted({(r['experiment']['duration'], r['experiment']['area']) for r in runs})
        out[study] = {'runs': len(runs), 'passing_runs': sum(r['observed_requirements_pass'] for r in runs),
                      'blocker_counts': dict(blockers.most_common()),
                      'duration_area_pairs': windows,
                      # Shortest start-to-goal distance in the archived scenario builder is 0.88 x side
                      # minus twice the 30 m deepest start offset, flown at the 12 m/s maximum speed.
                      'minimum_traversal_time_s': [round((.88 * area - 60.) / 12., 1) for _, area in windows],
                      'mean_cooperative_completion': rate([r['metrics']['completion_fraction'] for r in runs])}
    return out


def main():
    result = {'iteration_01': iteration_01(), 'iteration_03': iteration_03(), 'capacity_01': capacity_01(),
              'distributed_04': distributed_04()}
    path = ROOT / 'docs/report/data/history.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=1) + '\n')
    print(path)


if __name__ == '__main__':
    main()
