"""Synthetic regional RID feed; protocol/RF conformance is not simulated."""
import numpy as np


class Telemetry:
    def __init__(self, cfg, world):
        self.cfg, self.fault = cfg, world["scenario"].fault
        self.faults = set(self.fault.split("+"))
        self.rng = np.random.default_rng(np.random.SeedSequence([cfg.seed, 31]))
        self.position = world["position"].copy()
        self.velocity = world["velocity"].copy()
        self.source_time = np.zeros(cfg.drones)
        self.pending = []
        self.next_sample = cfg.telemetry_period
        self.delivered, self.dropped = cfg.drones, 0
        # Bias has a fixed sign per aircraft; samples are not falsely independent.
        self.bias = self.rng.normal(size=(cfg.drones, 3))
        self.bias /= np.maximum(np.linalg.norm(self.bias, axis=1)[:, None], 1e-9)
        self.bias *= cfg.position_error_bound * .6
        if "bias" in self.faults:
            self.bias[::3] += np.array([10., -8., 0.])
        if "datum" in self.faults:
            self.bias[::2, 2] += 18.

    def step(self, time, p, v):
        if time + 1e-8 >= self.next_sample:
            self.next_sample += self.cfg.telemetry_period
            n = len(p)
            noise = self.rng.normal(size=(n, 3))
            noise /= np.maximum(np.linalg.norm(noise, axis=1)[:, None], 1e-9)
            observed = p + self.bias + noise * self.cfg.position_error_bound * .2
            vel_noise = self.rng.normal(size=(n, 3))
            vel_noise /= np.maximum(np.linalg.norm(vel_noise, axis=1)[:, None], 1e-9)
            observed_v = v + vel_noise * self.cfg.velocity_error_bound * .8
            loss = .45 if "loss" in self.faults else .03
            receive = self.rng.random(n) >= loss
            if "outage" in self.faults and 8 <= time <= 15:
                receive[:] = False
            if "occlusion" in self.faults:
                receive &= ~((np.abs(p[:, 0]) < 30) & (p[:, 2] < 65))
            latency = 2.0 if "delay" in self.faults else .15
            if "handoff" in self.faults and 8 <= time <= 12:
                latency += 1.
            self.dropped += int(np.sum(~receive))
            self.pending.append((time + latency, time, receive, observed, observed_v))
        keep = []
        for arrival, source, mask, p_obs, v_obs in self.pending:
            if arrival <= time + 1e-8:
                # Old deliveries do not overwrite newer source observations.
                use = mask & (source > self.source_time)
                self.position[use], self.velocity[use] = p_obs[use], v_obs[use]
                self.source_time[use] = source
                self.delivered += int(np.sum(use))
            else:
                keep.append((arrival, source, mask, p_obs, v_obs))
        self.pending = keep

    def snapshot(self, time):
        age = np.maximum(0., time - self.source_time)
        pred = self.position + self.velocity * age[:, None]
        e = (self.cfg.position_error_bound + self.cfg.velocity_error_bound * age +
             .5 * self.cfg.advertised_acceleration_bound * age ** 2)
        ev = self.cfg.velocity_error_bound + self.cfg.advertised_acceleration_bound * age
        if "identity" in self.faults:
            # Two synthetic association possibilities, separated by 8 m, are
            # retained in one conservative enclosing ball rather than dropped.
            e = e + 8.
        return pred, self.velocity.copy(), e, ev, age
