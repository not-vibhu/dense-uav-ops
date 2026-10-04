"""Render a signed simulation replay as an offline inspectable HTML file."""
import argparse
import json
from pathlib import Path
from dense_ops.audit import verify


HTML = '''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>dense-uav-ops · Distributed replay</title>
<style>
body{margin:0;background:#10161c;color:#e2e8eb;font:15px system-ui}main{max-width:1100px;margin:auto;padding:26px}
h1{font-size:28px;margin-bottom:5px}.muted{color:#a3b5bd}header{margin-bottom:23px}.cards{display:flex;flex-wrap:wrap;gap:12px}
.card{flex:1;min-width:150px;background:#1b2831;padding:14px;border-radius:9px}.card b{display:block;font-size:24px;margin:5px 0}
canvas{background:#14212a;border:1px solid #34434d;border-radius:9px;width:100%;margin:18px 0;aspect-ratio:1.7}
input{width:65%;vertical-align:middle}button{background:#83dfc4;color:#10211e;border:0;border-radius:5px;padding:9px 20px;cursor:pointer}
.legend{margin:12px 0;display:flex;gap:22px}ul{color:#efcda3}footer{color:#a3b5bd;line-height:1.6;margin-top:22px}
</style><main><header><div class="muted">DENSE UAV OPS · RESEARCH V0.4</div>
<h1>Distributed flight replay</h1><div id="description" class="muted"></div></header>
<div class="cards" id="cards"></div><canvas id="plot" width="1020" height="600"></canvas>
<button id="play">Play</button> <input id="slider" type="range" min="0" value="0"> <span id="time"></span>
<div class="legend"><span style="color:#83dfc4">● Cooperative UAS</span><span style="color:#fac783">● Broadcast-only UAS</span><span style="color:#ff8195">▲ Manned traffic</span></div>
<h3>Failed requirements</h3><ul id="blockers"></ul>
<footer>Top-down projection; altitude is printed beside active aircraft. Queued and completed aircraft are faint.
Signatures and the checkpoint were verified when this file was generated. A signature attests a record's author; it does not establish sensor truth.
This view does not display uncertainty tubes, obstacles or maneuver certificates. Review the JSON and implementation guide for those conditions.
The displayed batch-fleet occupancy is not operational airspace capacity.</footer></main>
<script>const data=__DATA__;
const d=data.experiment,m=data.metrics,plot=document.getElementById('plot'),ctx=plot.getContext('2d'),slider=document.getElementById('slider');
document.getElementById('description').textContent=`${d.scenario} · ${d.mode} · ${d.guard} · ${d.drones} UAS + ${d.manned} manned · seed ${d.seed}`;
for(const [label,value] of [['Collision pairs',m.collision_pairs],['Separation breach pairs',m.protected_breach_pairs],['Cooperative completion',`${(100*m.completion_fraction).toFixed(0)}%`],['Peak occupancy',m.peak_occupancy]]){
 const div=document.createElement('div');div.className='card';const title=document.createElement('span');title.textContent=label;const v=document.createElement('b');v.textContent=value;div.append(title,v);document.getElementById('cards').append(div);
}
for(const blocker of data.blockers){const li=document.createElement('li');li.textContent=blocker.replaceAll('_',' ');document.getElementById('blockers').append(li);}
slider.max=data.replay.length-1;const cooperative=new Set(data.cooperative),scale=Math.min(850/d.area,500/d.area),cx=510,cy=300;
const xy=p=>[cx+p[0]*scale,cy-p[1]*scale];
function draw(){const f=data.replay[Number(slider.value)];ctx.clearRect(0,0,1020,600);ctx.strokeStyle='#263943';ctx.lineWidth=1;
for(let x=-d.area/2;x<=d.area/2;x+=d.area/8){let a=xy([x,-d.area/2]),b=xy([x,d.area/2]);ctx.beginPath();ctx.moveTo(...a);ctx.lineTo(...b);ctx.stroke();}
for(let y=-d.area/2;y<=d.area/2;y+=d.area/8){let a=xy([-d.area/2,y]),b=xy([d.area/2,y]);ctx.beginPath();ctx.moveTo(...a);ctx.lineTo(...b);ctx.stroke();}
ctx.strokeStyle='#637884';const a=xy([-d.area/2,d.area/2]);ctx.strokeRect(a[0],a[1],d.area*scale,d.area*scale);
f.positions.forEach((p,i)=>{const [x,y]=xy(p),man=i>=d.drones;ctx.globalAlpha=f.active[i]?1:.23;ctx.fillStyle=man?'#ff8195':cooperative.has(i)?'#83dfc4':'#fac783';ctx.beginPath();
if(man){ctx.moveTo(x,y-7);ctx.lineTo(x-6,y+5);ctx.lineTo(x+6,y+5);ctx.closePath();}else ctx.arc(x,y,4,0,2*Math.PI);ctx.fill();
if(f.active[i]){ctx.font='11px system-ui';ctx.fillText(`${i} · ${p[2].toFixed(0)}m`,x+8,y-6);}});ctx.globalAlpha=1;document.getElementById('time').textContent=`${f.time.toFixed(1)} s`;}
let playing=false,last=0;document.getElementById('play').onclick=()=>{playing=!playing;document.getElementById('play').textContent=playing?'Pause':'Play';if(Number(slider.value)===Number(slider.max))slider.value=0;};slider.oninput=draw;
function tick(t){if(playing&&t-last>100){slider.value=Math.min(Number(slider.max),Number(slider.value)+1);draw();last=t;if(Number(slider.value)===Number(slider.max)){playing=false;document.getElementById('play').textContent='Play';}}requestAnimationFrame(tick);}draw();requestAnimationFrame(tick);
</script></html>'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('replay', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    run = json.loads(args.replay.read_text())
    verify(run['audit']['events'], run['audit']['public'], run['audit']['anchor'])
    if not run.get('replay'): raise ValueError('Replay frames required')
    from swarm_sim.config import Config
    from swarm_sim.scenarios import build_world
    e = run['experiment']
    world = build_world(Config(drones=e['drones'], scenario=e['scenario'], seed=e['seed'], area=e['area'],
                              cooperative_fraction=e['cooperative_fraction'], fixed_wing_fraction=e['fixed_wing_fraction']))
    data = {key: run[key] for key in ('experiment','metrics','blockers','replay')}
    data['cooperative'] = [int(i) for i, yes in enumerate(world['cooperative']) if yes]
    encoded = json.dumps(data, allow_nan=False).replace('<', '\\u003c')
    args.out.write_text(HTML.replace('__DATA__', encoded))
    print(args.out)


if __name__ == '__main__':
    main()
