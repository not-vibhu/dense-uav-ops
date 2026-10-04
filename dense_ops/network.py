"""Independent receiver stores and bounded asynchronous directed-link queues."""
from dataclasses import dataclass
import heapq
import numpy as np


@dataclass(frozen=True)
class Links:
    latency: float = .1
    jitter: float = .05
    loss: float = .03
    partition: bool = False
    asymmetric: bool = False
    clock_skew: float = 0.

    def validate(self):
        if not all(np.isfinite(x) for x in (self.latency, self.jitter, self.loss, self.clock_skew)) or min(self.latency, self.jitter) < 0 or not 0 <= self.loss <= 1 or abs(self.clock_skew) > 1:
            raise ValueError('Invalid link conditions')
        return self


class Bus:
    def __init__(self, seed, links=Links(), capacity=200000):
        self.links = links.validate()
        self.rng = np.random.default_rng(seed)
        self.queue = []
        self.serial = 0
        self.dropped = 0
        self.capacity = capacity

    def send(self, sender, receiver, now, payload):
        partition = self.links.partition and sender != receiver and 2 <= now <= 6
        asymmetric = self.links.asymmetric and str(sender) < str(receiver)
        if partition or asymmetric or self.rng.random() < self.links.loss or len(self.queue) >= self.capacity:
            self.dropped += 1
            return False
        arrival = now+self.links.latency+self.rng.uniform(0, self.links.jitter)
        heapq.heappush(self.queue, (arrival, self.serial, receiver, payload))
        self.serial += 1
        return True

    def receive(self, now):
        result = []
        while self.queue and self.queue[0][0] <= now+1e-9:
            _, _, receiver, payload = heapq.heappop(self.queue)
            result.append((receiver, payload))
        return result


class Surveillance:
    def __init__(self, n, seed, links, period=.5, error=1., velocity_error=.3, sensor_range=600.):
        self.bus = Bus(seed, links)
        self.p = np.zeros((n, n, 3))
        self.v = np.zeros_like(self.p)
        self.source = np.full((n, n), -np.inf)
        self.frame_source = np.full(n, -np.inf)
        self.seen = np.zeros((n, n), bool)
        self.period, self.error, self.velocity_error, self.range = period, error, velocity_error, sensor_range
        self.next_sample = 0.
        self.rng = np.random.default_rng(seed+1)
        self.faults = set()
        self.bias = self.rng.normal(size=(n, 3))
        self.bias /= np.maximum(np.linalg.norm(self.bias, axis=1, keepdims=True), 1e-9)
        self.bias *= error*.2

    def step(self, now, p, v, visible, receivers, outage=False):
        if now+1e-9 >= self.next_sample:
            self.next_sample = now+self.period
            for own in receivers:
                neighbors = np.flatnonzero(visible & (np.linalg.norm(p-p[own], axis=1) <= self.range))
                if 'occlusion' in self.faults:
                    neighbors = neighbors[~((np.abs(p[neighbors, 0]) < 30) & (p[neighbors, 2] < 65))]
                if outage:
                    continue
                noise = self.rng.normal(size=(len(neighbors), 3))
                noise /= np.maximum(np.linalg.norm(noise, axis=1, keepdims=True), 1e-9)
                vn = self.rng.normal(size=noise.shape)
                vn /= np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-9)
                bias = self.bias[neighbors].copy()
                if 'bias' in self.faults:
                    bias[neighbors % 3 == 0] += [10., -8., 0.]
                if 'datum' in self.faults:
                    bias[neighbors % 2 == 0, 2] += 18.
                self.bus.send('receiver', int(own), now,
                              (now+self.bus.links.clock_skew, neighbors, p[neighbors]+bias+self.error*.8*noise, v[neighbors]+self.velocity_error*vn))
        for own, (source, ids, pp, vv) in self.bus.receive(now):
            self.frame_source[own] = max(self.frame_source[own], source)
            fresh = source > self.source[own, ids]
            ids, pp, vv = ids[fresh], pp[fresh], vv[fresh]
            self.p[own, ids], self.v[own, ids], self.source[own, ids] = pp, vv, source
            self.seen[own, ids] = True

    def ready(self, own, now, max_age):
        """Delivered frame freshness is necessary, not proof of full coverage."""
        source = self.frame_source[own]
        age = max(0., now-source+abs(self.bus.links.clock_skew))
        return bool(np.isfinite(source) and age <= max_age+1e-9)

    def snapshot(self, own, now, acceleration):
        nominal_age = np.where(self.seen[own], np.maximum(0., now-self.source[own]), 0.)
        clock = abs(self.bus.links.clock_skew)
        age = np.where(self.seen[own], np.maximum(0., now-self.source[own]+clock), 0.)
        error = self.error+self.velocity_error*age+.5*acceleration*age**2
        error += np.linalg.norm(self.v[own],axis=1)*clock
        if 'identity' in self.faults:
            error += 8.
        ev = self.velocity_error+acceleration*age
        return self.p[own]+self.v[own]*nominal_age[:, None], self.v[own].copy(), error, ev, age
