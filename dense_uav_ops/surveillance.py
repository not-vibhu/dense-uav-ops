"""Shared regional surveillance feed with delay, loss, bounded error and track management.

This is a synthetic stand-in for fused network Remote ID and ground sensors. It
does not encode ASTM F3411 messages or model RF propagation. The planner sees
only this feed; true positions of other aircraft are never passed to it.

Track management: a track is dropped when an end-of-operation notice arrives
(subject to the same delay and loss) or when no report has been received for
`TRACK_TIMEOUT_S`. Aircraft that are airborne but untracked are counted by the
engine as unknown-traffic exposure.
"""
from dataclasses import dataclass
import numpy as np

TRACK_TIMEOUT_S = 10.


@dataclass
class Snapshot:
    position: np.ndarray        # report propagated at constant velocity to now
    velocity: np.ndarray        # reported velocity
    position_error: np.ndarray  # declared bound on report error at its source time
    velocity_error: np.ndarray
    age: np.ndarray             # now - source time
    known: np.ndarray           # track currently held

    def take(self, ids):
        return Snapshot(*(x[ids] for x in (self.position, self.velocity, self.position_error,
                                            self.velocity_error, self.age, self.known)))


class Feed:
    def __init__(self, experiment, traffic):
        self.s = experiment.surveillance
        self.dt = experiment.window.dt_s
        n = traffic.n
        rng = np.random.default_rng(np.random.SeedSequence([experiment.seed, 201]))
        self.rng = rng
        self.p = np.zeros((n, 3))
        self.v = np.zeros((n, 3))
        self.source = np.full(n, -np.inf)
        self.seen = np.zeros(n, bool)
        self.ended = np.zeros(n, bool)
        direction = rng.normal(size=(n, 3))
        # A persistent per-aircraft bias: report errors are correlated in time, not independent.
        uncooperative = ~traffic.cooperative & ~traffic.manned
        self.position_error = np.where(uncooperative, self.s.uncooperative_error_scale, 1.) * self.s.position_error_m
        self.velocity_error = np.where(uncooperative, self.s.uncooperative_error_scale, 1.) * self.s.velocity_error_mps
        self.bias = direction / np.maximum(np.linalg.norm(direction, axis=1, keepdims=True), 1e-9)
        self.bias *= (self.position_error * self.s.bias_fraction)[:, None]
        detect = rng.random(n)
        self.detectable = np.where(traffic.manned, detect < self.s.manned_detection,
                                   np.where(uncooperative, detect < self.s.uncooperative_detection, True))
        # Per-aircraft draws keep random streams aligned across controllers (common random numbers).
        self.end_notice_lost = np.random.default_rng(np.random.SeedSequence([experiment.seed, 202])).random(n) < self.s.loss
        self.pending = []
        self.next_sample = 0.
        self.delivered = self.dropped = 0

    def outage(self, t):
        return self.s.outage_start_s <= t < self.s.outage_start_s + self.s.outage_duration_s

    def update(self, t, p, v, airborne, finished=()):
        s = self.s
        for i in finished:
            if not self.end_notice_lost[i]:
                self.pending.append((t + s.latency_s, t, 'end', int(i)))
        if t + 1e-9 >= self.next_sample:
            self.next_sample += s.period_s
            mask = airborne & self.detectable & (np.linalg.norm(p[:, :2], axis=1) <= s.range_m)
            if self.outage(t):
                mask[:] = False
            lost = self.rng.random(len(p)) < s.loss
            self.dropped += int(np.sum(mask & lost))
            mask &= ~lost
            noise = self.rng.normal(size=p.shape)
            noise /= np.maximum(np.linalg.norm(noise, axis=1, keepdims=True), 1e-9)
            noise *= (self.position_error * (1 - s.bias_fraction))[:, None] * self.rng.random((len(p), 1))
            velocity_noise = self.rng.normal(size=v.shape)
            velocity_noise /= np.maximum(np.linalg.norm(velocity_noise, axis=1, keepdims=True), 1e-9)
            velocity_noise *= self.velocity_error[:, None] * self.rng.random((len(p), 1))
            self.pending.append((t + s.latency_s, t, 'report', (mask, p + self.bias + noise, v + velocity_noise)))
        keep = []
        for arrival, source, kind, payload in self.pending:
            if arrival > t + 1e-9:
                keep.append((arrival, source, kind, payload))
            elif kind == 'end':
                self.ended[payload] = True
            else:
                mask, position, velocity = payload
                # A delayed report never overwrites a newer one.
                use = mask & (source > self.source) & ~self.ended
                self.p[use], self.v[use], self.source[use] = position[use], velocity[use], source
                self.seen |= use
                self.delivered += int(np.sum(use))
        self.pending = keep

    def snapshot(self, t):
        age = np.where(self.seen, np.maximum(0., t - self.source), np.inf)
        known = self.seen & ~self.ended & (age <= TRACK_TIMEOUT_S)
        safe_age = np.where(known, age, 0.)
        return Snapshot(position=self.p + self.v * safe_age[:, None], velocity=self.v.copy(),
                        position_error=self.position_error.copy(), velocity_error=self.velocity_error.copy(),
                        age=safe_age, known=known)
