"""Static visibility routes; runtime dynamics checks remain necessary."""
import heapq
import numpy as np
from .predictive import segment_distance


def plan_route(start, goal, radius, obstacles, cfg):
    margin = radius + 3.
    nodes = [start, goal]
    for x, y, z, r in obstacles:
        for direction in ((1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1),
                          (1,1,0),(1,-1,0),(-1,1,0),(-1,-1,0)):
            d = np.array(direction, float); d /= np.linalg.norm(d)
            nodes.append(np.array([x,y,z]) + d * (r + margin + 5.))
    nodes = np.array(nodes, float)
    low = np.array([-cfg.area/2, -cfg.area/2, cfg.altitude_floor]) + radius
    high = np.array([cfg.area/2, cfg.area/2, cfg.altitude_ceiling]) - radius
    valid = np.all((nodes >= low) & (nodes <= high), axis=1)
    for x,y,z,r in obstacles:
        valid &= np.linalg.norm(nodes-[x,y,z],axis=1) >= r + margin
    if not valid[0] or not valid[1]:
        return None
    delta = nodes[:,None] - nodes[None,:]
    weights = np.linalg.norm(delta,axis=-1)
    edges = valid[:,None] & valid[None,:]
    for x,y,z,r in obstacles:
        edges &= segment_distance(nodes[:,None]-[x,y,z],nodes[None,:]-[x,y,z]) >= r+margin
    np.fill_diagonal(edges,False)
    distances = np.full(len(nodes),np.inf); distances[0]=0.
    parent = np.full(len(nodes),-1,int); queue=[(0.,0)]
    while queue:
        dist,i = heapq.heappop(queue)
        if dist > distances[i]: continue
        if i == 1: break
        for j in np.flatnonzero(edges[i]):
            new = dist + weights[i,j]
            if new < distances[j]:
                distances[j],parent[j]=new,i
                heapq.heappush(queue,(new,int(j)))
    if not np.isfinite(distances[1]): return None
    path=[1]
    while path[-1] != 0: path.append(int(parent[path[-1]]))
    return nodes[path[::-1]][1:]


class Routes:
    def __init__(self,cfg,world):
        self.mission_goals=world["goals"].copy()
        self.paths=[]; self.index=np.zeros(cfg.drones,int)
        self.rejected=np.zeros(cfg.drones,bool)
        for i in range(cfg.drones):
            path=(plan_route(world["position"][i],self.mission_goals[i],world["radius"][i],world["obstacles"],cfg)
                  if cfg.routes == "visibility" and world["cooperative"][i] else self.mission_goals[i:i+1])
            self.rejected[i]=path is None
            self.paths.append(path if path is not None else self.mission_goals[i:i+1])

    def update(self,p,active,world):
        for i in np.flatnonzero(active & world["cooperative"]):
            path=self.paths[i]; ix=self.index[i]
            if ix < len(path)-1 and np.linalg.norm(p[i]-path[ix]) < 6.:
                self.index[i] += 1
        world["goals"] = np.array([path[ix] for path,ix in zip(self.paths,self.index)])
