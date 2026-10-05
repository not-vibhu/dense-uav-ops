from dataclasses import replace
import importlib.util
from pathlib import Path
import tempfile
import unittest

import numpy as np

from helpers import small

HAS_TORCH = importlib.util.find_spec('torch') is not None


@unittest.skipUnless(HAS_TORCH, 'install the learning extra (torch)')
class RecurrentTests(unittest.TestCase):
    def test_attention_is_invariant_to_neighbor_order(self):
        import torch
        from dense_uav_ops.learning.recurrent import network
        torch.manual_seed(0)
        model = network()
        own = torch.randn(1, 17)
        neighbors = torch.randn(1, 8, 11)
        mask = torch.tensor([[True] * 5 + [False] * 3])
        h = torch.zeros(1, 32)
        order = torch.tensor([3, 1, 4, 0, 2, 5, 6, 7])
        a, _ = model.actor(own, neighbors, mask, h)
        b, _ = model.actor(own, neighbors[:, order], mask[:, order], h)
        torch.testing.assert_close(a, b)

    def test_mask_overrides_extreme_logits(self):
        import torch
        from dense_uav_ops.learning.recurrent import distribution
        logits = torch.zeros(1, 22)
        logits[0, 0] = 1e6
        feasible = np.zeros((1, 22), bool)
        feasible[0, 5] = True
        dist, valid = distribution(logits, feasible)
        self.assertEqual(int(dist.logits.argmax()), 5)
        self.assertTrue(bool(valid[0]))

    def test_train_save_load_and_seed_isolation(self):
        from dense_uav_ops.engine import simulate
        from dense_uav_ops.learning.recurrent import load, load_policy, train
        base = small(demand={'uas_per_hour': 1440.})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'imitation.json'
            train(base, 'imitation', [500, 501], 2, 2, 7, path)
            _, metadata = load(path, stage='imitation')
            self.assertEqual(metadata['training_seeds'], [500, 501])
            self.assertGreater(metadata['admissible_decisions'], 0)
            mappo = Path(directory) / 'mappo.json'
            train(base, 'mappo', [502], 1, 1, 7, mappo, initial=path)
            self.assertEqual(load(mappo, stage='mappo')[1]['training_seeds'], [500, 501, 502])
            evaluation = replace(base, seed=600, controller=replace(base.controller, kind='recurrent', checkpoint=str(mappo)))
            result = simulate(evaluation)
            self.assertIsNotNone(result['policy_sha256'])
            with self.assertRaises(ValueError):
                simulate(replace(evaluation, seed=500), policy=load_policy(mappo))
            with self.assertRaises(ValueError):
                load(path, stage='mappo')


@unittest.skipUnless(HAS_TORCH, 'install the learning extra (torch)')
class GraphTests(unittest.TestCase):
    def test_aggregation_clips_and_rejects_malformed_updates(self):
        import torch
        from dense_uav_ops.learning.graph import aggregate
        base = {'w': torch.zeros(3)}
        merged = aggregate(base, [({'w': torch.tensor([100., 0., 0.])}, 1)], max_norm=2.)
        self.assertAlmostEqual(float(merged['w'].norm()), 2., places=5)
        for bad in ([({'w': torch.tensor([float('nan')] * 3)}, 1)], [({'x': torch.zeros(3)}, 1)], [({'w': torch.zeros(3)}, 0)]):
            with self.assertRaises(ValueError):
                aggregate(base, bad)

    def test_failing_model_falls_back_to_planner_choice(self):
        from dense_uav_ops.learning.graph import GraphPolicy

        class Broken:
            def __call__(self, *args):
                raise RuntimeError('broken')

        policy = GraphPolicy(Broken())
        feasible = np.array([[True, True, False]])
        chosen = policy.choose([0], feasible, np.array([1]), np.ones((1, 3)), np.ones((1, 3)), np.ones((1, 3)),
                               [(np.zeros((1, 10), np.float32), False)])
        self.assertEqual(chosen.tolist(), [1])

    def test_federated_training_round_trip(self):
        from dense_uav_ops.engine import simulate
        from dense_uav_ops.learning.graph import load_policy, train
        base = small(demand={'uas_per_hour': 2880.})
        domains = [(replace(base, airspace=replace(base.airspace, side_m=side)), [700 + k], [710 + k])
                   for k, side in enumerate((300., 400.))]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'graph.json'
            history = train(domains, path, rounds=1, epochs=1)
            self.assertEqual(len(history), 1)
            policy = load_policy(path)
            self.assertIn(700, policy.training_seeds)
            simulate(replace(base, seed=720), policy=policy)


@unittest.skipUnless(HAS_TORCH, 'install the learning extra (torch)')
class PreferenceTests(unittest.TestCase):
    def test_fitness_ranks_contacts_before_efficiency(self):
        from dense_uav_ops.learning.preferences import fitness
        safe_slow = [{'metrics': {'controlled_flight_hours': 1., 'controlled_steps': 10, 'attributable_contacts': 0,
                                  'attributable_los': 3, 'fallback_steps': 5, 'controlled_completion_fraction': .5,
                                  'mean_delay_s': 30.}}]
        fast_contact = [{'metrics': {**safe_slow[0]['metrics'], 'attributable_contacts': 1, 'attributable_los': 0,
                                     'fallback_steps': 0, 'controlled_completion_fraction': 1., 'mean_delay_s': 0.}}]
        self.assertLess(fitness(safe_slow), fitness(fast_contact))


if __name__ == '__main__':
    unittest.main()
