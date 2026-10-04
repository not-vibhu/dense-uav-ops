"""Reconstruct signed simulation controls, reconcile physical outcomes.

Uses the archived plant/geometry definitions and continuous oracle. This checks
record consistency, not observation truth, policy optimality or legal liability.
"""
import argparse
import gzip
import json
from pathlib import Path
import numpy as np
from dense_ops.audit import verify
from swarm_sim.config import Config
from swarm_sim.controllers import preferred_velocity, vehicle_project
from swarm_sim.oracle import swept_pairs, swept_obstacles, outside_volume
from swarm_sim.scenarios import build_world


def reconstruct(run, anchor):
    verify(run['audit']['events'], run['audit']['public'], anchor)
    e = run['experiment']
    if run['audit']['events'][0]['payload']['payload']['experiment'] != e:
        raise ValueError('Condition differs from signed start')
    if run['audit']['events'][-1]['payload']['payload']['metrics'] != run['metrics']:
        raise ValueError('Metrics differ from signed outcome')
    cfg = Config(drones=e['drones'], scenario=e['scenario'], seed=e['seed'], duration=e['duration'],
                 dt=e['dt'], area=e['area'], cooperative_fraction=e['cooperative_fraction'],
                 fixed_wing_fraction=e['fixed_wing_fraction'], controller='goal')
    w = build_world(cfg)
    p, v = w['position'].copy(), w['velocity'].copy()
    if e['manned']:
        m = e['manned']
        p = np.vstack((p, [[-e['area']/2-100-30*k, 0, 90] for k in range(m)]))
        v = np.vstack((v, np.tile([35., 0, 0], (m, 1))))
        w['goals'] = np.vstack((w['goals'], np.tile([e['area']/2, 0, 90], (m, 1))))
        for key, extra in [('cruise', np.full(m, 35.)), ('radius', np.full(m, 6.)),
                           ('fixed', np.ones(m, bool)), ('cooperative', np.zeros(m, bool))]:
            w[key] = np.concatenate((w[key], extra))
    n = len(p)
    manned = np.arange(n) >= e['drones']
    cooperative, fixed = w['cooperative'], w['fixed']
    active = ~cooperative & ~manned
    completed = np.zeros(n, bool)
    entry_v = v.copy(); v[cooperative] = 0
    events = {}
    for message in run['audit']['events']:
        event = message['payload']
        if event['kind'] in ('APPLY', 'ADMIT'):
            tick = int(round(event['time']/e['dt']))
            if abs(tick*e['dt']-event['time']) > 1e-8:
                raise ValueError('Off-grid flight event')
            events.setdefault(tick, []).append((int(message['actor']), event))
    collisions, breaches, obstacles, exits = set(), set(), set(), set()
    kinematic = 0
    previous = np.zeros_like(p)
    fault = w['scenario'].fault
    for step in range(round(e['duration']/e['dt'])):
        now = step*e['dt']
        approaching = manned & ~completed & (p[:, 0] < -e['area']/2)
        active[approaching & (p[:, 0]+v[:, 0]*e['dt'] >= -e['area']/2)] = True
        applied = np.zeros_like(p)
        recorded = set()
        for own, event in events.get(step, []):
            if not cooperative[own]:
                raise ValueError('Flight command for exogenous aircraft')
            if event['kind'] == 'ADMIT':
                if active[own] or completed[own]:
                    raise ValueError('Duplicate or completed admission')
                active[own] = True; v[own] = entry_v[own]
            else:
                body = event['payload']
                if own in recorded or not active[own]:
                    raise ValueError('Duplicate or inactive command')
                recorded.add(own)
                if not np.allclose(p[own], body['position'], atol=1e-7, rtol=0) or not np.allclose(v[own], body['velocity'], atol=1e-7, rtol=0):
                    raise ValueError('Signed state does not follow previous applied controls')
                applied[own] = body['control']
        if recorded != set(map(int, np.flatnonzero(active & cooperative))):
            raise ValueError('Missing applied control for active ownship')
        legacy = active & ~cooperative & ~manned
        target = preferred_velocity(p, w['goals'], w['cruise'], fixed, cfg)
        applied[legacy] = vehicle_project((target[legacy]-v[legacy])/.6, v[legacy], fixed[legacy], cfg)
        if 'stop' in fault and 3 <= now <= 6:
            stopped = legacy & ~fixed
            applied[stopped] = vehicle_project(-v[stopped], v[stopped], fixed[stopped], cfg)
        if 'intruder' in fault and 3 <= now <= 5:
            applied[legacy, 1] += 9
        if 'turn' in fault and 3 <= now <= 5:
            applied[legacy, 1] += 1
            applied[legacy] = vehicle_project(applied[legacy], v[legacy], fixed[legacy], cfg)
        if 'lag' in fault:
            applied[legacy] = .6*previous[legacy]+.4*applied[legacy]
        previous = applied.copy()
        actual = applied.copy()
        if e['fault'] in ('wind', 'compound') or 'wind' in fault:
            actual[active, 1] += e['disturbance']*np.sin(now)
        ids, others, distances, _ = swept_pairs(p, v, actual, active, w['radius'], 60., e['dt'])
        for a, b, distance in zip(ids, others, distances):
            pair = (int(a), int(b))
            if distance < w['radius'][a]+w['radius'][b]: collisions.add(pair)
            if distance < (60. if manned[a] or manned[b] else cfg.separation): breaches.add(pair)
        obstacles.update(swept_obstacles(p, v, actual, active, w['radius'], w['obstacles'], e['dt']))
        exits.update(map(int, np.flatnonzero(outside_volume(p, v, actual, cfg, e['dt']) & active & ~manned)))
        before_v = v.copy()
        moving = active | approaching
        p[moving] += v[moving]*e['dt']+.5*actual[moving]*e['dt']**2
        v[moving] += actual[moving]*e['dt']
        uas = active & ~manned
        bad = uas & ((np.linalg.norm(v, axis=1) > cfg.max_speed+1e-8) |
                     (np.linalg.norm(applied, axis=1) > cfg.acceleration_limit+1e-8))
        angle = np.abs((np.arctan2(v[:, 1], v[:, 0])-np.arctan2(before_v[:, 1], before_v[:, 0])+np.pi)%(2*np.pi)-np.pi)
        bad |= uas & fixed & ((np.linalg.norm(v[:, :2], axis=1) < cfg.fixed_wing_min_speed-1e-8) |
                              (np.abs(v[:, 2]) > cfg.fixed_wing_climb_limit+1e-8) |
                              (angle > np.deg2rad(cfg.fixed_wing_turn_rate_deg)*e['dt']+1e-8))
        kinematic += int(np.sum(bad))
        reached = active & (np.linalg.norm(p-w['goals'], axis=1) < cfg.goal_radius)
        reached |= active & manned & (p[:, 0] >= e['area']/2)
        completed |= reached; active[reached] = False
    measured = dict(collision_pairs=len(collisions), protected_breach_pairs=len(breaches), obstacle_pairs=len(obstacles),
                    volume_exits=len(exits), kinematic_violation_steps=kinematic,
                    cooperative_completed=int(np.sum(completed & cooperative)), total_completed=int(np.sum(completed)),
                    manned_completed=int(np.sum(completed & manned)))
    if any(run['metrics'][key] != value for key, value in measured.items()):
        raise ValueError('Published physical outcome differs from signed-control reconstruction')
    def categories(pairs):
        return dict(controlled=sum(cooperative[a] or cooperative[b] for a, b in pairs),
                    wholly_exogenous=sum(not cooperative[a] and not cooperative[b] for a, b in pairs),
                    manned_involved=sum(manned[a] or manned[b] for a, b in pairs))
    return {'experiment': e, 'verified': measured,
            'collision_categories': {k: int(v) for k, v in categories(collisions).items()},
            'breach_categories': {k: int(v) for k, v in categories(breaches).items()}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('campaign', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    from dense_ops.__main__ import validate_campaign
    validate_campaign(args.campaign)
    anchors = json.loads((args.campaign/'anchors.json').read_text())
    with gzip.open(args.campaign/'runs.jsonl.gz', 'rt') as stream:
        runs = [json.loads(line) for line in stream]
    if len(runs) != len(anchors): raise ValueError('Missing trusted anchors')
    rows = [reconstruct(run, anchor) for run, anchor in zip(runs, anchors)]
    args.out.write_text(json.dumps({'rows': rows,
        'scope': 'Signed-control plant reconstruction using the archived continuous oracle. Not a replay of surveillance, safety decisions or real aircraft truth.'}, indent=2)+'\n')
    print(f'{len(rows)} signed-control flights reconstructed; physical outcomes reconciled')


if __name__ == '__main__':
    main()
