import copy
import unittest
from cryptography.exceptions import InvalidSignature
from dense_ops.engine import Experiment, simulate
from scripts.verify_flight_replay import reconstruct


class FlightReplayTests(unittest.TestCase):
    def test_commands_reconstruct_mixed_flights_and_nonideal_faults(self):
        for scenario in ('wind_gust', 'actuator_lag', 'bound_violation', 'sudden_turn'):
            with self.subTest(scenario=scenario):
                run = simulate(Experiment(drones=6, duration=6., area=220., scenario=scenario, seed=8700))
                result = reconstruct(run, run['audit']['anchor'])
                self.assertEqual(result['verified']['total_completed'], run['metrics']['total_completed'])

    def test_exogenous_flights_reconstruct_without_control_authority(self):
        run = simulate(Experiment(drones=4, duration=2., cooperative_fraction=0., seed=8701))
        result = reconstruct(run, run['audit']['anchor'])
        self.assertEqual(result['collision_categories']['controlled'], 0)

    def test_unsigned_outcome_and_condition_edits_are_rejected(self):
        run = simulate(Experiment(drones=4, duration=2., seed=8702))
        changed = copy.deepcopy(run); changed['metrics']['collision_pairs'] += 1
        with self.assertRaises((ValueError, InvalidSignature)):
            reconstruct(changed, run['audit']['anchor'])
        changed = copy.deepcopy(run); changed['experiment']['area'] += 1
        with self.assertRaises(ValueError):
            reconstruct(changed, run['audit']['anchor'])


if __name__ == '__main__':
    unittest.main()
