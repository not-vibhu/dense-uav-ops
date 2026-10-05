import json
import unittest

from dense_uav_ops.config import Experiment, from_dict, override
from dense_uav_ops.stats import clopper_pearson, poisson_interval, rate


class ConfigTests(unittest.TestCase):
    def test_round_trip_and_identity(self):
        e = from_dict({'airspace': {'obstacles': [[0, 0, 50, 10]]}, 'seed': 3})
        again = from_dict(json.loads(json.dumps(e.to_dict())))
        self.assertEqual(e, again)
        self.assertEqual(e.run_id(), again.run_id())
        self.assertNotEqual(e.run_id(), override(e, 'seed', 4).run_id())

    def test_unknown_keys_are_rejected(self):
        with self.assertRaises(ValueError):
            from_dict({'assumptions': {'traffic_accel': 1}})
        with self.assertRaises(ValueError):
            from_dict({'surveilance': {}})
        with self.assertRaises(ValueError):
            override(Experiment(), 'controller.kind.extra', 1)

    def test_invalid_values_fail_validation(self):
        bad = [{'fleet': {'cooperative_fraction': 1.5}}, {'controller': {'kind': 'magic'}},
               {'window': {'measurement_s': 10.1}}, {'assumptions': {'horizon_s': 0.}},
               {'surveillance': {'period_s': .1}}, {'controller': {'kind': 'graph'}},
               {'airspace': {'obstacles': [[0, 0, 0, -1]]}}]
        for document in bad:
            with self.subTest(document=document), self.assertRaises(ValueError):
                from_dict(document).validate()

    def test_override_paths(self):
        e = override(Experiment(), 'assumptions.traffic_acceleration_mps2', 1.5)
        self.assertEqual(e.assumptions.traffic_acceleration_mps2, 1.5)
        self.assertEqual(override(e, 'name', 'x').name, 'x')


class StatsTests(unittest.TestCase):
    def test_clopper_pearson_reference_values(self):
        low, high = clopper_pearson(0, 10)
        self.assertEqual(low, 0.)
        self.assertAlmostEqual(high, 0.30850, places=4)
        low, high = clopper_pearson(5, 10)
        self.assertAlmostEqual(low, 0.18709, places=4)
        self.assertAlmostEqual(high, 0.81291, places=4)

    def test_poisson_reference_values(self):
        self.assertAlmostEqual(poisson_interval(0)[1], 3.68888, places=4)
        low, high = poisson_interval(10)
        self.assertAlmostEqual(low, 4.79539, places=3)
        self.assertAlmostEqual(high, 18.39036, places=3)

    def test_rate_without_exposure_is_undefined(self):
        self.assertIsNone(rate(0, 0.)['per_hour'])
        self.assertAlmostEqual(rate(2, .5)['per_hour'], 4.)


if __name__ == '__main__':
    unittest.main()
