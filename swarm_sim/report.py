import html
import json


def report_markdown(s):
    m = s["manifest"]
    text = ["# Mixed fleet safety comparison", "",
            f"Completed **{s['completed_runs']} / {s['expected_runs']}** reproducible runs. "
            f"Fleet sizes: {m['counts']}; cooperative fractions: {m['fractions']}; "
            f"fixed-wing fraction: {m['fixed_wing_fraction']}. Every catalog scenario was evaluated only if listed in the manifest.", "",
            f"Discovery choice: **{s['selected_on_discovery']}**. Stable on holdout: **{s['selection_stable_on_holdout']}**. "
            f"Empirical safety gate passed: **{s['passed_empirical_gate']}**.", "",
            "The gate requires zero participating-aircraft collisions, zero obstacle collisions, zero volume exits, zero unresolved barrier steps or failed predictive libraries, zero vehicle-limit violations, zero unavailable-backup steps, zero observed command deadline misses, at least 70% admission and at least 70% participating goal reach on holdout. Requested demand is the denominator. A gate pass would still be a finite-suite result, not a flight safety proof.", "",
            "## Holdout results", "",
            "| Controller | Collision runs | Obstacle runs | Volume exit runs | Separation exposure | Goal reach | Unresolved control steps |",
            "|---|---:|---:|---:|---:|---:|---:|"]
    for r in s["ranking_holdout"]:
        text.append(f"| {r['controller']} | {r['participant_collision_run_rate']:.1%} | "
                    f"{r['participant_obstacle_run_rate']:.1%} | {r['participant_volume_exit_run_rate']:.1%} | "
                    f"{r['separation_exposure_ratio']:.2%} | {r['participant_completion_fraction']:.1%} | "
                    f"{r['filter_infeasible_drone_steps'] + r.get('predictive_no_admissible_drone_steps', 0)} |")
    text += ["", "## Service and backup availability", "",
             f"Admission: {m.get('admission','off')}; capacity: {m.get('admission_limit','unlimited')}; routes: {m.get('routes','off')}.", "",
             "| Controller | Admitted / requested | Queued | Route rejected | Backup unavailable steps | Deadline-miss runs | Mean fleet p99 ms |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for r in s['ranking_holdout']:
        text.append(f"| {r['controller']} | {r.get('participant_admission_fraction',1.):.1%} | "
                    f"{r.get('queued_aircraft',0)} | {r.get('route_rejected_aircraft',0)} | "
                    f"{r.get('backup_unavailable_drone_steps',0)} | {r.get('command_deadline_exceeded_runs',0)} | "
                    f"{r['mean_command_p99_ms']:.2f} |")
    text += ["", "Collision run rates count encounters involving at least one equipped participant. Legacy–legacy collision pairs are published separately and are not attributed to control authority the system does not have. Zero-cooperation runs are included in raw results but excluded from controller ranking.", "",
             "Separation exposure is the fraction of active participating pair-time steps whose continuous swept trajectory crossed the 10 m boundary. A touched step counts its entire duration, so this is an upper step-based exposure measure. Collision thresholds use the sum of physical radii. Minimum distance away from threat thresholds is a conservative chord lower bound.", "",
             "## Interpretation", ""]
    if not s["passed_empirical_gate"]:
        text.append("**No configuration cleared the safety gate.** The discovery choice is a lower-risk research candidate under the published lexicographic ordering, not a deployment recommendation. Inspect failed scenarios and unresolved constraints; lower demand, better sensing, route redesign and admission control may be required.")
    else:
        text.append("The discovery choice cleared the empirical gate on this suite. Validate additional seeds, dynamics, timing, sensing and applicable operational requirements before extending the claim.")
    text += ["", "## Coverage and provenance", "",
             f"Discovery seeds: {m['discovery_seeds']}; holdout seeds: {m['holdout_seeds']}. "
             f"Step: {m['dt_s']} s; encounter duration: {m['duration_s']} s. "
             f"Source SHA-256: `{m['source_sha256']}`.", "",
             "The simulator uses a common synthetic regional feed, approximate finite-projection barriers, idealized mixed point-mass dynamics and absorbing goals. It does not implement authenticated ASTM messaging, an exact ORCA or QP solver, joint invariant traffic safety, RF propagation, impact/wreckage physics, or aircraft aerodynamic certification. Intentional out-of-bounds faults are separated in summary.json. Optional recurrent imitation and masked MAPPO policies are trained separately and pinned in the manifest when evaluated. Admission and static routes report unserved demand. Checked backups cover finite traffic envelopes; the limited static hover bound is not a mixed-fleet invariance proof. Goal reach includes diagnostic trajectories continuing after collisions and is not a successful real mission rate.", "",
             "See manifest.json, runs.jsonl, results.json and summary.json for every configuration and outcome. Reported timing is measured on this host, includes Python overhead, and cannot establish an onboard real-time deadline.", ""]
    return "\n".join(text)


def report_html(s):
    data = json.dumps(s, allow_nan=False).replace("<", "\\u003c")
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Federated swarm · Safety comparison</title><style>
:root{color-scheme:dark;--bg:#10191e;--fg:#e4eef0;--muted:#a3b8be;--line:#31444d;--accent:#75dfca;--alert:#ffa578}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px system-ui,sans-serif}main{max-width:1120px;margin:auto;padding:36px 24px}h1{font-size:32px;font-weight:600}h2{font-size:20px;margin-top:32px}p{line-height:1.65;color:var(--muted)}.status{padding:18px;border-left:3px solid var(--alert);background:#19262c}label{display:block;margin:20px 0}select{font:inherit;padding:8px;background:var(--bg);color:var(--fg);border:1px solid var(--line);border-radius:6px}table{width:100%;border-collapse:collapse}th,td{padding:14px 10px;text-align:right;border-bottom:1px solid var(--line);font-variant-numeric:tabular-nums}th:first-child,td:first-child{text-align:left}th{font-weight:500;color:var(--muted)}.table-wrap{overflow:auto}.bar-row{display:grid;grid-template-columns:110px 1fr 65px;gap:14px;align-items:center;margin:15px 0}.track{background:#23343c;height:14px}.bar{background:var(--accent);height:100%}.two{display:grid;grid-template-columns:1fr 1fr;gap:48px}small{color:var(--muted)}@media(max-width:700px){.two{display:block}main{padding:20px 14px}}
</style></head><body><main><small>FEDERATED SWARM / MIXED FLEET EXPERIMENT</small><h1>Which controller reduces observed risk?</h1><p id="scope"></p><div class="status" id="status"></div><label>Comparison scope <select id="scenario"><option value="all">All holdout scenarios</option><option value="bounded">Modeled fault bounds</option><option value="outside">Out-of-bounds faults</option></select></label><div class="two"><section><h2>Participating collision runs</h2><div id="risk"></div><small>Lower is better · fraction of scenario runs</small></section><section><h2>Participating goal reach</h2><div id="progress"></div><small>Higher is better · holding indefinitely does not clear the gate</small></section></div><h2>Safety before efficiency</h2><div class="table-wrap"><table><thead><tr><th>Controller</th><th>Collision runs</th><th>Obstacle runs</th><th>Volume exits</th><th>Separation exposure</th><th>Admitted</th><th>Goal reach / requested</th><th>Unresolved steps</th><th>Backup unavailable</th></tr></thead><tbody id="rows"></tbody></table></div><h2>What these results establish</h2><p>Every controller uses the same seeded traffic and observations. Fixed-wing aircraft have a minimum horizontal airspeed, turn-rate and climb limit; legacy aircraft never negotiate. Collision checks resolve constant-acceleration motion between samples. The barrier solver reports residual failures; the predictive planner reports a failed library whenever no candidate clears its conservative horizon checks. Checked mode uses independently checked finite backups. A limited static hover bound does not establish invariant mixed-fleet traffic safety. Optional recurrent actors rank checked candidates; all active traffic remains in the safety checker.</p><p>Ranking prioritizes participant collisions, obstacle collisions, volume exits, worst-stratum collision rate, separation exposure and then completion. Zero-cooperation runs are excluded from ranking; legacy-only collisions remain in raw results. Reported rates describe a finite scenario suite.</p><p>No flight certification, RF/ASTM conformance, aerodynamic validation or universally safest configuration is established. Negotiate and barrier variants use full intruder motion bounds; negotiation is an emulation rather than the signed production protocol.</p><small id="provenance"></small></main><script>
const S=__DATA__;
const pct=v=>(100*v).toFixed(1)+'%';
document.getElementById('scope').textContent=`${S.completed_runs.toLocaleString()} runs · ${S.manifest.counts.join(', ')} aircraft · ${S.manifest.fixed_wing_fraction*100}% fixed-wing · cooperative fractions ${S.manifest.fractions.join(', ')} · ${S.manifest.scenarios.length} scenarios.`;
document.getElementById('status').textContent=`Discovery choice: ${S.selected_on_discovery}. Holdout selection ${S.selection_stable_on_holdout?'stable':'unstable'}. ${S.passed_empirical_gate?'Passed the finite-suite empirical gate.':'No configuration cleared the empirical safety gate.'}`;
document.getElementById('provenance').textContent=`Discovery seeds ${S.manifest.discovery_seeds.join(', ')} · holdout seeds ${S.manifest.holdout_seeds.join(', ')} · step ${S.manifest.dt_s}s · source ${S.manifest.source_sha256}`;
const select=document.getElementById('scenario');Object.keys(S.per_scenario_holdout).forEach(name=>{let o=document.createElement('option');o.value=name;o.textContent=name.replaceAll('_',' ');select.append(o)});
function draw(){let rows=select.value==='all'?S.ranking_holdout:select.value==='bounded'?S.in_domain_holdout:select.value==='outside'?S.out_of_bounds_holdout:S.per_scenario_holdout[select.value];document.getElementById('rows').replaceChildren();['risk','progress'].forEach(id=>document.getElementById(id).replaceChildren());for(const r of rows){let tr=document.createElement('tr');for(const x of [r.controller,pct(r.participant_collision_run_rate),pct(r.participant_obstacle_run_rate),pct(r.participant_volume_exit_run_rate),pct(r.separation_exposure_ratio),pct(r.participant_admission_fraction??1),pct(r.participant_completion_fraction),(r.filter_infeasible_drone_steps+(r.predictive_no_admissible_drone_steps||0)).toLocaleString(),(r.backup_unavailable_drone_steps||0).toLocaleString()]){let td=document.createElement('td');td.textContent=x;tr.append(td)}document.getElementById('rows').append(tr);for(const [id,value] of [['risk',r.participant_collision_run_rate],['progress',r.participant_completion_fraction]]){let row=document.createElement('div');row.className='bar-row';let label=document.createElement('span');label.textContent=r.controller;let track=document.createElement('div');track.className='track';let bar=document.createElement('div');bar.className='bar';bar.style.width=(value*100)+'%';track.append(bar);let val=document.createElement('span');val.textContent=pct(value);row.append(label,track,val);document.getElementById(id).append(row)}}}select.addEventListener('change',draw);draw();
</script></body></html>""".replace("__DATA__", data)
