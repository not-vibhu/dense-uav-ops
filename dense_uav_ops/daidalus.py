"""NASA DAIDALUS as a detect-and-avoid baseline.

DAIDALUS computes well-clear alerts and horizontal direction bands for an
ownship against traffic it assumes is non-maneuvering (constant velocity). The
baseline guidance steers toward the conflict-free heading closest to the
desired heading, holding it for one guidance period. This makes DAIDALUS one
point on the frontier: an optimistic traffic model with a mature, formally
verified core, here driven through a research configuration whose thresholds
are not a published small-UAS well-clear definition.

The bridge binary and its NASA dependency are built by
`scripts/build_daidalus.py`; they are not part of this package.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import numpy as np

from .vehicles import project


class Bridge:
    """One persistent bridge process; one DAIDALUS instance per ownship inside it."""

    def __init__(self, manifest):
        manifest_path = Path(manifest)
        if not manifest_path.is_file():
            raise FileNotFoundError(f'{manifest} not found; run python scripts/build_daidalus.py')
        self.manifest = json.loads(manifest_path.read_text())
        for key in ('binary', 'configuration'):
            if hashlib.sha256(Path(self.manifest[key]).read_bytes()).hexdigest() != self.manifest[key + '_sha256']:
                raise ValueError(f'DAIDALUS {key} differs from its build manifest; rebuild it')
        self.process = subprocess.Popen([self.manifest['binary'], self.manifest['configuration']],
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)

    def query(self, own, ids, positions, velocities, time):
        """Alerts and direction bands for ownship `own` (its row must be first)."""
        lines = [f'{len(ids)} {time:.6f}']
        lines += [f'{i} ' + ' '.join(f'{x:.6f}' for x in (*p, *v)) for i, p, v in zip(ids, positions, velocities)]
        self.process.stdin.write('\n'.join(lines) + '\n')
        self.process.stdin.flush()
        reply = self.process.stdout.readline()
        if not reply:
            raise RuntimeError(f'DAIDALUS bridge stopped (exit {self.process.poll()})')
        result = json.loads(reply)
        if result['own'] != own:
            raise RuntimeError('DAIDALUS bridge answered for a different ownship')
        return result

    def close(self):
        if self.process.poll() is None:
            self.process.stdin.close()
            self.process.wait(timeout=10)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def track_angle(velocity):
    """Degrees clockwise from north (+y), the DAIDALUS convention."""
    return float(np.degrees(np.arctan2(velocity[0], velocity[1])) % 360.)


def select_heading(desired, bands):
    """Closest heading to `desired` inside a NONE band, else inside a RECOVERY band.

    Returns (heading, status) where status is 'clear', 'resolved', 'recovery' or 'none'.
    """
    def distance(a, b):
        return abs((a - b + 180.) % 360. - 180.)

    for region, status in (('NONE', 'clear'), ('RECOVERY', 'recovery')):
        best = None
        for low, high, kind in bands:
            if kind != region or low is None or high is None:
                continue
            if low <= desired <= high:
                return desired, status
            for edge in (low, high):
                # Step slightly inside the band so the boundary is not exactly on a conflict edge.
                inside = edge + (1. if edge == low else -1.) * min(1., (high - low) / 2)
                if best is None or distance(inside, desired) < distance(best, desired):
                    best = inside
        if best is not None:
            return best % 360., 'resolved' if status == 'clear' else status
    return desired, 'none'


class Guidance:
    """Holds each aircraft's DAIDALUS heading between guidance updates."""

    def __init__(self, experiment, bridge):
        self.e, self.bridge = experiment, bridge
        self.heading = {}
        self.next_update = {}
        self.counts = {'clear': 0, 'resolved': 0, 'recovery': 0, 'none': 0}
        self.max_alert = {}

    def commands(self, t, world, ids, p, v, snapshot, desired_velocity):
        e = self.e
        out = np.zeros((len(ids), 3))
        for row, i in enumerate(ids):
            want = desired_velocity[row]
            if t + 1e-9 >= self.next_update.get(i, 0.):
                self.next_update[i] = t + e.controller.daidalus_period_s
                others = np.flatnonzero(snapshot.known & (np.arange(len(p)) != i) &
                                        (np.linalg.norm(snapshot.position - p[i], axis=1) <= 400.))
                ids_frame = [int(i)] + [int(j) for j in others]
                positions = np.vstack((p[i], snapshot.position[others]))
                velocities = np.vstack((v[i], snapshot.velocity[others]))
                result = self.bridge.query(int(i), ids_frame, positions, velocities, t)
                level = max((a for _, a in result['alerts']), default=0)
                self.max_alert[int(i)] = max(self.max_alert.get(int(i), 0), level)
                heading, status = select_heading(track_angle(want), result['bands'])
                self.counts[status] += 1
                self.heading[i] = heading
            heading = np.radians(self.heading.get(i, track_angle(want)))
            speed = np.linalg.norm(want[:2])
            target = np.array([speed * np.sin(heading), speed * np.cos(heading), want[2]])
            out[row] = (target - v[i]) / .6
        return project(out, v[ids], world.limits.take(ids), e.window.dt_s)
