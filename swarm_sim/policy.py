"""Reproducible cross-entropy search of preferences, not safety thresholds.

This is evolutionary policy optimization, not a neural/MARL implementation.
JSON profiles contain only four allowlisted positive scalar weights.
"""
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

import numpy as np

from .config import Config, POLICY_FIELDS


def load_policy(path):
    profile = json.loads(Path(path).read_text())
    if profile.get("schema") != "federated-swarm-preferences-v1":
        raise ValueError("Unknown policy profile schema")
    weights = profile.get("weights", {})
    if set(weights) != set(POLICY_FIELDS):
        raise ValueError("Policy may contain only the four preference weights")
    if any(isinstance(x, bool) or not isinstance(x, (float, int)) or
           not np.isfinite(x) or not 1e-4 <= x <= 100 for x in weights.values()):
        raise ValueError("Policy weights must be finite scalars in [0.0001, 100]")
    return weights, profile


def fitness(results):
    ms = [r["metrics"] for r in results]
    rate = lambda key: sum(bool(m[key]) for m in ms) / len(ms)
    drone_steps = sum(r["config"]["duration"] / r["config"]["dt"] *
                      r["metrics"]["cooperative_aircraft"] for r in results)
    return [rate("participant_collision_pairs"), rate("participant_obstacle_collisions"),
            rate("participant_volume_exits"),
            sum(m["predictive_no_admissible_drone_steps"] for m in ms) / max(drone_steps, 1),
            sum(m["participating_separation_pair_step_seconds"] for m in ms),
            -sum(m["participant_completion_fraction"] for m in ms) / len(ms),
            sum(m["control_effort_proxy"] for m in ms) / len(ms)]


def _evaluate(values):
    from .engine import simulate
    return simulate(Config(**values))


def learn(args):
    from .cli import source_hash, write_json
    from .scenarios import SCENARIOS
    if args.population < 4 or args.generations < 1 or not 1 <= args.workers <= 16:
        raise ValueError("population >= 4, generations >= 1, workers 1–16 required")
    if any(s not in SCENARIOS for s in args.scenarios):
        raise ValueError("Unknown training scenario")
    if len(set(args.train_seeds)) != len(args.train_seeds):
        raise ValueError("Duplicate training seeds")
    bases = [asdict(Config(controller="predictive", scenario=s, drones=n,
                           cooperative_fraction=args.cooperative, fixed_wing_fraction=args.fixed_wing,
                           duration=args.duration, dt=args.dt, seed=seed).validate())
             for s in args.scenarios for n in args.counts for seed in args.train_seeds]
    if args.cooperative <= 0:
        raise ValueError("Training requires control authority")
    rng = np.random.default_rng(args.search_seed)
    original = np.array([getattr(Config(), key) for key in POLICY_FIELDS])
    mean, sigma = np.log(original), np.full(4, 1.)
    history, best = [], None
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for generation in range(args.generations):
            samples = rng.normal(mean, sigma, size=(args.population, 4))
            samples[0] = np.log(original) if best is None else np.log(list(best["weights"].values()))
            samples = np.clip(samples, np.log(1e-4), np.log(100))
            for member, sample in enumerate(samples):
                weights = dict(zip(POLICY_FIELDS, np.exp(sample).tolist()))
                runs = list(pool.map(_evaluate, [{**base, **weights} for base in bases]))
                entry = {"generation": generation, "member": member, "weights": weights,
                         "fitness": fitness(runs), "runs": runs}
                history.append(entry)
                if best is None or entry["fitness"] < best["fitness"]:
                    best = entry
                print(f"Generation {generation+1}/{args.generations}, member {member+1}/{args.population}: "
                      f"risk {entry['fitness'][:4]}", flush=True)
            ranked = sorted(history[-args.population:], key=lambda e: e["fitness"])
            elite = np.log([list(e["weights"].values()) for e in ranked[:max(2, args.population//3)]])
            mean = np.mean(elite, axis=0)
            sigma = np.maximum(np.std(elite, axis=0), .15)
    profile = {"schema": "federated-swarm-preferences-v1", "method": "cross-entropy-evolutionary-search",
               "weights": best["weights"], "training_seeds": args.train_seeds,
               "training_scenarios": args.scenarios, "training_counts": args.counts,
               "training_fixed_wing_fraction": args.fixed_wing,
               "training_cooperative_fraction": args.cooperative,
               "training_fitness": best["fitness"], "search_seed": args.search_seed,
               "source_sha256": source_hash(), "training_evaluations": len(history)*len(bases),
               "limitations": "Narrow finite training suite; no test-set tuning, safety proof or neural RL."}
    write_json(args.out, profile)
    trace = Path(args.out).with_suffix(".training.json")
    write_json(trace, history)
    print(json.dumps({"profile": args.out, "training_trace": str(trace),
                      "training_evaluations": profile["training_evaluations"]}, indent=2))


def profile_digest(profile):
    return hashlib.sha256(json.dumps(profile, sort_keys=True, allow_nan=False).encode()).hexdigest()
