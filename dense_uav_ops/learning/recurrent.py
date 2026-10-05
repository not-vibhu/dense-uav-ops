"""Recurrent attention actor with a centralized critic: imitation, then masked MAPPO.

The shared actor encodes ownship features and attention-pooled nearest tracks,
carries a GRU state, and scores the planner's candidates. Only admissible
candidates can be chosen; when none is admissible the planner's fallback runs
and no actor loss is taken. The critic additionally sees a global truth summary
during training only.
"""
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import numpy as np

from . import OBSERVATION_VERSION
from ..planner import ACTIONS
from .observations import CONTEXT_DIM, NEIGHBOR_DIM, OWN_DIM, central_context, observe

SCHEMA = 'dense-uav-ops-recurrent-v1'
ARCHITECTURE = {'own': OWN_DIM, 'neighbor': NEIGHBOR_DIM, 'context': CONTEXT_DIM, 'actions': ACTIONS,
                'hidden': 32, 'encoder': 'attention-gru-v1', 'observation': OBSERVATION_VERSION}


def network():
    import torch
    from torch import nn

    class ActorCritic(nn.Module):
        def __init__(self):
            super().__init__()
            self.own = nn.Sequential(nn.Linear(OWN_DIM, 32), nn.Tanh())
            self.neighbor = nn.Sequential(nn.Linear(NEIGHBOR_DIM, 32), nn.Tanh())
            self.query = nn.Linear(32, 32, bias=False)
            self.gru = nn.GRUCell(64, 32)
            self.action = nn.Linear(32, ACTIONS)
            self.critic = nn.Sequential(nn.Linear(32 + CONTEXT_DIM, 64), nn.Tanh(), nn.Linear(64, 1))

        def actor(self, own, neighbors, mask, hidden):
            x = self.own(own)
            nodes = self.neighbor(neighbors)
            scores = (nodes * self.query(x)[:, None]).sum(-1) / 32 ** .5
            weights = torch.softmax(scores.masked_fill(~mask, -1e9), dim=-1) * mask
            weights = weights / weights.sum(-1, keepdim=True).clamp_min(1e-8)
            pooled = (weights[:, :, None] * nodes).sum(1)
            h = self.gru(torch.cat((x, pooled), -1), hidden)
            return self.action(h), h

        def value(self, hidden, context):
            return self.critic(torch.cat((hidden, context), -1)).squeeze(-1)

    return ActorCritic()


def tensors(observation):
    import torch
    return (torch.as_tensor(observation['own'], dtype=torch.float32),
            torch.as_tensor(observation['neighbors'], dtype=torch.float32),
            torch.as_tensor(observation['mask'], dtype=torch.bool))


def distribution(logits, feasible):
    import torch
    from torch.distributions import Categorical
    feasible = torch.as_tensor(feasible, dtype=torch.bool)
    nonempty = feasible.any(-1)
    allowed = feasible.clone()
    allowed[~nonempty, 0] = True  # dummy distribution; its loss is excluded
    return Categorical(logits=logits.masked_fill(~allowed, -1e9)), nonempty


class RecurrentPolicy:
    """Engine policy. mode: 'inference' (argmax), 'rollout' (sample, record) or 'expert' (teacher, record)."""

    def __init__(self, model, mode='inference', training_seeds=(), checkpoint_sha256=None):
        self.model, self.mode = model, mode
        self.training_seeds = set(training_seeds)
        self.checkpoint_sha256 = checkpoint_sha256
        self.records, self.pending = [], None

    def reset(self, n):
        import torch
        self.hidden = torch.zeros(n, 32)
        self.records, self.pending = [], None

    def observe(self, e, world, ids, p, v, snapshot):
        observation = observe(e, world, ids, p, v, snapshot)
        if self.mode != 'inference':
            observation['context'] = central_context(e, world, p, v, world.airborne)
        return observation

    def choose(self, ids, feasible, teacher, clearance, remaining, effort, observation):
        import torch
        before = self.hidden[ids].clone()
        with torch.no_grad():
            logits, hidden = self.model.actor(*tensors(observation), before)
            dist, valid = distribution(logits, feasible)
            if self.mode == 'expert':
                action = torch.as_tensor(teacher, dtype=torch.long)
            elif self.mode == 'rollout':
                action = dist.sample()
            else:
                action = dist.logits.argmax(-1)
            action = torch.where(valid, action, torch.as_tensor(teacher, dtype=torch.long))
            self.hidden[ids] = hidden
            if self.mode != 'inference':
                context = torch.as_tensor(observation['context'])[None].expand(len(ids), -1)
                record = {'ids': np.array(ids), 'obs': {k: observation[k] for k in ('own', 'neighbors', 'mask')},
                          'mask': np.array(feasible), 'teacher': np.array(teacher), 'hidden': before,
                          'action': action.clone(), 'logp': dist.log_prob(action).clone(),
                          'value': self.model.value(hidden, context).clone(), 'context': observation['context'],
                          'valid': valid.clone()}
                self.records.append(record)
                self.pending = record
        return action.numpy()

    def transition(self, reward, done):
        import torch
        if self.pending is not None:
            ids = self.pending['ids']
            self.pending['reward'] = torch.as_tensor(reward[ids], dtype=torch.float32)
            self.pending['done'] = torch.full((len(ids),), bool(done), dtype=torch.bool)
            self.pending = None


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, model, metadata):
    from ..campaign import CORE, source_digest
    document = {'schema': SCHEMA, 'architecture': ARCHITECTURE,
                'metadata': {**metadata, 'core_sha256': source_digest(CORE)},
                'weights': {k: v.detach().cpu().tolist() for k, v in model.state_dict().items()}}
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(document, allow_nan=False) + '\n')
    return digest(path)


def load(path, stage=None):
    import torch
    path = Path(path)
    if not path.is_file() or path.stat().st_size > 5_000_000:
        raise ValueError(f'missing or oversized checkpoint {path}')
    document = json.loads(path.read_text())
    if document.get('schema') != SCHEMA or document.get('architecture') != ARCHITECTURE:
        raise ValueError('checkpoint schema, architecture or observation version differs; retrain')
    metadata = document['metadata']
    if stage is not None and metadata.get('stage') != stage:
        raise ValueError(f'checkpoint stage {metadata.get("stage")} is not {stage}')
    model = network()
    expected = model.state_dict()
    if set(document['weights']) != set(expected):
        raise ValueError('checkpoint parameter names differ')
    state = {}
    for key, value in document['weights'].items():
        array = np.asarray(value, dtype=np.float32)
        if array.shape != tuple(expected[key].shape) or not np.all(np.isfinite(array)) or np.max(np.abs(array)) > 1e6:
            raise ValueError('invalid checkpoint tensor ' + key)
        state[key] = torch.from_numpy(array)
    model.load_state_dict(state)
    model.eval()
    return model, metadata


def load_policy(path):
    import torch
    torch.set_num_threads(1)
    model, metadata = load(path)
    return RecurrentPolicy(model, training_seeds=metadata['training_seeds'], checkpoint_sha256=digest(path))


def chunks(episodes, length=8):
    out = []
    for records in episodes:
        per_aircraft = defaultdict(list)
        for record in records:
            for row, i in enumerate(record['ids']):
                per_aircraft[int(i)].append((record, row))
        for sequence in per_aircraft.values():
            out += [sequence[k:k + length] for k in range(0, len(sequence), length)]
    return out


def forward(model, sequence):
    import torch
    record, row = sequence[0]
    hidden = record['hidden'][row:row + 1].detach()
    outputs = []
    for record, row in sequence:
        obs = {k: v[row:row + 1] for k, v in record['obs'].items()}
        logits, hidden = model.actor(*tensors(obs), hidden)
        outputs.append((logits[0], model.value(hidden, torch.as_tensor(record['context'])[None])[0]))
    return outputs


def imitation_update(model, episodes, epochs, seed):
    import torch
    from torch import nn
    pieces = chunks(episodes)
    optimizer = torch.optim.Adam(model.parameters(), lr=3e-4)
    rng = np.random.default_rng(seed)
    history = []
    for epoch in range(epochs):
        order = rng.permutation(len(pieces))
        total = correct = count = 0
        for start in range(0, len(pieces), 16):
            terms = []
            for index in order[start:start + 16]:
                for (record, row), (logits, _) in zip(pieces[index], forward(model, pieces[index])):
                    if not record['valid'][row]:
                        continue  # fallback decisions are never imitation labels
                    dist, _ = distribution(logits[None], record['mask'][row:row + 1])
                    target = int(record['teacher'][row])
                    terms.append(-dist.log_prob(torch.tensor([target]))[0])
                    correct += int(dist.logits.argmax(-1).item() == target)
                    count += 1
            if terms:
                loss = torch.stack(terms).mean()
                optimizer.zero_grad()
                loss.backward()
                nn.utils.clip_grad_norm_(model.parameters(), .5)
                optimizer.step()
                total += float(loss.detach()) * len(terms)
        history.append({'epoch': epoch + 1, 'loss': total / max(count, 1), 'agreement': correct / max(count, 1), 'labels': count})
    return history


def advantages(records, gamma=.99, lam=.95):
    """GAE per aircraft; the configured episode end is terminal (no bootstrap)."""
    import torch
    next_value, next_adv = {}, {}
    for record in reversed(records):
        adv = torch.zeros(len(record['ids']))
        for row, i in enumerate(record['ids']):
            i = int(i)
            keep = 0. if bool(record['done'][row]) else 1.
            delta = record['reward'][row] + gamma * next_value.get(i, 0.) * keep - record['value'][row]
            adv[row] = delta + gamma * lam * next_adv.get(i, 0.) * keep
            next_value[i], next_adv[i] = record['value'][row], adv[row]
        record['advantage'], record['return'] = adv, adv + record['value']
    valid = [r['advantage'][r['valid']] for r in records if r['valid'].any()]
    if valid:
        flat = torch.cat(valid)
        mean, std = flat.mean(), flat.std(unbiased=False).clamp_min(1e-5)
        for record in records:
            record['advantage'] = (record['advantage'] - mean) / std


def ppo_update(model, records, optimizer, epochs, seed):
    import torch
    from torch import nn
    advantages(records)
    pieces = chunks([records])
    rng = np.random.default_rng(seed)
    history = []
    for epoch in range(epochs):
        losses, kls = [], []
        for start in range(0, len(pieces), 16):
            actor_terms, value_terms, entropies = [], [], []
            for index in rng.permutation(len(pieces))[start:start + 16]:
                for (record, row), (logits, value) in zip(pieces[index], forward(model, pieces[index])):
                    old, target = record['value'][row], record['return'][row]
                    clipped = old + (value - old).clamp(-.2, .2)
                    value_terms.append(torch.maximum((value - target) ** 2, (clipped - target) ** 2))
                    if not record['valid'][row]:
                        continue
                    dist, _ = distribution(logits[None], record['mask'][row:row + 1])
                    logp = dist.log_prob(record['action'][row:row + 1])[0]
                    ratio = (logp - record['logp'][row]).exp()
                    adv = record['advantage'][row]
                    actor_terms.append(-torch.minimum(ratio * adv, ratio.clamp(.8, 1.2) * adv))
                    entropies.append(dist.entropy()[0])
                    kls.append(float((record['logp'][row] - logp).detach()))
            if not value_terms:
                continue
            loss = .5 * torch.stack(value_terms).mean()
            if actor_terms:
                loss = loss + torch.stack(actor_terms).mean() - .01 * torch.stack(entropies).mean()
            optimizer.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), .5)
            optimizer.step()
            losses.append(float(loss.detach()))
        history.append({'epoch': epoch + 1, 'loss': float(np.mean(losses)) if losses else 0.,
                        'approximate_kl': float(np.mean(kls)) if kls else 0.})
    return history


def train(base, method, seeds, episodes, epochs, training_seed, out, initial=None):
    """Imitation of the planner's admissible choices, or MAPPO fine-tuning from an imitation checkpoint."""
    import torch
    from dataclasses import replace
    from ..engine import simulate
    torch.set_num_threads(1)
    torch.manual_seed(training_seed)
    parent, parent_meta = None, {}
    if method == 'mappo':
        if not initial:
            raise ValueError('MAPPO starts from an imitation checkpoint (--initial)')
        model, parent_meta = load(initial, stage='imitation')
        parent = digest(initial)
    else:
        model = network()
    policy = RecurrentPolicy(model, mode='expert' if method == 'imitation' else 'rollout')
    optimizer = torch.optim.Adam(model.parameters(), lr=3e-4)
    collected, history, rollouts = [], [], []
    for episode in range(episodes):
        experiment = replace(base, seed=seeds[episode % len(seeds)])
        result = simulate(experiment, policy=policy)
        collected.append(policy.records)
        rollouts.append({'seed': experiment.seed, 'metrics': result['metrics']})
        if method == 'mappo':
            history.append({'episode': episode + 1, 'updates': ppo_update(model, policy.records, optimizer, epochs,
                                                                          training_seed + episode)})
        print(f'{method} episode {episode + 1}/{episodes}: '
              f'{sum(int(r["valid"].sum()) for r in policy.records)} admissible decisions', flush=True)
    labels = sum(int(r['valid'].sum()) for records in collected for r in records)
    if labels == 0:
        raise ValueError('no admissible decisions collected; refusing to save an untrained checkpoint')
    if method == 'imitation':
        history = imitation_update(model, collected, epochs, training_seed)
    metadata = {'stage': method, 'training_seed': training_seed,
                'training_seeds': sorted(set(seeds) | set(parent_meta.get('training_seeds', []))),
                'training_experiment': base.to_dict(), 'episodes': episodes, 'admissible_decisions': labels,
                'parent_sha256': parent, 'history': history, 'rollouts': rollouts,
                'scope': 'Research training run on a small budget; not evidence of convergence or of a safety gain.'}
    return save(out, model, metadata)
