import gzip,hashlib,itertools,json,platform,shutil,tarfile
from dataclasses import asdict
from pathlib import Path
import numpy as np
from swarm_sim.cli import source_hash,write_json
from swarm_sim.config import Config
from swarm_sim.engine import config_id
from swarm_sim.analysis import summarize

root=Path.cwd();out=root/'experiments/iteration-03';sha=source_hash();catalogs={}
for source in sorted((root/'artifacts').glob('iteration03-*/manifest.json')):
 directory=source.parent;name=directory.name.removeprefix('iteration03-');manifest=json.loads(source.read_text())
 if manifest['source_sha256']!=sha: raise ValueError('Source revision mismatch: '+name)
 result_path=directory/'results.json';summary_path=directory/'summary.json'
 if not result_path.exists() or not summary_path.exists(): raise ValueError('Incomplete campaign: '+name)
 for controller,pin in manifest.get('neural_checkpoints',{}).items():
  model_path=Path(pin['checkpoint'])
  if hashlib.sha256(model_path.read_bytes()).hexdigest()!=pin['checkpoint_sha256']: raise ValueError('Checkpoint changed after evaluation: '+controller)
 runs=json.loads(result_path.read_text());summary=json.loads(summary_path.read_text())
 expected={}
 for sc,n,f,c,seed in itertools.product(manifest['scenarios'],manifest['counts'],manifest['fractions'],manifest['controllers'],manifest['discovery_seeds']+manifest['holdout_seeds']):
  kw=manifest['neural_checkpoints'].get(c,{})
  cfg=Config(scenario=sc,drones=n,cooperative_fraction=f,controller=c,seed=seed,duration=manifest['duration_s'],dt=manifest['dt_s'],fixed_wing_fraction=manifest['fixed_wing_fraction'],admission=manifest['admission'],admission_limit=manifest['admission_limit'],routes=manifest['routes'],require_invariant_backup=manifest['require_invariant_backup'],**kw)
  expected[config_id(cfg)]=asdict(cfg)
 if len(runs)!=manifest['expected_runs'] or len({r['run_id'] for r in runs})!=len(runs) or {r['run_id'] for r in runs}!=set(expected): raise ValueError('Missing/extra/duplicate runs: '+name)
 for run in runs:
  if run['config']!=expected[run['run_id']]: raise ValueError('Wrong run configuration')
 replay=summarize(runs,manifest)
 for field in ('results_sha256','ranking_discovery','ranking_holdout','passed_empirical_gate'):
  if replay[field]!=summary[field]: raise ValueError('Summary validation failed: '+field)
 dest=out/name;dest.mkdir(parents=True,exist_ok=True)
 for file in ['manifest.json','summary.json','REPORT.md','report.html']: shutil.copyfile(directory/file,dest/file)
 payload=json.dumps(runs,sort_keys=True,allow_nan=False,separators=(',',':')).encode()
 (dest/'runs.json.gz').write_bytes(gzip.compress(payload,mtime=0))
 catalogs[name]={'runs':len(runs),'gate':summary['passed_empirical_gate'],'holdout':summary['ranking_holdout']}
if len(catalogs)!=8 or sum(c['runs'] for c in catalogs.values())!=948: raise ValueError('Incomplete development suite')
write_json(out/'validation.json',{'source_sha256':sha,'total_runs':sum(c['runs'] for c in catalogs.values()),'campaigns':catalogs,'validated':'Exact Cartesian configurations, unique IDs, frozen source, reconstructed summaries and result digests'})
shutil.copyfile(root/'artifacts/iteration03-environment.txt',out/'environment.txt')
shutil.copyfile(root/'artifacts/iteration03-strict-terminal.json',out/'strict-terminal.json')
with tarfile.open(out/'simulator-source.tar.gz','w:gz') as archive:
 for p in sorted((root/'swarm_sim').glob('*.py')): archive.add(p,arcname='swarm_sim/'+p.name)
checksums={str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.rglob('*')) if p.is_file() and p.name!='checksums.json'}
write_json(out/'checksums.json',checksums)
print(json.dumps({'validated_runs':sum(c['runs'] for c in catalogs.values()),'source_sha256':sha,'campaigns':{k:{'runs':v['runs'],'gate':v['gate']} for k,v in catalogs.items()}},indent=2))
