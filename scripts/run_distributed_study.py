"""Execute a declared, finite development grid without selecting favorable runs."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

from swarm_sim.scenarios import SCENARIOS


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--checkpoint', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    grids = [
        ('catalog', 'mixed-mission', list(SCENARIOS), [10], ['local', 'federated'], ['continuation'], ['none'], [8200, 8201]),
        ('guard-comparison', 'mixed-mission', ['head_on', 'crossing', 'corridor', 'wind_gust'], [10], ['local', 'federated'], ['reference', 'continuation'], ['none'], [8200, 8201]),
        ('graph-comparison', 'mixed-mission', ['crossing', 'corridor', 'urban', 'wind_gust'], [10], ['local', 'federated', 'graph', 'federated_graph'], ['continuation'], ['none'], [8500, 8501]),
        ('density', 'density-stress', ['crossing', 'corridor'], [50, 100, 200, 500], ['local', 'federated'], ['continuation'], ['none'], [8300]),
        ('partition-clock', 'partition-clock', ['crossing', 'corridor'], [10], ['local', 'federated'], ['continuation'], ['compound'], [8400, 8401]),
    ]
    args.out.mkdir(parents=True, exist_ok=True)
    if any(args.out.iterdir()):
        raise ValueError('Study output must be empty')
    commands = []
    for name, profile, scenarios, counts, modes, guards, faults, seeds in grids:
        command = [sys.executable, '-m', 'dense_ops', 'campaign', '--profile', f'profiles/distributed-04/{profile}.json',
                   '--scenarios', *scenarios, '--counts', *map(str, counts), '--modes', *modes, '--guards', *guards,
                   '--faults', *faults, '--seeds', *map(str, seeds), '--workers', '2', '--checkpoint', str(args.checkpoint),
                   '--out', str(args.out/name)]
        commands.append(command)
    (args.out/'commands.json').write_text(json.dumps(commands, indent=2)+'\n')
    for command in commands:
        subprocess.run(command, check=True)
        subprocess.run([sys.executable, '-m', 'dense_ops', 'validate', command[-1]], check=True)


if __name__ == '__main__':
    main()
