import unittest
import numpy as np

from dense_uav_ops.config import Experiment
from dense_uav_ops.oracle import outside_volume, quadratic_minimum, swept_pairs
from dense_uav_ops.recovery import hover_certificate, P
from dense_uav_ops.vehicles import limits_for, project, violations


class OracleTests(unittest.TestCase):
    def test_crossing_between_samples_is_detected(self):
        p = np.array([[-5., 0., 50.], [0., -5., 50.]])
        v = np.array([[50., 0., 0.], [0., 50., 0.]])
        i, j, d = swept_pairs(p, v, np.zeros_like(p), np.ones(2, bool), lambda a, b: np.full(len(a), 10.), .2)
        self.assertLess(d[0], 1e-6)  # both endpoints are 7+ m apart, the paths meet at t = 0.1 s

    def test_acceleration_extremum_inside_step(self):
        r, v, a = np.array([10., 0, 0]), np.array([-10., 0, 0]), np.array([10., 0, 0])
        self.assertAlmostEqual(quadratic_minimum(r, v, a, 2.), 5., places=6)

    def test_inactive_aircraft_are_excluded(self):
        p = np.zeros((2, 3))
        i, j, d = swept_pairs(p, np.zeros_like(p), np.zeros_like(p), np.array([True, False]), lambda a, b: 10., .2)
        self.assertEqual(len(d), 0)

    def test_volume_exit_between_endpoints(self):
        low, high = np.array([-10., -10, 0]), np.array([10., 10, 20])
        p, v, a = np.array([[8., 0, 10]]), np.array([[10., 0, 0]]), np.array([[-100., 0, 0]])
        # Ends inside, but the turnaround at t = 0.1 s reaches x = 8.5 + body radius 2 > 10.
        self.assertTrue(outside_volume(p, v, a, low, high, np.array([2.]), .2)[0])


class VehicleTests(unittest.TestCase):
    def test_fixed_wing_cannot_stop_or_turn_instantly(self):
        lim = limits_for(Experiment(), np.array([True]))
        v = np.array([[8., 0., 0.]])
        a = project(np.array([[-100., 100., 0.]]), v, lim, .2)
        new_v = v + a * .2
        self.assertGreaterEqual(np.linalg.norm(new_v[0, :2]), 6. - 1e-9)
        heading = np.degrees(np.arctan2(new_v[0, 1], new_v[0, 0]))
        self.assertLessEqual(heading, 35. * .2 + 1e-6)
        self.assertFalse(violations(a, v, new_v, lim, .2).any())

    def test_multirotor_bounds(self):
        lim = limits_for(Experiment(), np.array([False]))
        v = np.array([[11.5, 0., 0.]])
        a = project(np.array([[30., 0., 0.]]), v, lim, .2)
        self.assertLessEqual(np.linalg.norm(a), 4. + 1e-9)
        self.assertLessEqual(np.linalg.norm(v + a * .2), 12. + 1e-9)
        self.assertTrue(violations(np.array([[5., 0, 0]]), v, v, lim, .2).any())


class HoverLemmaTests(unittest.TestCase):
    def test_contracting_and_invariant_under_random_bounded_disturbance(self):
        dt, d = .2, .8
        cert = hover_certificate(dt, 4., 12., d)
        self.assertTrue(cert['valid'])
        self.assertLess(cert['contraction'], 1.)
        F = np.array([[1 - .5 * dt ** 2, dt - .75 * dt ** 2], [-dt, 1 - 1.5 * dt]])
        G = np.array([.5 * dt ** 2, dt])
        rng = np.random.default_rng(0)
        L = np.linalg.cholesky(P)
        for _ in range(50):
            x = np.linalg.solve(L.T, rng.normal(size=(2, 3)))
            x *= np.sqrt(cert['rho'] / np.einsum('ac,ab,bc->', x, P, x))  # start on the boundary
            for _ in range(200):
                w = rng.normal(size=3)
                w *= d * rng.random() / np.linalg.norm(w)
                x = F @ x + np.outer(G, w)
                self.assertLessEqual(np.einsum('ac,ab,bc->', x, P, x), cert['rho'] * (1 + 1e-9))
                self.assertLessEqual(np.linalg.norm(np.array([1., 1.5]) @ x), cert['command_bound'] + 1e-9)


if __name__ == '__main__':
    unittest.main()
