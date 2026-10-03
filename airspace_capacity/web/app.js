const $ = id => document.getElementById(id);
const labels = {
  area_m:'Airspace side length · m', cooperative_fraction:'Cooperative drone fraction · 0–1',
  compliance_fraction:'Conforming drone fraction · 0–1', fixed_wing_fraction:'Fixed-wing drone fraction · 0–1',
  manned_operations_per_hour:'Manned demand · operations/hour', manned_speed_mps:'Manned cruise speed · m/s',
  manned_separation_m:'Manned protection distance · m', position_error_m:'Position error bound · m',
  telemetry_latency_s:'Surveillance latency · s', manned_detection_fraction:'Manned detection fraction · 0–1',
  sensor_range_m:'Surveillance range · m', uas_separation_m:'UAS protection distance · m',
  hardware_time_multiplier:'Target hardware timing multiplier · synthetic', command_deadline_ms:'Command deadline · ms',
  minimum_completion_fraction:'Minimum cohort completion · 0–1', maximum_p95_wait_s:'Maximum p95 entry wait · s',
  failure_probability_per_run:'Maximum modeled failure probability per run', confidence:'Simultaneous confidence · 0–1',
  warmup_s:'Warm-up window · s', measurement_s:'Measurement window · s', drain_s:'Drain window · s',
  maximum_backlog_growth:'Maximum backlog growth · aircraft'
};
const conditions = ['area_m','cooperative_fraction','compliance_fraction','fixed_wing_fraction',
  'manned_operations_per_hour','manned_speed_mps','manned_separation_m','uas_separation_m',
  'position_error_m','telemetry_latency_s','manned_detection_fraction','sensor_range_m',
  'hardware_time_multiplier','command_deadline_ms'];
const requirements = ['minimum_completion_fraction','maximum_p95_wait_s','maximum_backlog_growth',
  'failure_probability_per_run','confidence','warmup_s','measurement_s','drain_s'];
const scenarios = ['crossing','corridor','urban','manned_intrusion','sensor_outage','wind_gust'];
let defaults, latest, submitted;
function populate(profile) {
  for (const field of [...conditions,...requirements]) $(field).value = profile[field];
  $('profile-json').value = JSON.stringify(profile,null,2);
  document.querySelectorAll('#scenarios input').forEach(input=>input.checked=input.value===profile.scenario);
}
function makeFields(container, keys) {
  for (const key of keys) {
    const label = document.createElement('label');
    label.textContent = labels[key];
    const input = document.createElement('input');
    input.id = key; input.type = 'number'; input.step = key === 'maximum_backlog_growth' ? '1' : 'any'; input.required = true;
    label.append(input); $(container).append(label);
  }
}
function values(id) {
  const raw = $(id).value.split(/[\s,]+/).filter(Boolean).map(Number);
  if (!raw.length || raw.some(x=>!Number.isFinite(x))) throw new Error('Enter finite numeric grid values.');
  return raw;
}
function show(result) {
  latest = {...result, configuration:submitted};
  const s = result.summary;
  $('results').hidden = false;
  $('observed').textContent = s.maximum_observed_passing_uas_demand_per_hour === null ? 'Not demonstrated' : `${s.maximum_observed_passing_uas_demand_per_hour} ops/h`;
  $('supported').textContent = s.maximum_statistically_supported_tested_uas_demand_per_hour === null ? 'Not demonstrated' : `${s.maximum_statistically_supported_tested_uas_demand_per_hour} ops/h`;
  $('outcome').textContent = 'The table separates UAS demand, total demand including manned traffic, measured exits and concurrent occupancy. A missing capacity value means the requirements were not demonstrated; it does not mean the airspace has zero physical capacity.';
  $('rows').replaceChildren();
  for (const r of s.cells) {
    const tr = document.createElement('tr');
    const cells = [r.scenario.replaceAll('_',' '), r.uas_demand_per_hour, r.total_demand_per_hour,
      r.occupancy_limit,r.observed_total_throughput_min_per_hour.toFixed(1),r.observed_peak_total_occupancy,
      r.observed_requirements_pass ? 'Pass' : 'Blocked', (r.failure_probability_upper*100).toFixed(2)+'%',
      r.blockers.map(x=>x.replaceAll('_',' ')).join(' · ') || 'None in tested model'];
    cells.forEach((value,i)=>{
      const td = document.createElement('td');
      if (i===6) { const span=document.createElement('span'); span.className='badge '+(r.observed_requirements_pass?'pass':'fail'); span.textContent=value; td.append(span); }
      else td.textContent = value;
      tr.append(td);
    });
    $('rows').append(tr);
  }
  $('limitations').replaceChildren();
  s.limits.forEach(text=>{ const li=document.createElement('li'); li.textContent=text; $('limitations').append(li); });
  $('provenance').textContent = `Evidence saved to ${result.output}. Source SHA-256: ${s.source_sha256}`;
}
async function poll(id) {
  const response = await fetch('/api/jobs/'+id); const job = await response.json();
  if (!response.ok) throw new Error(job.error);
  $('status').textContent = `${job.completed} / ${job.total} simulations ${job.state}`;
  if (job.state === 'complete') { show(job); $('run').disabled=false; }
  else if (job.state === 'failed') { $('error').textContent=job.error; $('run').disabled=false; }
  else setTimeout(()=>poll(id).catch(error=>{ $('error').textContent=error.message; $('run').disabled=false; }),750);
}
$('campaign').addEventListener('submit',async event=>{
  event.preventDefault(); $('error').textContent='';
  try {
    const profile=JSON.parse($('profile-json').value);
    [...conditions,...requirements].forEach(key=>profile[key]=Number($(key).value));
    const chosen=[...document.querySelectorAll('#scenarios input:checked')].map(input=>input.value);
    const body={profile,rates:values('rates'),limits:values('limits'),seeds:values('seeds'),scenarios:chosen};
    $('run').disabled=true; $('status').textContent='Preparing campaign…';
    const response=await fetch('/api/campaign',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const result=await response.json();
    if (!response.ok) throw new Error(result.error);
    submitted=body;
    await poll(result.id);
  } catch(error) { $('error').textContent=error.message; $('run').disabled=false; $('status').textContent='Configuration needs attention'; }
});
$('apply-profile').addEventListener('click',()=>{
  try { populate({...defaults,...JSON.parse($('profile-json').value)}); $('error').textContent=''; }
  catch(error) { $('error').textContent=error.message; }
});
$('export').addEventListener('click',()=>{
  if (!latest) return;
  const text=JSON.stringify(latest,null,2);
  $('export-json').value=text;
  $('download-json').href='data:application/json;charset=utf-8,'+encodeURIComponent(text);
  $('export-panel').hidden=false;
});
makeFields('conditions',conditions); makeFields('requirements',requirements);
scenarios.forEach((scenario,i)=>{
  const label=document.createElement('label'); const input=document.createElement('input');
  input.type='checkbox'; input.value=scenario; input.checked=i===0;
  label.append(input,document.createTextNode(scenario.replaceAll('_',' '))); $('scenarios').append(label);
});
fetch('/api/defaults').then(r=>r.json()).then(profile=>{ defaults=profile; populate(profile); }).catch(error=>$('error').textContent=error.message);
