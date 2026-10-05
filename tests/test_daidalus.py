from pathlib import Path
import unittest

from dense_uav_ops.daidalus import select_heading, track_angle
from helpers import small

MANIFEST = Path('artifacts/daidalus/manifest.json')


class HeadingSelectionTests(unittest.TestCase):
    def test_desired_heading_kept_when_clear(self):
        self.assertEqual(select_heading(90., [[0., 360., 'NONE']]), (90., 'clear'))

    def test_nearest_conflict_free_heading(self):
        bands = [[0., 20., 'NEAR'], [20., 340., 'NONE'], [340., 360., 'NEAR']]
        heading, status = select_heading(5., bands)
        self.assertEqual(status, 'resolved')
        self.assertAlmostEqual(heading, 21.)
        heading, _ = select_heading(355., bands)
        self.assertAlmostEqual(heading, 339.)

    def test_recovery_used_only_without_conflict_free_headings(self):
        heading, status = select_heading(0., [[0., 180., 'NEAR'], [180., 360., 'RECOVERY']])
        self.assertEqual(status, 'recovery')
        self.assertAlmostEqual(heading, 359.)
        self.assertEqual(select_heading(0., [[0., 360., 'NEAR']]), (0., 'none'))

    def test_track_angle_convention(self):
        self.assertAlmostEqual(track_angle([0., 1., 0.]), 0.)
        self.assertAlmostEqual(track_angle([1., 0., 0.]), 90.)


@unittest.skipUnless(MANIFEST.exists(), 'build the bridge with python scripts/build_daidalus.py')
class BridgeTests(unittest.TestCase):
    def test_head_on_alert_and_bands(self):
        from dense_uav_ops.daidalus import Bridge
        with Bridge(MANIFEST) as bridge:
            result = bridge.query(1, [1, 2], [[0, 0, 60], [0, 100, 60]], [[0, 8, 0], [0, -8, 0]], 0.)
            self.assertGreater(result['alerts'][0][1], 0)
            regions = {region for _, _, region in result['bands']}
            self.assertIn('NONE', regions)
            far = bridge.query(1, [1, 2], [[0, 0, 60], [0, -300, 60]], [[0, 8, 0], [0, -8, 0]], 1.)
            self.assertEqual(far['alerts'][0][1], 0)

    def test_daidalus_controller_runs(self):
        from dense_uav_ops.engine import simulate
        m = simulate(small(controller={'kind': 'daidalus'}, demand={'uas_per_hour': 1440.}))['metrics']
        self.assertGreater(sum(m['daidalus_guidance'].values()), 0)
        self.assertEqual(m['kinematic_violation_steps'], 0)


if __name__ == '__main__':
    unittest.main()
