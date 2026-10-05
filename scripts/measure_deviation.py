"""Measure how far aircraft actually depart from constant-velocity prediction (supports report section 4.3).

Records one frontier-02 cell and, from true positions sampled every 0.4 s, computes
|p(t+tau) - p(t) - v(t) tau| with v(t) from a central difference, for controlled and
noncompliant aircraft, at tau = 1.2 s (report age plus a replanning step) and tau = 2.8 s
(report age plus the full 2.4 s planning horizon). Writes docs/report/data/deviation.json.

Usage: python scripts/measure_deviation.py
"""
import json
from pathlib import Path
import numpy as np

from dense_uav_ops.config import load, override
from dense_uav_ops.engine import simulate
from dense_uav_ops.traffic import build

ROOT = Path(__file__).resolve().parents[1]


def main():
    e = load(ROOT / 'profiles/frontier-base.json')
    for path, value in (('fleet.cooperative_fraction', 1.), ('fleet.noncompliant_fraction', .3),
                        ('fleet.noncompliant_acceleration_mps2', 3.), ('demand.uas_per_hour', 2880.),
                        ('assumptions.traffic_acceleration_mps2', 0.), ('seed', 21)):
        e = override(e, path, value)
    run = simulate(e, record=True)
    traffic = build(e)
    frames = run['replay']['frames']
    step = frames[1]['t'] - frames[0]['t']
    track = {}
    for k, frame in enumerate(frames):
        for i, p in zip(frame['id'], frame['p']):
            track.setdefault(i, {})[k] = np.array(p)
    out = {'experiment': e.to_dict(), 'frame_interval_s': step, 'results': {}}
    for tau in (1.2, 2.8):
        lag = int(round(tau / step))
        for group, mask in (('controlled', traffic.controlled), ('noncompliant', ~traffic.compliant & ~traffic.manned)):
            errors = []
            for i in np.flatnonzero(mask):
                positions = track.get(int(i), {})
                for k in positions:
                    if k - 1 in positions and k + 1 in positions and k + lag in positions:
                        v = (positions[k + 1] - positions[k - 1]) / (2 * step)
                        errors.append(float(np.linalg.norm(positions[k + lag] - positions[k] - v * tau)))
            errors = np.array(errors)
            out['results'][f'{group} tau={tau}'] = {'samples': int(len(errors)), 'median_m': float(np.median(errors)),
                                                    'p95_m': float(np.percentile(errors, 95)), 'max_m': float(errors.max())}
    out['worst_case_bound_m'] = {f'tau={tau}': .5 * 4. * tau ** 2 for tau in (1.2, 2.8)}
    path = ROOT / 'docs/report/data/deviation.json'
    path.write_text(json.dumps(out, indent=1) + '\n')
    print(json.dumps(out['results'], indent=1), out['worst_case_bound_m'])


if __name__ == '__main__':
    main()
