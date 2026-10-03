"""Local reported traffic for the actor; separate simulator-only critic context."""
import numpy as np

OWN_DIM, NEIGHBOR_DIM, CONTEXT_DIM, ACTIONS, NEIGHBORS = 17, 11, 9, 22, 8


def observe(cfg, world, ids, p, v, active, snapshot, debt=None):
    pred, observed_v, error, error_v, age = snapshot
    low = np.array([-cfg.area/2, -cfg.area/2, cfg.altitude_floor])
    high = np.array([cfg.area/2, cfg.area/2, cfg.altitude_ceiling])
    own = np.concatenate((p[ids]/cfg.area, v[ids]/cfg.max_speed,
                          (world['goals'][ids]-p[ids])/cfg.area,
                          (p[ids]-low)/cfg.area, (high-p[ids])/cfg.area,
                          world['fixed'][ids,None].astype(float),
                          (np.zeros(len(ids)) if debt is None else debt[ids]/100)[:,None]), axis=1)
    neighbors = np.zeros((len(ids),NEIGHBORS,NEIGHBOR_DIM))
    mask = np.zeros((len(ids),NEIGHBORS),bool)
    for row,i in enumerate(ids):
        others = np.flatnonzero(active & (np.arange(len(p)) != i))
        order = np.argsort(np.linalg.norm(pred[others]-p[i],axis=1),kind='stable')
        js = others[order[:NEIGHBORS]]; count=len(js)
        neighbors[row,:count] = np.concatenate(((pred[js]-p[i])/cfg.area,
                    (observed_v[js]-v[i])/cfg.max_speed, error[js,None]/cfg.area,
                    error_v[js,None]/cfg.max_speed, age[js,None]/5,
                    world['fixed'][js,None], world['cooperative'][js,None]),axis=1)
        mask[row,:count]=True
    # Normalization clips observation magnitude only, never safety uncertainty.
    return {'own':np.clip(own,-10,10).astype(np.float32),
            'neighbors':np.clip(neighbors,-10,10).astype(np.float32),'neighbor_mask':mask}


def central_context(cfg,world,p,v,active):
    """Training-only global information, not supplied to actor.forward()."""
    if not np.any(active): return np.zeros(CONTEXT_DIM,np.float32)
    return np.array([np.mean(active), np.mean(active & world['cooperative']),
                     np.mean(active & world['fixed']),
                     *np.mean(p[active]/cfg.area,axis=0),
                     *np.mean(v[active]/cfg.max_speed,axis=0)],np.float32)
