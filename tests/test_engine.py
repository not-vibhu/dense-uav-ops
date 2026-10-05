import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import numpy as np

from dense_uav_ops import engine
from dense_uav_ops.campaign import _first_mismatch, deterministic, finish, publish, run_campaign, validate
from dense_uav_ops.engine import category, simulate
from helpers import small


class EngineTests(unittest.TestCase):
    def test_identical_inputs_reproduce_exactly(self):
        e = small(demand={'uas_per_hour': 1440.}, fleet={'cooperative_fraction': .5})
        self.assertEqual(deterministic(simulate(e)), deterministic(simulate(e)))

    def test_host_timing_never_changes_outcomes(self):
        e = small(demand={'uas_per_hour': 1440.})
        normal = simulate(e)
        ticks = iter(np.arange(0, 1e6, 5.))  # every timer read jumps 5 s: a pathologically slow host
        with mock.patch.object(engine.clock, 'perf_counter', side_effect=lambda: next(ticks)):
            slow = simulate(e)
        self.assertEqual(deterministic(normal), deterministic(slow))
        self.assertGreater(slow['compute']['control_seconds'], normal['compute']['control_seconds'])

    def test_attribution_categories(self):
        controlled = np.array([True, False, False])
        manned = np.array([False, False, True])
        self.assertEqual(category(controlled, manned, 0, 1), 'cu')
        self.assertEqual(category(controlled, manned, 1, 2), 'um')
        self.assertEqual(category(controlled, manned, 2, 0), 'cm')

    def test_uncontrolled_traffic_is_never_attributed(self):
        e = small(demand={'uas_per_hour': 5400.}, fleet={'cooperative_fraction': 0.}, controller={'kind': 'none'})
        m = simulate(e)['metrics']
        self.assertGreater(m['los_events']['uu'], 0)
        self.assertEqual(m['attributable_los'], 0)
        self.assertEqual(m['controlled_flight_hours'], 0.)

    def test_uncontrolled_trajectories_do_not_depend_on_the_controller(self):
        base = dict(demand={'uas_per_hour': 1440.}, fleet={'cooperative_fraction': .5})
        runs = [simulate(small(**base, controller={'kind': k}), record=True) for k in ('none', 'predictive')]
        controlled = np.array(runs[0]['replay']['controlled'], bool)
        for a, b in zip(runs[0]['replay']['frames'], runs[1]['replay']['frames']):
            pa = {i: p for i, p in zip(a['id'], a['p']) if not controlled[i]}
            pb = {i: p for i, p in zip(b['id'], b['p']) if not controlled[i]}
            self.assertEqual(pa, pb)

    def test_avoidance_reduces_attributable_events_against_no_avoidance(self):
        base = dict(demand={'uas_per_hour': 2880.}, fleet={'cooperative_fraction': 1.})
        none = simulate(small(**base, controller={'kind': 'none'}))['metrics']
        planned = simulate(small(**base, controller={'kind': 'predictive'}))['metrics']
        self.assertGreater(none['attributable_los'], planned['attributable_los'])

    def test_occupancy_limit_holds_controlled_entries(self):
        e = small(demand={'uas_per_hour': 2880.}, admission={'occupancy_limit': 3})
        m = simulate(e)['metrics']
        self.assertLessEqual(m['peak_uas_occupancy'], 3)
        self.assertLess(m['admitted_controlled'], m['offered_controlled'])
        self.assertGreater(m['mean_entry_wait_s'], 0)

    def test_entry_clearance_check_denies_entries_under_conservative_assumptions(self):
        # A one-direction corridor at 1.5 entries/s puts successive entrants a few metres apart.
        e = small(demand={'uas_per_hour': 5400., 'pattern': 'corridor'}, admission={'entry_check': 'clearance'})
        self.assertGreater(simulate(e)['metrics']['entry_denials'], 0)

    def test_obstacles_route_controlled_aircraft(self):
        e = small(demand={'uas_per_hour': 720.}, airspace={'obstacles': [[0., 0., 75., 30.]]})
        m = simulate(e)['metrics']
        self.assertEqual(m['obstacle_contacts_controlled'], 0)
        self.assertEqual(m['route_rejected_controlled'], 0)


class CampaignTests(unittest.TestCase):
    spec = {'name': 'test', 'base': {'window': {'warmup_s': 4., 'measurement_s': 12., 'drain_s': 4.},
                                     'demand': {'uas_per_hour': 720.}},
            'arms': [{'name': 'none', 'set': {'controller.kind': 'none'}},
                     {'name': 'predictive', 'set': {'controller.kind': 'predictive'}}],
            'grid': {'assumptions.traffic_acceleration_mps2': [0., 4.]}, 'seeds': [1, 2]}

    def test_run_resume_validate_and_detect_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / 'c'
            spec = Path(directory) / 'spec.json'
            spec.write_text(json.dumps(self.spec))
            summary = run_campaign(spec, out)
            self.assertEqual(summary['runs'], 8)
            self.assertEqual(len(summary['cells']), 4)
            self.assertIn('8 declared runs', validate(out, rerun=2))
            # Resume: remove one run and its summary; only that run is recomputed.
            lines = (out / 'runs.jsonl').read_text().splitlines()
            (out / 'runs.jsonl').write_text('\n'.join(lines[:-1]) + '\n')
            with self.assertRaises(ValueError):
                finish(out)
            again = run_campaign(spec, out)
            self.assertEqual(again['outcomes_sha256'], summary['outcomes_sha256'])
            publish(out)
            validate(out)
            # Tampering with any published file is detected.
            summary_path = out / 'summary.json'
            saved = summary_path.read_text()
            summary_path.write_text(saved.replace('"runs": 8', '"runs": 7'))
            with self.assertRaises(ValueError):
                validate(out)

    def test_a_different_campaign_cannot_reuse_an_output(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / 'c'
            spec = Path(directory) / 'spec.json'
            spec.write_text(json.dumps({**self.spec, 'seeds': [1]}))
            run_campaign(spec, out)
            spec.write_text(json.dumps({**self.spec, 'seeds': [3]}))
            with self.assertRaises(ValueError):
                run_campaign(spec, out)

    def test_summary_comparison_tolerates_only_floating_point_noise(self):
        saved = {'events': 3, 'interval': [0.2924017738212874, 3.4301540339602994], 'name': 'a'}
        self.assertIsNone(_first_mismatch(saved, {**saved, 'interval': [0.2924017738212892, 3.430154033960279]}))
        self.assertEqual(_first_mismatch(saved, {**saved, 'events': 4}), 'summary.events')
        self.assertEqual(_first_mismatch(saved, {**saved, 'interval': [0.2924, 3.4301540339602994]}), 'summary.interval[0]')
        self.assertEqual(_first_mismatch(saved, {**saved, 'events': 3.}), 'summary.events')
        self.assertEqual(_first_mismatch(saved, {k: v for k, v in saved.items() if k != 'name'}), 'summary')


if __name__ == '__main__':
    unittest.main()


class ReviewRegressionTests(unittest.TestCase):
    """Defects found in independent review before the frontier-01 campaign."""

    def test_entry_spacing_includes_same_tick_admissions(self):
        from dense_uav_ops.engine import World, entry_allowed, own_fleet_picture
        from dense_uav_ops.surveillance import Snapshot
        from dense_uav_ops.traffic import build
        e = small(demand={'uas_per_hour': 720.})
        t = build(e)
        t.start[1] = t.start[0] + [3., 0., 0.]  # two entries 3 m apart
        world = World(limits=t.limits, radius=t.radius, cruise=t.cruise, manned=t.manned, fixed=t.fixed,
                      controlled=t.controlled, waypoint=t.goal, final_leg=np.ones(t.n, bool), goal=t.goal,
                      burden=np.zeros(t.n), airborne=np.zeros(t.n, bool))
        empty = Snapshot(np.zeros((t.n, 3)), np.zeros((t.n, 3)), np.ones(t.n), np.ones(t.n) * .3, np.zeros(t.n), np.zeros(t.n, bool))
        self.assertTrue(entry_allowed(e, world, 0, t, empty))
        admitted = np.zeros(t.n, bool)
        admitted[0] = True
        admit_time = np.where(admitted, 0., np.nan)
        picture = own_fleet_picture(e, empty, admitted, admit_time, t, 0.)
        self.assertFalse(entry_allowed(e, world, 1, t, picture))
        # Long-admitted aircraft are not dead-reckoned from entry: surveillance must report them.
        self.assertFalse(own_fleet_picture(e, empty, admitted, admit_time, t, 5.).known[0])

    def test_entry_spacing_allows_for_braking_and_closure(self):
        from dense_uav_ops.engine import World, entry_allowed
        from dense_uav_ops.surveillance import Snapshot
        from dense_uav_ops.traffic import build
        e = small(demand={'uas_per_hour': 720.})
        t = build(e)
        world = World(limits=t.limits, radius=t.radius, cruise=t.cruise, manned=t.manned, fixed=t.fixed,
                      controlled=t.controlled, waypoint=t.goal, final_leg=np.ones(t.n, bool), goal=t.goal,
                      burden=np.zeros(t.n), airborne=np.zeros(t.n, bool))
        direction = t.velocity[0] / np.linalg.norm(t.velocity[0])
        known = np.zeros(t.n, bool)
        known[1] = True
        position = np.zeros((t.n, 3))
        velocity = np.zeros((t.n, 3))
        position[1] = t.start[0] + direction * 14.  # 14 m ahead on the entrant's path, reported 1 s ago
        velocity[1] = t.velocity[0] * .5            # and slower than the entrant
        ahead = Snapshot(position, velocity, np.full(t.n, 1.5), np.full(t.n, .3), np.where(known, 1., 0.), known)
        self.assertFalse(entry_allowed(e, world, 0, t, ahead))
        position[1] = t.start[0] - direction * 60.  # well behind
        self.assertTrue(entry_allowed(e, world, 0, t, ahead))

    def test_entry_phase_events_are_counted_separately(self):
        e = small(demand={'uas_per_hour': 5760., 'pattern': 'head-on'}, fleet={'cooperative_fraction': .5},
                  controller={'kind': 'none'})
        result = simulate(e)
        m = result['metrics']
        self.assertGreater(sum(m['entry_los_events'].values()), 0)
        phases = {event['phase'] for event in result['events']}
        self.assertEqual(phases, {'entry', 'flight'})
        flight = sum(1 for event in result['events'] if event['phase'] == 'flight' and event['type'] == 'los'
                     and event['category'] in ('cc', 'cu'))
        self.assertEqual(flight, m['attributable_uas_los'])

    def test_no_controlled_entry_inside_loss_of_separation(self):
        e = small(demand={'uas_per_hour': 2880., 'pattern': 'corridor'}, controller={'kind': 'none'})
        result = simulate(e, record=True)
        admissions = {}
        for frame in result['replay']['frames']:
            for i in frame['id']:
                admissions.setdefault(i, frame['t'])
        for event in result['events']:
            if event['category'] == 'cc':
                # An event exactly at an aircraft's first recorded frame would mean it entered inside LoS.
                self.assertFalse(all(abs(admissions.get(i, -1) - event['time']) < .25 for i in event['pair']))

    def test_profile_and_spec_base_merge_by_section(self):
        from dense_uav_ops.campaign import expand
        with tempfile.TemporaryDirectory() as directory:
            profile = Path(directory) / 'p.json'
            profile.write_text(json.dumps({'demand': {'pattern': 'corridor', 'uas_per_hour': 2000.}}))
            runs = expand({'base_profile': 'p.json', 'base': {'demand': {'manned_per_hour': 5.}}, 'seeds': [1]}, Path(directory))
            demand = runs[0][1].demand
            self.assertEqual((demand.pattern, demand.uas_per_hour, demand.manned_per_hour), ('corridor', 2000., 5.))

    def test_surveillance_noise_aligned_across_arms(self):
        from dense_uav_ops.surveillance import Feed
        from dense_uav_ops.traffic import build
        e = small(demand={'uas_per_hour': 1440.})
        t = build(e)
        feeds = [Feed(e, t), Feed(e, t)]
        p, v, airborne = t.start.copy(), t.velocity.copy(), np.ones(t.n, bool)
        for step in range(30):
            feeds[0].update(step * .2, p, v, airborne, finished=[0] if step == 3 else [])
            feeds[1].update(step * .2, p, v, airborne, finished=[1, 2] if step == 5 else [])
        np.testing.assert_array_equal(feeds[0].p[5:], feeds[1].p[5:])

    def test_unfinished_operations_are_censored_not_dropped(self):
        e = small(demand={'uas_per_hour': 2880.}, admission={'occupancy_limit': 3})
        m = simulate(e)['metrics']
        self.assertGreater(len(m['controlled_censored_delays_s']), 0)
        everything = m['controlled_delays_s'] + m['controlled_censored_delays_s']
        self.assertEqual(len(everything), m['offered_controlled'])
        self.assertTrue(all(d >= 0 for d in m['controlled_censored_delays_s']))

    def test_noncooperative_surveillance_is_configurable(self):
        e = small(demand={'uas_per_hour': 2880.}, fleet={'cooperative_fraction': .5},
                  surveillance={'uncooperative_detection': 0.})
        m = simulate(e)['metrics']
        self.assertGreater(m['unknown_traffic_seconds'], 100.)
