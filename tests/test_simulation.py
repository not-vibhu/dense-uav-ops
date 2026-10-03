import copy
from dataclasses import asdict
import json
import unittest
from unittest.mock import patch
import numpy as np

from swarm_sim.analysis import summarize
from swarm_sim.config import Config
from swarm_sim.controllers import vehicle_project, barrier_filter
from swarm_sim.engine import simulate
from swarm_sim.oracle import quadratic_minimum, swept_pairs, outside_volume
from swarm_sim.scenarios import SCENARIOS, Scenario, build_world
from swarm_sim.telemetry import Telemetry


class OracleTests(unittest.TestCase):
    def test_linear_crossing_between_samples(self):
        self.assertAlmostEqual(quadratic_minimum(np.array([-10., 0, 0]), np.array([20., 0, 0]), np.zeros(3), 1), 0)
        p = np.array([[-5., 0, 40], [5., 0, 40]])
        v = np.array([[10., 0, 0], [-10., 0, 0]])
        i, j, d, _ = swept_pairs(p, v, np.zeros_like(p), np.ones(2, bool), np.ones(2), 3, 1)
        self.assertEqual(list(zip(i, j)), [(0, 1)])
        self.assertLess(d[0], 1e-8)

    def test_acceleration_extremum(self):
        r, v, a = np.array([3., 0, 0]), np.array([-8., 0, 0]), np.array([8., 0, 0])
        exact = quadratic_minimum(r, v, a, 1)
        ts = np.linspace(0, 1, 10001)
        grid = np.min(np.linalg.norm(r + ts[:, None]*v + .5*ts[:, None]**2*a, axis=1))
        self.assertLessEqual(exact, grid + 1e-9)
        self.assertLess(grid - exact, .002)

    def test_boundary_extremum_not_only_endpoints(self):
        cfg = Config(area=100)
        # Both endpoints are inside; midpoint reaches x=60 outside the box.
        p, v, a = np.array([[40., 0, 40]]), np.array([[80., 0, 0]]), np.array([[-160., 0, 0]])
        self.assertTrue(outside_volume(p, v, a, cfg, 1)[0])

    def test_inactive_aircraft_excluded(self):
        _, _, d, _ = swept_pairs(np.zeros((2, 3)), np.zeros((2, 3)), np.zeros((2, 3)),
                                np.array([True, False]), np.ones(2), 10, .2)
        self.assertEqual(len(d), 0)


class DynamicsTests(unittest.TestCase):
    def test_fixed_wing_cannot_stop_or_turn_instantly(self):
        cfg = Config()
        v = np.array([[6., 0, 0], [8., 0, 0]])
        desired = np.array([[-100., 100., 100.], [-100., 0, 0]])
        a = vehicle_project(desired, v, np.array([True, False]), cfg)
        nv = v + cfg.dt * a
        self.assertGreaterEqual(np.linalg.norm(nv[0, :2]), cfg.fixed_wing_min_speed - 1e-9)
        self.assertLessEqual(abs(np.arctan2(nv[0, 1], nv[0, 0])), np.deg2rad(cfg.fixed_wing_turn_rate_deg) * cfg.dt + 1e-9)
        self.assertLessEqual(abs(nv[0, 2]), cfg.fixed_wing_climb_limit)
        self.assertTrue(np.all(np.linalg.norm(a, axis=1) <= cfg.acceleration_limit + 1e-9))
        self.assertLess(nv[1, 0], 8)

    def test_infeasible_filter_is_reported(self):
        cfg = Config(drones=2)
        w = build_world(cfg)
        p = np.array([[0., 0, 50], [1., 0, 50]])
        v = np.zeros_like(p)
        snap = (p.copy(), v.copy(), np.ones(2), np.ones(2), np.zeros(2))
        _, stats = barrier_filter(cfg, w, p, v, np.ones(2, bool), snap, np.zeros_like(p))
        self.assertTrue(np.any(stats['residual'] > 0))
        self.assertTrue(np.all(stats['invalid_initial']))


class FeedTests(unittest.TestCase):
    def test_identity_ambiguity_retains_enclosing_hypotheses(self):
        cfg = Config(scenario='identity_ambiguity', drones=10)
        w = build_world(cfg)
        ambiguous = Telemetry(cfg, w).snapshot(0)[2]
        normal_cfg = Config(scenario='crossing', drones=10)
        normal = Telemetry(normal_cfg, build_world(normal_cfg)).snapshot(0)[2]
        np.testing.assert_allclose(ambiguous - normal, 8.)

    def test_delay_increases_age_and_uncertainty(self):
        cfg = Config(scenario='stale_telemetry', drones=10)
        w = build_world(cfg)
        feed = Telemetry(cfg, w)
        feed.step(.6, w['position'] + 20, w['velocity'])
        pred, _, e, _, age = feed.snapshot(1.5)
        np.testing.assert_allclose(age, 1.5)
        self.assertTrue(np.all(e > cfg.position_error_bound))
        np.testing.assert_allclose(pred, w['position'] + w['velocity']*1.5)

    def test_outage_does_not_delete_threats(self):
        cfg = Config(scenario='network_outage', drones=10)
        w = build_world(cfg)
        feed = Telemetry(cfg, w)
        feed.step(9, w['position'], w['velocity'])
        _, _, e, _, age = feed.snapshot(10)
        self.assertEqual(len(e), 10)
        self.assertTrue(np.all(age == 10))
        self.assertTrue(np.all(e > 100))


class IntegrationTests(unittest.TestCase):
    def test_seed_reproducibility(self):
        cfg = Config(drones=10, duration=3)
        first, second = simulate(cfg, True), simulate(cfg, True)
        for result in (first, second):
            for key in ('wall_seconds','command_p99_ms','command_max_ms'):
                result['metrics'].pop(key)
        self.assertEqual(first, second)

    def test_legacy_behavior_independent_of_selected_controller(self):
        a = simulate(Config(drones=10, duration=3, cooperative_fraction=0, controller='goal'), True)
        b = simulate(Config(drones=10, duration=3, cooperative_fraction=0, controller='negotiated'), True)
        self.assertEqual(a['replay'], b['replay'])

    def test_collision_categories_are_disjoint(self):
        for controller in ('goal', 'repulsion', 'barrier', 'negotiated'):
            r = simulate(Config(drones=10, duration=20, controller=controller))
            m = r['metrics']
            self.assertEqual(m['collision_pairs'], m['collision_pairs_ee']+m['collision_pairs_el']+m['collision_pairs_ll'])

    def test_all_scenarios_construct_and_run(self):
        for scenario in SCENARIOS:
            with self.subTest(scenario=scenario):
                result = simulate(Config(scenario=scenario, drones=10, duration=1))
                json.dumps(result, allow_nan=False)

    def test_mixed_fleet_initial_states_within_vehicle_limits(self):
        for name in SCENARIOS:
            w = build_world(Config(scenario=name, drones=200))
            speed = np.linalg.norm(w['velocity'][w['fixed'], :2], axis=1)
            self.assertTrue(np.all(speed >= 6 - 1e-6), name)

    def test_no_false_safety_gate_with_collision(self):
        runs=[]
        for seed in (0, 1001):
            r=simulate(Config(drones=10,duration=1,seed=seed))
            r['metrics']['participant_collision_pairs']=1
            runs.append(r)
        manifest={'scenarios':['crossing'],'discovery_seeds':[0],'holdout_seeds':[1001],'expected_runs':2}
        s=summarize(runs,manifest)
        self.assertFalse(s['passed_empirical_gate'])

    def test_config_rejects_bad_inputs(self):
        for changes in ({'drones':1},{'dt':float('nan')},{'cooperative_fraction':1.1},{'seed':-1}):
            with self.assertRaises(ValueError):
                Config(**changes).validate()


if __name__ == '__main__':
    unittest.main()
