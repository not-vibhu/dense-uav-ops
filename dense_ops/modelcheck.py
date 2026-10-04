"""Bounded exhaustive protocol exploration; not an unbounded formal proof."""
import itertools
from .audit import Journal
from .federation import Negotiator


def explore():
    explored = 0
    for count in (2,3,4):
        names = [str(i) for i in range(count)]
        journal = Journal(names+['broker'])
        proposal = journal.sign('broker', {'type':'PROPOSE','members':names,'epoch':1,'start':1.,'end':2.,'bundle':'fixed'})
        nodes = [Negotiator(n,journal.public,journal) for n in names]
        accept = [n.prepare(proposal,0.,True) for n in nodes]
        for delivered in itertools.product((False,True), repeat=count):
            certificates = [a for a,d in zip(accept,delivered) if d]
            for now in (.5,1.5,2.5):
                for safe in (False,True):
                    for node in nodes:
                        authorized = node.authorized(proposal,certificates,now,safe)
                        expected = all(delivered) and now==1.5 and safe
                        assert authorized == expected, 'Unsafe partial/expired/local-veto authorization'
                        explored += 1
    # Every ordering of four competing broker/aircraft prepare events.
    for order in itertools.permutations([(a,b) for a in ('a','b') for b in ('x','y')]):
        j=Journal(['a','b','x','y']);nodes={a:Negotiator(a,j.public,j) for a in ('a','b')}
        proposals={b:j.sign(b,{'type':'PROPOSE','members':['a','b'],'epoch':1 if b=='x' else 2,
                              'start':1.,'end':2.,'bundle':b}) for b in ('x','y')}
        accept={b:[] for b in ('x','y')}
        for a,b in order:
            message=nodes[a].prepare(proposals[b],0.,True)
            if message:accept[b].append(message)
        for a,node in nodes.items():
            assert sum(node.authorized(proposals[b],accept[b],1.5,True) for b in ('x','y')) <= 1
            explored += 1
    return {'bounded_states_checked':explored,'violations':0,'participants':[2,3,4],
            'scope':'Finite exploration of partial certificates, competing brokers, expiry and local veto. Not a continuous-flight or unbounded protocol proof.'}
