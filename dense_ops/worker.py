"""Importable process target, including on spawn-only platforms."""
from .engine import simulate


def worker(job):
    config, checkpoint = job
    policy = None
    if 'graph' in config.mode:
        from .learning import GraphPolicy
        from .__main__ import source_hash
        policy = GraphPolicy(checkpoint, source_hash())
    return simulate(config, policy=policy, record=False)
