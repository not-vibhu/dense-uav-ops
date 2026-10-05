"""Static visibility routes around spherical obstacles for controlled aircraft.

Route edges clear inflated obstacles geometrically. Dynamic feasibility and
traffic are left to the runtime planner, so a route is not a certified path.
"""
import heapq
import numpy as np

from .planner import segment_distance


def plan_route(start, goal, radius, obstacles, low, high):
    margin = radius + 3.
    nodes = [start, goal]
    for x, y, z, r in obstacles:
        for direction in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1),
                          (1, 1, 0), (1, -1, 0), (-1, 1, 0), (-1, -1, 0)):
            d = np.array(direction, float)
            nodes.append(np.array([x, y, z]) + d / np.linalg.norm(d) * (r + margin + 5.))
    nodes = np.array(nodes, float)
    valid = np.all((nodes >= low + radius) & (nodes <= high - radius), axis=1)
    for x, y, z, r in obstacles:
        valid &= np.linalg.norm(nodes - [x, y, z], axis=1) >= r + margin
    if not valid[0] or not valid[1]:
        return None
    weights = np.linalg.norm(nodes[:, None] - nodes[None, :], axis=-1)
    edges = valid[:, None] & valid[None, :]
    for x, y, z, r in obstacles:
        edges &= segment_distance(nodes[:, None] - [x, y, z], nodes[None, :] - [x, y, z]) >= r + margin
    np.fill_diagonal(edges, False)
    distance = np.full(len(nodes), np.inf)
    distance[0] = 0.
    parent = np.full(len(nodes), -1)
    queue = [(0., 0)]
    while queue:
        d, i = heapq.heappop(queue)
        if d > distance[i]:
            continue
        if i == 1:
            break
        for j in np.flatnonzero(edges[i]):
            if d + weights[i, j] < distance[j]:
                distance[j], parent[j] = d + weights[i, j], i
                heapq.heappush(queue, (distance[j], int(j)))
    if not np.isfinite(distance[1]):
        return None
    path = [1]
    while path[-1] != 0:
        path.append(int(parent[path[-1]]))
    return nodes[path[::-1]][1:]


class Routes:
    """Waypoint lists; uncontrolled aircraft fly straight to their exit."""

    def __init__(self, experiment, traffic):
        a = experiment.airspace
        low = np.array([-a.side_m / 2, -a.side_m / 2, a.floor_m])
        high = np.array([a.side_m / 2, a.side_m / 2, a.ceiling_m])
        self.paths, self.rejected = [], np.zeros(traffic.n, bool)
        for i in range(traffic.n):
            path = traffic.goal[i:i + 1]
            if a.obstacles and traffic.controlled[i]:
                path = plan_route(traffic.start[i], traffic.goal[i], traffic.radius[i], a.obstacles, low, high)
                self.rejected[i] = path is None
                path = traffic.goal[i:i + 1] if path is None else path
            self.paths.append(path)
        self.index = np.zeros(traffic.n, int)

    def waypoints(self):
        return np.array([path[k] for path, k in zip(self.paths, self.index)])

    def final(self):
        return np.array([k == len(path) - 1 for path, k in zip(self.paths, self.index)])

    def advance(self, p, airborne, capture=6.):
        for i in np.flatnonzero(airborne):
            if self.index[i] < len(self.paths[i]) - 1 and np.linalg.norm(p[i] - self.paths[i][self.index[i]]) < capture:
                self.index[i] += 1
