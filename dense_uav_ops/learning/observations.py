"""Actor inputs built only from ownship state and the surveillance snapshot.

Neighbor class labels (fixed-wing, controlled) are idealized metadata: a real
system would need Remote ID type fields or USS data to know them. The critic's
global context is simulator truth and is used only during training.
"""
import numpy as np

from ..planner import enclosure

OWN_DIM, NEIGHBOR_DIM, CONTEXT_DIM, NEIGHBORS = 17, 11, 9, 8


def observe(e, world, ids, p, v, snapshot):
    side = e.airspace.side_m
    low = np.array([-side / 2, -side / 2, e.airspace.floor_m])
    high = np.array([side / 2, side / 2, e.airspace.ceiling_m])
    speed = max(e.multirotor.max_speed_mps, e.fixed_wing.max_speed_mps)
    own = np.concatenate((p[ids] / side, v[ids] / speed, (world.waypoint[ids] - p[ids]) / side,
                          (p[ids] - low) / side, (high - p[ids]) / side,
                          world.fixed[ids, None].astype(float), world.burden[ids, None] / 100.), axis=1)
    neighbors = np.zeros((len(ids), NEIGHBORS, NEIGHBOR_DIM))
    mask = np.zeros((len(ids), NEIGHBORS), bool)
    radius_now = enclosure(snapshot, 0., e.assumptions.traffic_acceleration_mps2)
    for row, i in enumerate(ids):
        others = np.flatnonzero(snapshot.known & (np.arange(len(p)) != i))
        order = np.argsort(np.linalg.norm(snapshot.position[others] - p[i], axis=1), kind='stable')
        js = others[order[:NEIGHBORS]]
        if len(js):
            neighbors[row, :len(js)] = np.column_stack((
                (snapshot.position[js] - p[i]) / side, (snapshot.velocity[js] - v[i]) / speed,
                radius_now[js] / side, snapshot.velocity_error[js] / speed, snapshot.age[js] / 5.,
                world.fixed[js].astype(float), world.controlled[js].astype(float)))
            mask[row, :len(js)] = True
    return {'own': np.clip(own, -10, 10).astype(np.float32),
            'neighbors': np.clip(neighbors, -10, 10).astype(np.float32), 'mask': mask}


def central_context(e, world, p, v, airborne):
    """Training-only global summary for the centralized critic."""
    if not np.any(airborne):
        return np.zeros(CONTEXT_DIM, np.float32)
    side = e.airspace.side_m
    speed = max(e.multirotor.max_speed_mps, e.fixed_wing.max_speed_mps)
    return np.array([np.mean(airborne), np.mean(airborne & world.controlled), np.mean(airborne & world.fixed),
                     *np.mean(p[airborne] / side, axis=0), *np.mean(v[airborne] / speed, axis=0)], np.float32)
