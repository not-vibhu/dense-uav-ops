"""Signed finite leases; agreement supplies intent, never weaker traffic bounds."""
from dataclasses import dataclass
import numpy as np
from cryptography.exceptions import InvalidSignature
from .audit import Journal, digest
from swarm_sim.oracle import quadratic_minimum


def compatible(left, right, separation):
    start = max(left.start, right.start)
    end = min(left.start+len(left.a)*left.dt, right.start+len(right.a)*right.dt)
    if end <= start:
        return True
    if abs(left.dt-right.dt) > 1e-9:
        return False
    dt = left.dt
    il, ir = round((start-left.start)/dt), round((start-right.start)/dt)
    if abs(left.start+il*dt-start) > 1e-8 or abs(right.start+ir*dt-start) > 1e-8:
        return False
    for k in range(int(round((end-start)/dt))):
        a, b = il+k, ir+k
        guard = separation+left.slab[a]+right.slab[b]
        if quadratic_minimum(left.p[a]-right.p[b], left.v[a]-right.v[b], left.a[a]-right.a[b], dt) < guard:
            return False
    return True


class Reservations:
    def __init__(self):
        self.plans = {}

    def accept(self, own, plan, separation, now):
        self.plans = {i: p for i, p in self.plans.items() if p.start+len(p.a)*p.dt > now}
        if any(i != own and not compatible(plan, p, separation) for i, p in self.plans.items()):
            return False
        self.plans[own] = plan
        return True


@dataclass
class Promise:
    epoch: int
    digest: str
    start: float
    end: float


class Negotiator:
    """One local promise per overlapping interval, exact membership certificates."""
    def __init__(self, actor, public, journal, clock_bound=.05):
        if not np.isfinite(clock_bound) or not 0 <= clock_bound <= 1:
            raise ValueError('Unsupported negotiation clock bound')
        self.actor = str(actor)
        self.public, self.journal, self.clock_bound = public, journal, clock_bound
        self.promise = None
        self.latest_epoch = -1

    def _proposal(self, proposal):
        try:
            p = Journal.authenticate(proposal, self.public)
            if (not isinstance(p, dict) or p.get('type') != 'PROPOSE' or
                    not isinstance(p.get('members'), list) or not 1 <= len(p['members']) <= 500 or
                    any(type(a) is not str or a not in self.public for a in p['members']) or
                    len(set(p['members'])) != len(p['members']) or self.actor not in p['members'] or
                    type(p.get('epoch')) is not int or p['epoch'] < 0 or
                    any(type(p.get(k)) not in (int, float) for k in ('start', 'end')) or
                    not np.isfinite([p['start'], p['end']]).all() or p['end'] <= p['start']):
                return None
            return p
        except (InvalidSignature, ValueError, KeyError, TypeError):
            return None

    def prepare(self, proposal, now, locally_safe):
        p = self._proposal(proposal)
        if p is None or not np.isfinite(now):
            return None
        if (
                now+self.clock_bound >= p['start'] or p['end'] <= p['start'] or p['epoch'] <= self.latest_epoch or not locally_safe):
            return None
        old = self.promise
        if old and max(old.start, p['start']) < min(old.end, p['end']):
            return None
        self.promise = Promise(p['epoch'], digest(p), p['start'], p['end'])
        self.latest_epoch = p['epoch']
        return self.journal.sign(self.actor, {'type': 'ACCEPT', 'proposal': digest(p), 'epoch': p['epoch']})

    def authorized(self, proposal, acceptances, now, locally_safe):
        p = self._proposal(proposal)
        if p is None or not np.isfinite(now) or self.promise is None or self.promise.digest != digest(p) or not locally_safe or not p['start']+self.clock_bound <= now < p['end']-self.clock_bound:
            return False
        try:
            actors = []
            for acceptance in acceptances:
                a = Journal.authenticate(acceptance, self.public)
                if a != {'type': 'ACCEPT', 'proposal': digest(p), 'epoch': p['epoch']}:
                    return False
                actors.append(acceptance['actor'])
            return len(actors) == len(set(actors)) and set(actors) == set(p['members'])
        except (InvalidSignature, ValueError, KeyError, TypeError):
            return False
