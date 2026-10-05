"""Cross-entropy search over the planner's four preference weights.

Only the cost weights that rank admissible candidates are searched; thresholds,
assumptions and the fallback are not. Fitness is lexicographic so a collision
can never be traded for efficiency: attributable contacts, then attributable
losses of separation, then fallback fraction, then incomplete operations, then
mean delay. No neural network or gradient is involved.
"""
from dataclasses import replace
import json
from pathlib import Path
import numpy as np

FIELDS = ('progress_weight', 'effort_weight', 'turn_weight', 'vertical_weight')


def fitness(results):
    m = [r['metrics'] for r in results]
    hours = sum(x['controlled_flight_hours'] for x in m) or 1e-9
    steps = sum(x['controlled_steps'] for x in m) or 1
    completion = [x['controlled_completion_fraction'] for x in m if x['controlled_completion_fraction'] is not None]
    delays = [x['mean_delay_s'] for x in m if x['mean_delay_s'] is not None]
    return [sum(x['attributable_contacts'] for x in m) / hours, sum(x['attributable_los'] for x in m) / hours,
            sum(x['fallback_steps'] for x in m) / steps, -float(np.mean(completion)) if completion else 0.,
            float(np.mean(delays)) if delays else 0.]


def search(base, seeds, population, generations, search_seed, out, workers=1):
    from concurrent.futures import ProcessPoolExecutor
    from ..campaign import _run
    rng = np.random.default_rng(search_seed)
    original = np.log([getattr(base.controller, f) for f in FIELDS])
    mean, sigma = original.copy(), np.ones(4)
    history, best = [], None
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for generation in range(generations):
            samples = np.clip(rng.normal(mean, sigma, size=(population, 4)), np.log(1e-4), np.log(100))
            samples[0] = original if best is None else np.log([best['weights'][f] for f in FIELDS])
            for member, sample in enumerate(samples):
                weights = dict(zip(FIELDS, np.exp(sample).tolist()))
                configs = [replace(base, seed=s, controller=replace(base.controller, **weights)).to_dict() for s in seeds]
                runs = list(pool.map(_run, configs))
                entry = {'generation': generation, 'member': member, 'weights': weights, 'fitness': fitness(runs)}
                history.append(entry)
                if best is None or entry['fitness'] < best['fitness']:
                    best = entry
                print(f'generation {generation + 1} member {member + 1}: fitness {np.round(entry["fitness"], 4).tolist()}', flush=True)
            elite = sorted(history[-population:], key=lambda x: x['fitness'])[:max(2, population // 3)]
            logs = np.log([[e['weights'][f] for f in FIELDS] for e in elite])
            mean, sigma = logs.mean(axis=0), np.maximum(logs.std(axis=0), .15)
    profile = {'schema': 'dense-uav-ops-preferences-v1', 'weights': best['weights'], 'fitness': best['fitness'],
               'training_seeds': list(seeds), 'training_experiment': base.to_dict(), 'search_seed': search_seed,
               'history': history,
               'scope': 'Narrow training suite; fitness ranks safety events before efficiency; not a safety result.'}
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(profile, indent=1, allow_nan=False) + '\n')
    return profile
