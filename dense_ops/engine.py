"""Asynchronous mixed-fleet research with per-ownship information boundaries."""
from dataclasses import asdict, dataclass, field, replace
from time import perf_counter
import numpy as np
from swarm_sim.config import Config
from swarm_sim.scenarios import build_world, SCENARIOS
from swarm_sim.controllers import preferred_velocity, vehicle_project
from swarm_sim.oracle import swept_pairs, swept_obstacles, outside_volume
from .audit import Journal
from .network import Links, Surveillance, Bus
from .safety import Plan, candidates, recovery, validate, resume
from .federation import Reservations, compatible
from .learning import features, graph


@dataclass(frozen=True)
class Experiment:
    drones: int = 10
    scenario: str = 'crossing'
    mode: str = 'local'
    seed: int = 8100
    duration: float = 12.
    dt: float = .2
    area: float = 600.
    cooperative_fraction: float = .5
    fixed_wing_fraction: float = .4
    manned: int = 1
    horizon: float = 4.
    disturbance: float = .4
    deadline_ms: float = 200.
    sensor_range: float = 600.
    warmup: float = 1.
    max_surveillance_age: float = 1.
    entry_limit: int = 200
    guard: str = 'continuation'
    fault: str = 'none'
    links: Links = field(default_factory=Links)

    def validate(self):
        if type(self.drones) is not int or not 2 <= self.drones <= 500 or type(self.manned) is not int or not 0 <= self.manned <= 10:
            raise ValueError('Invalid fleet size')
        if self.mode not in ('local', 'federated', 'graph', 'federated_graph') or self.guard not in ('reference', 'continuation'):
            raise ValueError('Unknown architecture/guard')
        if self.scenario not in SCENARIOS or self.fault not in ('none', 'outage', 'deadline', 'wind', 'compound'):
            raise ValueError('Unknown scenario/fault')
        numbers = (self.duration, self.dt, self.area, self.cooperative_fraction, self.fixed_wing_fraction,
                   self.horizon, self.disturbance, self.deadline_ms, self.sensor_range, self.warmup, self.max_surveillance_age)
        if not np.isfinite(numbers).all() or not 0 <= self.cooperative_fraction <= 1 or not 0 <= self.fixed_wing_fraction <= 1:
            raise ValueError('Invalid numeric condition')
        if (not .02 <= self.dt <= .5 or not self.dt <= self.horizon <= 12 or not 1 <= self.duration <= 180 or
                self.area <= 100 or not 0 <= self.disturbance <= .8 or not 0 < self.deadline_ms <= self.dt*1000 or
                self.sensor_range <= 0 or not self.dt <= self.max_surveillance_age <= self.horizon or
                not 0 <= self.warmup < self.duration or type(self.seed) is not int or self.seed < 0 or
                type(self.entry_limit) is not int or not 1 <= self.entry_limit <= 500):
            raise ValueError('Condition outside research domain')
        self.links.validate()
        return self


def from_document(document):
    return Experiment(**{**document, 'links': Links(**document.get('links', {}))}).validate()


def decode_plan(doc):
    return Plan(**{k: np.array(v) if k in ('p', 'v', 'a', 'ep', 'ev', 'slab', 'center') and v is not None else v
                   for k, v in doc.items()})


def simulate(exp, policy=None, samples=None, record=False):
    exp.validate()
    if 'graph' in exp.mode and policy is None:
        raise ValueError('Graph modes require an explicitly trained checkpoint')
    if policy is not None and exp.seed in policy.training_seeds:
        raise ValueError('Training/evaluation environment seed overlap')
    cfg = Config(drones=exp.drones, scenario=exp.scenario, seed=exp.seed, duration=exp.duration,
                 dt=exp.dt, area=exp.area, cooperative_fraction=exp.cooperative_fraction,
                 fixed_wing_fraction=exp.fixed_wing_fraction, controller='goal')
    world = build_world(cfg)
    modeled_fault = world['scenario'].fault
    faults = set(modeled_fault.split('+'))
    p, v = world['position'].copy(), world['velocity'].copy()
    # Manned traffic starts outside the protected volume and is observed on approach.
    if exp.manned:
        mp = np.array([[-exp.area/2-100.-30*k, 0., 90.] for k in range(exp.manned)])
        mv = np.tile([35., 0., 0.], (exp.manned, 1))
        p = np.vstack((p, mp)); v = np.vstack((v, mv))
        for key, extra in [('goals', np.column_stack((np.full(exp.manned, exp.area/2), np.zeros(exp.manned), np.full(exp.manned, 90.)))),
                           ('cruise', np.full(exp.manned, 35.)), ('radius', np.full(exp.manned, 6.)),
                           ('fixed', np.ones(exp.manned, bool)), ('cooperative', np.zeros(exp.manned, bool))]:
            world[key] = np.concatenate((world[key], extra))
    n = len(p)
    manned = np.arange(n) >= exp.drones
    cooperative = world['cooperative']
    fixed = world['fixed']
    active = ~cooperative & ~manned
    pending = cooperative.copy()
    completed = np.zeros(n, bool)
    entry_v = v.copy()
    v[pending] = 0.
    sensor_links = replace(exp.links, loss=.45 if 'loss' in faults else exp.links.loss,
                           latency=2. if 'delay' in faults else exp.links.latency)
    sensors = Surveillance(n, exp.seed+991, sensor_links, error=cfg.position_error_bound,
                           velocity_error=cfg.velocity_error_bound, sensor_range=exp.sensor_range)
    sensors.faults = faults
    federation = Bus(exp.seed+992, replace(exp.links, asymmetric=exp.links.asymmetric or 'partial' in faults))
    journal = Journal([*map(str, range(n)), 'broker-0', 'broker-1'])
    books = [Reservations() for _ in range(2)]
    retained = [None]*n
    known_plans = {}
    metrics = dict(collision_pairs=0, protected_breach_pairs=0, obstacle_pairs=0, volume_exits=0,
                   no_safe_continuation_steps=0, retained_recovery_activations=0, unavailable_deadline_recoveries=0,
                   command_deadline_misses=0, unknown_traffic_aircraft_steps=0, stale_traffic_aircraft_steps=0,
                   noninvariant_fixed_wing_steps=0, reservation_rejections=0, joint_entry_rejections=0,
                   admission_surveillance_rejections=0,
                   peak_occupancy=0, cooperative_admitted=0, cooperative_completed=0,
                   static_terminal_steps=0, kinematic_violation_steps=0, operator_burden=[0., 0., 0.])
    metrics['learned_proposal_rejections'] = 0
    collisions, breaches, obstacles, exits = set(), set(), set(), set()
    times, frames, admission_times = [], [], []
    previous_applied = np.zeros_like(p)
    journal.append('broker-0', 0., 'START', {'experiment': asdict(exp), 'assurance': 'finite numerical research'})
    for step in range(round(exp.duration/exp.dt)):
        now = step*exp.dt
        approaching = manned & ~completed & (p[:, 0] < -exp.area/2)
        enter = approaching & (p[:, 0]+v[:, 0]*exp.dt >= -exp.area/2)
        active[enter] = True
        sensing_outage = exp.fault in ('outage', 'compound') and 3 <= now <= 6
        sensing_outage |= 'outage' in modeled_fault and 3 <= now <= 6
        sensors.bus.links = replace(sensor_links, latency=sensor_links.latency+(1. if 'handoff' in faults and 3 <= now <= 6 else 0.))
        sensors.step(now, p, v, active | approaching, np.flatnonzero(cooperative), sensing_outage)
        for broker, signed in federation.receive(now):
            payload = Journal.authenticate(signed, journal.public)
            plan = decode_plan(payload['plan'])
            if plan.digest() != payload['digest'] or plan.start+len(plan.a)*plan.dt <= now:
                continue
            books[int(broker)].accept(int(payload['own']), plan, cfg.separation, now)
            journal.append('broker-'+str(broker), now, 'RECEIVE_INTENT', {'actor': signed['actor'], 'digest': plan.digest()})
        applied = np.zeros_like(p)
        preexisting_recoveries = list(retained)
        tactical_start = perf_counter()
        for own in np.flatnonzero(cooperative & (active | pending)):
            if pending[own] and (now < exp.warmup or np.sum(active) >= exp.entry_limit):
                continue
            if pending[own] and not sensors.ready(own, now, exp.max_surveillance_age):
                metrics['admission_surveillance_rejections'] += 1
                source = sensors.frame_source[own]
                journal.append(own, now, 'DEFER_ENTRY', {'reason': 'surveillance-not-ready',
                    'last_frame_source': float(source) if np.isfinite(source) else None,
                    'maximum_age': exp.max_surveillance_age})
                continue
            snapshot = sensors.snapshot(own, now, cfg.advertised_acceleration_bound)
            seen = sensors.seen[own]
            neighbors = np.flatnonzero(seen & (np.arange(n) != own))
            # Forecasts of approaching manned aircraft are included, before entry.
            required = np.where(manned, 60., cfg.separation)
            vel = entry_v[own] if pending[own] else v[own]
            if exp.guard == 'reference' and active[own]:
                # Same local observations and same entry gate; finite-library reference.
                from swarm_sim.predictive import predictive_control
                local_active = seen.copy(); local_active[own] = True
                local_world = {**world, 'cooperative': np.arange(n) == own}
                desired = np.zeros_like(p)
                target = preferred_velocity(p, world['goals'], world['cruise'], fixed, cfg)
                desired[own] = vehicle_project(((target[own]-vel)/.6)[None], vel[None], fixed[own:own+1], cfg)[0]
                command, stats = predictive_control(cfg, local_world, p, v, local_active, snapshot, desired)
                applied[own] = command[own]
                metrics['no_safe_continuation_steps'] += int(stats['unresolved'][own])
                continue
            pool = candidates(cfg, p[own], vel, bool(fixed[own]), world['goals'][own], now, exp.horizon, exp.disturbance)
            acceptable, clearances, candidate_ids = [], [], []
            for k, plan in enumerate(pool):
                okay, reason, clearance = validate(plan, cfg, world['radius'][own], snapshot, neighbors,
                                                    world['radius'], required, now, world['obstacles'])
                if okay and 'federated' in exp.mode:
                    for other, reservation in books[own % 2].plans.items():
                        if other != own and not compatible(plan, reservation, cfg.separation):
                            okay = False
                            metrics['reservation_rejections'] += 1
                            break
                if okay:
                    acceptable.append(plan); clearances.append(clearance); candidate_ids.append(k)
            chosen = None
            if acceptable:
                data = features(acceptable, world['goals'][own], clearances, bool(fixed[own]))
                costs = data[:, 0]+.03*data[:, 1]
                label = int(np.argmin(costs))
                nodes = graph(snapshot, own, p[own], vel, seen, fixed, cooperative)
                if samples is not None and len(acceptable) > 1:
                    samples.append({'features': data.tolist(), 'graph': nodes.tolist(), 'label': label,
                                    'operator': int(own % 3), 'seed': exp.seed})
                try:
                    index = policy.choose(data, nodes) if policy else label
                except (ValueError, RuntimeError, FloatingPointError):
                    # A failed preference model cannot bypass the checked pool.
                    metrics['learned_proposal_rejections'] += 1
                    index = label
                if type(index) is not int or not 0 <= index < len(acceptable):
                    metrics['learned_proposal_rejections'] += 1
                    index = label
                chosen = acceptable[index]
            if chosen is None:
                if not pending[own]:
                    old = resume(retained[own], p[own], vel, now)
                    okay, _, _ = validate(old, cfg, world['radius'][own], snapshot, neighbors, world['radius'], required, now, world['obstacles'])
                    if okay:
                        chosen = old
                        metrics['retained_recovery_activations'] += 1
                    else:
                        metrics['no_safe_continuation_steps'] += 1
                        journal.append(own, now, 'LOSS_OF_GUARANTEE', {'reason': 'no-checked-continuation'})
                if chosen is None:
                    continue  # explicit emergency zero command; counted, never called safe
            if pending[own]:
                # Preserve every known protected continuation, not just entrant separation.
                if not books[own % 2].accept(own, chosen, cfg.separation, now):
                    metrics['joint_entry_rejections'] += 1
                    continue
                pending[own] = False; active[own] = True; v[own] = vel
                metrics['cooperative_admitted'] += 1; admission_times.append(now)
                journal.append(own, now, 'ADMIT', {'plan': chosen.digest()})
            simulate_miss = (exp.fault in ('deadline', 'compound') or 'overrun' in faults) and step % 7 == 0
            if simulate_miss:
                old = resume(retained[own], p[own], vel, now)
                okay, _, _ = validate(old, cfg, world['radius'][own], snapshot, neighbors, world['radius'], required, now, world['obstacles'])
                metrics['command_deadline_misses'] += 1
                if okay:
                    chosen = old; metrics['retained_recovery_activations'] += 1
                else:
                    metrics['unavailable_deadline_recoveries'] += 1
                    journal.append(own, now, 'LOSS_OF_GUARANTEE', {'reason': 'expired-watchdog-recovery'})
                    continue
            applied[own] = chosen.command(p[own], v[own])
            retained[own] = chosen
            books[own % 2].plans[int(own)] = chosen
            metrics['static_terminal_steps'] += int(chosen.static_terminal)
            metrics['noninvariant_fixed_wing_steps'] += int(fixed[own])
            baseline = preferred_velocity(p[own:own+1], world['goals'][own:own+1], world['cruise'][own:own+1], fixed[own:own+1], cfg)[0]
            metrics['operator_burden'][own % 3] += float(np.linalg.norm(applied[own]-(baseline-v[own])/.6)*exp.dt)
            journal.append(own, now, 'AUTHORIZE', {'plan': chosen.digest(), 'control': applied[own].tolist(),
                                                 'seen': neighbors.tolist(), 'static_terminal': chosen.static_terminal})
            known_plans[chosen.digest()] = chosen.document()
            if 'federated' in exp.mode and step % max(1, round(1/exp.dt)) == 0:
                signed = journal.sign(own, {'type': 'INTENT', 'own': int(own), 'digest': chosen.digest(), 'plan': chosen.document()})
                federation.send(int(own % 2), int(1-own % 2), now, signed)
        command_ms = (perf_counter()-tactical_start)*1000
        times.append(command_ms)
        if command_ms > exp.deadline_ms:
            metrics['command_deadline_misses'] += 1
            # This measurement is fleet host timing, not an isolated onboard WCET.
            # Independently revalidate pre-existing recoveries for a missed fleet tick.
            for own in np.flatnonzero(active & cooperative):
                previous = preexisting_recoveries[own]
                snapshot = sensors.snapshot(own, now, cfg.advertised_acceleration_bound)
                neighbors = np.flatnonzero(sensors.seen[own] & (np.arange(n) != own))
                old = resume(previous, p[own], v[own], now)
                okay, _, _ = validate(old, cfg, world['radius'][own], snapshot, neighbors, world['radius'], np.where(manned, 60., 10.), now, world['obstacles'])
                if okay:
                    applied[own] = old.command(p[own], v[own]); metrics['retained_recovery_activations'] += 1
                    retained[own] = old
                else:
                    applied[own] = 0.; metrics['unavailable_deadline_recoveries'] += 1
                journal.append(own, now, 'WATCHDOG', {'checked_recovery': bool(okay), 'control': applied[own].tolist()})
        goal_v = preferred_velocity(p, world['goals'], world['cruise'], fixed, cfg)
        legacy = active & ~cooperative & ~manned
        applied[legacy] = vehicle_project(((goal_v[legacy]-v[legacy])/.6), v[legacy], fixed[legacy], cfg)
        applied[manned] = 0.
        if 'stop' in faults and 3 <= now <= 6:
            stopped = legacy & ~fixed
            applied[stopped] = vehicle_project(-v[stopped], v[stopped], fixed[stopped], cfg)
        if 'intruder' in faults and 3 <= now <= 5:
            applied[legacy, 1] += 9.
        if 'turn' in modeled_fault and 3 <= now <= 5:
            applied[legacy, 1] += 1.
            applied[legacy] = vehicle_project(applied[legacy], v[legacy], fixed[legacy], cfg)
        if 'lag' in faults:
            applied[~manned] = .6*previous_applied[~manned]+.4*applied[~manned]
        previous_applied = applied.copy()
        actual = applied.copy()
        if exp.fault in ('wind', 'compound') or 'wind' in modeled_fault:
            actual[active, 1] += exp.disturbance*np.sin(now)
        for own in np.flatnonzero(active & cooperative):
            relevant = active | approaching
            relevant[own] = False
            metrics['unknown_traffic_aircraft_steps'] += int(np.sum(relevant & ~sensors.seen[own]))
            snapshot = sensors.snapshot(own, now, cfg.advertised_acceleration_bound)
            metrics['stale_traffic_aircraft_steps'] += int(np.sum(relevant & sensors.seen[own] & (snapshot[-1] > exp.max_surveillance_age)))
        i, j, distance, _ = swept_pairs(p, v, actual, active, world['radius'], 60., exp.dt)
        for a, b, d in zip(i, j, distance):
            if d < world['radius'][a]+world['radius'][b]: collisions.add((int(a), int(b)))
            if d < (60. if manned[a] or manned[b] else cfg.separation): breaches.add((int(a), int(b)))
        obstacles.update(swept_obstacles(p, v, actual, active, world['radius'], world['obstacles'], exp.dt))
        # Manned aircraft traverse the boundary; it is not a UAS containment violation.
        exits.update(map(int, np.flatnonzero(outside_volume(p, v, actual, cfg, exp.dt) & active & ~manned)))
        # Applied commands and state are logged AFTER every override.
        for own in np.flatnonzero(active & cooperative):
            journal.append(own, now, 'APPLY', {'position': p[own].tolist(), 'velocity': v[own].tolist(),
                                             'control': applied[own].tolist(),
                                             'plan': retained[own].digest() if retained[own] else None})
        before_v = v.copy()
        moving = active | approaching
        p[moving] += v[moving]*exp.dt+.5*actual[moving]*exp.dt**2
        v[moving] += actual[moving]*exp.dt
        uas = active & ~manned
        violation = uas & ((np.linalg.norm(v, axis=1) > cfg.max_speed+1e-8) |
                           (np.linalg.norm(applied, axis=1) > cfg.acceleration_limit+1e-8))
        fw = uas & fixed
        angle = np.abs((np.arctan2(v[:, 1], v[:, 0])-np.arctan2(before_v[:, 1], before_v[:, 0])+np.pi)%(2*np.pi)-np.pi)
        violation |= fw & ((np.linalg.norm(v[:, :2], axis=1) < cfg.fixed_wing_min_speed-1e-8) |
                           (np.abs(v[:, 2]) > cfg.fixed_wing_climb_limit+1e-8) |
                           (angle > np.deg2rad(cfg.fixed_wing_turn_rate_deg)*exp.dt+1e-8))
        metrics['kinematic_violation_steps'] += int(np.sum(violation))
        reached = active & (np.linalg.norm(p-world['goals'], axis=1) < cfg.goal_radius)
        reached |= active & manned & (p[:, 0] >= exp.area/2)
        completed |= reached; active[reached] = False
        metrics['peak_occupancy'] = max(metrics['peak_occupancy'], int(np.sum(active)))
        if record and step % 2 == 0:
            frames.append(dict(time=now+exp.dt, positions=p.tolist(), active=active.astype(int).tolist()))
    metrics.update(collision_pairs=len(collisions), protected_breach_pairs=len(breaches), obstacle_pairs=len(obstacles),
                   volume_exits=len(exits), cooperative_completed=int(np.sum(completed & cooperative)),
                   cooperative_requested=int(np.sum(cooperative)), queued=int(np.sum(pending)),
                   manned_completed=int(np.sum(completed & manned)), total_completed=int(np.sum(completed)),
                   uas_completion_fraction=float(np.sum(completed & ~manned)/exp.drones),
                   completion_fraction=float(np.sum(completed & cooperative)/max(1, np.sum(cooperative))),
                   max_entry_wait_s=max(admission_times, default=None), command_max_ms=max(times, default=0.),
                   command_p99_ms=float(np.percentile(times, 99)) if times else 0., messages_dropped=federation.dropped,
                   surveillance_messages_dropped=sensors.bus.dropped,
                   offered_aircraft=exp.drones+exp.manned, aircraft_per_km3=(exp.drones+exp.manned)/(exp.area**2*104/1e9))
    blockers = [k for k in ('collision_pairs', 'protected_breach_pairs', 'obstacle_pairs', 'volume_exits',
                           'no_safe_continuation_steps', 'unavailable_deadline_recoveries', 'command_deadline_misses',
                           'unknown_traffic_aircraft_steps', 'stale_traffic_aircraft_steps', 'kinematic_violation_steps') if metrics[k]]
    if world['scenario'].domain == 'out_of_bounds':
        blockers.append('outside_declared_assurance_domain')
    if metrics['completion_fraction'] < .95: blockers.append('completion_requirement')
    if metrics['uas_completion_fraction'] < .95: blockers.append('all_uas_completion_requirement')
    if exp.manned and metrics['manned_completed']/exp.manned < .95: blockers.append('manned_completion_requirement')
    if not metrics['cooperative_requested']: blockers.append('no_controlled_service')
    journal.append('broker-0', exp.duration, 'END', {'metrics': metrics, 'blockers': blockers})
    result = dict(experiment=asdict(exp), metrics=metrics, observed_requirements_pass=not blockers, blockers=blockers,
                  operational_capacity=None, audit=dict(events=journal.events, public=journal.public, anchor=journal.anchor()),
                  limits=['Finite renewable traffic horizon; no joint invariant safety proof.',
                          'Fixed-wing turns are not robust loiter certificates.',
                          'Synthetic RF, known vehicle metadata, idealized local own-state and pre-entry demand.',
                          'No wake, landing, impact physics, ATC/pilot model or target-hardware WCET.',
                          'Intent exchange uses asynchronous broker replicas; multi-party certificate protocol is tested separately.'])
    if record:
        result['replay'] = frames
        result['plans'] = known_plans
    return result
