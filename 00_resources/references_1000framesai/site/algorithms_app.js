// Algorithms page: built-in algorithm cards with hover previews and task links.
import { algorithms, ApiError, runs } from "../shared/api.js";

const ORDER = ["go2_rl_gym", "wheel_leg_rl_gym", "wheel_leg_gait_rl_gym", "wheel_leg_jump_rl_gym", "wheel_leg_high_speed", "wheel_leg_gait_hip_degradation", "amp_cts", "np3o", "quadrupedal_agility", "parkour", "omni_jump"];
const META = {
  go2_rl_gym: {
    label: "Go2 RL Gym",
    abbr: "PPO",
    tint: "rgba(20,184,166,.16)",
    color: "#5eead4",
    desc: "Built-in legged_gym / rsl_rl PPO backend for Go2 velocity tracking.",
    tags: ["PPO", "legged_gym", "ONNX"],
    media: {
      poster: "./media/go2_rl_gym.webp",
      video: "./media/go2_rl_gym.webm",
      label: "sim2sim / cross slope",
    },
  },
  wheel_leg_rl_gym: {
    label: "Wheel-Leg MoE-CTS",
    abbr: "MOE",
    tint: "rgba(245,158,11,.15)",
    color: "#fbbf24",
    desc: "MoE-CTS training for standardized 16-DoF wheel-leg robots, with W1W retained as the validated built-in baseline.",
    tags: ["MoE-CTS", "16-DoF", "wheel-leg"],
  },
  wheel_leg_gait_rl_gym: {
    label: "Wheel-Leg Gait MoE-CTS",
    abbr: "GAIT",
    tint: "rgba(16,185,129,.15)",
    color: "#34d399",
    desc: "Gait-switch MoE-CTS with a 0.7 s phase clock, enabled on 25% of training episodes with a lighter Barrier influence.",
    tags: ["MoE-CTS", "gait", "10-frame history", "wheel-leg"],
  },
  wheel_leg_gait_hip_degradation: {
    label: "Wheel-Leg Gait Full-Torque MoE-CTS",
    abbr: "GAIT+",
    tint: "rgba(14,165,233,.15)",
    color: "#38bdf8",
    desc: "Sin/cos gait phase input with a 0.7 s diagonal clock and 25% gait episodes, while retaining the full dynamic Hip torque envelope.",
    tags: ["MoE-CTS", "sin/cos phase", "full torque", "wheel-leg"],
  },
  wheel_leg_jump_rl_gym: {
    label: "Wheel-Leg Jump MoE-CTS",
    abbr: "JUMP",
    tint: "rgba(249,115,22,.16)",
    color: "#fb923c",
    desc: "Normal wheel-leg walking with an explicit Space/button jump command, trained on flat terrain first.",
    tags: ["MoE-CTS", "jump", "16-DoF", "flat"],
  },
  wheel_leg_high_speed: {
    label: "Wheel-Leg High-Speed",
    abbr: "FAST",
    tint: "rgba(239,68,68,.14)",
    color: "#f87171",
    desc: "High-speed wheel-leg curriculum that raises or lowers the speed range from measured tracking quality on flat and simple sloped terrain.",
    tags: ["MoE-CTS", "8 m/s", "curriculum", "wheel-leg"],
  },
  amp_cts: {
    label: "W1W AMP MoE-CTS",
    abbr: "AMP",
    tint: "rgba(22,163,74,.16)",
    color: "#4ade80",
    desc: "W1W-only AMP motion-prior training layered on the production MoE-CTS rewards and controls.",
    tags: ["AMP", "MoE-CTS", "W1W", "54D motion prior"],
  },
  np3o: {
    label: "NP3O",
    abbr: "P3O",
    tint: "rgba(96,165,250,.16)",
    color: "#93c5fd",
    desc: "Constraint-aware NP3O backend with estimated velocity and history observations.",
    tags: ["NP3O", "history", "ONNX"],
    media: {
      poster: "./media/np3o.webp",
      video: "./media/np3o.webm",
      label: "sim2sim / stairs",
    },
  },
  quadrupedal_agility: {
    label: "Quadrupedal Agility",
    abbr: "TSC",
    tint: "rgba(245,158,11,.15)",
    color: "#fbbf24",
    desc: "TSC Go2 agility task with the upstream deploy checkpoint and fused low-level ONNX Sim2Sim path wired for validation.",
    tags: ["TSC", "Go2", "agility"],
    media: {
      poster: "./media/quadrupedal_agility.webp",
      video: "./media/quadrupedal_agility.webm",
      label: "sim2sim / cross stairs",
    },
  },
  parkour: {
    label: "Robot Parkour",
    abbr: "PKR",
    tint: "rgba(52,211,153,.15)",
    color: "#86efac",
    desc: "Robot Parkour Learning Go2 rough-terrain task. Training is wired first; visual field/distill tasks are staged next.",
    tags: ["parkour", "Go2", "rough"],
    media: {
      poster: "./media/parkour.webp",
      video: "./media/parkour.webm",
      label: "sim2sim / race track",
    },
  },
  omni_jump: {
    label: "Omni-Jump",
    abbr: "JMP",
    tint: "rgba(251,113,133,.15)",
    color: "#fb7185",
    desc: "ARCLab HKU Omni-Jump / OmniNet GenHis adapter for height-aware Go1/Go2 jumping. GenHis history export is wired as one fused browser ONNX graph.",
    tags: ["GenHis", "height", "Go1/Go2"],
    media: {
      poster: "./media/omni_jump.png",
      label: "sim2sim / jump terrain",
    },
  },
};

const el = {
  refreshButton: document.getElementById("refreshButton"),
  algoCards: document.getElementById("algoCards"),
  algoCount: document.getElementById("algoCount"),
};

init();

function init() {
  el.refreshButton.addEventListener("click", loadList);
  loadList();
}

async function loadList() {
  let list = [];
  let runList = [];
  try {
    const [algorithmResult, runResult] = await Promise.allSettled([
      algorithms.list(),
      runs.list(),
    ]);
    if (algorithmResult.status === "rejected") throw algorithmResult.reason;
    list = algorithmResult.value;
    if (runResult.status === "fulfilled" && Array.isArray(runResult.value)) {
      runList = runResult.value;
    } else if (runResult.status === "rejected") {
      console.warn("run list unavailable for algorithm quick play", runResult.reason);
    }
  } catch (err) {
    el.algoCards.innerHTML = `<p class="inline-error">${
      err instanceof ApiError ? escapeHtml(err.message) : "算法加载失败"
    }</p>`;
    el.algoCount.textContent = "0";
    return;
  }
  const builtins = list
    .filter((algo) => isBuiltin(algo))
    .sort((a, b) => sortKey(a) - sortKey(b));
  el.algoCount.textContent = String(builtins.length);
  render(builtins, runList);
}

function isBuiltin(algo) {
  const name = algorithmKey(algo);
  return ORDER.includes(name) || String(algo.git_url || "").startsWith("builtin://");
}

function algorithmKey(algo) {
  return String(algo.manifest?.name || algo.name || "").toLowerCase();
}

function sortKey(algo) {
  const index = ORDER.indexOf(algorithmKey(algo));
  return index >= 0 ? index : ORDER.length;
}

function render(list, runList = []) {
  el.algoCards.innerHTML = "";
  if (!list.length) {
    el.algoCards.innerHTML = `<p class="text-sm text-slate-500">暂无内置算法。</p>`;
    return;
  }
  const latestByAlgorithm = latestPlayableRunsByAlgorithm(runList, list);
  for (const algo of list) el.algoCards.append(card(algo, latestByAlgorithm.get(algoMatchKey(algo))));
}

function normalizedTasks(algo) {
  const tasks = Array.isArray(algo.manifest?.tasks) ? algo.manifest.tasks : [];
  if (tasks.length) return tasks;
  return [{
    id: "default",
    name: algo.manifest?.name || algo.name || "Default task",
    description: algo.manifest?.description || "",
    contract: algo.manifest?.contract || {},
    compatible_robots: algo.manifest?.compatible_robots || [],
    preview: { robot: "go2", terrain: "rough", gait: "trot", accent: "#5eead4", speed: 1 },
  }];
}

function card(algo, latestRun = null) {
  const key = algorithmKey(algo);
  const meta = META[key] || {
    label: algo.manifest?.name || algo.name || algo.id,
    abbr: "ALG",
    tint: "rgba(148,163,184,.14)",
    color: "#cbd5e1",
    desc: algo.manifest?.description || "",
    tags: ["builtin"],
  };
  const tasks = normalizedTasks(algo);
  const unifiedWheelLeg = key === "wheel_leg_rl_gym";
  const preview = tasks[0]?.preview || {};
  const quickPlay = quickPlayPreview(tasks[0]);
  const pretrainedDemo = pretrainedSim2sim(tasks[0]);
  const contract = tasks[0]?.contract || algo.manifest?.contract || {};
  const caps = capabilitySnapshot(algo, tasks[0]);
  const maturity = adapterMaturity(algo, caps);
  const statusText = algorithmStatusLabel(algo, maturity, caps);
  const ready = algo.status === "ready";
  const accent = preview.accent || meta.color || "#5eead4";

  const wrap = document.createElement("article");
  wrap.className = `algo-card ${escapeAttr(maturity)}`;
  wrap.style.setProperty("--accent", accent);
  wrap.innerHTML = `
    <div class="algo-card-head">
      <div class="algo-mark" style="background:${meta.tint};color:${meta.color}">${escapeHtml(meta.abbr)}</div>
      <div class="algo-title">
        <h3>${escapeHtml(meta.label)}</h3>
        <p>v${escapeHtml(algo.version || algo.manifest?.version || "")} / ${escapeHtml(algo.id)}</p>
      </div>
      <span class="status-badge ${escapeAttr(maturity)}">${escapeHtml(statusText)}</span>
    </div>
    ${previewScene(preview, meta.media)}
    <p class="algo-desc">${escapeHtml(meta.desc || algo.manifest?.description || "")}</p>
    <div class="algo-tags">${meta.tags.map((tag) => `<span class="algo-tag">${escapeHtml(tag)}</span>`).join("")}</div>
    <div class="capability-strip">${capabilityStrip(caps)}</div>
    ${weightSourcePanel(algo, tasks[0], caps, latestRun)}
    ${latestPolicyPanel(latestRun, quickPlay, caps, pretrainedDemo)}
    <div class="algo-meta">
      ${unifiedWheelLeg ? metric("robots", tasks.length) : metric("tasks", tasks.length)}
      ${metric("hist", contract.history_len)}
      ${metric("act", contract.action_dim)}
      ${metric("scale", contract.action_scale)}
    </div>
    <div class="task-list">${unifiedWheelLeg
      ? wheelLegTaskCard(algo, tasks, ready)
      : tasks.map((task) => taskCard(algo, task, ready)).join("")}</div>
    ${algo.error ? `<div class="inline-error algo-error">${escapeHtml(algo.error)}</div>` : ""}`;
  bindPreviewPlayback(wrap);
  return wrap;
}

function latestPolicyPanel(run, preview = {}, caps = {}, pretrainedDemo = null) {
  const policy = playablePolicy(run);
  if (!run || !policy) {
    if (pretrainedDemo?.url && caps.sim2sim !== false) {
      return `
        <div class="algo-play-card">
          <span>内置 ONNX</span>
          <strong>${escapeHtml(pretrainedDemo.label || "预训练策略")}</strong>
          <small>随算法发布 · 无需先训练</small>
          <a class="play-link" href="${escapeHtml(pretrainedDemo.url)}">直接仿真</a>
        </div>`;
    }
    return `
      <div class="algo-play-card empty">
        <span>最新 ONNX</span>
        <strong>暂无可播放权重</strong>
        <small>训练导出后会自动出现在这里</small>
      </div>`;
  }
  if (caps.sim2sim === false) {
    return `
      <div class="algo-play-card empty">
        <span>最新 ONNX</span>
        <strong>${escapeHtml(policyIterationLabel(policy))}</strong>
        <small>混合位置 / 速度控制尚未通过 Sim2Sim 验收</small>
      </div>`;
  }
  const live = ["queued", "running", "evaluating"].includes(String(run.status || "").toLowerCase());
  const lag = exportLag(run, policy);
  const lagText = lag === null ? "" : ` / 同步差 ${lag} 轮`;
  return `
    <div class="algo-play-card ${live ? "live" : ""}">
      <span>${live ? "正在训练" : "最新 ONNX"}</span>
      <strong>${escapeHtml(policyIterationLabel(policy))}${escapeHtml(lagText)}</strong>
      <small>${escapeHtml(taskName(run))} / ${escapeHtml(shortRunId(run.id))}</small>
      <a class="play-link" href="${escapeHtml(sim2simHref(run, policy, preview))}">直接仿真</a>
    </div>`;
}

function quickPlayPreview(task) {
  const preview = task?.preview || {};
  const artifacts = task?.artifacts || {};
  return {
    ...preview,
    quick_terrain: artifacts.quick_terrain || artifacts.sim2sim_terrain || preview.quick_terrain || "",
    quick_autoplay: artifacts.quick_autoplay,
  };
}

function pretrainedSim2sim(task) {
  const value = task?.artifacts?.sim2sim_demo;
  if (typeof value === "string" && value.trim()) return { url: value.trim(), label: "预训练策略" };
  if (!value || typeof value !== "object") return null;
  const url = String(value.url || "").trim();
  if (!url) return null;
  return { url, label: String(value.label || "预训练策略") };
}

function weightSourcePanel(algo, task, caps, run) {
  const policy = playablePolicy(run);
  const source = pretrainedSource(algo, task);
  if (caps.pretrained_policy === true) {
    const label = source ? `官方预训练：${source}` : "官方预训练权重可用";
    return `
      <div class="weight-source ready">
        <span>权重来源</span>
        <strong>${escapeHtml(label)}</strong>
      </div>`;
  }
  if (policy) {
    return `
      <div class="weight-source training">
        <span>权重来源</span>
        <strong>平台训练导出 · ${escapeHtml(policyIterationLabel(policy))}</strong>
      </div>`;
  }
  return `
    <div class="weight-source pending">
      <span>权重来源</span>
      <strong>未发现官方预训练权重，需先训练导出</strong>
    </div>`;
}

function pretrainedSource(algo, task) {
  const artifacts = {
    ...(algo?.manifest?.artifacts || {}),
    ...(task?.artifacts || {}),
  };
  const candidates = [
    artifacts.pretrained,
    artifacts.pretrained_policy,
    artifacts.pretrained_checkpoint,
    artifacts.pretrained_onnx,
    artifacts.checkpoint,
  ];
  for (const value of candidates) {
    if (typeof value === "string" && value.trim()) return value.trim().split(/[\\/]/).pop();
    if (value && typeof value === "object") {
      const text = value.filename || value.name || value.path || value.url || value.checkpoint;
      if (typeof text === "string" && text.trim()) return text.trim().split(/[\\/]/).pop();
    }
  }
  return "";
}

function bindPreviewPlayback(cardEl) {
  const video = cardEl.querySelector(".preview-video");
  const play = () => {
    const wasPlaying = cardEl.classList.contains("preview-playing");
    cardEl.classList.add("preview-playing");
    if (video) {
      if (!wasPlaying) video.currentTime = 0;
      if (video.paused) video.play().catch(() => {});
    }
  };
  const pause = () => {
    cardEl.classList.remove("preview-playing");
    if (video) {
      video.pause();
      video.currentTime = 0;
    }
  };
  const pauseIfLeaving = (event) => {
    if (!cardEl.contains(event.relatedTarget)) pause();
  };
  cardEl.addEventListener("pointerenter", play);
  cardEl.addEventListener("pointerleave", pause);
  cardEl.addEventListener("pointerover", play);
  cardEl.addEventListener("pointermove", play);
  cardEl.addEventListener("pointerout", pauseIfLeaving);
  cardEl.addEventListener("mouseenter", play);
  cardEl.addEventListener("mouseleave", pause);
  cardEl.addEventListener("mouseover", play);
  cardEl.addEventListener("mousemove", play);
  cardEl.addEventListener("mouseout", pauseIfLeaving);
  cardEl.addEventListener("click", (event) => {
    if (event.target.closest("a, button")) return;
    play();
  });
  cardEl.addEventListener("touchstart", play, { passive: true });
  cardEl.addEventListener("focusin", play);
  cardEl.addEventListener("focusout", (event) => {
    if (!cardEl.contains(event.relatedTarget)) pause();
  });
}

function capabilitySnapshot(algo, task) {
  return {
    ...(algo.manifest?.capabilities || {}),
    ...(task?.capabilities || {}),
  };
}

function capabilityStrip(caps) {
  const items = [
    ["训练", caps.train !== false],
    ["续训", caps.resume === true],
    ["导出", caps.onnx_export !== false],
    ["仿真", caps.sim2sim !== false],
    ["权重", caps.pretrained_policy === true],
    ["预览", caps.preview_video === true],
  ];
  return items.map(([label, ok]) =>
    `<span class="capability-pill ${ok ? "ok" : "miss"}">${escapeHtml(label)}</span>`
  ).join("");
}

function adapterMaturity(algo, caps) {
  if (algo.status !== "ready") return algo.status || "blocked";
  if (caps.deployment) return String(caps.deployment);
  if (caps.onnx_export === false || caps.sim2sim === false) return "partial";
  return "ready";
}

function algorithmStatusLabel(algo, maturity, caps = {}) {
  if (isAmpAlgorithm(algo) && caps.train === false) return "开发中";
  const trainable = algo.status === "ready" && caps.train !== false;
  const labels = {
    ready: trainable ? "可训练 · 已验证" : "已验证",
    partial: trainable ? "可训练 · 持续优化" : "持续优化",
    experimental: trainable ? "开放体验" : "开发中",
    blocked: "开发中",
    invalid: "暂未开放",
  };
  return labels[String(maturity || "").toLowerCase()] || (trainable ? "可训练" : "开发中");
}

function isAmpAlgorithm(algo) {
  const value = algo?.manifest?.name || algo?.name || algo?.id || "";
  return String(value).toLowerCase().replace(/[^a-z0-9]+/g, "_").includes("amp_cts");
}

function previewScene(preview, media) {
  const terrain = escapeAttr(preview.terrain || "rough");
  const gait = preview.gait || "hover to preview";
  if (media?.video) {
    const poster = media.poster ? ` poster="${escapeHtml(media.poster)}"` : "";
    const source = `<source src="${escapeHtml(media.video)}" type="video/webm" />`;
    const label = media.label || gait;
    return `
      <div class="algo-preview has-media terrain-${terrain}" aria-label="algorithm locomotion preview">
        <video class="preview-video" muted loop playsinline preload="metadata"${poster}>${source}</video>
        <div class="preview-vignette"></div>
        <div class="preview-hint">${escapeHtml(label)}</div>
      </div>`;
  }
  if (media?.poster) {
    const label = media.label || gait;
    return `
      <div class="algo-preview has-poster terrain-${terrain}" aria-label="algorithm locomotion preview">
        <img class="preview-poster" src="${escapeHtml(media.poster)}" alt="" loading="lazy" />
        <div class="preview-vignette"></div>
        <div class="preview-hint">${escapeHtml(label)}</div>
        ${previewDog(preview)}
        <div class="preview-terrain"></div>
      </div>`;
  }
  return `
    <div class="algo-preview terrain-${terrain}" aria-label="algorithm locomotion preview">
      <div class="preview-sky"></div>
      <div class="preview-hint">${escapeHtml(gait)}</div>
      ${previewDog(preview)}
      <div class="preview-terrain"></div>
    </div>`;
}

function previewDog(preview) {
  return `
    <div class="dog" style="animation-duration:${previewDuration(preview.speed)}s">
      <div class="dog-body"></div>
      <div class="dog-head"></div>
      <div class="dog-leg l1"></div>
      <div class="dog-leg l2"></div>
      <div class="dog-leg l3"></div>
      <div class="dog-leg l4"></div>
    </div>`;
}

function taskCard(algo, task, ready) {
  const contract = task.contract || algo.manifest?.contract || {};
  const caps = capabilitySnapshot(algo, task);
  const href = `/train/?algorithm=${encodeURIComponent(algo.id)}&task=${encodeURIComponent(task.id || "default")}`;
  const trainable = ready && caps.train !== false;
  const exportable = caps.onnx_export !== false;
  const simReady = caps.sim2sim !== false;
  const deployable = exportable && simReady;
  const developing = isAmpAlgorithm(algo) && caps.train === false;
  const demo = pretrainedSim2sim(task);
  const cta = developing
    ? "进入开发版训练"
    : deployable
    ? "训练并导出 ONNX"
    : (exportable ? "训练并导出 ONNX" : "训练冒烟");
  const note = demo
    ? "内置预训练权重 · 支持 Sim2Sim"
    : developing
    ? "开发中 · 训练链路持续完善"
    : deployable
      ? "支持 ONNX 导出与 Sim2Sim 体验"
      : (exportable ? "支持 ONNX 导出 · Sim2Sim 持续适配" : "支持训练 · Sim2Sim 持续适配");
  return `
    <div class="task-card">
      <strong>${escapeHtml(task.name || task.id || "Default task")}</strong>
      <span>${escapeHtml(task.description || `${fmt(contract.obs_dim)} obs / ${fmt(contract.action_dim)} act`)}</span>
      <small class="task-note ${demo || (deployable && !developing) ? "ready" : "partial"}">${escapeHtml(note)}</small>
      ${demo
        ? `<div class="task-actions">
            <a class="primary" href="${escapeHtml(demo.url)}">直接仿真</a>
            ${trainable
              ? `<a class="primary secondary" href="${href}">训练 / 续训</a>`
              : ""}
          </div>`
        : trainable
          ? `<a class="primary ${deployable ? "" : "secondary"}" href="${href}">${escapeHtml(cta)}</a>`
          : `<button class="primary" type="button" disabled>暂未开放</button>`}
    </div>`;
}

function wheelLegTaskCard(algo, tasks, ready) {
  const task = tasks.find((item) => item.id === "w1w_moe_cts") || tasks[0];
  const trainable = ready && task && capabilitySnapshot(algo, task).train !== false;
  const href = `/train/?algorithm=${encodeURIComponent(algo.id)}&task=${encodeURIComponent(task?.id || "w1w_moe_cts")}`;
  return `
    <div class="task-card">
      <strong>16 关节轮足训练</strong>
      <span>使用 W1W MoE-CTS 训练底座，并注入每台机器人的标准化 URDF、关节顺序、控制增益和电机约束。</span>
      <small class="task-note ready">W1W 直接仿真 · 用户轮足从零训练</small>
      ${trainable
        ? `<a class="primary" href="${href}">开始轮足训练</a>`
        : `<button class="primary" type="button" disabled>暂未开放</button>`}
    </div>`;
}

function metric(label, value) {
  return `<div class="algo-metric"><span>${label}</span><strong>${fmt(value)}</strong></div>`;
}

function previewDuration(speed) {
  const n = Number(speed);
  const safe = Number.isFinite(n) && n > 0 ? n : 1;
  return (0.68 / safe).toFixed(2);
}

function latestPlayableRunsByAlgorithm(runList, algorithms = []) {
  const best = new Map();
  const allowedTasks = new Map(
    algorithms.map((algo) => [
      algoMatchKey(algo),
      new Set(normalizedTasks(algo).map((task) => String(task.id || "default"))),
    ])
  );
  for (const run of Array.isArray(runList) ? runList : []) {
    const policy = playablePolicy(run);
    if (!policy) continue;
    if (isSmokePolicy(run, policy)) continue;
    const key = runAlgorithmKey(run);
    if (!key) continue;
    const taskIds = allowedTasks.get(key);
    if (taskIds?.size && !taskIds.has(String(run?.task_id || "default"))) continue;
    if (key === "wheel_leg_rl_gym" && !isW1WRun(run)) continue;
    const current = best.get(key);
    if (!current || runScore(run, policy) > runScore(current, playablePolicy(current))) {
      best.set(key, run);
    }
  }
  return best;
}

function isW1WRun(run) {
  const robot = run?.robot_snapshot || {};
  return run?.task_id === "w1w_moe_cts"
    && (run?.robot_id === "rbt_builtin_w1w" || robot.id === "rbt_builtin_w1w")
    && String(robot.urdf_ref || "").replaceAll("\\", "/").includes("w1w_urdf1/");
}

function algoMatchKey(algo) {
  return normalizeAlgorithmKey(algorithmKey(algo) || algo.id);
}

function runAlgorithmKey(run) {
  return normalizeAlgorithmKey(run?.algorithm_name || run?.algorithm_id || "");
}

function normalizeAlgorithmKey(value) {
  const key = String(value || "").toLowerCase().replace(/^alg_builtin_/, "");
  const aliases = [
    "go2_rl_gym",
    "wheel_leg_rl_gym",
    "wheel_leg_gait_rl_gym",
    "wheel_leg_gait_hip_degradation",
    "wheel_leg_jump_rl_gym",
    "wheel_leg_high_speed",
    "amp_cts",
    "np3o",
    "quadrupedal_agility",
    "parkour",
    "omni_jump",
  ];
  return aliases.find((alias) => key === alias || key.includes(alias)) || key;
}

function runScore(run, policy) {
  const iter = policyIterationValue(policy) || 0;
  const live = ["queued", "running", "evaluating"].includes(String(run?.status || "").toLowerCase()) ? 500_000 : 0;
  const freshness = Number(policy?.created_at ?? run?.updated_at ?? 0) / 1000;
  return live + iter + freshness;
}

function isSmokePolicy(run, policy = null) {
  const picked = policy || playablePolicy(run) || run?.latest_policy || {};
  const iter = policyIterationValue(picked) || 0;
  const maxIterations = Number(run?.hyperparams?.max_iterations ?? 0);
  return (Number.isFinite(iter) && iter > 0 && iter <= 10)
    || (Number.isFinite(maxIterations) && maxIterations > 0 && maxIterations <= 10);
}

function playablePolicy(run) {
  if (isPolicyPlayable(run?.playable_policy)) return run.playable_policy;
  if (isPolicyPlayable(run?.latest_policy)) return run.latest_policy;
  return null;
}

function isPolicyPlayable(policy) {
  if (!policy?.id || !policy?.onnx_url) return false;
  const status = String(policy.health?.status || "pass").toLowerCase();
  return ["pass", "ready"].includes(status);
}

function sim2simHref(run, policy, preview = {}) {
  const params = new URLSearchParams({ run_id: run.id, policy: policy.id });
  const iter = policyIterationValue(policy);
  if (iter !== null) params.set("iter", String(iter));
  const terrain = simTerrainParam(runQuickTerrain(run) || preview?.quick_terrain || preview?.terrain);
  if (terrain) params.set("terrain", terrain);
  const autoplay = quickAutoplay(preview);
  if (autoplay !== null) params.set("autoplay", autoplay ? "1" : "0");
  const robot = quickRobotParam(preview);
  if (robot) params.set("robot", robot);
  params.set("v", String(policy.created_at || run.updated_at || Date.now()));
  return `/sim2sim/?${params.toString()}`;
}

function quickRobotParam(preview = {}) {
  return normalizePreviewRobot(preview.robot || preview.quick_robot || preview.robot_asset);
}

function normalizePreviewRobot(value) {
  const key = String(value || "")
    .trim()
    .toLowerCase()
    .replace(/^rbt_builtin_/, "")
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
  if (!key) return "";
  if (key.includes("fsdog")) return "fsdog1";
  if (key === "go2" || key.includes("unitree_go2")) return "go2";
  return key;
}

function quickAutoplay(preview = {}) {
  if (preview.quick_autoplay === undefined || preview.quick_autoplay === null) return true;
  if (typeof preview.quick_autoplay === "string") {
    return !["0", "false", "no", "off"].includes(preview.quick_autoplay.trim().toLowerCase());
  }
  return preview.quick_autoplay !== false;
}

function runQuickTerrain(run) {
  const artifacts = run?.task_snapshot?.artifacts;
  if (artifacts && typeof artifacts === "object") {
    return artifacts.quick_terrain || artifacts.sim2sim_terrain || "";
  }
  return "";
}

function simTerrainParam(value) {
  const raw = String(value || "").trim().toLowerCase();
  if (!raw) return "";
  const normalized = raw.replace(/\.xml$/i, "").replace(/[-\s]+/g, "_");
  const aliases = {
    slope: "cross_slope",
    rough: "stairs",
    stairs: "stairs",
    obstacle: "cross_stairs",
    obstacles: "cross_stairs",
    agility: "cross_stairs",
    parkour: "race_track",
    jump: "race_track",
    jumping: "race_track",
    flat: "flat",
  };
  return aliases[normalized] || normalized;
}

function policyIterationLabel(policy) {
  const iter = policyIterationValue(policy);
  return iter !== null ? `第 ${iter} 轮 ONNX` : "已导出 ONNX";
}

function policyIterationValue(policy) {
  const direct = integerOrNull(policy?.checkpoint_iteration);
  if (direct !== null) return direct;
  const checkpoint = String(policy?.checkpoint || "");
  const match = checkpoint.match(/(?:model|checkpoint|ckpt|iter|iteration)[_-]?(\d+)\b/i);
  if (match) return Number(match[1]);
  return null;
}

function exportLag(run, policy) {
  const trainIter = integerOrNull(run?.progress?.iteration);
  const policyIter = policyIterationValue(policy);
  if (trainIter === null || policyIter === null) return null;
  return Math.max(0, trainIter - policyIter);
}

function integerOrNull(value) {
  if (value === undefined || value === null || value === "") return null;
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed >= 0 ? parsed : null;
}

function taskName(run) {
  return run?.task_id || run?.progress?.stage || run?.status || "run";
}

function shortRunId(id) {
  const text = String(id || "");
  return text.length > 13 ? `${text.slice(0, 9)}...${text.slice(-4)}` : text;
}

function fmt(v) { return v === undefined || v === null ? "-" : String(v); }
function escapeAttr(s) { return String(s).replace(/[^a-zA-Z0-9_-]/g, ""); }
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
