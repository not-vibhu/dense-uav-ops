"""Independent finite-path checker plus limited sampled hover certificate.

Hover invariance concerns the stated point-mass plant and static environment.
Traffic exclusion is finite horizon. No fixed-wing invariant set is claimed.
"""
import numpy as np
from .controllers import vehicle_project,unit
from .predictive import segment_distance,volume_clearance,traffic_enclosure


def hover_certificate(cfg, disturbance=.8):
    P=np.array([[17/12,.5],[.5,2/3]])
    F=np.array([[1-.5*cfg.dt**2,cfg.dt-.75*cfg.dt**2],[-cfg.dt,1-1.5*cfg.dt]])
    G=np.array([.5*cfg.dt**2,cfg.dt])
    L=np.linalg.cholesky(P).T
    contraction=float(np.linalg.norm(L@F@np.linalg.inv(L),2))+1e-10
    if contraction >= 1: return {"valid":False,"reason":"not-contracting"}
    rho=float((disturbance*np.sqrt(G@P@G)/(1-contraction))**2*1.01)
    inv=np.linalg.inv(P); gain=np.array([1.,1.5])
    command=float(np.sqrt(rho*(gain@inv@gain)))
    speed=float(np.sqrt(rho*inv[1,1]))
    position=float(np.sqrt(rho*inv[0,0]))
    # Account for all intersample points using a reachable position envelope.
    swept=position+speed*cfg.dt+.5*(command+disturbance)*cfg.dt**2
    return {"valid":command <= cfg.acceleration_limit and speed <= cfg.max_speed,
            "kind":"sampled-multirotor-static-hover", "P":P.tolist(),"F":F.tolist(),
            "rho":rho,"contraction_upper":contraction,"command_bound":command,
            "speed_bound":speed,"position_bound":position,"swept_position_bound":swept,
            "disturbance_bound":disturbance,"scope":"static environment only; finite traffic exclusion"}


def verify_hover_certificate(certificate,cfg):
    # Reconstruct every bound from the model, rather than trusting a caller flag.
    expected=hover_certificate(cfg)
    if not expected.get("valid") or set(certificate)!=set(expected): return False
    for key,value in expected.items():
        other=certificate[key]
        if isinstance(value,(list,float)):
            if not np.allclose(value,other,rtol=0,atol=1e-9): return False
        elif value != other: return False
    return True


def check_backup(cfg,world,own_id,p,v,active,snapshot):
    pred,obs_v,error,error_v,age=snapshot
    q=p.copy(); vel=v.copy(); path=[]
    fixed=bool(world["fixed"][own_id]); radius=world["radius"][own_id]
    stop_time=np.linalg.norm(v)/cfg.acceleration_limit
    center=p+unit(v)*np.linalg.norm(v)**2/(2*cfg.acceleration_limit)
    hover=hover_certificate(cfg)
    # Finite replayable backup, never a promise of infinite traffic clearance.
    for step in range(int(np.ceil(cfg.predictive_horizon/cfg.dt))):
        t=(step+1)*cfg.dt
        if fixed:
            horizontal=np.linalg.norm(vel[:2])
            target=np.array([-vel[1],vel[0],0.])*1.5/max(horizontal,1e-9)
            target[2]=-vel[2]
        elif step*cfg.dt < stop_time:
            target=-unit(vel)*cfg.acceleration_limit
            if np.linalg.norm(vel) <= cfg.acceleration_limit*cfg.dt: target=-vel/cfg.dt
        else:
            target=-(q-center)-1.5*vel
        a=vehicle_project(target[None],vel[None],np.array([fixed]),cfg)[0]
        end=q+vel*cfg.dt+.5*a*cfg.dt**2
        own_error=.4*t*t
        if volume_clearance(q,vel,a,radius,cfg)-own_error < 0:
            return {"valid":False,"reason":"backup-volume"}
        curve=np.linalg.norm(a)*cfg.dt**2/8
        for x,y,z,r in world["obstacles"]:
            if segment_distance(q-[x,y,z],end-[x,y,z])-curve-own_error < r+radius:
                return {"valid":False,"reason":"backup-obstacle"}
        others=active.copy();others[own_id]=False
        lower=segment_distance(q-(pred+obs_v*(t-cfg.dt)),end-(pred+obs_v*t))-curve-own_error
        lower-=traffic_enclosure(error,error_v,age,t,cfg)
        required=np.maximum(cfg.separation,radius+world["radius"])
        if np.any(lower[others] < required[others]):
            return {"valid":False,"reason":"backup-traffic"}
        path.append({"position":q.tolist(),"velocity":vel.tolist(),"acceleration":a.tolist()})
        q=end;vel=vel+a*cfg.dt
    invariant=False
    if not fixed and hover.get("valid"):
        phase=np.stack((q-center,vel))
        nominal_norm=np.sqrt(float(np.einsum('ac,ab,bc->',phase,np.array(hover['P']),phase)))
        # The nominal endpoint alone is insufficient: enclose position AND
        # velocity disturbance at the terminal time before asserting membership.
        terminal_time=len(path)*cfg.dt
        envelope=np.array([.4*terminal_time**2,.8*terminal_time])
        error_norm=np.sqrt(float(envelope@np.abs(np.array(hover['P']))@envelope))
        in_set=nominal_norm+error_norm <= np.sqrt(hover['rho'])
        guard=radius+hover['swept_position_bound']
        floors=np.array([-cfg.area/2,-cfg.area/2,cfg.altitude_floor])
        ceilings=np.array([cfg.area/2,cfg.area/2,cfg.altitude_ceiling])
        static=np.all(center-guard>=floors)&np.all(center+guard<=ceilings)
        static &= all(np.linalg.norm(center-np.array([x,y,z])) >= r+guard for x,y,z,r in world['obstacles'])
        invariant=bool(in_set and static and verify_hover_certificate(hover,cfg))
    if cfg.require_invariant_backup and not invariant:
        return {"valid":False,"reason":"no-static-invariant-terminal"}
    certificate = {"valid":True,"kind":"fixed-wing-finite-turn" if fixed else "multirotor-brake-hover",
            "static_invariant_terminal":invariant,"traffic_horizon_s":len(path)*cfg.dt,
            "path":path,"hover":hover if invariant else None, "hover_center":center.tolist() if invariant else None,
            "reason":"checked-finite-horizon"}
    if not verify_backup_path(cfg,world,own_id,certificate,p,v,active,snapshot):
        return {"valid":False,"reason":"independent-check-failed"}
    return certificate


def first_backup_command(certificate):
    return np.array(certificate['path'][0]['acceleration'])


def verify_backup_path(cfg, world, own_id, certificate, p, v, active, snapshot):
    """Second numeric checker: cubic extrema, not the planner's chord bound.

    This verifies finite collision envelopes and nominal actuator constraints.
    It is not a machine-checked proof or a bound on disturbed fixed-wing stall.
    """
    from dataclasses import replace
    from .oracle import quadratic_minimum, outside_volume
    pred, observed_v, error, error_v, age = snapshot
    path=certificate.get('path',[])
    if len(path)!=int(np.ceil(cfg.predictive_horizon/cfg.dt)): return False
    q=np.array(p,float);vel=np.array(v,float)
    radius=world['radius'][own_id];fixed=world['fixed'][own_id]
    others=np.flatnonzero(active & (np.arange(len(active))!=own_id))
    for step,item in enumerate(path):
        if set(item)!={'position','velocity','acceleration'}: return False
        a=np.asarray(item['acceleration'],float)
        if a.shape!=(3,) or not np.all(np.isfinite(a)): return False
        if not np.allclose(q,item['position'],atol=1e-8,rtol=0) or not np.allclose(vel,item['velocity'],atol=1e-8,rtol=0): return False
        nextv=vel+a*cfg.dt
        if np.linalg.norm(a)>cfg.acceleration_limit+1e-8 or np.linalg.norm(nextv)>cfg.max_speed+1e-8: return False
        if fixed:
            angle=np.arctan2(nextv[1],nextv[0])-np.arctan2(vel[1],vel[0])
            angle=abs((angle+np.pi)%(2*np.pi)-np.pi)
            if np.linalg.norm(nextv[:2])<cfg.fixed_wing_min_speed-1e-8 or angle>np.deg2rad(cfg.fixed_wing_turn_rate_deg)*cfg.dt+1e-8 or abs(nextv[2])>cfg.fixed_wing_climb_limit+1e-8: return False
        t=(step+1)*cfg.dt; own_error=.4*t*t; guard=radius+own_error
        inner=replace(cfg,area=cfg.area-2*guard,altitude_floor=cfg.altitude_floor+guard,altitude_ceiling=cfg.altitude_ceiling-guard)
        if outside_volume(q[None],vel[None],a[None],inner,cfg.dt)[0]: return False
        for x,y,z,r in world['obstacles']:
            if quadratic_minimum(q-[x,y,z],vel,a,cfg.dt)<r+guard: return False
        for j in others:
            enclosure=error[j]+error_v[j]*t+.5*cfg.advertised_acceleration_bound*t*t+.4*(age[j]+t)**2
            minimum=quadratic_minimum(q-pred[j]-observed_v[j]*(t-cfg.dt),vel-observed_v[j],a,cfg.dt)
            if minimum<max(cfg.separation,radius+world['radius'][j])+own_error+enclosure: return False
        q=q+vel*cfg.dt+.5*a*cfg.dt**2;vel=nextv
    if certificate.get('static_invariant_terminal'):
        cert=certificate.get('hover')
        if cert is None or not verify_hover_certificate(cert,cfg) or fixed: return False
        center=np.asarray(certificate.get('hover_center'),float)
        if center.shape!=(3,) or not np.all(np.isfinite(center)): return False
        phase=np.stack((q-center,vel));P=np.array(cert['P'])
        nominal=np.sqrt(float(np.einsum('ac,ab,bc->',phase,P,phase)))
        e=np.array([.4*t*t,.8*t]);robust=nominal+np.sqrt(float(e@np.abs(P)@e))
        if robust>np.sqrt(cert['rho']): return False
        guard=radius+cert['swept_position_bound']
        floors=np.array([-cfg.area/2,-cfg.area/2,cfg.altitude_floor]);ceilings=np.array([cfg.area/2,cfg.area/2,cfg.altitude_ceiling])
        if np.any(center-guard<floors) or np.any(center+guard>ceilings): return False
        if any(np.linalg.norm(center-[x,y,z])<r+guard for x,y,z,r in world['obstacles']): return False
    return True
