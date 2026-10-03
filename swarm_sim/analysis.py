from collections import defaultdict
import hashlib
import json
import platform
from . import __version__


def aggregate(runs):
    buckets = defaultdict(list)
    for r in runs:
        if r["metrics"]["cooperative_aircraft"]:
            buckets[r["config"]["controller"]].append(r)
    rows = []
    for controller, group in buckets.items():
        ms = [r["metrics"] for r in group]
        strata = defaultdict(list)
        for r in group:
            key = (r["config"]["scenario"], r["config"]["drones"], r["config"]["cooperative_fraction"])
            strata[key].append(bool(r["metrics"]["participant_collision_pairs"]))
        rate = lambda field: sum(bool(m[field]) for m in ms) / len(ms)
        exposure = sum(m["participating_pair_seconds"] for m in ms)
        completion = sum(m["participant_completion_fraction"] for m in ms) / len(ms)
        row = {"controller": controller, "eligible_runs": len(ms),
               "participant_collision_run_rate": rate("participant_collision_pairs"),
               "participant_obstacle_run_rate": rate("participant_obstacle_collisions"),
               "participant_volume_exit_run_rate": rate("participant_volume_exits"),
               "worst_stratum_collision_rate": max(sum(v) / len(v) for v in strata.values()),
               "separation_exposure_ratio": sum(m["participating_separation_pair_step_seconds"] for m in ms) / max(exposure, 1e-9),
               "participant_completion_fraction": completion,
               "participant_collision_pairs": sum(m["participant_collision_pairs"] for m in ms),
               "legacy_only_collision_pairs": sum(m["collision_pairs_ll"] for m in ms),
               "filter_infeasible_drone_steps": sum(m["filter_infeasible_drone_steps"] for m in ms),
               "predictive_no_admissible_drone_steps": sum(m.get("predictive_no_admissible_drone_steps", 0) for m in ms),
               "kinematic_violation_drone_steps": sum(m["kinematic_violation_drone_steps"] for m in ms),
               "mean_command_p99_ms": sum(m["command_p99_ms"] for m in ms) / len(ms)}
        row["risk_key"] = [row["participant_collision_run_rate"], row["participant_obstacle_run_rate"],
                           row["participant_volume_exit_run_rate"], row["worst_stratum_collision_rate"],
                           row["separation_exposure_ratio"], -completion]
        rows.append(row)
    return sorted(rows, key=lambda x: (x["risk_key"], x["controller"]))


def summarize(runs, manifest):
    discovery = [r for r in runs if r["config"]["seed"] in manifest["discovery_seeds"]]
    holdout = [r for r in runs if r["config"]["seed"] in manifest["holdout_seeds"]]
    training_rows, holdout_rows = aggregate(discovery), aggregate(holdout)
    selected = training_rows[0]["controller"] if training_rows else None
    selected_holdout = next((r for r in holdout_rows if r["controller"] == selected), None)
    safety_gate = bool(selected_holdout and
                       selected_holdout["participant_collision_run_rate"] == 0 and
                       selected_holdout["participant_obstacle_run_rate"] == 0 and
                       selected_holdout["participant_volume_exit_run_rate"] == 0 and
                       selected_holdout["filter_infeasible_drone_steps"] == 0 and
                       selected_holdout["predictive_no_admissible_drone_steps"] == 0 and
                       selected_holdout["kinematic_violation_drone_steps"] == 0 and
                       selected_holdout["participant_completion_fraction"] >= .7 and
                       selected in ("barrier", "negotiated", "predictive", "evolved"))
    # Report out-of-bound injected faults separately; they never silently vanish.
    per_scenario = {name: aggregate([r for r in holdout if r["config"]["scenario"] == name])
                    for name in manifest["scenarios"]}
    return {"manifest": manifest, "completed_runs": len(runs), "expected_runs": manifest["expected_runs"],
            "ranking_discovery": training_rows, "ranking_holdout": holdout_rows,
            "selected_on_discovery": selected,
            "selection_stable_on_holdout": bool(holdout_rows and selected == holdout_rows[0]["controller"]),
            "passed_empirical_gate": safety_gate,
            "recommendation": "provisional-tested-profile" if safety_gate else "no-configuration-cleared-safety-gate",
            "per_scenario_holdout": per_scenario,
            "in_domain_holdout": aggregate([r for r in holdout if r["domain"] == "modeled"]),
            "out_of_bounds_holdout": aggregate([r for r in holdout if r["domain"] != "modeled"]),
            "zero_cooperation_runs": sum(r["metrics"]["cooperative_aircraft"] == 0 for r in runs),
            "statistics_note": "Descriptive finite-suite results; paired seeds and all strata are published. No universal safest or certification inference. Individual trajectories sharing a scenario are not independent trials.",
            "software": {"version": __version__, "python": platform.python_version()},
            "results_sha256": hashlib.sha256(json.dumps(runs, sort_keys=True, allow_nan=False).encode()).hexdigest()}
