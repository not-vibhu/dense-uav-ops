import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import subprocess
import sys
from unittest.mock import patch

import numpy as np

from dense_ops.engine import Experiment, simulate
from dense_ops.learning import graph
from dense_ops.modelcheck import explore
from dense_ops.network import Links, Surveillance


class InformationTests(unittest.TestCase):
    def test_reference_does_not_build_unused_active_recoveries(self):
        from dense_ops.safety import candidates
        with patch('dense_ops.engine.candidates', wraps=candidates) as planner:
            result = simulate(Experiment(drones=2, duration=2., manned=0, fixed_wing_fraction=0.,
                                         cooperative_fraction=1., guard='reference', seed=8611))
        self.assertEqual(result['metrics']['cooperative_admitted'], 2)
        self.assertEqual(planner.call_count, 2)

    def test_spawn_campaign_cli_and_complete_validation(self):
        from dataclasses import asdict
        from dense_ops.__main__ import validate_campaign
        with tempfile.TemporaryDirectory() as directory:
            profile = Path(directory)/'profile.json'
            profile.write_text(json.dumps(asdict(Experiment(drones=4, duration=2., manned=0))))
            out = Path(directory)/'campaign'
            subprocess.run([sys.executable, '-m', 'dense_ops', 'campaign', '--profile', str(profile),
                            '--counts', '4', '--scenarios', 'crossing', '--modes', 'local',
                            '--guards', 'continuation', '--seeds', '8600', '--out', str(out)],
                           check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            validate_campaign(out)
            manifest = json.loads((out/'manifest.json').read_text())
            manifest['configs'][0]['area'] += 100
            (out/'manifest.json').write_text(json.dumps(manifest))
            with self.assertRaises(ValueError):
                validate_campaign(out)

    def test_graph_keeps_all_reported_neighbors(self):
        n = 41
        p = np.arange(n*3, dtype=float).reshape(n, 3)
        snap = (p, np.zeros_like(p), np.ones(n), np.ones(n), np.zeros(n))
        nodes = graph(snap, 0, p[0], np.zeros(3), np.ones(n, bool), np.zeros(n, bool), np.ones(n, bool))
        self.assertEqual(nodes.shape, (40, 10))

    def test_declared_clock_error_encloses_linear_motion(self):
        for clock in (-.4, .4):
            sensor = Surveillance(2, 22, Links(latency=.1, jitter=0, loss=0, clock_skew=clock))
            p = np.array([[0., 0., 50.], [30., 0., 50.]])
            v = np.array([[0., 0., 0.], [10., 0., 0.]])
            sensor.step(0., p, v, np.ones(2, bool), [0])
            sensor.step(.2, p+v*.2, v, np.ones(2, bool), [0])
            pred, _, error, _, _ = sensor.snapshot(0, .2, 4.)
            self.assertLessEqual(np.linalg.norm(pred[1]-(p[1]+v[1]*.2)), error[1])

    def test_bounded_protocol_exploration(self):
        result = explore()
        self.assertEqual(result['bounded_states_checked'], 624)
        self.assertEqual(result['violations'], 0)

    def test_failed_preference_model_falls_back_to_checked_choice(self):
        class BrokenPolicy:
            training_seeds = set()
            def choose(self, candidates, neighbors):
                raise RuntimeError('failed proposal model')
        result = simulate(Experiment(drones=10, duration=2., manned=0, fixed_wing_fraction=0.,
                                     cooperative_fraction=1.), policy=BrokenPolicy())
        self.assertGreater(result['metrics']['learned_proposal_rejections'], 0)
        self.assertGreater(result['metrics']['cooperative_admitted'], 0)


@unittest.skipUnless(importlib.util.find_spec('torch'), 'Install optional learning dependencies')
class LearningTests(unittest.TestCase):
    def test_attention_is_permutation_invariant(self):
        import torch
        from dense_ops.learning import network
        torch.manual_seed(12)
        model = network().eval()
        candidates = torch.randn(7, 6)
        neighbors = torch.randn(37, 10)
        with torch.no_grad():
            a = model(candidates, neighbors)
            b = model(candidates, neighbors[torch.randperm(37)])
        self.assertTrue(torch.allclose(a, b, atol=1e-6, rtol=0))

    def test_aggregation_clips_and_rejects_malformed_updates(self):
        import torch
        from dense_ops.learning import aggregate
        base = {'x': torch.zeros(2)}
        merged = aggregate(base, [({'x': torch.ones(2)*1000}, 10)], max_norm=2.)
        self.assertLessEqual(float(torch.linalg.vector_norm(merged['x'])), 2.000001)
        for state, count in [({'x': torch.tensor([float('nan'), 0])}, 1),
                             ({'x': torch.ones(3)}, 1), ({'y': torch.ones(2)}, 1),
                             ({'x': torch.ones(2)}, -1), ({'x': torch.ones(2)}, 1.5)]:
            with self.assertRaises(ValueError):
                aggregate(base, [(state, count)])
        with self.assertRaises(ValueError):
            aggregate(base, [({'x': torch.ones(2)}, 1)], max_norm=float('nan'))

    def test_checkpoint_source_tensor_and_evaluation_seed_gates(self):
        from dense_ops.learning import network, GraphPolicy
        document = {'schema': 'dense-ops-graph-v1', 'source_sha256': 'test-source',
                    'weights': {k: v.detach().tolist() for k, v in network().state_dict().items()},
                    'training_seeds': [42]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'model.json'
            path.write_text(json.dumps(document))
            with self.assertRaises(ValueError):
                GraphPolicy(path, 'different-source')
            policy = GraphPolicy(path, 'test-source')
            with self.assertRaises(ValueError):
                simulate(Experiment(seed=42), policy=policy)
            key = next(iter(document['weights']))
            document['weights'][key] = [1.]
            path.write_text(json.dumps(document))
            with self.assertRaises(ValueError):
                GraphPolicy(path, 'test-source')


if __name__ == '__main__':
    unittest.main()
