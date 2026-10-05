import unittest
from types import SimpleNamespace
import numpy as np

from dense_uav_ops.config import Experiment, from_dict
from dense_uav_ops.planner import enclosure, plan
from dense_uav_ops.surveillance import TRACK_TIMEOUT_S, Feed, Snapshot
from dense_uav_ops.traffic import arrival_times, build
from dense_uav_ops.vehicles import limits_for


def traffic_stub(n):
    return SimpleNamespace(n=n, manned=np.zeros(n, bool), cooperative=np.ones(n, bool))


class FeedTests(unittest.TestCase):
    def setUp(self):
        self.e = from_dict({'surveillance': {'period_s': 1., 'latency_s': .4, 'loss': 0.}})
        self.p = np.array([[0., 0., 50.], [30., 0., 50.]])
        self.v = np.array([[5., 0., 0.], [0., 5., 0.]])

    def test_no_truth_initialization_and_delay(self):
        feed = Feed(self.e, traffic_stub(2))
        feed.update(0., self.p, self.v, np.ones(2, bool))
        self.assertFalse(feed.snapshot(0.).known.any())  # first report still in transit
        feed.update(.4, self.p, self.v, np.ones(2, bool))
        snap = feed.snapshot(.4)
        self.assertTrue(snap.known.all())
        np.testing.assert_allclose(snap.age, .4)

    def test_report_error_within_declared_bound(self):
        feed = Feed(self.e, traffic_stub(2))
        feed.update(0., self.p, self.v, np.ones(2, bool))
        feed.update(.4, self.p, self.v, np.ones(2, bool))
        self.assertTrue(np.all(np.linalg.norm(feed.p - self.p, axis=1) <= 1.5 + 1e-9))
        self.assertTrue(np.all(np.linalg.norm(feed.v - self.v, axis=1) <= .3 + 1e-9))

    def test_end_notice_and_timeout_drop_tracks(self):
        feed = Feed(self.e, traffic_stub(2))
        feed.update(0., self.p, self.v, np.ones(2, bool))
        feed.update(.4, self.p, self.v, np.ones(2, bool), finished=[0])
        feed.update(.8, self.p, self.v, np.array([False, True]))
        self.assertFalse(feed.snapshot(.8).known[0])
        # Aircraft 1 stops reporting after its t = 0 report: the track persists, ageing, until the timeout.
        for t in np.arange(1., TRACK_TIMEOUT_S - .1, .2):
            feed.update(t, self.p, self.v, np.zeros(2, bool))
            self.assertTrue(feed.snapshot(t).known[1])
        feed.update(TRACK_TIMEOUT_S + .2, self.p, self.v, np.zeros(2, bool))
        self.assertFalse(feed.snapshot(TRACK_TIMEOUT_S + .2).known[1])

    def test_poisson_arrival_rate(self):
        rng = np.random.default_rng(1)
        counts = [len(arrival_times(720., 3600., 'poisson', rng)) for _ in range(40)]
        self.assertAlmostEqual(np.mean(counts) / 720., 1., delta=.03)


def world_for(e, p, controlled):
    n = len(p)
    fixed = np.zeros(n, bool)
    return SimpleNamespace(limits=limits_for(e, fixed), radius=np.full(n, 1.2), cruise=np.full(n, 8.),
                           manned=np.zeros(n, bool), fixed=fixed, controlled=controlled,
                           waypoint=p + np.array([150., 0., 0.]), final_leg=np.ones(n, bool), burden=np.zeros(n))


def snapshot_of(p, v, known=None, age=.5):
    n = len(p)
    return Snapshot(position=p.copy(), velocity=v.copy(), position_error=np.full(n, 1.5),
                    velocity_error=np.full(n, .3), age=np.full(n, age),
                    known=np.ones(n, bool) if known is None else known)


class PlannerTests(unittest.TestCase):
    def test_enclosure_grows_with_assumed_acceleration_and_age(self):
        snap = snapshot_of(np.zeros((1, 3)), np.zeros((1, 3)), age=.5)
        radii = [enclosure(snap, 2.4, a)[0] for a in (0., 1., 2., 4.)]
        self.assertEqual(radii, sorted(radii))
        self.assertAlmostEqual(radii[-1], 1.5 + .3 * 2.9 + 2. * 2.9 ** 2)

    def test_planner_uses_reports_not_truth(self):
        e = Experiment()
        p = np.array([[0., 0., 60.], [40., 0., 60.]])
        v = np.array([[8., 0., 0.], [-8., 0., 0.]])
        snap = snapshot_of(p, v)
        world = world_for(e, p, np.array([True, False]))
        first = plan(e, world, np.array([0]), p, v, snap, np.zeros_like(p))
        moved = p.copy()
        moved[1] += [500., 500., 0.]  # truth of the other aircraft changes; its report does not
        second = plan(e, world, np.array([0]), moved, v, snap, np.zeros_like(p))
        np.testing.assert_array_equal(first.command, second.command)
        np.testing.assert_array_equal(first.feasible, second.feasible)

    def test_head_on_conflict_removes_straight_candidate(self):
        e = from_dict({'assumptions': {'traffic_acceleration_mps2': 0.}})
        p = np.array([[0., 0., 60.], [50., 0., 60.]])
        v = np.array([[8., 0., 0.], [-8., 0., 0.]])
        result = plan(e, world_for(e, p, np.array([True, False])), np.array([0]), p, v, snapshot_of(p, v), np.zeros_like(p))
        # 50 m head-on at 16 m/s closure: flying straight on enters the other aircraft's tube within the horizon.
        self.assertFalse(result.feasible[0, 0])
        self.assertTrue(result.feasible[0].any())
        self.assertTrue(result.feasible[0, result.chosen[0]])

    def test_conservative_assumption_can_leave_no_admissible_candidate(self):
        e = from_dict({'assumptions': {'traffic_acceleration_mps2': 4.}})
        p = np.array([[0., 0., 60.]] + [[x, y, 60.] for x in (-25., 25.) for y in (-25., 25.)])
        v = np.zeros_like(p)
        v[0] = [8., 0., 0.]
        result = plan(e, world_for(e, p, np.array([True] + [False] * 4)), np.array([0]), p, v, snapshot_of(p, v),
                      np.zeros_like(p))
        self.assertTrue(result.fallback[0])
        relaxed = from_dict({'assumptions': {'traffic_acceleration_mps2': 0.}})
        result = plan(relaxed, world_for(relaxed, p, np.array([True] + [False] * 4)), np.array([0]), p, v,
                      snapshot_of(p, v), np.zeros_like(p))
        self.assertFalse(result.fallback[0])

    def test_policy_cannot_choose_inadmissible_candidate(self):
        e = from_dict({'assumptions': {'traffic_acceleration_mps2': 0.}})
        p = np.array([[0., 0., 60.], [50., 0., 60.]])
        v = np.array([[8., 0., 0.], [-8., 0., 0.]])

        class Reckless:
            def choose(self, ids, feasible, teacher, *rest):
                return np.zeros(len(ids), int)  # always "straight on"

        result = plan(e, world_for(e, p, np.array([True, False])), np.array([0]), p, v, snapshot_of(p, v),
                      np.zeros_like(p), policy=Reckless())
        self.assertFalse(result.feasible[0, 0])
        self.assertNotEqual(result.chosen[0], 0)

    def test_unknown_tracks_are_not_constraints(self):
        e = from_dict({'assumptions': {'traffic_acceleration_mps2': 0.}})
        p = np.array([[0., 0., 60.], [40., 0., 60.]])
        v = np.array([[8., 0., 0.], [-8., 0., 0.]])
        snap = snapshot_of(p, v, known=np.array([True, False]))
        result = plan(e, world_for(e, p, np.array([True, False])), np.array([0]), p, v, snap, np.zeros_like(p))
        self.assertTrue(result.feasible[0, 0])  # the planner cannot avoid what surveillance does not report


class TrafficTests(unittest.TestCase):
    def test_mix_and_routes(self):
        e = from_dict({'demand': {'uas_per_hour': 3600., 'manned_per_hour': 60.},
                       'fleet': {'cooperative_fraction': .5, 'noncompliant_fraction': .2}})
        t = build(e)
        self.assertTrue(np.all(~t.controlled | (t.cooperative & t.compliant & ~t.manned)))
        self.assertFalse(np.any(t.cooperative & t.manned))
        uas = ~t.manned
        half = e.airspace.side_m / 2
        self.assertTrue(np.all(np.abs(t.start[uas, :2]) <= half - e.demand.entry_inset_m + 1e-9))
        self.assertTrue(np.all((t.start[uas, 2] > e.airspace.floor_m) & (t.start[uas, 2] < e.airspace.ceiling_m)))
        self.assertTrue(np.all(t.start[t.manned, 0] < -half))  # manned traffic is observable before it enters
        self.assertAlmostEqual(np.mean(t.cooperative[uas]), .5, delta=.1)


if __name__ == '__main__':
    unittest.main()


class CullingTests(unittest.TestCase):
    def test_broad_phase_never_changes_admissibility_or_choice(self):
        rng = np.random.default_rng(5)
        for trial in range(20):
            e = from_dict({'assumptions': {'traffic_acceleration_mps2': float(rng.choice([0., 1., 4.]))}})
            n = 60
            p = np.column_stack((rng.uniform(-150, 150, (n, 2)), rng.uniform(40, 110, n)))
            v = np.column_stack((rng.normal(0, 6, (n, 2)), rng.normal(0, 1, n)))
            v *= np.minimum(1., 11. / np.linalg.norm(v, axis=1))[:, None]
            controlled = rng.random(n) < .5
            ids = np.flatnonzero(controlled)
            snap = snapshot_of(p + rng.normal(0, 1, p.shape), v, known=rng.random(n) < .9, age=float(rng.uniform(0, 2)))
            world = world_for(e, p, controlled)
            a = plan(e, world, ids, p, v, snap, np.zeros_like(p), cull=True)
            b = plan(e, world, ids, p, v, snap, np.zeros_like(p), cull=False)
            np.testing.assert_array_equal(a.feasible, b.feasible)
            np.testing.assert_array_equal(a.chosen, b.chosen)
            np.testing.assert_array_equal(a.fallback, b.fallback)
            np.testing.assert_allclose(a.command, b.command)
