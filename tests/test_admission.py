import copy
from dataclasses import replace
import unittest
from unittest.mock import patch
import numpy as np

from swarm_sim.config import Config
from swarm_sim.engine import simulate
from swarm_sim.routes import plan_route
from swarm_sim.predictive import segment_distance
from swarm_sim.backup import hover_certificate,verify_hover_certificate,check_backup,verify_backup_path
from swarm_sim.scenarios import build_world


class AdmissionTests(unittest.TestCase):
    def test_legacy_replay_unchanged_by_queue_and_routes(self):
        cfg=Config(drones=10,duration=3,cooperative_fraction=0,controller='predictive')
        a=simulate(cfg,True);b=simulate(replace(cfg,admission='checked',routes='visibility',admission_limit=1),True)
        self.assertEqual(a['replay'],b['replay'])
        self.assertEqual(b['metrics']['participant_admitted_aircraft'],0)

    def test_legacy_alone_can_exhaust_capacity_and_requested_demand_stays_in_denominator(self):
        cfg=Config(drones=10,duration=2,cooperative_fraction=.5,admission='checked',admission_limit=3)
        result=simulate(cfg,True);m=result['metrics']
        self.assertEqual(m['participant_admitted_aircraft'],0)
        self.assertEqual(m['queued_aircraft'],5)
        self.assertEqual(m['participant_completion_fraction'],0)
        self.assertEqual(m['participant_admission_fraction'],0)
        self.assertGreaterEqual(m['active_aircraft_seconds'],10)
        self.assertEqual(sum(result['replay']['initial_active']),5)

    def test_route_edges_clear_inflated_obstacle(self):
        cfg=Config();start=np.array([-60.,0,60]);goal=np.array([60.,0,60])
        obstacles=np.array([[0.,0,60,18.]])
        path=plan_route(start,goal,1.2,obstacles,cfg)
        self.assertIsNotNone(path);self.assertGreater(len(path),1)
        for a,b in zip(np.vstack((start,path))[:-1],path):
            self.assertGreaterEqual(segment_distance(a-obstacles[0,:3],b-obstacles[0,:3]),22.2-1e-8)
        np.testing.assert_array_equal(path[-1],goal)
        self.assertIsNone(plan_route(np.array([0.,0,60]),goal,1.2,obstacles,cfg))

    def test_failed_route_is_rejected_without_direct_flight_fallback(self):
        cfg=Config(drones=2,duration=1,cooperative_fraction=1,routes='visibility')
        w=build_world(cfg);w['obstacles']=np.array([[*w['goals'][0],10.]])
        with patch('swarm_sim.engine.build_world',return_value=w): result=simulate(cfg)
        self.assertGreaterEqual(result['metrics']['route_rejected_aircraft'],1)
        self.assertLess(result['metrics']['participant_admission_fraction'],1)

    def test_waypoint_does_not_count_as_completed_mission(self):
        cfg=Config(drones=2,duration=1,cooperative_fraction=1,routes='visibility',fixed_wing_fraction=0)
        w=build_world(cfg)
        class FakeRoutes:
            def __init__(self,cfg,world):
                self.mission_goals=world['goals'].copy();self.rejected=np.zeros(2,bool)
            def update(self,p,active,world): world['goals']=p.copy()
        with patch('swarm_sim.engine.build_world',return_value=w),patch('swarm_sim.engine.Routes',FakeRoutes):
            result=simulate(cfg)
        self.assertEqual(result['metrics']['participant_completion_fraction'],0)


class BackupTests(unittest.TestCase):
    def test_hover_set_input_bounds_and_random_disturbance_invariance(self):
        cfg=Config();cert=hover_certificate(cfg)
        self.assertTrue(verify_hover_certificate(cert,cfg))
        self.assertLessEqual(cert['command_bound'],cfg.acceleration_limit)
        rng=np.random.default_rng(7);P=np.array(cert['P']);F=np.array(cert['F']);L=np.linalg.cholesky(P).T
        G=np.array([.5*cfg.dt**2,cfg.dt])
        for _ in range(500):
            x=rng.normal(size=(2,3));x*=np.sqrt(cert['rho']/np.sum((L@x)**2))
            disturbance=rng.normal(size=3);disturbance*=.8/np.linalg.norm(disturbance)
            nxt=F@x+G[:,None]*disturbance
            self.assertLessEqual(np.sum((L@nxt)**2),cert['rho']+1e-8)
        forged=copy.deepcopy(cert);forged['rho']*=10
        self.assertFalse(verify_hover_certificate(forged,cfg))

    def world(self,fixed=False,horizon=2.4):
        cfg=Config(drones=2,fixed_wing_fraction=float(fixed),predictive_horizon=horizon)
        w=build_world(cfg);p=np.array([[0.,0,60],[-90.,90,100.]])
        v=np.array([[8.,0,0],[0.,0,0.]])
        snap=(p.copy(),v.copy(),np.zeros(2),np.zeros(2),np.zeros(2))
        return cfg,w,p,v,snap

    def test_independent_verifier_rejects_modified_and_discontinuous_paths(self):
        cfg,w,p,v,snap=self.world();active=np.ones(2,bool)
        cert=check_backup(cfg,w,0,p[0],v[0],active,snap)
        self.assertTrue(cert['valid']);self.assertTrue(verify_backup_path(cfg,w,0,cert,p[0],v[0],active,snap))
        forged=copy.deepcopy(cert);forged['path'][1]['position'][0]+=1
        self.assertFalse(verify_backup_path(cfg,w,0,forged,p[0],v[0],active,snap))
        forged=copy.deepcopy(cert);forged['path'][0]['acceleration']=[100.,0,0]
        self.assertFalse(verify_backup_path(cfg,w,0,forged,p[0],v[0],active,snap))

    def test_nominal_terminal_does_not_establish_robust_membership(self):
        cfg,w,p,v,snap=self.world();cert=check_backup(cfg,w,0,p[0],v[0],np.ones(2,bool),snap)
        self.assertTrue(cert['valid']);self.assertFalse(cert['static_invariant_terminal'])
        strict=check_backup(replace(cfg,require_invariant_backup=True),w,0,p[0],v[0],np.ones(2,bool),snap)
        self.assertFalse(strict['valid'])

    def test_short_hover_terminal_can_be_enclosed_but_fixed_wing_never_certifies_hover(self):
        cfg,w,p,v,snap=self.world(horizon=.2);v[0]=0;snap=(p.copy(),v.copy(),np.zeros(2),np.zeros(2),np.zeros(2))
        cert=check_backup(cfg,w,0,p[0],v[0],np.ones(2,bool),snap)
        self.assertTrue(cert['valid']);self.assertTrue(cert['static_invariant_terminal'])
        cfg,w,p,v,snap=self.world(fixed=True)
        cert=check_backup(cfg,w,0,p[0],v[0],np.ones(2,bool),snap)
        self.assertTrue(cert['valid']);self.assertFalse(cert['static_invariant_terminal'])
        self.assertFalse(check_backup(replace(cfg,require_invariant_backup=True),w,0,p[0],v[0],np.ones(2,bool),snap)['valid'])

    def test_backup_rejects_overlapping_traffic_and_wall(self):
        cfg,w,p,v,snap=self.world();p[1]=p[0];snap=(p.copy(),v.copy(),np.zeros(2),np.zeros(2),np.zeros(2))
        self.assertFalse(check_backup(cfg,w,0,p[0],v[0],np.ones(2,bool),snap)['valid'])
        cfg,w,p,v,snap=self.world();p[0,0]=109
        self.assertFalse(check_backup(cfg,w,0,p[0],v[0],np.ones(2,bool),snap)['valid'])


if __name__=='__main__': unittest.main()
