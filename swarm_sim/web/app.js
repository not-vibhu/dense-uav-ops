const $ = (id) => document.getElementById(id);
let catalog,
  run,
  playing = false,
  lastFrame = 0,
  playbackTime = 0;
const canvas = $("airspace"),
  ctx = canvas.getContext("2d");
function metric(label, value) {
  const box = document.createElement("div"),
    name = document.createElement("span"),
    val = document.createElement("strong");
  name.textContent = label;
  val.textContent = value;
  box.append(name, val);
  return box;
}
function populate(select, items) {
  select.replaceChildren();
  for (const [value, label] of items) {
    const o = document.createElement("option");
    o.value = value;
    o.textContent = label;
    select.append(o);
  }
}
async function load() {
  try {
    catalog = await (await fetch("/api/catalog")).json();
    populate(
      $("scenario"),
      Object.keys(catalog.scenarios).map((k) => [k, k.replaceAll("_", " ")]),
    );
    $("scenario").value = "crossing";
    populate($("controller"), [
      ["goal", "Direct goal flight"],
      ["repulsion", "Heuristic repulsion"],
      ["barrier", "Barrier filter"],
      ["negotiated", "Negotiation + barrier"],
    ]);
    $("controller").value = "negotiated";
    description();
    await loadCampaigns();
    draw();
  } catch (e) {
    $("status").textContent = e.message;
  }
}
function description() {
  $("description").textContent =
    catalog.scenarios[$("scenario").value].description;
}
$("scenario").addEventListener("change", description);
for (const [id, output] of [
  ["cooperative", "coop-value"],
  ["fixed", "fixed-value"],
]) {
  $(id).addEventListener(
    "input",
    () => ($(output).textContent = $(id).value + "%"),
  );
}
$("config").addEventListener("submit", async (e) => {
  e.preventDefault();
  playing = false;
  $("play").textContent = "Play";
  $("run").disabled = true;
  $("status").textContent =
    "Simulating dynamics, telemetry and swept collision checks…";
  try {
    const response = await fetch("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        scenario: $("scenario").value,
        controller: $("controller").value,
        drones: Number($("drones").value),
        seed: Number($("seed").value),
        cooperative_fraction: Number($("cooperative").value) / 100,
        fixed_wing_fraction: Number($("fixed").value) / 100,
        duration: Number($("duration").value),
        dt: Number($("dt").value),
      }),
    });
    const data = await response.json();
    if (!response.ok) throw Error(data.error || "Simulation failed");
    run = data;
    const m = data.metrics;
    $("status").textContent =
      `Completed ${data.config.drones} aircraft in ${m.wall_seconds.toFixed(2)} s. ${data.domain === "modeled" ? "Modeled fault bounds." : "Injected fault exceeds modeled bounds."}`;
    $("metrics").replaceChildren(
      metric("Participant collision pairs", m.participant_collision_pairs),
      metric("Separation pairs", m.separation_pairs),
      metric(
        "Goal reach",
        (m.completion_fraction * 100).toFixed(0) + "%",
      ),
      metric("Unresolved filter steps", m.filter_infeasible_drone_steps),
    );
    $("events").textContent = JSON.stringify(
      {
        run_id: data.run_id,
        legacy_only_collision_pairs: m.collision_pairs_ll,
        participant_volume_exits: m.participant_volume_exits,
        vehicle_limit_violations: m.kinematic_violation_drone_steps,
        first_collision_s: m.first_participant_collision_s,
        events: data.events.slice(0, 30),
      },
      null,
      2,
    );
    $("time").max = data.config.duration;
    $("time").value = 0;
    $("time").disabled = false;
    $("play").disabled = false;
    draw();
  } catch (err) {
    $("status").textContent = err.message;
  } finally {
    $("run").disabled = false;
  }
});
function positionsAt(t) {
  const frames = [
    {
      time: 0,
      positions: run.replay.initial_positions,
      active: run.replay.initial_positions.map(() => 1),
    },
    ...run.replay.frames,
  ];
  let i = 0;
  while (i + 1 < frames.length && frames[i + 1].time < t) i++;
  const a = frames[i],
    b = frames[Math.min(i + 1, frames.length - 1)],
    f = Math.min(1, Math.max(0, (t - a.time) / (b.time - a.time || 1)));
  return {
    positions: a.positions.map((p, k) =>
      p.map((x, c) => x + (b.positions[k][c] - x) * f),
    ),
    active: f < 1 ? a.active : b.active,
  };
}
function draw() {
  const rect = canvas.getBoundingClientRect(),
    dpr = window.devicePixelRatio || 1;
  canvas.width = rect.width * dpr;
  canvas.height = rect.height * dpr;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  const w = rect.width,
    h = rect.height;
  ctx.clearRect(0, 0, w, h);
  const area = run?.config.area || 220,
    scale = Math.min(w / (area * 1.65), h / (area * 1.05));
  function project(p) {
    return $("projection").value === "top"
      ? [w / 2 + p[0] * scale * 1.2, h / 2 - p[1] * scale * 1.2]
      : [
          w / 2 + (p[0] - p[1]) * 0.72 * scale,
          h * 0.72 + (p[0] + p[1]) * 0.31 * scale - p[2] * scale * 0.9,
        ];
  }
  ctx.strokeStyle = "#36515b";
  ctx.lineWidth = 0.6;
  for (let a = -area / 2; a <= area / 2; a += 22) {
    for (const points of [
      [
        [a, -area / 2, 0],
        [a, area / 2, 0],
      ],
      [
        [-area / 2, a, 0],
        [area / 2, a, 0],
      ],
    ]) {
      ctx.beginPath();
      points.forEach((p, i) => {
        const xy = project(p);
        i ? ctx.lineTo(...xy) : ctx.moveTo(...xy);
      });
      ctx.stroke();
    }
  }
  ctx.fillStyle = "#9ab2bc";
  ctx.font = "11px system-ui";
  ctx.fillText("220 m × 220 m · altitude 12–116 m", 16, h - 16);
  if (!run) {
    ctx.fillText("Run a simulation to load the replay", w / 2 - 100, h / 2);
    return;
  }
  const t = Number($("time").value);
  $("clock").textContent = t.toFixed(1) + " s";
  const view = positionsAt(t),
    replay = run.replay;
  for (const o of replay.obstacles) {
    const xy = project(o);
    ctx.beginPath();
    ctx.fillStyle = "#71828b55";
    ctx.strokeStyle = "#8096a3";
    ctx.ellipse(
      xy[0],
      xy[1],
      o[3] * scale,
      o[3] * scale * 0.6,
      0,
      0,
      Math.PI * 2,
    );
    ctx.fill();
    ctx.stroke();
  }
  const collisionIds = new Set(
    run.events
      .filter(
        (e) =>
          e.type === "physical_collision" && e.time <= t && e.time >= t - 1,
      )
      .flatMap((e) => e.aircraft),
  );
  const order = view.positions
    .map((p, i) => ({ p, i }))
    .sort((a, b) => a.p[2] - b.p[2]);
  for (const { p, i } of order) {
    if (!view.active[i]) continue;
    const xy = project(p),
      cooperative = replay.cooperative[i],
      fixed = replay.fixed_wing[i];
    ctx.fillStyle = cooperative ? "#83e1d0" : "#f5b084";
    ctx.globalAlpha = 0.85;
    ctx.beginPath();
    if (fixed) {
      ctx.moveTo(xy[0], xy[1] - 4.5);
      ctx.lineTo(xy[0] - 3.7, xy[1] + 3);
      ctx.lineTo(xy[0] + 3.7, xy[1] + 3);
      ctx.closePath();
    } else ctx.arc(xy[0], xy[1], 3, 0, Math.PI * 2);
    ctx.fill();
    if (collisionIds.has(i)) {
      ctx.strokeStyle = "#ff6f80";
      ctx.lineWidth = 1.6;
      ctx.beginPath();
      ctx.arc(xy[0], xy[1], 8, 0, Math.PI * 2);
      ctx.stroke();
    }
  }
  ctx.globalAlpha = 1;
}
$("projection").addEventListener("change", draw);
$("time").addEventListener("input", () => {
  playing = false;
  $("play").textContent = "Play";
  draw();
});
$("play").addEventListener("click", () => {
  playing = !playing;
  $("play").textContent = playing ? "Pause" : "Play";
  if (playing) {
    if (Number($("time").value) >= Number($("time").max)) $("time").value = 0;
    playbackTime = Number($("time").value);
    lastFrame = performance.now();
    requestAnimationFrame(animate);
  }
});
function animate(now) {
  if (!playing) return;
  playbackTime += ((now - lastFrame) / 1000) * 2;
  lastFrame = now;
  $("time").value = Math.min(playbackTime, Number($("time").max));
  draw();
  if (playbackTime >= Number($("time").max)) {
    playing = false;
    $("play").textContent = "Play";
  } else requestAnimationFrame(animate);
}
async function loadCampaigns() {
  const names = await (await fetch("/api/campaigns")).json();
  populate(
    $("campaign"),
    names.map((x) => [x, x]),
  );
  if (names.length) await showCampaign();
}
async function showCampaign() {
  const response = await fetch(
    "/api/summary?campaign=" + encodeURIComponent($("campaign").value),
  );
  const s = await response.json();
  if (!response.ok) {
    $("campaign-status").textContent = s.error;
    return;
  }
  $("campaign-status").textContent =
    `${s.completed_runs.toLocaleString()} runs across ${s.manifest.scenarios.length} scenarios. Discovery choice: ${s.selected_on_discovery}; holdout ${s.selection_stable_on_holdout ? "stable" : "unstable"}. ${s.passed_empirical_gate ? "Empirical gate passed." : "No configuration cleared the safety gate."}`;
  $("comparison-rows").replaceChildren();
  for (const r of s.ranking_holdout) {
    const tr = document.createElement("tr");
    for (const value of [
      r.controller,
      (r.participant_collision_run_rate * 100).toFixed(1) + "%",
      (r.participant_obstacle_run_rate * 100).toFixed(1) + "%",
      (r.participant_volume_exit_run_rate * 100).toFixed(1) + "%",
      (r.participant_completion_fraction * 100).toFixed(1) + "%",
      r.filter_infeasible_drone_steps.toLocaleString(),
    ]) {
      const td = document.createElement("td");
      td.textContent = value;
      tr.append(td);
    }
    $("comparison-rows").append(tr);
  }
}
$("campaign").addEventListener("change", showCampaign);
window.addEventListener("resize", draw);
load();
