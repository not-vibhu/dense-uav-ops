from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class Scenario:
    geometry: str
    description: str
    fault: str = "none"
    domain: str = "modeled"


SCENARIOS = {
    "head_on": Scenario("head_on", "Opposing fleets exchange sides"),
    "crossing": Scenario("crossing", "Four crossing traffic streams"),
    "overtaking": Scenario("overtaking", "Faster aircraft overtake slower traffic"),
    "merge": Scenario("merge", "Two streams merge into a common route"),
    "corridor": Scenario("corridor", "Opposing aircraft in a narrow corridor"),
    "vertical": Scenario("vertical", "Climbing and descending crossings"),
    "urban": Scenario("crossing", "Crossing near conservative building volumes", "buildings"),
    "blocked_escape": Scenario("corridor", "Low-clearance route and blocked alternatives", "blocked"),
    "overload": Scenario("crossing", "Compressed volume stresses available maneuver space", "overload"),
    "boundary_handoff": Scenario("crossing", "Handoff temporarily delays shared observations", "handoff"),
    "sudden_turn": Scenario("crossing", "Legacy aircraft change route without negotiation", "turn"),
    "stopped_legacy": Scenario("head_on", "Legacy multirotors stop in the crossing", "stop"),
    "packet_loss": Scenario("crossing", "45 percent independent telemetry loss", "loss"),
    "stale_telemetry": Scenario("crossing", "Two-second source-to-receiver delay", "delay"),
    "network_outage": Scenario("crossing", "Regional feed outage during the encounter", "outage"),
    "sensor_occlusion": Scenario("urban", "Receivers miss aircraft behind a central obstruction", "occlusion"),
    "gnss_bias": Scenario("crossing", "Persistent position bias exceeds declared enclosure", "bias", "out_of_bounds"),
    "datum_error": Scenario("vertical", "Unrecognized vertical datum error", "datum", "out_of_bounds"),
    "identity_ambiguity": Scenario("crossing", "Conflicting identities retain an extra hypothesis", "identity"),
    "wind_gust": Scenario("crossing", "Bounded lateral wind acceleration", "wind"),
    "actuator_lag": Scenario("crossing", "Actuator command lag differs from ideal tracking", "lag", "out_of_bounds"),
    "bound_violation": Scenario("crossing", "Unexpected intruder acceleration exceeds the model", "intruder", "out_of_bounds"),
    "solver_overrun": Scenario("crossing", "Simulated missing safety-control updates", "overrun", "out_of_bounds"),
    "partial_commit": Scenario("crossing", "Some equipped agents miss negotiation certificates", "partial"),
    "loss_wind": Scenario("crossing", "Compound packet loss and bounded gust", "loss+wind"),
    "outage_turn": Scenario("crossing", "Compound feed outage and legacy turn", "outage+turn"),
    "lag_datum": Scenario("vertical", "Compound lag and wrong vertical datum", "lag+datum", "out_of_bounds"),
}


def _side_slots(n, rng, area, low, high):
    # Shared grid supplies separated starts even at 200 aircraft per fleet.
    ys = np.arange(-area * .39, area * .40, 13.)
    zs = np.arange(low + 6., high - 3., 13.)
    depths = (0., 15., 30.)
    slots = np.array([(d, y, z) for d in depths for y in ys for z in zs])
    if n > len(slots):
        raise ValueError("Fleet exceeds separated spawn capacity for this volume")
    return slots[rng.permutation(len(slots))[:n]].copy()


def build_world(cfg):
    rng = np.random.default_rng(np.random.SeedSequence([cfg.seed, 11]))
    n = cfg.drones
    spec = SCENARIOS[cfg.scenario]
    p = np.empty((n, 3))
    g = np.empty_like(p)
    side = np.arange(n) % (4 if spec.geometry in ("crossing", "urban") else 2)
    if spec.geometry == "overtaking":
        side[:] = 0
    for s in np.unique(side):
        ids = np.flatnonzero(side == s)
        slots = _side_slots(len(ids), rng, cfg.area, cfg.altitude_floor, cfg.altitude_ceiling)
        base = np.column_stack((-cfg.area * .44 + slots[:, 0], slots[:, 1], slots[:, 2]))
        if spec.geometry in ("crossing", "urban"):
            theta = s * np.pi / 2
        else:
            theta = s * np.pi
        rot = np.array([[np.cos(theta), -np.sin(theta)], [np.sin(theta), np.cos(theta)]])
        p[ids, :2] = base[:, :2] @ rot.T
        p[ids, 2] = base[:, 2]
        dest = base.copy()
        dest[:, 0] = cfg.area * .44 - slots[:, 0]
        if spec.geometry in ("merge", "corridor"):
            dest[:, 1] *= .15
        if spec.geometry == "vertical":
            dest[:, 2] = cfg.altitude_floor + cfg.altitude_ceiling - slots[:, 2]
        g[ids, :2] = dest[:, :2] @ rot.T
        g[ids, 2] = dest[:, 2]
    # Small bounded perturbations avoid exact symmetric degeneracy.
    p += rng.uniform(-.4, .4, p.shape)
    g += rng.uniform(-.4, .4, g.shape)
    # Resolve near-overlapping adjacent entry streams before the experiment.
    # Overload compression is applied afterwards and is reported separately.
    for _ in range(150):
        r = p[:, None, :] - p[None, :, :]
        dist = np.linalg.norm(r, axis=2)
        np.fill_diagonal(dist, np.inf)
        close = np.maximum(0., cfg.separation + 1 - dist)
        if not np.any(close > .001):
            break
        p += .3 * np.sum(r / np.maximum(dist[..., None], 1e-8) * close[..., None], axis=1)
    if spec.fault == "overload":
        p[:, :2] *= .65
        g[:, :2] *= .65
    fixed = np.zeros(n, bool)
    fixed[rng.permutation(n)[:round(n * cfg.fixed_wing_fraction)]] = True
    cooperative = np.zeros(n, bool)
    cooperative[rng.permutation(n)[:round(n * cfg.cooperative_fraction)]] = True
    direction = g - p
    direction /= np.maximum(np.linalg.norm(direction, axis=1)[:, None], 1e-9)
    speeds = np.full(n, cfg.cruise_speed)
    if spec.geometry == "overtaking":
        speeds[::2] = cfg.fixed_wing_min_speed
    v = direction * speeds[:, None]
    # Respect initial fixed-wing climb limit.
    v[fixed, 2] = np.clip(v[fixed, 2], -cfg.fixed_wing_climb_limit, cfg.fixed_wing_climb_limit)
    horizontal = np.linalg.norm(v[fixed, :2], axis=1)
    v[fixed, :2] *= (np.maximum(horizontal, cfg.fixed_wing_min_speed) /
                     np.maximum(horizontal, 1e-9))[:, None]
    obstacles = []
    if spec.fault in ("buildings", "blocked", "occlusion"):
        obstacles = [(-22., -22., 30., 18.), (24., 25., 38., 21.)]
        if spec.fault == "blocked":
            obstacles += [(0., 0., 72., 22.)]
    return {"position": p, "goals": g, "velocity": v, "fixed": fixed,
            "cooperative": cooperative, "cruise": speeds,
            "radius": np.where(fixed, 2.5, 1.2),
            "obstacles": np.array(obstacles, float).reshape(-1, 4), "scenario": spec}
