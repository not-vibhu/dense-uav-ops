"""Self-contained HTML replay of one recorded run (top-down view, altitude as shade)."""
import html
import json

TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Run replay</title>
<style>
:root{--bg:#fafaf8;--fg:#1d1d1b;--muted:#6b6b66;--line:#d8d6cf;--ctl:#2563a8;--unc:#c2650a;--man:#b42318;--ev:#7a1fa2}
@media (prefers-color-scheme:dark){:root{--bg:#161615;--fg:#ecebe6;--muted:#a3a29b;--line:#3a3935;--ctl:#6aa5e8;--unc:#f0a052;--man:#f07068;--ev:#c98ce0}}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,sans-serif}
main{max-width:980px;margin:0 auto;padding:16px}
h1{font-size:18px;margin:0 0 4px}p{margin:4px 0;color:var(--muted)}
canvas{width:100%;max-width:720px;aspect-ratio:1;border:1px solid var(--line);display:block;margin:12px 0}
.row{display:flex;gap:12px;align-items:center;flex-wrap:wrap}
input[type=range]{flex:1;min-width:200px}
.key span{display:inline-block;width:10px;height:10px;border-radius:50%;margin:0 4px 0 12px;vertical-align:middle}
pre{white-space:pre-wrap;font-size:12px;color:var(--muted);max-height:220px;overflow:auto;border-top:1px solid var(--line);padding-top:8px}
</style></head><body><main>
<h1>__TITLE__</h1><p>__SUBTITLE__</p>
<p class="key"><span style="background:var(--ctl)"></span>controlled UAS<span style="background:var(--unc)"></span>uncontrolled UAS<span style="background:var(--man)"></span>manned<span style="background:var(--ev)"></span>event (LoS or contact)</p>
<canvas id="c" width="1200" height="1200"></canvas>
<div class="row"><button id="play">Play</button><input id="t" type="range" min="0" value="0" step="1"><span id="clock"></span></div>
<pre id="log"></pre>
<p>Simulation replay of a research model. Positions are true (oracle) states; aircraft did not see each other this precisely.</p>
</main><script>
const D=__DATA__;const c=document.getElementById('c'),g=c.getContext('2d'),s=document.getElementById('t');
s.max=D.frames.length-1;const css=n=>getComputedStyle(document.documentElement).getPropertyValue(n);
const [lo,hi]=D.bounds,span=Math.max(hi[0]-lo[0],hi[1]-lo[1])*1.08,cx=(lo[0]+hi[0])/2,cy=(lo[1]+hi[1])/2;
const X=x=>(x-cx)/span*c.width+c.width/2,Y=y=>c.height/2-(y-cy)/span*c.height,S=r=>Math.max(3,r/span*c.width);
function draw(k){const f=D.frames[k];g.clearRect(0,0,c.width,c.height);g.strokeStyle=css('--line');g.lineWidth=2;
g.strokeRect(X(lo[0]),Y(hi[1]),X(hi[0])-X(lo[0]),Y(lo[1])-Y(hi[1]));g.fillStyle=css('--line');
for(const o of D.obstacles){g.beginPath();g.arc(X(o[0]),Y(o[1]),o[3]/span*c.width,0,7);g.fill();}
const recent=new Set(D.events.filter(e=>e.time<=f.t&&e.time>f.t-2).flatMap(e=>e.pair));
f.id.forEach((id,i)=>{const p=f.p[i];const z=(p[2]-lo[2])/Math.max(1,hi[2]-lo[2]);
g.globalAlpha=0.45+0.55*Math.min(1,Math.max(0,z));g.fillStyle=css(D.manned[id]?'--man':D.controlled[id]?'--ctl':'--unc');
g.beginPath();g.arc(X(p[0]),Y(p[1]),S(D.radius[id])*1.6,0,7);g.fill();
if(recent.has(id)){g.globalAlpha=1;g.strokeStyle=css('--ev');g.lineWidth=3;g.beginPath();g.arc(X(p[0]),Y(p[1]),S(D.radius[id])*4,0,7);g.stroke();}});
g.globalAlpha=1;document.getElementById('clock').textContent=f.t.toFixed(1)+' s, '+f.id.length+' airborne';}
s.oninput=()=>draw(+s.value);let timer=null;document.getElementById('play').onclick=e=>{if(timer){clearInterval(timer);timer=null;e.target.textContent='Play';return;}
e.target.textContent='Pause';timer=setInterval(()=>{s.value=(+s.value+1)%(+s.max+1);draw(+s.value);},60);};
document.getElementById('log').textContent=D.events.map(e=>e.time.toFixed(1)+' s  '+e.type+'  '+e.category+'  aircraft '+e.pair.join(', ')).join('\\n')||'No events in the measurement window.';
draw(0);
</script></body></html>
"""


def render(result):
    replay = result['replay']
    e = result['experiment']
    m = result['metrics']
    title = f"{e['name']}: {e['controller']['kind']} controller, seed {e['seed']}"
    subtitle = (f"{e['demand']['uas_per_hour']:g} UAS/h offered, assumed traffic acceleration "
                f"{e['assumptions']['traffic_acceleration_mps2']:g} m/s², {m['attributable_los']} attributable LoS, "
                f"{m['attributable_contacts']} attributable contacts in the measurement window.")
    data = json.dumps(replay, separators=(',', ':')).replace('</', '<\\/')
    return (TEMPLATE.replace('__TITLE__', html.escape(title)).replace('__SUBTITLE__', html.escape(subtitle))
            .replace('__DATA__', data))
