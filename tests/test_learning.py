import copy
from dataclasses import replace
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np

from swarm_sim.config import Config
from swarm_sim.scenarios import build_world
from swarm_sim.predictive import predictive_control
from swarm_sim.observations import observe,central_context

TORCH_AVAILABLE=importlib.util.find_spec('torch') is not None
if TORCH_AVAILABLE:
    import torch
    from swarm_sim.learning import ActorCritic,Policy,tensors,distribution,save_checkpoint,load_model,checkpoint_digest,ppo_update,imitation_update


class VetoTests(unittest.TestCase):
    def test_invalid_policy_action_is_vetoed(self):
        cfg=Config(drones=2,controller='predictive',fixed_wing_fraction=0)
        w=build_world(cfg);w['cooperative']=np.array([True,False])
        p=np.array([[90.,0,50],[-90.,80,100]]);v=np.array([[8.,0,0],[0.,0,0]])
        snap=(p.copy(),v.copy(),np.zeros(2),np.zeros(2),np.zeros(2))
        class Bad:
            def choose(self,*args): return np.array([-10])
        reference,stats=predictive_control(cfg,w,p,v,np.ones(2,bool),snap,np.zeros_like(p))
        actual,bad=predictive_control(cfg,w,p,v,np.ones(2,bool),snap,np.zeros_like(p),Bad())
        self.assertFalse(stats['unresolved'][0]);self.assertEqual(bad['proposal_rejections'],1)
        np.testing.assert_array_equal(actual,reference)

    def test_ninth_neighbor_remains_in_safety_check(self):
        cfg=Config(drones=10,fixed_wing_fraction=0,controller='predictive')
        w=build_world(cfg);w['cooperative'][:]=False;w['cooperative'][0]=True
        p=np.zeros((10,3));p[:,2]=60;p[1:9,0]=np.arange(1,9)*.1;p[9,0]=60
        v=np.zeros_like(p);v[9,0]=-12
        # Eight nearest parked reports have no collision radius in this synthetic
        # fixture; the ninth large-radius aircraft must still block the library.
        w['radius'][9]=200
        active=np.ones(10,bool);snap=(p.copy(),v.copy(),np.zeros(10),np.zeros(10),np.zeros(10))
        obs=observe(cfg,w,np.array([0]),p,v,active,snap)
        self.assertEqual(obs['neighbor_mask'].sum(),8)
        _,stats=predictive_control(cfg,w,p,v,active,snap,np.zeros_like(p))
        self.assertTrue(stats['unresolved'][0])
        # Remove the eight close reports, retaining the same ninth threat.
        active[1:9]=False
        _,stats=predictive_control(cfg,w,p,v,active,snap,np.zeros_like(p))
        self.assertTrue(stats['unresolved'][0])


@unittest.skipUnless(TORCH_AVAILABLE,'Install the optional learning extra')
class LearningTests(unittest.TestCase):
    def setUp(self):
        torch.set_num_threads(1);torch.manual_seed(2)
        self.model=ActorCritic()
        cfg=Config(drones=10);w=build_world(cfg);p=w['position'];v=w['velocity']
        snap=(p.copy(),v.copy(),np.ones(10),np.ones(10),np.zeros(10))
        self.obs=observe(cfg,w,np.array([0,1]),p,v,np.ones(10,bool),snap)
        self.context=central_context(cfg,w,p,v,np.ones(10,bool))

    def test_attention_is_invariant_to_neighbor_order_and_critic_context_is_separate(self):
        logits,h=self.model.actor(*tensors(self.obs),torch.zeros(2,32))
        shuffled={k:(v[:,::-1].copy() if k!='own' else v) for k,v in self.obs.items()}
        changed,h2=self.model.actor(*tensors(shuffled),torch.zeros(2,32))
        torch.testing.assert_close(logits,changed,atol=1e-6,rtol=1e-6)
        a=self.model.value(h,torch.zeros(2,9));b=self.model.value(h,torch.ones(2,9))
        self.assertFalse(torch.allclose(a,b))
        again,_=self.model.actor(*tensors(self.obs),torch.zeros(2,32))
        torch.testing.assert_close(logits,again)

    def test_inference_does_not_call_critic_or_require_global_context(self):
        policy=Policy(self.model);policy.reset(2)
        with patch.object(self.model,'value',side_effect=AssertionError('critic used in inference')):
            action=policy.choose(np.array([0,1]),self.obs,np.ones((2,22),bool),np.array([0,0]),None)
        self.assertEqual(action.shape,(2,))
        cfg=Config(drones=10,controller='predictive');w=build_world(cfg)
        p=w['position'];v=w['velocity'];snap=(p.copy(),v.copy(),np.ones(10),np.ones(10),np.zeros(10))
        policy.reset(10)
        with patch('swarm_sim.observations.central_context',side_effect=AssertionError('global context used')):
            predictive_control(cfg,w,p,v,np.ones(10,bool),snap,np.zeros_like(p),policy)

    def test_mask_blocks_extreme_unsafe_logit_and_empty_mask_is_marked(self):
        logits=torch.zeros(2,22);logits[:,0]=1e6
        mask=np.zeros((2,22),bool);mask[0,7]=True
        dist,valid=distribution(logits,mask)
        self.assertEqual(dist.sample()[0].item(),7)
        self.assertEqual(valid.tolist(),[True,False])

    def test_json_checkpoint_roundtrip_checksum_stage_and_corruption(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'model.json';save_checkpoint(path,self.model,{'stage':'imitation','training_seeds':[4000]})
            loaded,_=load_model(path,checkpoint_digest(path),'imitation')
            for k,v in self.model.state_dict().items(): torch.testing.assert_close(v,loaded.state_dict()[k])
            with self.assertRaises(ValueError): load_model(path,'0'*64)
            with self.assertRaises(ValueError): load_model(path,stage='mappo')
            doc=json.loads(path.read_text());key=next(iter(doc['weights']));doc['weights'][key]=[float('nan')]
            path.write_text(json.dumps(doc))
            with self.assertRaises(ValueError): load_model(path)

    def records(self,mode='rollout'):
        policy=Policy(self.model,mode=mode,stochastic=True);policy.reset(2)
        for step in range(4):
            mask=np.ones((2,22),bool);mask[:,0]=False
            policy.choose(np.array([0,1]),self.obs,mask,np.array([7,7]),self.context)
            policy.transition(np.array([.2,.3]),np.array([step==3,step==3]))
        return policy.records

    def test_recurrent_ppo_updates_finite_parameters_with_on_policy_samples(self):
        records=self.records();before=copy.deepcopy(self.model.state_dict())
        opt=torch.optim.Adam(self.model.parameters(),lr=3e-4)
        history=ppo_update(self.model,records,opt,epochs=2)
        self.assertEqual(history[0]['actor_samples'],8)
        self.assertTrue(all(np.isfinite(x['loss']) for x in history))
        self.assertTrue(any(not torch.equal(before[k],v) for k,v in self.model.state_dict().items()))
        self.assertTrue(all(torch.isfinite(v).all() for v in self.model.parameters()))

    def test_imitation_learns_admissible_teacher_and_excludes_forced_fallback(self):
        records=self.records('expert');records[0]['valid'][:]=False
        history=imitation_update(self.model,[records],epochs=100)
        self.assertEqual(history[-1]['labels'],6)
        self.assertLess(history[-1]['loss'],history[0]['loss'])
        self.assertEqual(history[-1]['accuracy'],1.)


if __name__=='__main__': unittest.main()
