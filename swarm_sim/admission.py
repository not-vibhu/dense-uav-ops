"""Pre-entry demand management. Legacy traffic is never held or rerouted."""
import numpy as np
from .backup import check_backup


class Admission:
    def __init__(self,cfg,world,routes):
        self.cfg=cfg;self.world=world
        self.queued=world['cooperative'].copy() if cfg.admission!='off' else np.zeros(cfg.drones,bool)
        self.rejected=routes.rejected & world['cooperative']
        self.queued &= ~self.rejected
        self.admitted=~self.queued & ~self.rejected
        self.entry_velocity=world['velocity'].copy()
        self.release_time=np.where(self.admitted,0.,np.nan)
        self.next_check=0.;self.checks=0;self.denials={};self.certificates={}

    def release(self,time,p,v,active,snapshot,telemetry):
        if self.cfg.admission=='off' or time+1e-9<self.next_check: return []
        self.next_check=time+self.cfg.admission_period
        released=[]
        for i in np.flatnonzero(self.queued):
            if np.sum(active)>=self.cfg.admission_limit: break
            self.checks+=1
            trial=active.copy();trial[i]=True
            cert=check_backup(self.cfg,self.world,int(i),p[i],self.entry_velocity[i],trial,snapshot)
            if self.cfg.admission=='checked' and not cert['valid']:
                reason=cert['reason'];self.denials[reason]=self.denials.get(reason,0)+1
                continue
            self.queued[i]=False;self.admitted[i]=True;active[i]=True
            v[i]=self.entry_velocity[i];self.release_time[i]=time
            self.certificates[int(i)]=cert
            # Explicit idealized entry-state announcement, like initial t=0
            # traffic initialization. This is not a real RID latency bypass.
            telemetry.position[i]=p[i];telemetry.velocity[i]=v[i];telemetry.source_time[i]=time
            snapshot=telemetry.snapshot(time)
            released.append(int(i))
        return released
