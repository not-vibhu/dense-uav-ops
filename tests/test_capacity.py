from dataclasses import asdict, replace
import copy
import math
import unittest
from unittest.mock import patch
from pathlib import Path
import tempfile
from types import SimpleNamespace
import numpy as np

from airspace_capacity.profile import Profile
from airspace_capacity.simulation import Feed, build_traffic, protection, simulate
from airspace_capacity.simulation import schedule
from airspace_capacity.assessment import identity, reasons, summarize, upper_failure_probability
from swarm_sim.cli import source_hash
from airspace_capacity.__main__ import run_campaign
from airspace_capacity.server import request_config


class CapacityTests(unittest.TestCase):
    def setUp(self):
        self.profile = Profile(area_m=160., warmup_s=5., measurement_s=15., drain_s=20.,
                               dt_s=.5, command_deadline_ms=500., manned_operations_per_hour=720.,
                               manned_separation_m=30., cooperative_fraction=1., compliance_fraction=1.,
                               telemetry_latency_s=0., telemetry_loss_fraction=0.)

    def passing_run(self, seed=1, profile=None):
        p = profile or self.profile
        m = dict(collision_pairs=0, protected_volume_breach_pairs=0, obstacle_collision_pairs=0,
                 body_volume_exit_aircraft=0, kinematic_violation_aircraft_steps=0,
                 no_admissible_aircraft_steps=0, command_deadline_misses=0,
                 control_failure_aircraft_steps=0, endurance_exceeded_aircraft_steps=0,
                 unobserved_manned_aircraft_steps=0, occupancy_overflow_steps=0,
                 uas_requested=20, manned_requested=2, uas_completion_fraction=1.,
                 manned_completion_fraction=1., p95_uas_wait_s=0., backlog_growth=0,
                 uas_completed_per_hour=720., manned_completed_per_hour=720.,
                 peak_total_occupancy=7, peak_uas_occupancy=5, command_max_ms=1.)
        return dict(profile=asdict(p), uas_demand_per_hour=720., occupancy_limit=10, seed=seed, metrics=m)

    def test_invalid_parameters(self):
        for changes in ({'position_error_m': -1}, {'compliance_fraction': 1.1},
                        {'wind_acceleration_mps2': .9}, {'confidence': 1.},
                        {'command_deadline_ms': 1000}, {'manned_speed_mps': 70.},
                        {'measurement_s': float('nan')}, {'maximum_backlog_growth': True}):
            with self.assertRaises(ValueError):
                replace(self.profile, **changes).validate()

    def test_compliance_and_cooperation_independent(self):
        p = replace(self.profile, cooperative_fraction=1., compliance_fraction=0.)
        w, requested, manned, coop, compliant = build_traffic(p, 720., 1)
        ua = ~manned & np.isfinite(requested)
        self.assertTrue(np.all(coop[ua]))
        self.assertFalse(np.any(compliant[ua]))
        self.assertFalse(np.any(w['cooperative']))
        self.assertFalse(np.any(w['cooperative'][manned]))

    def test_configured_altitude_bands_and_route_width(self):
        p = replace(self.profile, uas_altitude_min_m=24., uas_altitude_max_m=36., uas_route_half_width_m=0., scenario='corridor')
        w, _, manned, _, _ = build_traffic(p, 720., 1)
        self.assertTrue(np.all(w['position'][~manned, 2] >= 24.))
        self.assertTrue(np.all(w['position'][~manned, 2] <= 36.))
        np.testing.assert_allclose(w['position'][:, 1], 0.)
        with self.assertRaises(ValueError):
            replace(p, uas_altitude_min_m=0.).validate()

    def test_manned_radius_and_speed_are_separate(self):
        w, _, manned, _, _ = build_traffic(self.profile, 720., 1)
        np.testing.assert_allclose(np.linalg.norm(w['velocity'][manned], axis=1), 35.)
        np.testing.assert_allclose(w['radius'][manned], 6.)
        i = np.flatnonzero(manned)[0]
        j = np.flatnonzero(~manned)[0]
        self.assertEqual(protection(self.profile, manned, w['radius'], i, j), 30.)

    def test_feed_does_not_initialize_from_truth(self):
        feed = Feed(self.profile, 2, 1)
        self.assertFalse(np.any(feed.seen))
        p = np.array([[0., 0, 80.], [0, 0, 50.]])
        feed = Feed(replace(self.profile, manned_detection_fraction=0.), 2, 1)
        feed.update(0., p, np.zeros_like(p), np.ones(2, bool), np.array([True, False]))
        self.assertFalse(feed.seen[0])
        self.assertTrue(feed.seen[1])

    def test_coverage_range_and_latency(self):
        feed = Feed(replace(self.profile, sensor_range_m=20., telemetry_latency_s=1.), 2, 1)
        p = np.array([[0., 0, 10.], [100., 0, 10.]])
        feed.update(0., p, np.zeros_like(p), np.ones(2, bool), np.zeros(2, bool))
        self.assertFalse(np.any(feed.seen))
        feed.update(1., p, np.zeros_like(p), np.ones(2, bool), np.zeros(2, bool))
        self.assertTrue(feed.seen[0])
        self.assertFalse(feed.seen[1])

    def test_manned_commands_are_exogenous(self):
        # Even a faulty proposal returned for manned actors cannot control them.
        def fake(cfg, world, p, v, active, snapshot, desired):
            return np.full_like(p, 1000.), {'unresolved': np.zeros(len(p), bool)}
        with patch('airspace_capacity.simulation.predictive_control', fake):
            run = simulate(replace(self.profile, cooperative_fraction=0.), 720., 10, 1)
        self.assertEqual(run['metrics']['manned_completion_fraction'], 1.)
        self.assertGreater(run['metrics']['manned_completed_per_hour'], 0.)

    def test_manned_intrusion_keeps_a_reachable_exit(self):
        p = replace(self.profile, scenario='manned_intrusion', cooperative_fraction=0.)
        run = simulate(p, 720., 10, 1)
        self.assertEqual(run['metrics']['manned_completion_fraction'], 1.)
        self.assertEqual(run['metrics']['body_volume_exit_aircraft'], 0)

    def test_streaming_metrics_and_measured_cohort(self):
        run = simulate(self.profile, 720., 10, 1)
        m = run['metrics']
        self.assertEqual(m['uas_requested'], 3)
        self.assertEqual(m['manned_requested'], 3)
        self.assertGreater(m['average_total_occupancy'], 0.)
        self.assertGreaterEqual(m['peak_total_occupancy'], m['peak_uas_occupancy'])
        self.assertNotEqual(m['uas_completed_per_hour'], m['peak_uas_occupancy'])

    def test_capacity_includes_legacy_and_manned_failures(self):
        for key in ('collision_pairs', 'protected_volume_breach_pairs', 'body_volume_exit_aircraft',
                    'no_admissible_aircraft_steps', 'command_deadline_misses', 'unobserved_manned_aircraft_steps'):
            run = self.passing_run()
            run['metrics'][key] = 1
            self.assertIn(key, reasons(run))

    def test_zero_service_and_partial_surveillance_cannot_pass(self):
        run = self.passing_run(profile=replace(self.profile, manned_detection_fraction=.99))
        run['metrics']['uas_completion_fraction'] = 0.
        self.assertIn('uas_completion_requirement', reasons(run))
        self.assertIn('incomplete_manned_surveillance_assumption', reasons(run))

    def test_exact_binomial_bound(self):
        self.assertAlmostEqual(upper_failure_probability(0, 100, .05), 1-.05**.01)
        self.assertEqual(upper_failure_probability(2, 2, .05), 1.)
        self.assertAlmostEqual(upper_failure_probability(1, 2, .05), math.sqrt(.95))

    def test_small_campaign_is_not_statistically_qualified(self):
        summary = summarize([self.passing_run()], [self.profile], [720.], [10], [1])
        self.assertEqual(summary['maximum_observed_passing_uas_demand_per_hour'], 720.)
        self.assertIsNone(summary['maximum_statistically_supported_tested_uas_demand_per_hour'])
        self.assertIsNone(summary['operationally_certified_capacity'])
        self.assertEqual(summary['per_profile_capacity'][0]['highest_observed_passing_total_demand_per_hour'], 1440.)

    def test_sufficient_independent_runs_can_meet_model_target(self):
        seeds = list(range(300))
        summary = summarize([self.passing_run(seed=x) for x in seeds], [self.profile], [720.], [10], seeds)
        self.assertEqual(summary['maximum_statistically_supported_tested_uas_demand_per_hour'], 720.)
        self.assertIsNone(summary['operationally_certified_capacity'])

    def test_worst_profile_vetoes_envelope_and_missing_rows_fail(self):
        p = replace(self.profile, name='poor-sensing', position_error_m=8.)
        bad = self.passing_run(profile=p)
        bad['metrics']['collision_pairs'] = 1
        result = summarize([self.passing_run(), bad], [self.profile, p], [720.], [10], [1])
        self.assertIsNone(result['maximum_observed_passing_uas_demand_per_hour'])
        self.assertNotEqual(identity(asdict(p)), identity(asdict(self.profile)))
        with self.assertRaises(ValueError):
            summarize([self.passing_run()], [self.profile, p], [720.], [10], [1])
        with self.assertRaises(ValueError):
            summarize([self.passing_run(), self.passing_run()], [self.profile], [720.], [10], [1])

    def test_no_monotonic_capacity_assumption(self):
        runs = [self.passing_run() for _ in range(3)]
        for run, rate in zip(runs, [360., 720., 1080.]):
            run['uas_demand_per_hour'] = rate
        runs[1]['metrics']['collision_pairs'] = 1
        summary = summarize(runs, [self.profile], [360., 720., 1080.], [10], [1])
        self.assertEqual(summary['maximum_observed_passing_uas_demand_per_hour'], 1080.)
        self.assertFalse(summary['envelope'][1]['observed_requirements_pass'])

    def test_large_campaign_is_rejected_instead_of_truncating(self):
        with self.assertRaises(ValueError):
            build_traffic(self.profile, 100000., 1)

    def test_low_rate_does_not_force_an_arrival_every_window(self):
        counts = [len(schedule(1., 10., np.random.default_rng(seed))) for seed in range(100)]
        self.assertLess(sum(counts), 10)

    def test_existing_learned_checkpoint_source_pin_unchanged(self):
        self.assertEqual(source_hash(), '454b8cdae5ed609fa46bcc6e4908c4675f5adefc04e1d759d867fb8e436d953e')

    def test_campaign_provenance_and_overwrite_refusal(self):
        import json
        import hashlib
        with tempfile.TemporaryDirectory() as temp:
            args = SimpleNamespace(out=Path(temp), rates=[720.], occupancy_limits=[10], seeds=[1])
            result = run_campaign(args, [self.profile], lambda *_: None)
            raw = (Path(temp)/'runs.jsonl').read_bytes()
            self.assertEqual(result['runs_sha256'], hashlib.sha256(raw).hexdigest())
            self.assertEqual(json.loads((Path(temp)/'summary.json').read_text())['source_sha256'], result['source_sha256'])
            with self.assertRaises(ValueError):
                run_campaign(args, [self.profile])

    def test_lab_rejects_invalid_and_unbounded_requests(self):
        body = dict(profile=asdict(self.profile), rates=[720.], limits=[10], seeds=[1], scenarios=['crossing'])
        args, profiles, total = request_config(body, Path('/tmp/capacity-test'))
        self.assertEqual(total, 1)
        self.assertEqual(profiles[0].scenario, 'crossing')
        for changes in ({'limits': [True]}, {'seeds': [1.5]}, {'rates': [float('nan')]},
                        {'scenarios': []}, {'extra': 'field'}, {'seeds': [1, 1]},
                        {'scenarios': ['crossing','crossing']}, {'rates': [0.]}):
            with self.assertRaises((ValueError, TypeError)):
                request_config({**body, **changes}, Path('/tmp/capacity-test'))

    def test_hardware_failure_and_endurance_are_reported(self):
        p = replace(self.profile, control_failure_fraction=1., control_failure_after_s=0., flight_endurance_s=.5)
        m = simulate(p, 720., 10, 1)['metrics']
        self.assertGreater(m['control_failure_aircraft_steps'], 0)
        self.assertGreater(m['endurance_exceeded_aircraft_steps'], 0)


if __name__ == '__main__':
    unittest.main()
