"""Variable-neighborhood graph ranking and gated federated imitation research.

Models rank only independently checked continuations. Training is offline;
neither parameters nor federated updates can alter the assurance thresholds.
"""
import json
from pathlib import Path
import numpy as np


def graph(snapshot, own, p, v, seen, fixed, cooperative):
    ids = np.flatnonzero(seen & (np.arange(len(seen)) != own))
    if not len(ids):
        return np.zeros((1, 10), np.float32)
    pred, vv, error, ev, age = snapshot
    r, rel = pred[ids]-p, vv[ids]-v
    tau = np.clip(-np.sum(r*rel, axis=1)/np.maximum(np.sum(rel*rel, axis=1), 1e-9), 0, 10)
    clearance = np.linalg.norm(r+rel*tau[:, None], axis=1)-error[ids]-ev[ids]*tau
    # Every reported node participates; risk ordering is for diagnostics only.
    order = np.argsort(clearance, kind='stable')
    features = np.column_stack((r/200, rel/20, error[ids]/20, age[ids]/5,
                                fixed[ids], cooperative[ids]))
    return np.clip(features[order], -20, 20).astype(np.float32)


def features(plans, goal, clearances, fixed):
    rows = []
    for plan, clearance in zip(plans, clearances):
        rows.append([np.linalg.norm(plan.p[-1]-goal)/200, np.mean(np.sum(plan.a**2, axis=1))/16,
                     min(clearance, 100)/100, np.linalg.norm(plan.v[-1])/12,
                     float(plan.static_terminal), float(fixed)])
    return np.array(rows, np.float32)


def network():
    import torch
    from torch import nn

    class Ranker(nn.Module):
        def __init__(self):
            super().__init__()
            self.node = nn.Sequential(nn.Linear(10, 16), nn.Tanh())
            self.attention = nn.Linear(10, 1)
            self.candidate = nn.Sequential(nn.Linear(6, 16), nn.Tanh())
            self.score = nn.Sequential(nn.Linear(32, 16), nn.Tanh(), nn.Linear(16, 1))

        def forward(self, candidate, neighbors):
            weights = torch.softmax(self.attention(neighbors).squeeze(-1), dim=0)
            context = (weights[:, None]*self.node(neighbors)).sum(0)
            return self.score(torch.cat((self.candidate(candidate), context.expand(len(candidate), -1)), dim=-1)).squeeze(-1)

    return Ranker()


class GraphPolicy:
    def __init__(self, path, source):
        import torch
        torch.set_num_threads(1)
        document = json.loads(Path(path).read_text())
        if document.get('schema') != 'dense-ops-graph-v1' or document['source_sha256'] != source:
            raise ValueError('Graph checkpoint source/schema mismatch')
        self.model = network()
        state = self.model.state_dict()
        if set(state) != set(document['weights']):
            raise ValueError('Graph checkpoint keys mismatch')
        loaded = {}
        for key, tensor in state.items():
            x = np.asarray(document['weights'][key], np.float32)
            if x.shape != tuple(tensor.shape) or not np.isfinite(x).all() or np.abs(x).max() > 1e4:
                raise ValueError('Graph checkpoint tensor invalid')
            loaded[key] = torch.tensor(x)
        self.model.load_state_dict(loaded)
        self.model.eval()
        self.training_seeds = set(document['training_seeds'])

    def choose(self, candidate, neighbors):
        import torch
        with torch.no_grad():
            return int(self.model(torch.tensor(candidate), torch.tensor(neighbors)).argmax())


def loss(model, samples):
    import torch
    if not samples:
        raise ValueError('Empty independent validation domain')
    values = []
    with torch.no_grad():
        for sample in samples:
            logits = model(torch.tensor(sample['features']), torch.tensor(sample['graph']))
            values.append(float(torch.nn.functional.cross_entropy(logits[None], torch.tensor([sample['label']]))))
    return float(np.mean(values))


def update(model, samples, epochs):
    import torch
    optimizer = torch.optim.Adam(model.parameters(), lr=.003)
    for _ in range(epochs):
        for sample in samples:
            logits = model(torch.tensor(sample['features']), torch.tensor(sample['graph']))
            objective = torch.nn.functional.cross_entropy(logits[None], torch.tensor([sample['label']]))
            optimizer.zero_grad(); objective.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), .5); optimizer.step()
    return model


def aggregate(base, updates, max_norm=2.):
    """Clipped model deltas; malformed/stale clients fail closed, no poisoning proof."""
    import torch
    if not updates or not np.isfinite(max_norm) or max_norm <= 0:
        raise ValueError('No valid federated clients')
    if any(type(count) is not int or count <= 0 for state, count in updates):
        raise ValueError('Malformed client sample count')
    total = sum(count for state, count in updates)
    if total <= 0:
        raise ValueError('Invalid client sample counts')
    merged = {k: v.clone() for k, v in base.items()}
    for state, count in updates:
        if type(count) is not int or count <= 0 or set(state) != set(base):
            raise ValueError('Malformed client update')
        delta = {}
        for k in base:
            if state[k].shape != base[k].shape or not torch.isfinite(state[k]).all():
                raise ValueError('Invalid federated tensor')
            delta[k] = state[k]-base[k]
        norm = torch.sqrt(sum(torch.sum(v*v) for v in delta.values()))
        scale = min(1., max_norm/max(float(norm), 1e-12))
        for k in merged:
            merged[k] += count/total*scale*delta[k]
    return merged


def train(clients, validation, source, seeds, out, rounds=3, epochs=2, seed=42):
    import torch
    torch.set_num_threads(1); torch.manual_seed(seed)
    model = network()
    history = []
    for round in range(rounds):
        base = {k: v.detach().clone() for k, v in model.state_dict().items()}
        updates = []
        for samples in clients:
            if not samples:
                continue  # explicit dropout, no fabricated updates
            local = network(); local.load_state_dict(base)
            update(local, samples, epochs)
            updates.append((local.state_dict(), len(samples)))
        proposal = network(); proposal.load_state_dict(aggregate(base, updates))
        before = [loss(model, domain) for domain in validation]
        after = [loss(proposal, domain) for domain in validation]
        accepted = all(a <= b+1e-6 for a, b in zip(after, before))
        if accepted:
            model = proposal
        history.append(dict(round=round+1, clients=len(updates), before=before, after=after, accepted=accepted))
    document = dict(schema='dense-ops-graph-v1', source_sha256=source, training_seeds=seeds,
                    weights={k: v.detach().tolist() for k, v in model.state_dict().items()},
                    history=history, scope='offline federated imitation; held-out loss gate is not safety qualification')
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(document, allow_nan=False)+'\n')
    return history
