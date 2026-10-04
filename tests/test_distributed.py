import copy
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
from cryptography.exceptions import InvalidSignature
from swarm_sim.config import Config
from dense_ops.safety import recovery, validate, resume
from dense_ops.network import Bus, Links, Surveillance
from dense_ops.federation import Reservations, Negotiator, compatible
from dense_ops.audit import Journal, verify, digest
from dense_ops.engine import Experiment, simulate


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.cfg = Config(area=600)
        self.p = np.array([0., 0., 50.]); self.v = np.array([6., 0., 0.])
        self.plan = recovery(self.cfg, self.p, self.v, False, 0., horizon=4., disturbance=.4)
        self.snapshot = (np.array([[200., 200., 50.]]), np.zeros((1,3)), np.ones(1), np.ones(1)*.3, np.zeros(1))

    def test_feedback_tube_encloses_randomized_disturbance_and_actuators(self):
        self.assertIsNotNone(self.plan)
        self.assertTrue(self.plan.static_terminal)
        for seed in range(30):
            rng = np.random.default_rng(seed)
            p = self.p + rng.normal(size=3)/np.sqrt(3)*.02
            v = self.v.copy()
            for k in range(len(self.plan.a)):
                command = self.plan.command(p, v, k)
                self.assertLessEqual(np.linalg.norm(command), self.cfg.acceleration_limit+1e-8)
                disturbance = rng.normal(size=3); disturbance *= .4/max(1., np.linalg.norm(disturbance))
                a = command+disturbance
                for t in np.linspace(0,self.cfg.dt,7):
                    actual = p+v*t+.5*a*t*t
                    nominal = self.plan.p[k]+self.plan.v[k]*t+.5*self.plan.a[k]*t*t
                    self.assertLessEqual(np.linalg.norm(actual-nominal), self.plan.slab[k]+1e-8)
                p = p+v*self.cfg.dt+.5*a*self.cfg.dt**2; v = v+a*self.cfg.dt
                self.assertLessEqual(np.linalg.norm(p-self.plan.p[k+1]), self.plan.ep[k+1]+1e-8)
                self.assertLessEqual(np.linalg.norm(v-self.plan.v[k+1]), self.plan.ev[k+1]+1e-8)

    def test_continuous_collision_and_malformed_certificate_rejected(self):
        snap = (np.array([[0., 0., 50.]]), np.zeros((1,3)), np.zeros(1), np.zeros(1), np.zeros(1))
        self.assertFalse(validate(self.plan,self.cfg,1.,snap,[0],np.ones(1),np.ones(1)*10,0.)[0])
        altered = copy.deepcopy(self.plan); altered.p[2,0] += 1
        self.assertFalse(validate(altered,self.cfg,1.,self.snapshot,[],np.ones(1),np.ones(1)*10,0.)[0])

    def test_fixed_wing_never_claims_robust_terminal_hover(self):
        plan = recovery(self.cfg,self.p,self.v,True,0.,disturbance=.4)
        self.assertFalse(plan.static_terminal)
        self.assertIsNone(plan.center)
        self.assertGreaterEqual(np.min(np.linalg.norm(plan.v[:,:2],axis=1)),self.cfg.fixed_wing_min_speed)

    def test_watchdog_expiry_state_departure_and_fresh_intruder(self):
        self.assertIsNone(resume(self.plan,self.p+5,self.v,0.))
        self.assertIsNone(resume(self.plan,self.p,self.v,20.))
        tail = resume(self.plan,self.plan.p[1],self.plan.v[1],self.cfg.dt)
        self.assertIsNotNone(tail)
        snap = (tail.p[:1],np.zeros((1,3)),np.zeros(1),np.zeros(1),np.zeros(1))
        self.assertFalse(validate(tail,self.cfg,1.,snap,[0],np.ones(1),np.ones(1)*10,self.cfg.dt)[0])

    def test_joint_admission_preserves_prior_reserved_recovery(self):
        book = Reservations()
        self.assertTrue(book.accept(0,self.plan,10.,0.))
        self.assertFalse(book.accept(1,self.plan,10.,0.))
        self.assertIn(0,book.plans)
        self.assertNotIn(1,book.plans)

    def test_far_traffic_and_approaching_manned_forecast(self):
        self.assertTrue(validate(self.plan,self.cfg,1.,self.snapshot,[0],np.ones(1),np.ones(1)*10,0.)[0])
        snap = (np.array([[-100.,0.,50.]]),np.array([[35.,0.,0.]]),np.ones(1),np.ones(1)*.3,np.zeros(1))
        self.assertFalse(validate(self.plan,self.cfg,1.,snap,[0],np.ones(1)*6,np.ones(1)*60,0.)[0])


class DistributedTests(unittest.TestCase):
    def test_entry_requires_delivered_fresh_surveillance_frame(self):
        sensor=Surveillance(2,11,Links(latency=.1,jitter=0,loss=0))
        self.assertFalse(sensor.ready(0,0.,1.))
        p=np.array([[0.,0.,50.],[50.,0.,50.]])
        sensor.step(0.,p,np.zeros_like(p),np.zeros(2,bool),[0])
        sensor.step(.2,p,np.zeros_like(p),np.zeros(2,bool),[0])
        self.assertTrue(sensor.ready(0,.2,1.))
        self.assertFalse(sensor.ready(0,2.,1.))

    def test_stale_delay_defers_entry_and_preserves_requested_service(self):
        result=simulate(Experiment(drones=10,duration=3.,area=220.,scenario='stale_telemetry',seed=8200))
        self.assertEqual(result['metrics']['cooperative_admitted'],0)
        self.assertEqual(result['metrics']['queued'],result['metrics']['cooperative_requested'])
        self.assertGreater(result['metrics']['admission_surveillance_rejections'],0)
        self.assertFalse(result['observed_requirements_pass'])
        self.assertTrue(any(e['payload']['kind']=='DEFER_ENTRY' for e in result['audit']['events']))

    def test_readiness_uses_clock_bound_and_rejects_invalid_freshness(self):
        sensor=Surveillance(2,11,Links(clock_skew=.4))
        sensor.frame_source[0]=.4
        self.assertFalse(sensor.ready(0,1.2,1.))
        for age in (-1.,float('nan'),5.):
            with self.assertRaises(ValueError):replace(Experiment(),max_surveillance_age=age).validate()

    def test_independent_receiver_loss_and_source_age(self):
        s = Surveillance(2,12,Links(latency=.2,jitter=0,loss=0),sensor_range=20)
        p=np.array([[0.,0.,50.],[100.,0.,50.]]);v=np.zeros_like(p)
        s.step(0.,p,v,np.ones(2,bool),[0,1]);s.step(.2,p,v,np.ones(2,bool),[0,1])
        self.assertTrue(s.seen[0,0]);self.assertFalse(s.seen[0,1])
        self.assertTrue(s.seen[1,1]);self.assertFalse(s.seen[1,0])
        old=s.snapshot(0,.2,4.)[2][0];later=s.snapshot(0,2.,4.)[2][0]
        self.assertGreater(later,old)

    def test_asymmetry_partition_capacity_and_late_delivery(self):
        bus=Bus(1,Links(latency=.5,jitter=0,loss=0,asymmetric=True),capacity=1)
        self.assertFalse(bus.send('a','b',0.,'blocked'))
        self.assertTrue(bus.send('b','a',0.,'ok'))
        self.assertFalse(bus.send('b','a',0.,'overflow'))
        self.assertEqual(bus.receive(.2),[]);self.assertEqual(bus.receive(.5),[('a','ok')])
        partition=Bus(1,Links(loss=0,partition=True))
        self.assertFalse(partition.send('a','b',3.,'blocked'))

    def test_partial_certificate_local_veto_and_overlapping_brokers(self):
        j=Journal(['a','b','broker','broker2'])
        nodes=[Negotiator(a,j.public,j) for a in ('a','b')]
        body={'type':'PROPOSE','members':['a','b'],'epoch':1,'start':1.,'end':2.,'bundle':'abc'}
        proposal=j.sign('broker',body)
        accept=[n.prepare(proposal,0.,True) for n in nodes]
        self.assertFalse(nodes[0].authorized(proposal,accept[:1],1.2,True))
        self.assertTrue(nodes[0].authorized(proposal,accept,1.2,True))
        self.assertFalse(nodes[0].authorized(proposal,accept,1.2,False))
        self.assertFalse(nodes[0].authorized(proposal,accept,2.1,True))
        conflicting=j.sign('broker2',{**body,'epoch':2})
        self.assertIsNone(nodes[0].prepare(conflicting,.1,True))

    def test_replayed_epoch_future_window_and_missing_member(self):
        j=Journal(['a','broker']);n=Negotiator('a',j.public,j)
        body={'type':'PROPOSE','members':['a'],'epoch':1,'start':1.,'end':2.}
        p=j.sign('broker',body);a=n.prepare(p,0.,True)
        self.assertIsNone(n.prepare(p,0.,True))
        self.assertFalse(n.authorized(p,[a],.9,True))
        self.assertFalse(n.authorized(p,[a,a],1.2,True))

    def test_malformed_and_forged_negotiations_fail_without_authorization(self):
        j=Journal(['a','broker']);n=Negotiator('a',j.public,j)
        body={'type':'PROPOSE','members':['a'],'epoch':1,'start':1.,'end':2.}
        for alteration in ({'members':['a','a']},{'epoch':True},{'end':'later'},{'members':[]},{'type':'EXECUTE'}):
            self.assertIsNone(n.prepare(j.sign('broker',{**body,**alteration}),0.,True))
        forged=j.sign('broker',body);forged['signature']='00'*64
        self.assertIsNone(n.prepare(forged,0.,True))
        proposal=j.sign('broker',body);accept=n.prepare(proposal,0.,True)
        forged_accept=copy.deepcopy(accept);forged_accept['signature']='00'*64
        self.assertFalse(n.authorized(proposal,[forged_accept],1.2,True))
        self.assertTrue(n.authorized(proposal,[accept],1.2,True))

    def test_signed_witness_tampering_deletion_reorder_and_tail(self):
        j=Journal(['a','b']);j.append('a',0.,'OBSERVE',{'x':1});j.append('b',.1,'APPLY',{'u':2})
        anchor=j.anchor();self.assertTrue(verify(j.events,j.public,anchor))
        for altered in (j.events[:1],j.events[::-1]):
            with self.assertRaises(ValueError):verify(altered,j.public,anchor)
        altered=copy.deepcopy(j.events);altered[0]['payload']['payload']['x']=9
        with self.assertRaises(InvalidSignature):verify(altered,j.public,anchor)
        public=dict(j.public);public['a']=public['b']
        with self.assertRaises(ValueError):verify(j.events,public,anchor)

    def test_invalid_conditions_and_no_implicit_graph_checkpoint(self):
        for changes in ({'drones':True},{'deadline_ms':500},{'disturbance':1.},{'sensor_range':float('nan')}):
            with self.assertRaises(ValueError):replace(Experiment(),**changes).validate()
        with self.assertRaises(ValueError):simulate(Experiment(mode='graph'))

    def test_no_control_authority_zero_equipage_and_signed_outcome(self):
        a=simulate(Experiment(drones=4,duration=2.,cooperative_fraction=0.,manned=0))
        b=simulate(Experiment(drones=4,duration=2.,cooperative_fraction=0.,manned=0,mode='federated'))
        self.assertEqual(a['metrics']['collision_pairs'],b['metrics']['collision_pairs'])
        self.assertEqual(a['metrics']['cooperative_admitted'],0)
        self.assertFalse(a['observed_requirements_pass'])
        self.assertTrue(verify(a['audit']['events'],a['audit']['public'],a['audit']['anchor']))

    def test_density_never_becomes_operational_capacity(self):
        result=simulate(Experiment(drones=10,duration=2.,manned=1,area=220.))
        self.assertIsNone(result['operational_capacity'])
        self.assertIn('completion_requirement',result['blockers'])


class NasaTests(unittest.TestCase):
    @unittest.skipUnless(Path('artifacts/nasa/manifest.json').exists(),'Build pinned optional NASA adapter')
    def test_actual_nasa_head_on_alert_and_vertical_separation(self):
        from dense_ops.nasa import Daidalus
        daa=Daidalus('artifacts/nasa/manifest.json')
        r=daa.evaluate(0,[0,1],[[0,0,100],[800,0,100]],[[20,0,0],[-20,0,0]])
        self.assertGreater(r['alerts'][0]['level'],0)
        self.assertTrue(r['direction_bands_deg'])
        separate=daa.evaluate(0,[0,1],[[0,0,100],[800,0,1000]],[[20,0,0],[-20,0,0]])
        self.assertEqual(separate['alerts'][0]['level'],0)


if __name__=='__main__':unittest.main()
