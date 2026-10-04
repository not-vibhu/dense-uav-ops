"""Continuous numerical runtime assurance for a stated sampled point-mass plant.

Multirotor recovery uses a closed-loop error tube and a static invariant terminal
ellipsoid. Traffic exclusion is renewable finite horizon, never infinite safety.
Fixed-wing recovery is a finite turn; a nominal loiter is not a robust invariant.
"""
from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
import numpy as np
from swarm_sim.controllers import vehicle_project
from swarm_sim.oracle import quadratic_minimum


@lru_cache(maxsize=32)
def feedback_tables(dt, steps):
    F = np.array([[1-.5*dt**2, dt-.75*dt**2], [-dt, 1-1.5*dt]])
    G = np.array([.5*dt**2, dt])
    powers = np.array([np.linalg.matrix_power(F, j) for j in range(steps+1)])
    impulse = powers@G
    summed = np.vstack((np.zeros(2), np.cumsum(np.abs(impulse[:-1]), axis=0)))
    control = np.r_[0., np.cumsum(np.abs(impulse[:-1]@np.array([1., 1.5])))]
    return powers, summed, control


@dataclass
class Plan:
    start: float
    dt: float
    p: np.ndarray
    v: np.ndarray
    a: np.ndarray
    ep: np.ndarray
    ev: np.ndarray
    slab: np.ndarray
    kind: str
    center: np.ndarray | None = None
    feedback_from: int = 0
    static_terminal: bool = False
    disturbance: float = .4
    terminal_radius: float = 0.

    def document(self):
        return {k: v.tolist() if isinstance(v, np.ndarray) else v for k, v in vars(self).items()}

    def digest(self):
        return hashlib.sha256(json.dumps(self.document(), sort_keys=True, allow_nan=False).encode()).hexdigest()

    def command(self, p, v, index=0):
        if self.center is not None and index >= self.feedback_from:
            return -(p-self.center)-1.5*v
        return self.a[index].copy()


def recovery(cfg, p, v, fixed, now, horizon=8., disturbance=.8, own_error=.1, prefix=None):
    steps = int(np.ceil(horizon/cfg.dt))
    q, vel = np.array(p, float), np.array(v, float)
    pp, vv, aa = [q.copy()], [vel.copy()], []
    ep, ev, slabs = [own_error], [0.], []
    P = np.array([[17/12, .5], [.5, 2/3]])
    inv = np.linalg.inv(P)
    L = np.linalg.cholesky(P).T
    F = np.array([[1-.5*cfg.dt**2, cfg.dt-.75*cfg.dt**2], [-cfg.dt, 1-1.5*cfg.dt]])
    G = np.array([.5*cfg.dt**2, cfg.dt])
    contraction = np.linalg.norm(L@F@np.linalg.inv(L), 2) + 1e-10
    noise = disturbance*np.sqrt(G@P@G)
    gain = np.sqrt(np.array([1., 1.5])@inv@np.array([1., 1.5]))
    alpha = own_error*np.sqrt(P[0, 0])
    feedback_initial = np.array([own_error, 0.])
    feedback_steps = 0
    powers, summed, control = feedback_tables(cfg.dt, steps)
    center = None if fixed else q+1.5*vel
    feedback_from = int(prefix is not None)
    valid_inputs = True
    for s in range(steps):
        if s == 0 and prefix is not None:
            a = np.array(prefix, float)
            slabs.append(ep[-1]+ev[-1]*cfg.dt+.5*disturbance*cfg.dt**2)
            next_ep = ep[-1]+ev[-1]*cfg.dt+.5*disturbance*cfg.dt**2
            next_ev = ev[-1]+disturbance*cfg.dt
            alpha = np.sqrt(P[0, 0])*next_ep+np.sqrt(P[1, 1])*next_ev
            feedback_initial = np.array([next_ep, next_ev])
        elif fixed:
            speed = np.linalg.norm(vel[:2])
            theta = min(np.deg2rad(cfg.fixed_wing_turn_rate_deg), cfg.acceleration_limit/max(speed, 1e-9)*.8)*cfg.dt
            target = np.array([vel[0]*np.cos(theta)-vel[1]*np.sin(theta),
                               vel[0]*np.sin(theta)+vel[1]*np.cos(theta), 0.])
            a = vehicle_project(((target-vel)/cfg.dt)[None], vel[None], np.array([True]), cfg)[0]
            t = (s+1)*cfg.dt
            next_ep, next_ev = own_error+.5*disturbance*t*t, disturbance*t
            slabs.append(next_ep)
        else:
            a = -(q-center)-1.5*vel
            # This certificate is valid only while the feedback is unsaturated.
            # Support-function sums preserve the correlation created by feedback.
            # Each disturbance is an independent bounded 3D acceleration vector.
            A = powers[feedback_steps]
            K = np.array([1., 1.5])
            error_control = float(np.abs(K@A)@feedback_initial)
            error_control += disturbance*control[feedback_steps]
            valid_inputs &= np.linalg.norm(a)+error_control <= cfg.acceleration_limit+1e-9
            slabs.append(ep[-1]+ev[-1]*cfg.dt+
                         .5*(error_control+disturbance)*cfg.dt**2)
            feedback_steps += 1
            A = powers[feedback_steps]
            bounds = np.abs(A)@feedback_initial
            bounds += disturbance*summed[feedback_steps]
            next_ep, next_ev = bounds
            alpha = np.sqrt(P[0, 0])*next_ep+np.sqrt(P[1, 1])*next_ev
        q = q+vel*cfg.dt+.5*a*cfg.dt**2
        vel = vel+a*cfg.dt
        valid_inputs &= np.linalg.norm(a) <= cfg.acceleration_limit+1e-9
        valid_inputs &= np.linalg.norm(vel)+next_ev <= cfg.max_speed+1e-9
        aa.append(a); pp.append(q.copy()); vv.append(vel.copy()); ep.append(next_ep); ev.append(next_ev)
    terminal = False
    radius = 0.
    if not fixed and contraction < 1:
        # Largest terminal ellipsoid satisfying input and speed bounds.
        radius = min(cfg.acceleration_limit/gain, cfg.max_speed/np.sqrt(inv[1, 1]))*.99
        phase = np.stack((q-center, vel))
        norm = np.sqrt(np.einsum('ac,ab,bc->', phase, P, phase))
        terminal = bool(contraction*radius+noise <= radius and norm+alpha <= radius and valid_inputs)
        guard = radius*np.sqrt(inv[0, 0])+radius*np.sqrt(inv[1, 1])*cfg.dt+.5*(gain*radius+disturbance)*cfg.dt**2
        lo = np.array([-cfg.area/2, -cfg.area/2, cfg.altitude_floor])
        hi = np.array([cfg.area/2, cfg.area/2, cfg.altitude_ceiling])
        terminal &= bool(np.all(center-guard >= lo) and np.all(center+guard <= hi))
    plan = Plan(now, cfg.dt, np.array(pp), np.array(vv), np.array(aa), np.array(ep), np.array(ev),
                np.array(slabs), 'finite-fixed-wing-turn' if fixed else 'closed-loop-hover', center,
                feedback_from, terminal, disturbance, radius)
    return plan if valid_inputs else None


def candidates(cfg, p, v, fixed, goal, now, horizon, disturbance):
    direction = goal-p
    norm = np.linalg.norm(direction)
    target = direction/max(norm, 1e-9)*min(cfg.cruise_speed, np.sqrt(2*cfg.acceleration_limit*norm))
    options = [None]
    for angle in (0., -np.pi/3, np.pi/3, np.pi):
        for scale in (1., .5):
            vv = target.copy()
            vv[:2] = scale*np.array([target[0]*np.cos(angle)-target[1]*np.sin(angle),
                                     target[0]*np.sin(angle)+target[1]*np.cos(angle)])
            options.append(vehicle_project(((vv-v)/.6)[None], v[None], np.array([fixed]), cfg)[0])
    return [recovery(cfg, p, v, fixed, now, horizon, disturbance, prefix=a) for a in options]


def validate(plan, cfg, radius, snapshot, neighbors, radii, required, now, obstacles=()):
    """Independent polynomial-extrema checker; no planner feasible flags trusted."""
    if plan is None:
        return False, 'input-envelope', -np.inf
    arrays = (plan.p, plan.v, plan.a, plan.ep, plan.ev, plan.slab)
    h = len(plan.a)
    if (h < 1 or plan.p.shape != (h+1, 3) or plan.v.shape != plan.p.shape or plan.a.shape != (h, 3) or
            any(x.shape != (h+1,) for x in (plan.ep, plan.ev)) or plan.slab.shape != (h,) or
            not all(np.isfinite(x).all() for x in arrays) or not np.isfinite([plan.start,plan.dt,now,plan.terminal_radius]).all() or
            any(np.any(x < 0) for x in (plan.ep, plan.ev, plan.slab)) or
            type(plan.feedback_from) is not int or not 0 <= plan.feedback_from <= h or
            plan.kind not in ('closed-loop-hover', 'finite-fixed-wing-turn') or
            (plan.center is not None and (plan.center.shape != (3,) or not np.isfinite(plan.center).all())) or
            (plan.kind == 'closed-loop-hover' and plan.center is None) or
            (plan.kind == 'finite-fixed-wing-turn' and (plan.center is not None or plan.static_terminal)) or
            abs(plan.dt-cfg.dt) > 1e-10 or plan.start > now+1e-9):
        return False, 'malformed-plan', -np.inf
    offset = now-plan.start
    pred, obs_v, error, error_v, age = snapshot
    neighbors = np.asarray(neighbors, int)
    if len(neighbors) and (not all(np.isfinite(x[neighbors]).all() for x in snapshot) or
                           np.any(error[neighbors] < 0) or np.any(error_v[neighbors] < 0) or np.any(age[neighbors] < 0)):
        return False, 'invalid-surveillance', -np.inf
    minimum = np.inf
    lo = np.array([-cfg.area/2, -cfg.area/2, cfg.altitude_floor])
    hi = np.array([cfg.area/2, cfg.area/2, cfg.altitude_ceiling])
    if not np.isfinite(plan.disturbance) or not 0 <= plan.disturbance <= .8:
        return False, 'unsupported-disturbance', -np.inf
    if plan.static_terminal:
        P = np.array([[17/12, .5], [.5, 2/3]])
        inv = np.linalg.inv(P); K = np.array([1., 1.5])
        F = np.array([[1-.5*cfg.dt**2, cfg.dt-.75*cfg.dt**2], [-cfg.dt, 1-1.5*cfg.dt]])
        G = np.array([.5*cfg.dt**2, cfg.dt]); L = np.linalg.cholesky(P).T
        q = np.linalg.norm(L@F@np.linalg.inv(L), 2)+1e-10
        r = plan.terminal_radius
        gain = np.sqrt(K@inv@K)
        if plan.center is None or plan.center.shape != (3,) or not np.isfinite(plan.center).all() or r <= 0 or q*r+plan.disturbance*np.sqrt(G@P@G) > r or gain*r > cfg.acceleration_limit or r*np.sqrt(inv[1,1]) > cfg.max_speed:
            return False, 'invalid-terminal-set', -np.inf
        phase=np.stack((plan.p[-1]-plan.center,plan.v[-1]))
        norm=np.sqrt(np.einsum('ac,ab,bc->',phase,P,phase))
        terminal_error=np.sqrt(P[0,0])*plan.ep[-1]+np.sqrt(P[1,1])*plan.ev[-1]
        if norm+terminal_error > r+1e-9:
            return False, 'terminal-membership', -np.inf
        guard = radius+r*np.sqrt(inv[0, 0])+r*np.sqrt(inv[1, 1])*cfg.dt+.5*(gain*r+plan.disturbance)*cfg.dt**2
        if (np.any(plan.center-guard < lo) or np.any(plan.center+guard > hi) or
                any(np.linalg.norm(plan.center-np.array([x,y,z])) < guard+rr for x,y,z,rr in obstacles)):
            return False, 'terminal-environment', -np.inf
    for k, a in enumerate(plan.a):
        t0, t1 = k*plan.dt-offset, (k+1)*plan.dt-offset
        if t0 < -1e-9:
            return False, 'expired-prefix', -np.inf
        q, vel, end = plan.p[k], plan.v[k], plan.p[k+1]
        if plan.center is not None and k >= plan.feedback_from and not np.allclose(a,-(q-plan.center)-1.5*vel,atol=1e-8,rtol=0):
            return False, 'feedback-mismatch', -np.inf
        if (not np.allclose(q+vel*plan.dt+.5*a*plan.dt**2, end, atol=1e-8, rtol=0) or
                not np.allclose(vel+a*plan.dt, plan.v[k+1], atol=1e-8, rtol=0) or
                np.linalg.norm(a) > cfg.acceleration_limit+1e-8):
            return False, 'discontinuous-plan', -np.inf
        if np.linalg.norm(plan.v[k+1])+plan.ev[k+1] > cfg.max_speed+1e-8:
            return False, 'speed-envelope', -np.inf
        if plan.kind == 'finite-fixed-wing-turn':
            heading=abs((np.arctan2(plan.v[k+1,1],plan.v[k+1,0])-np.arctan2(vel[1],vel[0])+np.pi)%(2*np.pi)-np.pi)
            if (np.linalg.norm(plan.v[k+1,:2])-plan.ev[k+1] < cfg.fixed_wing_min_speed-1e-8 or
                    abs(plan.v[k+1,2])+plan.ev[k+1] > cfg.fixed_wing_climb_limit+1e-8 or
                    heading > np.deg2rad(cfg.fixed_wing_turn_rate_deg)*cfg.dt+1e-8):
                return False, 'fixed-wing-envelope', -np.inf
        guard = radius+max(plan.ep[k], plan.ep[k+1], plan.slab[k])
        turning = np.clip(np.divide(-vel, a, out=np.zeros(3), where=np.abs(a)>1e-12), 0, plan.dt)
        extreme = q+vel*turning+.5*a*turning**2
        c = min(np.min(np.minimum(np.minimum(q, end), extreme)-lo),
                np.min(hi-np.maximum(np.maximum(q, end), extreme)))-guard
        minimum = min(minimum, c)
        if c < 0:
            return False, 'volume', minimum
        for x, y, z, r in obstacles:
            c = quadratic_minimum(q-np.array([x, y, z]), vel, a, plan.dt)-guard-r
            minimum = min(minimum, c)
            if c < 0:
                return False, 'obstacle', minimum
        if not len(neighbors):
            continue
        # Safe broad phase: a lower bound over the complete segment. No nearest-k truncation.
        js = neighbors
        r0 = q-pred[js]-obs_v[js]*t0
        rel = vel-obs_v[js]
        enclosure = error[js]+error_v[js]*t1+.5*cfg.advertised_acceleration_bound*t1*t1+.4*(age[js]+t1)**2
        threshold = np.maximum(required[js], radius+radii[js])+guard-radius+enclosure
        lower = np.linalg.norm(r0, axis=1)-np.linalg.norm(rel, axis=1)*plan.dt-.5*np.linalg.norm(a)*plan.dt**2
        nearby = lower <= threshold
        for j, r, rv, bound in zip(js[nearby], r0[nearby], rel[nearby], threshold[nearby]):
            c = quadratic_minimum(r, rv, a, plan.dt)-bound
            minimum = min(minimum, c)
            if c < 0:
                return False, 'traffic', minimum
    # Terminal static traffic clearance is intentionally NOT claimed.
    return True, 'checked-finite-continuation', minimum


def resume(plan, p, v, now):
    """Retained recovery must enclose current state and still have a future slab."""
    if plan is None:
        return None
    index = int(round((now-plan.start)/plan.dt))
    if index < 0 or index >= len(plan.a) or abs(now-plan.start-index*plan.dt) > 1e-8:
        return None
    if np.linalg.norm(p-plan.p[index]) > plan.ep[index]+1e-8 or np.linalg.norm(v-plan.v[index]) > plan.ev[index]+1e-8:
        return None
    return Plan(now, plan.dt, plan.p[index:].copy(), plan.v[index:].copy(), plan.a[index:].copy(),
                plan.ep[index:].copy(), plan.ev[index:].copy(), plan.slab[index:].copy(), plan.kind,
                plan.center, max(0, plan.feedback_from-index), plan.static_terminal, plan.disturbance, plan.terminal_radius)
