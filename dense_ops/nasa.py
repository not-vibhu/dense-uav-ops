"""Actual DAIDALUS subprocess adapter, advisory and independent of the shield."""
import hashlib
import json
from pathlib import Path
import subprocess
import numpy as np


class Daidalus:
    def __init__(self, manifest):
        self.manifest = json.loads(Path(manifest).read_text())
        for key in ('binary', 'configuration'):
            path = Path(self.manifest['binary' if key == 'binary' else 'configuration_path'])
            if hashlib.sha256(path.read_bytes()).hexdigest() != self.manifest[key+'_sha256']:
                raise ValueError('NASA adapter artifact checksum mismatch')

    def evaluate(self, own_id, ids, positions, velocities, time=0.):
        ids = list(ids)
        p, v = np.asarray(positions), np.asarray(velocities)
        if (own_id not in ids or len(ids) != len(set(ids)) or p.shape != (len(ids), 3) or
                v.shape != p.shape or not np.isfinite(p).all() or not np.isfinite(v).all() or
                not np.isfinite(time) or any(type(i) is not int or i < 0 for i in ids)):
            raise ValueError('Finite SI ENU state with unique integer IDs required')
        order = [ids.index(own_id)] + [i for i, id in enumerate(ids) if id != own_id]
        lines = [f'{len(ids)} {time}']
        lines.extend(' '.join(map(str, [ids[i], *p[i], *v[i]])) for i in order)
        result = subprocess.run([self.manifest['binary'], self.manifest['configuration_path']],
                                input='\n'.join(lines)+'\n', text=True, capture_output=True,
                                check=True, timeout=5)
        data = json.loads(result.stdout)
        data['upstream_sha256_pin'] = self.manifest['daidalus']
        data['configuration_sha256'] = self.manifest['configuration_sha256']
        data['sensor_uncertainty_mapping'] = 'disabled: hard bounds are not standard deviations'
        return data
