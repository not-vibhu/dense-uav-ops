import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from swarm_sim.config import Config, POLICY_FIELDS
from swarm_sim.analysis import summarize
from swarm_sim.engine import simulate
from swarm_sim.policy import load_policy
from swarm_sim.predictive import (choose_candidate, predictive_control,
                                  segment_distance, traffic_enclosure, volume_clearance)
from swarm_sim.scenarios import build_world


class PredictiveTests(unittest.TestCase):
    def test_wind_enclosure_covers_stale_and_future_intervals(self):
        cfg = Config()
        age, horizon = np.array([2.]), 1.
        e = cfg.position_error_bound + cfg.velocity_error_bound * age + .5 * cfg.advertised_acceleration_bound * age**2
        ev = cfg.velocity_error_bound + cfg.advertised_acceleration_bound * age
        bound = traffic_enclosure(e, ev, age, horizon, cfg)
        expected = cfg.position_error_bound + cfg.velocity_error_bound * (age+horizon) + .5*(cfg.advertised_acceleration_bound+.8)*(age+horizon)**2
        np.testing.assert_allclose(bound, expected)

    def test_swept_segment_detects_between_endpoint_crossing(self):
        self.assertEqual(segment_distance(np.array([-5., 0., 0.]), np.array([5., 0., 0.])), 0.)

    def test_boundary_clearance_includes_interior_extremum(self):
        cfg = Config(dt=.5)
        p = np.array([[109.9, 0., 50.]])
        clear = volume_clearance(p, np.array([[2., 0., 0.]]), np.array([[-8., 0., 0.]]), 0., cfg)
        self.assertLess(clear[0], 0.)

    def test_unsafe_candidate_cannot_buy_selection_with_lower_cost(self):
        chosen = choose_candidate(np.array([[False, True]]), np.zeros((1, 2)),
                                  np.zeros((1, 2)), np.zeros((1, 2)), np.array([[-1e12, 1e12]]))
        self.assertEqual(chosen[0], 1)

    def test_failed_library_fallback_ignores_learned_preferences(self):
        args = (np.zeros((1, 2), bool), np.array([[4., 0.]]),
                np.zeros((1, 2)), np.zeros((1, 2)))
        for cost in (np.array([[0., 100.]]), np.array([[100., 0.]])):
            self.assertEqual(choose_candidate(*args, cost)[0], 1)

    def test_brakes_before_boundary(self):
        cfg = Config(controller="predictive", drones=2, fixed_wing_fraction=0)
        w = build_world(cfg)
        w["cooperative"] = np.array([True, False])
        p = np.array([[90., 0., 50.], [-90., 80., 100.]])
        v = np.array([[8., 0., 0.], [0., 0., 0.]])
        w["goals"][0] = [200., 0., 50.]
        snap = (p.copy(), v.copy(), np.zeros(2), np.zeros(2), np.zeros(2))
        command, stats = predictive_control(cfg, w, p, v, np.ones(2, bool), snap, np.zeros_like(p))
        self.assertLess(command[0, 0], 0.)
        self.assertFalse(stats["unresolved"][0])

    def test_never_reads_other_aircraft_true_position(self):
        cfg = Config(controller="predictive", drones=2)
        w = build_world(cfg)
        w["cooperative"] = np.array([True, False])
        p, v = w["position"].copy(), w["velocity"].copy()
        snap = (p.copy(), v.copy(), np.ones(2), np.ones(2), np.zeros(2))
        first, _ = predictive_control(cfg, w, p, v, np.ones(2, bool), snap, np.zeros_like(p))
        p[1] += 1000
        second, _ = predictive_control(cfg, w, p, v, np.ones(2, bool), snap, np.zeros_like(p))
        np.testing.assert_array_equal(first[0], second[0])

    def test_no_authority_preserves_legacy_replay(self):
        kwargs = dict(drones=10, duration=3, cooperative_fraction=0)
        a = simulate(Config(controller="goal", **kwargs), True)
        b = simulate(Config(controller="predictive", **kwargs), True)
        self.assertEqual(a["replay"], b["replay"])

    def test_no_library_candidate_is_explicitly_reported(self):
        cfg = Config(controller="predictive", drones=2)
        w = build_world(cfg)
        w["cooperative"][:] = True
        p = np.zeros((2, 3)); p[:, 2] = 50.
        v = np.zeros_like(p)
        snap = (p.copy(), v.copy(), np.zeros(2), np.zeros(2), np.zeros(2))
        _, stats = predictive_control(cfg, w, p, v, np.ones(2, bool), snap, np.zeros_like(p))
        self.assertTrue(np.all(stats["unresolved"]))

    def test_profile_cannot_override_safety_thresholds(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "profile.json"
            profile = {"schema": "federated-swarm-preferences-v1", "weights": {k: 1. for k in POLICY_FIELDS}}
            path.write_text(json.dumps(profile))
            weights, _ = load_policy(path)
            self.assertEqual(set(weights), set(POLICY_FIELDS))
            profile["weights"]["separation"] = .1
            path.write_text(json.dumps(profile))
            with self.assertRaises(ValueError):
                load_policy(path)

    def test_failed_library_blocks_gate_even_with_zero_collisions(self):
        runs = []
        for seed in (0, 1001):
            r = simulate(Config(controller="predictive", drones=10, duration=1, seed=seed))
            m = r["metrics"]
            for key in ("participant_collision_pairs", "participant_obstacle_collisions",
                        "participant_volume_exits", "filter_infeasible_drone_steps",
                        "kinematic_violation_drone_steps"):
                m[key] = 0
            m["participant_completion_fraction"] = 1.
            m["predictive_no_admissible_drone_steps"] = 1
            runs.append(r)
        result = summarize(runs, {"scenarios": ["crossing"], "discovery_seeds": [0],
                                  "holdout_seeds": [1001], "expected_runs": 2})
        self.assertFalse(result["passed_empirical_gate"])


if __name__ == "__main__":
    unittest.main()
