import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict
import hashlib
import itertools
import json
import os
from pathlib import Path
import time

from .config import Config, CONTROLLERS
from .engine import simulate, config_id
from .scenarios import SCENARIOS


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def _job(values):
    return simulate(Config(**values))


def source_hash():
    root = Path(__file__).parent
    digest = hashlib.sha256()
    for p in sorted(root.glob("*.py")):
        digest.update(p.name.encode())
        digest.update(p.read_bytes())
    return digest.hexdigest()


def campaign(args):
    from .analysis import summarize
    scenarios = list(SCENARIOS) if args.scenarios == ["all"] else args.scenarios
    if set(args.discovery_seeds) & set(args.holdout_seeds):
        raise ValueError("Discovery and holdout seeds must be disjoint")
    if len(args.counts) != len(set(args.counts)) or len(args.fractions) != len(set(args.fractions)):
        raise ValueError("Duplicate experimental strata are not allowed")
    if len(args.discovery_seeds) != len(set(args.discovery_seeds)) or len(args.holdout_seeds) != len(set(args.holdout_seeds)):
        raise ValueError("Duplicate seeds are not allowed")
    if len(args.controllers) != len(set(args.controllers)):
        raise ValueError("Duplicate controllers are not allowed")
    weights, profile = {}, None
    if "evolved" in args.controllers and not args.policy:
        raise ValueError("The evolved controller requires --policy")
    if args.policy:
        from .policy import load_policy
        weights, profile = load_policy(args.policy)
        if set(profile.get("training_seeds", [])) & set(args.discovery_seeds + args.holdout_seeds):
            raise ValueError("Learned policy training seeds must be disjoint from comparison seeds")
    jobs = [asdict(Config(scenario=sc, controller=c, drones=n, cooperative_fraction=f,
                          fixed_wing_fraction=args.fixed_wing, seed=seed, duration=args.duration,
                          dt=args.dt, **(weights if c == "evolved" else {})).validate())
            for sc, n, f, c, seed in itertools.product(scenarios, args.counts, args.fractions,
                                                      args.controllers, args.discovery_seeds + args.holdout_seeds)]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    manifest = {"scenarios": scenarios, "counts": args.counts, "fractions": args.fractions,
                "controllers": args.controllers, "discovery_seeds": args.discovery_seeds,
                "holdout_seeds": args.holdout_seeds, "fixed_wing_fraction": args.fixed_wing,
                "duration_s": args.duration, "dt_s": args.dt, "expected_runs": len(jobs),
                "source_sha256": source_hash(), "vehicle_model": "mixed-point-mass-v0",
                "ranking_order": ["participant collisions", "participant obstacle collisions",
                                  "participant volume exits", "worst stratum collisions",
                                  "separation exposure", "mission completion"]}
    if profile:
        from .policy import profile_digest
        manifest["policy_profile"] = profile
        manifest["policy_sha256"] = profile_digest(profile)
    prior_path = out / "manifest.json"
    if prior_path.exists() and json.loads(prior_path.read_text()) != manifest:
        raise ValueError("Output contains a different manifest/source revision; choose a new output directory")
    write_json(prior_path, manifest)
    path = out / "runs.jsonl"
    results = []
    if path.exists():
        for line in path.read_text().splitlines():
            if line.strip():
                results.append(json.loads(line))
    ids = {r["run_id"] for r in results}
    if len(ids) != len(results):
        raise ValueError("Duplicate existing runs detected")
    pending = [j for j in jobs if config_id(Config(**j)) not in ids]
    started = time.perf_counter()
    print(f"Campaign: {len(jobs)} runs, {len(pending)} remaining, {args.workers} workers", flush=True)
    with path.open("a") as log, ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(_job, j): j for j in pending}
        for future in as_completed(futures):
            result = future.result()  # Any failed run fails the campaign, never silently excluded.
            results.append(result)
            log.write(json.dumps(result, allow_nan=False) + "\n")
            log.flush()
            if len(results) % 40 == 0 or len(results) == len(jobs):
                print(f"Completed {len(results)}/{len(jobs)}; elapsed {time.perf_counter()-started:.1f}s", flush=True)
    results.sort(key=lambda r: r["run_id"])
    summary = summarize(results, manifest)
    write_json(out / "summary.json", summary)
    write_json(out / "results.json", results)
    build_report(out, summary)
    print(json.dumps({"selected_on_discovery": summary["selected_on_discovery"],
                      "stable_on_holdout": summary["selection_stable_on_holdout"],
                      "safety_gate": summary["passed_empirical_gate"],
                      "report": str(out / "report.html")}, indent=2))


def build_report(out, summary):
    from .report import report_html, report_markdown
    (out / "report.html").write_text(report_html(summary))
    (out / "REPORT.md").write_text(report_markdown(summary))


def main():
    parser = argparse.ArgumentParser(description="Mixed-equipage UAS simulation; research use")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("scenarios")
    run = sub.add_parser("run")
    run.add_argument("--scenario", choices=SCENARIOS, default="crossing")
    run.add_argument("--controller", choices=CONTROLLERS, default="negotiated")
    run.add_argument("--drones", type=int, default=50)
    run.add_argument("--cooperative", type=float, default=.5)
    run.add_argument("--fixed-wing", type=float, default=.4)
    run.add_argument("--seed", type=int, default=0)
    run.add_argument("--duration", type=float, default=36)
    run.add_argument("--dt", type=float, default=.2)
    run.add_argument("--out", default="artifacts/replay.json")
    run.add_argument("--policy", help="JSON preference profile; predictive controller only")
    compare = sub.add_parser("compare")
    compare.add_argument("--scenarios", nargs="+", default=["all"])
    compare.add_argument("--counts", nargs="+", type=int, default=[10, 50, 100, 200])
    compare.add_argument("--fractions", nargs="+", type=float, default=[0, .1, .5, .9, 1])
    compare.add_argument("--discovery-seeds", nargs="+", type=int, default=[0, 1])
    compare.add_argument("--holdout-seeds", nargs="+", type=int, default=[1001, 1002])
    compare.add_argument("--fixed-wing", type=float, default=.4)
    compare.add_argument("--duration", type=float, default=36)
    compare.add_argument("--dt", type=float, default=.2)
    compare.add_argument("--workers", type=int, default=min(4, os.cpu_count() or 1))
    compare.add_argument("--out", default="artifacts/predictive-campaign")
    compare.add_argument("--controllers", nargs="+", choices=CONTROLLERS, default=list(CONTROLLERS[:-1]))
    compare.add_argument("--policy", help="Frozen JSON preference profile")
    train = sub.add_parser("learn", help="Cross-entropy optimization of predictive preferences")
    train.add_argument("--scenarios", nargs="+", default=["head_on", "crossing", "overtaking", "urban"])
    train.add_argument("--counts", nargs="+", type=int, default=[10, 50])
    train.add_argument("--train-seeds", nargs="+", type=int, default=[20, 21])
    train.add_argument("--cooperative", type=float, default=.5)
    train.add_argument("--fixed-wing", type=float, default=.4)
    train.add_argument("--duration", type=float, default=36)
    train.add_argument("--dt", type=float, default=.2)
    train.add_argument("--population", type=int, default=6)
    train.add_argument("--generations", type=int, default=2)
    train.add_argument("--search-seed", type=int, default=42)
    train.add_argument("--workers", type=int, default=4)
    train.add_argument("--out", default="artifacts/policy-search/preferences.json")
    server = sub.add_parser("serve")
    server.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if args.command == "scenarios":
        for name, spec in SCENARIOS.items():
            print(f"{name:22} {spec.domain:15} {spec.description}")
    elif args.command == "run":
        weights = {}
        if args.policy:
            from .policy import load_policy
            if args.controller not in ("predictive", "evolved"):
                parser.error("--policy requires a predictive or evolved controller")
            weights, _ = load_policy(args.policy)
        elif args.controller == "evolved":
            parser.error("--controller evolved requires --policy")
        result = simulate(Config(scenario=args.scenario, controller=args.controller, drones=args.drones,
                                 cooperative_fraction=args.cooperative, fixed_wing_fraction=args.fixed_wing,
                                 seed=args.seed, duration=args.duration, dt=args.dt, **weights), record=True)
        write_json(args.out, result)
        print(json.dumps(result["metrics"], indent=2))
    elif args.command == "compare":
        if args.workers < 1 or args.workers > 16:
            parser.error("workers must be 1–16")
        campaign(args)
    elif args.command == "learn":
        from .policy import learn
        learn(args)
    else:
        from .server import serve
        serve(args.port)


if __name__ == "__main__":
    main()
