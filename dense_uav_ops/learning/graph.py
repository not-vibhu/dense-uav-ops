"""Attention-pooled graph ranker trained by offline federated imitation.

Each ownship's reported neighbors form a variable-size node set; the ranker
scores the admissible candidates only. Training simulates separate airspace
"domains" as federated clients that fit locally from the same round base; the
server averages clipped parameter deltas weighted by sample counts and accepts
a round only if imitation loss does not increase on any domain's held-out data.

This is federated imitation, not reinforcement learning, Byzantine-robust
aggregation or a demonstration of a safety gain.
"""
import hashlib
import json
from pathlib import Path
import numpy as np

from ..planner import enclosure

SCHEMA = 'dense-uav-ops-graph-v1'
NODE_DIM, CANDIDATE_DIM = 10, 4


def node_features(e, world, i, p, v, snapshot):
    others = np.flatnonzero(snapshot.known & (np.arange(len(p)) != i))
    if not len(others):
        return np.zeros((1, NODE_DIM), np.float32)
    reach = enclosure(snapshot, 0., e.assumptions.traffic_acceleration_mps2)
    rows = np.column_stack(((snapshot.position[others] - p[i]) / 200., (snapshot.velocity[others] - v[i]) / 20.,
                            reach[others] / 20., snapshot.age[others] / 5., world.fixed[others], world.controlled[others]))
    return np.clip(rows, -20, 20).astype(np.float32)


def candidate_features(clearance, remaining, effort, fixed):
    lag = remaining - remaining[0]
    return np.column_stack((lag / 50., effort / 16., np.minimum(clearance, 100.) / 100.,
                            np.full(len(clearance), float(fixed)))).astype(np.float32)


def network():
    import torch
    from torch import nn

    class Ranker(nn.Module):
        def __init__(self):
            super().__init__()
            self.node = nn.Sequential(nn.Linear(NODE_DIM, 16), nn.Tanh())
            self.attention = nn.Linear(NODE_DIM, 1)
            self.candidate = nn.Sequential(nn.Linear(CANDIDATE_DIM, 16), nn.Tanh())
            self.score = nn.Sequential(nn.Linear(32, 16), nn.Tanh(), nn.Linear(16, 1))

        def forward(self, candidates, nodes):
            weights = torch.softmax(self.attention(nodes).squeeze(-1), dim=0)
            context = (weights[:, None] * self.node(nodes)).sum(0)
            return self.score(torch.cat((self.candidate(candidates), context.expand(len(candidates), -1)), -1)).squeeze(-1)

    return Ranker()


class GraphPolicy:
    """Engine policy: rank admissible candidates; record teacher labels when `recorder` is set."""

    def __init__(self, model=None, training_seeds=(), recorder=None, checkpoint_sha256=None):
        self.model, self.recorder = model, recorder
        self.training_seeds = set(training_seeds)
        self.checkpoint_sha256 = checkpoint_sha256

    def reset(self, n):
        pass

    def observe(self, e, world, ids, p, v, snapshot):
        return [(node_features(e, world, i, p, v, snapshot), bool(world.fixed[i])) for i in ids]

    def choose(self, ids, feasible, teacher, clearance, remaining, effort, observation):
        import torch
        chosen = np.array(teacher)
        for row, (nodes, fixed) in enumerate(observation):
            allowed = np.flatnonzero(feasible[row])
            if len(allowed) < 2:
                continue
            features = candidate_features(clearance[row], remaining[row], effort[row], fixed)[allowed]
            if self.recorder is not None:
                label = int(np.flatnonzero(allowed == teacher[row])[0])
                self.recorder.append({'features': features.tolist(), 'graph': nodes.tolist(), 'label': label})
                continue
            try:
                with torch.no_grad():
                    index = int(self.model(torch.tensor(features), torch.tensor(nodes)).argmax())
                chosen[row] = allowed[index]
            except (RuntimeError, ValueError, FloatingPointError):
                pass  # a failing model falls back to the planner's choice
        return chosen


def to_document(model, training_seeds, history):
    from ..campaign import CORE, source_digest
    return {'schema': SCHEMA, 'core_sha256': source_digest(CORE), 'training_seeds': sorted(training_seeds),
            'weights': {k: v.detach().tolist() for k, v in model.state_dict().items()}, 'history': history,
            'scope': 'Offline federated imitation; held-out loss is not a safety measure.'}


def load_policy(path):
    import torch
    torch.set_num_threads(1)
    document = json.loads(Path(path).read_text())
    if document.get('schema') != SCHEMA:
        raise ValueError('not a graph-ranker checkpoint')
    model = network()
    state = {}
    for key, tensor in model.state_dict().items():
        array = np.asarray(document['weights'].get(key), np.float32)
        if array.shape != tuple(tensor.shape) or not np.isfinite(array).all() or np.abs(array).max() > 1e4:
            raise ValueError('invalid graph checkpoint tensor ' + key)
        state[key] = torch.tensor(array)
    model.load_state_dict(state)
    model.eval()
    return GraphPolicy(model, document['training_seeds'], checkpoint_sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest())


def loss(model, samples):
    import torch
    with torch.no_grad():
        values = [float(torch.nn.functional.cross_entropy(model(torch.tensor(s['features']), torch.tensor(s['graph']))[None],
                                                           torch.tensor([s['label']]))) for s in samples]
    return float(np.mean(values))


def fit(model, samples, epochs):
    import torch
    optimizer = torch.optim.Adam(model.parameters(), lr=.003)
    for _ in range(epochs):
        for s in samples:
            logits = model(torch.tensor(s['features']), torch.tensor(s['graph']))
            objective = torch.nn.functional.cross_entropy(logits[None], torch.tensor([s['label']]))
            optimizer.zero_grad()
            objective.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), .5)
            optimizer.step()
    return model


def aggregate(base, updates, max_norm=2.):
    """Sample-weighted average of clipped deltas. Malformed updates are rejected, not repaired."""
    import torch
    if not updates or not np.isfinite(max_norm) or max_norm <= 0:
        raise ValueError('no valid client updates')
    for state, count in updates:
        if type(count) is not int or count <= 0 or set(state) != set(base):
            raise ValueError('malformed client update')
    total = sum(count for _, count in updates)
    merged = {k: v.clone() for k, v in base.items()}
    for state, count in updates:
        delta = {}
        for key in base:
            if state[key].shape != base[key].shape or not torch.isfinite(state[key]).all():
                raise ValueError('invalid client tensor')
            delta[key] = state[key] - base[key]
        norm = float(torch.sqrt(sum(torch.sum(d * d) for d in delta.values())))
        scale = min(1., max_norm / max(norm, 1e-12))
        for key in merged:
            merged[key] += count / total * scale * delta[key]
    return merged


def collect(experiment, seeds):
    from dataclasses import replace
    from ..engine import simulate
    samples = []
    policy = GraphPolicy(recorder=samples)
    for seed in seeds:
        simulate(replace(experiment, seed=seed), policy=policy)
    return samples


def train(domains, out, rounds=3, epochs=2, seed=42):
    """`domains`: list of (experiment, training seeds, validation seeds), one per federated client."""
    import torch
    torch.set_num_threads(1)
    torch.manual_seed(seed)
    clients = [collect(e, train_seeds) for e, train_seeds, _ in domains]
    validation = [collect(e, valid_seeds) for e, _, valid_seeds in domains]
    if any(not x for x in clients + validation):
        raise ValueError('a domain produced no decisions with two or more admissible candidates')
    model = network()
    history = []
    for number in range(rounds):
        base = {k: v.detach().clone() for k, v in model.state_dict().items()}
        updates = []
        for samples in clients:
            local = network()
            local.load_state_dict(base)
            updates.append((fit(local, samples, epochs).state_dict(), len(samples)))
        proposal = network()
        proposal.load_state_dict(aggregate(base, updates))
        before = [loss(model, v) for v in validation]
        after = [loss(proposal, v) for v in validation]
        accepted = all(a <= b + 1e-6 for a, b in zip(after, before))
        if accepted:
            model = proposal
        history.append({'round': number + 1, 'clients': len(updates), 'before': before, 'after': after, 'accepted': accepted})
        print(f'round {number + 1}: validation loss {np.round(before, 3).tolist()} -> {np.round(after, 3).tolist()} '
              f'{"accepted" if accepted else "rejected"}', flush=True)
    seeds = {s for _, t, v in domains for s in (*t, *v)}
    document = to_document(model, seeds, history)
    document['domains'] = [{'experiment': e.to_dict(), 'training_seeds': t, 'validation_seeds': v,
                            'training_samples': len(c), 'validation_samples': len(val)}
                           for (e, t, v), c, val in zip(domains, clients, validation)]
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(document, allow_nan=False) + '\n')
    return history
