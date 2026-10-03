"""Optional recurrent imitation + masked MAPPO research implementation.

The shared attention actor sees local reports; the critic sees training-only
context. The finite maneuver checker supplies the action mask and retains final
veto authority. Empty masks execute deterministic fallback with no actor loss.
JSON checkpoints contain arrays, never executable pickle objects.
"""
from collections import defaultdict
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import numpy as np
import torch
from torch import nn
from torch.distributions import Categorical

from .observations import OWN_DIM, NEIGHBOR_DIM, CONTEXT_DIM, ACTIONS

ARCHITECTURE = {'own':OWN_DIM,'neighbor':NEIGHBOR_DIM,'context':CONTEXT_DIM,
                'actions':ACTIONS,'hidden':32,'encoder':'attention-gru-v1'}


class ActorCritic(nn.Module):
    def __init__(self):
        super().__init__()
        self.own = nn.Sequential(nn.Linear(OWN_DIM,32),nn.Tanh())
        self.neighbor = nn.Sequential(nn.Linear(NEIGHBOR_DIM,32),nn.Tanh())
        self.query = nn.Linear(32,32,bias=False)
        self.gru = nn.GRUCell(64,32)
        self.action = nn.Linear(32,ACTIONS)
        self.critic = nn.Sequential(nn.Linear(32+CONTEXT_DIM,64),nn.Tanh(),nn.Linear(64,1))

    def actor(self, own, neighbors, mask, hidden):
        x = self.own(own); nodes=self.neighbor(neighbors)
        scores=(nodes*self.query(x)[:,None]).sum(-1)/(32**.5)
        weights=torch.softmax(scores.masked_fill(~mask,-1e9),dim=-1)*mask
        weights=weights/weights.sum(-1,keepdim=True).clamp_min(1e-8)
        aggregate=(weights[:,:,None]*nodes).sum(1)
        h=self.gru(torch.cat((x,aggregate),-1),hidden)
        return self.action(h),h

    def value(self,hidden,context):
        return self.critic(torch.cat((hidden,context),-1)).squeeze(-1)


def tensors(observation):
    return (torch.as_tensor(observation['own'],dtype=torch.float32),
            torch.as_tensor(observation['neighbors'],dtype=torch.float32),
            torch.as_tensor(observation['neighbor_mask'],dtype=torch.bool))


def distribution(logits, feasible):
    feasible=torch.as_tensor(feasible,dtype=torch.bool)
    # Empty rows are dummy distributions. Their actor loss is explicitly zero.
    nonempty=feasible.any(-1)
    allowed=feasible.clone();allowed[~nonempty,0]=True
    return Categorical(logits=logits.masked_fill(~allowed,-1e9)),nonempty


class Policy:
    def __init__(self,model,mode='inference',stochastic=False):
        self.model=model;self.mode=mode;self.stochastic=stochastic

    def reset(self,n):
        self.hidden=torch.zeros(n,32);self.records=[];self.pending=None

    def choose(self,ids,observation,feasible,teacher,context):
        before=self.hidden[ids].clone()
        with torch.no_grad():
            logits,hidden=self.model.actor(*tensors(observation),before)
            dist,valid=distribution(logits,feasible)
            action=dist.sample() if self.stochastic else dist.logits.argmax(-1)
            if self.mode=='expert': action=torch.as_tensor(teacher,dtype=torch.long)
            action=torch.where(valid,action,torch.as_tensor(teacher,dtype=torch.long))
            if self.mode=='inference':
                self.hidden[ids]=hidden
                return action.numpy()
            value=self.model.value(hidden,torch.as_tensor(context)[None].expand(len(ids),-1))
            logp=dist.log_prob(action)
            self.hidden[ids]=hidden
        if self.mode!='inference':
            record={'ids':ids.copy(),'obs':observation,'mask':feasible.copy(),'teacher':teacher.copy(),
                    'hidden':before,'action':action.clone(),'logp':logp.clone(),'value':value.clone(),
                    'context':context.copy(),'valid':valid.clone()}
            self.records.append(record);self.pending=record
        return action.numpy()

    def transition(self,reward,done):
        if self.pending is not None:
            ids=self.pending['ids']
            self.pending['reward']=torch.as_tensor(reward[ids],dtype=torch.float32)
            self.pending['done']=torch.as_tensor(done[ids],dtype=torch.bool)
            self.pending=None
        # Completed agents cannot carry their hidden state into a later episode.
        self.hidden[np.asarray(done,dtype=bool)]=0


def checkpoint_digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save_checkpoint(path,model,metadata):
    from .cli import write_json,source_hash
    metadata={**metadata,'source_sha256':source_hash(),'torch_version':torch.__version__}
    value={'schema':'federated-swarm-actor-v1','architecture':ARCHITECTURE,
           'metadata':metadata,'weights':{k:v.detach().cpu().tolist() for k,v in model.state_dict().items()}}
    write_json(path,value)
    return checkpoint_digest(path)


def load_model(path,expected_sha256='',stage=None):
    from .cli import source_hash
    path=Path(path)
    if not path.is_file() or path.stat().st_size>5_000_000:
        raise ValueError('Missing or oversized neural checkpoint')
    if expected_sha256 and checkpoint_digest(path)!=expected_sha256:
        raise ValueError('Neural checkpoint checksum mismatch')
    document=json.loads(path.read_text())
    if document.get('schema')!='federated-swarm-actor-v1' or document.get('architecture')!=ARCHITECTURE:
        raise ValueError('Unsupported checkpoint schema/architecture')
    meta=document['metadata']
    if meta.get('source_sha256')!=source_hash():
        raise ValueError('Checkpoint belongs to another simulator revision; retrain explicitly')
    if stage is not None and meta.get('stage')!=stage:
        raise ValueError('Checkpoint training stage does not match the selected controller')
    model=ActorCritic();expected=model.state_dict()
    if set(document['weights'])!=set(expected): raise ValueError('Invalid checkpoint parameter keys')
    state={}
    for key,value in document['weights'].items():
        arr=np.asarray(value,dtype=np.float32)
        if arr.shape!=tuple(expected[key].shape) or not np.all(np.isfinite(arr)) or np.max(np.abs(arr))>1e6:
            raise ValueError('Invalid checkpoint parameters')
        state[key]=torch.from_numpy(arr)
    model.load_state_dict(state);model.eval()
    return model,meta


def load_actor(path,expected_sha256='',stage=None):
    torch.set_num_threads(1)
    model,_=load_model(path,expected_sha256,stage)
    return Policy(model)


def trajectories(episodes,chunk_length=8):
    chunks=[]
    for records in episodes:
        aircraft=defaultdict(list)
        for rec in records:
            for row,i in enumerate(rec['ids']): aircraft[int(i)].append((rec,row))
        for sequence in aircraft.values():
            for start in range(0,len(sequence),chunk_length): chunks.append(sequence[start:start+chunk_length])
    return chunks


def forward_sequence(model,sequence):
    hidden=sequence[0][0]['hidden'][sequence[0][1]:sequence[0][1]+1].detach()
    outputs=[]
    for rec,row in sequence:
        obs={k:v[row:row+1] for k,v in rec['obs'].items()}
        logits,hidden=model.actor(*tensors(obs),hidden)
        context=torch.as_tensor(rec['context'])[None]
        outputs.append((logits[0],model.value(hidden,context)[0]))
    return outputs


def imitation_update(model,episodes,epochs=8,seed=0):
    chunks=trajectories(episodes);optimizer=torch.optim.Adam(model.parameters(),lr=3e-4)
    rng=np.random.default_rng(seed);history=[]
    for epoch in range(epochs):
        total_loss=correct=count=0
        for batch_start in range(0,len(chunks),16):
            if batch_start==0: order=rng.permutation(len(chunks))
            terms=[]
            for index in order[batch_start:batch_start+16]:
                seq=chunks[index]
                for (rec,row),(logits,_) in zip(seq,forward_sequence(model,seq)):
                    if not rec['valid'][row]: continue
                    dist,_=distribution(logits[None],rec['mask'][row:row+1])
                    target=int(rec['teacher'][row]);terms.append(-dist.log_prob(torch.tensor([target]))[0])
                    correct+=int(dist.logits.argmax(-1).item()==target);count+=1
            if terms:
                loss=torch.stack(terms).mean();optimizer.zero_grad();loss.backward()
                nn.utils.clip_grad_norm_(model.parameters(),.5);optimizer.step()
                total_loss+=float(loss.detach())*len(terms)
        history.append({'epoch':epoch+1,'loss':total_loss/max(count,1),'accuracy':correct/max(count,1),'labels':count})
    return history


def add_advantages(records,gamma=.99,lam=.95):
    """Finite-horizon episodes terminate at configured duration; no time bootstrap."""
    next_value={};next_advantage={}
    for rec in reversed(records):
        adv=torch.zeros(len(rec['ids']))
        for row,i in enumerate(rec['ids']):
            i=int(i);cont=not bool(rec['done'][row])
            delta=rec['reward'][row]+gamma*next_value.get(i,0.)*cont-rec['value'][row]
            adv[row]=delta+gamma*lam*next_advantage.get(i,0.)*cont
            next_value[i]=rec['value'][row];next_advantage[i]=adv[row]
        rec['advantage']=adv;rec['return']=adv+rec['value']
    valid_values=[r['advantage'][r['valid']] for r in records if r['valid'].any()]
    if valid_values:
        all_adv=torch.cat(valid_values);mean=all_adv.mean();std=all_adv.std(unbiased=False).clamp_min(1e-5)
        for rec in records: rec['advantage']=(rec['advantage']-mean)/std


def ppo_update(model,records,optimizer,epochs=3,seed=0):
    add_advantages(records);chunks=trajectories([records]);rng=np.random.default_rng(seed)
    history=[]
    for epoch in range(epochs):
        order=rng.permutation(len(chunks));losses=[];kls=[];actors=0
        for batch_start in range(0,len(chunks),16):
            actor_terms=[];value_terms=[];entropies=[]
            for index in order[batch_start:batch_start+16]:
                seq=chunks[index]
                for (rec,row),(logits,value) in zip(seq,forward_sequence(model,seq)):
                    old_value=rec['value'][row];target=rec['return'][row]
                    clipped=old_value+(value-old_value).clamp(-.2,.2)
                    value_terms.append(torch.maximum((value-target)**2,(clipped-target)**2))
                    if not rec['valid'][row]: continue
                    dist,_=distribution(logits[None],rec['mask'][row:row+1])
                    logp=dist.log_prob(rec['action'][row:row+1])[0]
                    ratio=(logp-rec['logp'][row]).exp();adv=rec['advantage'][row]
                    actor_terms.append(-torch.minimum(ratio*adv,ratio.clamp(.8,1.2)*adv))
                    entropies.append(dist.entropy()[0]);actors+=1
                    kls.append(float((rec['logp'][row]-logp).detach()))
            if not value_terms: continue
            loss=.5*torch.stack(value_terms).mean()
            if actor_terms: loss+=torch.stack(actor_terms).mean()-.01*torch.stack(entropies).mean()
            optimizer.zero_grad();loss.backward();nn.utils.clip_grad_norm_(model.parameters(),.5);optimizer.step()
            losses.append(float(loss.detach()))
        history.append({'epoch':epoch+1,'loss':float(np.mean(losses)) if losses else 0.,
                        'approximate_kl':float(np.mean(kls)) if kls else 0.,'actor_samples':actors})
    return history


def train(args):
    from .cli import write_json
    from .config import Config
    from .engine import simulate
    torch.set_num_threads(1);torch.manual_seed(args.training_seed)
    np.random.seed(args.training_seed)
    model=ActorCritic();parent_meta={};parent_sha=None
    if args.method=='mappo':
        if not args.initial: raise ValueError('MAPPO requires --initial imitation checkpoint')
        model,parent_meta=load_model(args.initial,stage='imitation')
        parent_sha=checkpoint_digest(args.initial)
    base=Config(controller='predictive',drones=args.drones,duration=args.duration,
                cooperative_fraction=args.cooperative,fixed_wing_fraction=args.fixed_wing,
                admission=args.admission,admission_limit=args.admission_limit,routes=args.routes)
    policy=Policy(model,mode='expert' if args.method=='imitation' else 'rollout',stochastic=args.method=='mappo')
    episodes=[];runs=[];history=[];optimizer=torch.optim.Adam(model.parameters(),lr=3e-4)
    seeds=list(args.train_seeds)
    for episode in range(args.episodes):
        cfg=replace(base,scenario=args.scenarios[episode%len(args.scenarios)],seed=seeds[episode%len(seeds)])
        result=simulate(cfg,policy=policy);episodes.append(policy.records)
        runs.append({'config':result['config'],'metrics':result['metrics']})
        if args.method=='mappo':
            update=ppo_update(model,policy.records,optimizer,epochs=args.epochs,seed=args.training_seed+episode)
            history.append({'episode':episode+1,'updates':update})
        print(f"{args.method}: episode {episode+1}/{args.episodes}; admissible decisions "
              f"{sum(int(r['valid'].sum()) for r in policy.records)}",flush=True)
    if args.method=='imitation': history=imitation_update(model,episodes,args.epochs,args.training_seed)
    labels=sum(int(r['valid'].sum()) for ep in episodes for r in ep)
    if labels==0: raise ValueError('No admissible decisions collected; refusing empty training checkpoint')
    metadata={'stage':args.method,'training_seed':args.training_seed,
              'training_seeds':sorted(set(seeds+parent_meta.get('training_seeds',[]))),
              'scenarios':args.scenarios,'episodes':args.episodes,'admissible_decisions':labels,
              'teacher':'finite predictive library; excludes failed-library labels',
              'scope':'research training run; no safety certificate',
              'initial_checkpoint_sha256':parent_sha,
              'reward':'mission progress/speed +5 reach -.02dt -.001 effort*dt -20 collision/obstacle -5 exit -.2dt separation',
              'ppo':{'clip':.2,'gamma':.99,'gae_lambda':.95,'entropy':.01,'chunk_length':8,
                     'centralized_critic':True,'finite_duration_terminal':True} if args.method=='mappo' else None}
    sha=save_checkpoint(args.out,model,metadata)
    write_json(Path(args.out).with_suffix('.training.json'),{'metadata':metadata,'checkpoint_sha256':sha,
                 'history':history,'rollouts':runs,'note':'Rollouts generated during training are not evaluation evidence.'})
    print(json.dumps({'checkpoint':args.out,'sha256':sha,'admissible_decisions':labels},indent=2))
