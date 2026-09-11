import { algorithms, ApiError, auth, meta, ops, play, robots, runs } from "./shared/api.js?v=public-demos-1";

const el = {
  refresh: document.getElementById("homeRefresh"),
  subtitle: document.getElementById("homeSubtitle"),
  activeRunHint: document.getElementById("activeRunHint"),
  activeRunHeading: document.getElementById("activeRunHeading"),
  activeRunBadge: document.getElementById("activeRunBadge"),
  activeRunTitle: document.getElementById("activeRunTitle"),
  activeRunMeta: document.getElementById("activeRunMeta"),
  activeRunProgressBar: document.getElementById("activeRunProgressBar"),
  activeRunMetrics: document.getElementById("activeRunMetrics"),
  activeRunTrainLink: document.getElementById("activeRunTrainLink"),
  activeRunPlayLink: document.getElementById("activeRunPlayLink"),
  quickHint: document.getElementById("quickHint"),
  quickPrimaryLink: document.getElementById("quickPrimaryLink"),
  quickExperienceList: document.getElementById("quickExperienceList"),
  systemHint: document.getElementById("systemHint"),
  systemBadge: document.getElementById("systemBadge"),
  systemRows: document.getElementById("systemRows"),
  counts: document.getElementById("homeCounts"),
  adapterHint: document.getElementById("adapterHint"),
  adapterList: document.getElementById("adapterList"),
  recentRuns: document.getElementById("recentRuns"),
  adminOpsLink: document.getElementById("adminOpsLink"),
};

init();

function init() {
  el.refresh.addEventListener("click", loadDashboard);
  loadDashboard();
}

async function loadDashboard() {
  el.refresh.disabled = true;
  el.subtitle.textContent = "同步平台状态中。";
  const session = await auth.me().catch(() => ({ user: null }));
  const user = session?.user || null;
  const isAdmin = user?.role === "admin";
  if (el.adminOpsLink) el.adminOpsLink.hidden = !isAdmin;
  const protectedCall = (call, fallback) => user ? call() : Promise.resolve(fallback);
  const [healthResult, robotsResult, algorithmsResult, runsResult, opsResult, recommendedResult, demosResult] = await Promise.allSettled([
    meta.health(),
    protectedCall(() => robots.list(), []),
    protectedCall(() => algorithms.list(), []),
    protectedCall(() => runs.list(), []),
    isAdmin ? ops.algorithms() : Promise.resolve(null),
    protectedCall(() => play.latest(), null),
    play.demos(),
  ]);

  const health = fulfilled(healthResult);
  const robotList = arrayValue(robotsResult);
  const algorithmList = arrayValue(algorithmsResult);
  const runList = arrayValue(runsResult);
  const opsAlgorithms = fulfilled(opsResult);
  const recommendedPlay = fulfilled(recommendedResult);
  const publicDemos = arrayValue(demosResult);

  renderSystem(health);
  renderCounts({ robots: robotList, algorithms: algorithmList, runs: runList, opsAlgorithms });
  let personalItems = quickExperienceItems(runList, algorithmList, robotList);
  personalItems = prioritizeRecommendedQuickItem(personalItems, recommendedPlay, runList, algorithmList, robotList);
  const quickItems = mergeDemoItems(demoExperienceItems(publicDemos), personalItems);
  renderQuickExperience(quickItems);
  renderActiveRun(runList, quickItems, algorithmList);
  renderAdapters(opsAlgorithms, algorithmList, opsResult.reason);
  renderRecentRuns(runList, algorithmList);

  const active = pickActiveRun(runList, quickItems);
  el.subtitle.textContent = active
    ? subtitleForRun(active)
    : "没有运行中的训练任务，可以从训练页新建或继续已有任务。";
  el.refresh.disabled = false;
}

function renderQuickExperience(items) {
  if (!items.length) {
    el.quickHint.textContent = "还没有训练出的 ONNX，可先打开内置 Go2 demo 或去训练页创建任务。";
    el.quickPrimaryLink.href = "/sim2sim/";
    el.quickPrimaryLink.textContent = "打开 Demo";
    el.quickExperienceList.innerHTML = `
      <div class="home-empty">
        暂无可播放权重。训练产生第一个 ONNX 后，这里会自动变成一键体验入口。
      </div>`;
    return;
  }

  const primary = items[0];
  const liveCount = items.filter((item) => item.live).length;
  el.quickHint.textContent = `${items.length} 个 Demo / 策略可直接播放${liveCount ? `，${liveCount} 个还在继续导出 ONNX` : ""}，默认加载 ${primary.robotName} / ${primary.iterLabel}。`;
  el.quickPrimaryLink.href = primary.href;
  el.quickPrimaryLink.textContent = "立即体验";
  el.quickExperienceList.innerHTML = items.map((item, index) => `
    <a class="home-quick-card ${index === 0 ? "featured" : ""}" href="${item.href}" data-testid="quick-card">
      <div>
        <strong>${escapeHtml(item.algorithmName)}</strong>
        <span>${escapeHtml(item.robotName)} / ${escapeHtml(item.taskId)}</span>
        ${item.subLabel ? `<small>${escapeHtml(item.subLabel)}</small>` : ""}
        ${item.liveMeta ? `<small class="home-quick-live">${escapeHtml(item.liveMeta)}</small>` : ""}
      </div>
      <div class="home-quick-meta">
        <span class="status-badge ${escapeAttr(item.badgeClass)}">${escapeHtml(item.badgeText)}</span>
        <strong>${escapeHtml(item.iterLabel)}</strong>
      </div>
    </a>
  `).join("");
}

function renderSystem(health) {
  const worker = health?.worker || {};
  const embedded = worker.embedded !== false;
  el.systemBadge.className = `status-badge ${embedded ? "partial" : "ready"}`;
  el.systemBadge.textContent = embedded ? "embedded" : "web-only";
  el.systemHint.textContent = health?.status === "ok" ? "后端 health 正常" : "health 接口不可用";
  el.systemRows.innerHTML = [
    systemRow("环境", health?.env || "-"),
    systemRow("登录", health?.auth_required ? "required" : "dev open"),
    systemRow("Worker", embedded ? "web 内嵌" : "外部/关闭"),
    systemRow("孤儿恢复", String(worker.mark_orphaned_runs_on_startup ?? "-")),
  ].join("");
}

function renderCounts({ robots, algorithms, runs, opsAlgorithms }) {
  const nonterminal = runs.filter((run) => ["queued", "running", "evaluating"].includes(run.status));
  const policyCount = runs.filter((run) => playablePolicy(run)).length;
  const adapters = Array.isArray(opsAlgorithms?.adapters) ? opsAlgorithms.adapters : [];
  const algorithmCount = algorithms.length || adapters.length;
  const trainable = algorithms.length
    ? algorithms.filter((algo) => algo.status === "ready" && !isAmpAlgorithm(algo.manifest?.name || algo.name || algo.id)).length
    : adapters.filter((adapter) => adapterTrainable(adapter) && !isAmpAlgorithm(adapter.name)).length;
  el.counts.innerHTML = [
    countTile("机器人", robots.length),
    countTile("内置算法", algorithmCount),
    countTile("可训练算法", trainable),
    countTile("训练中", nonterminal.length),
    countTile("可播放策略", policyCount),
  ].join("");
}

function renderActiveRun(runList, quickItems = [], algorithmList = []) {
  const run = pickActiveRun(runList, quickItems);
  if (!run) {
    el.activeRunBadge.className = "status-badge queued";
    el.activeRunBadge.textContent = "idle";
    el.activeRunHint.textContent = "当前没有非终态 run";
    el.activeRunTitle.textContent = "等待新训练";
    el.activeRunMeta.textContent = "可以从训练页选择算法和机器人开始。";
    el.activeRunProgressBar.style.width = "0%";
    el.activeRunMetrics.innerHTML = [
      metric("进度", "-"),
      metric("ONNX", "-"),
      metric("地形等级", "-"),
      metric("checkpoint", "-"),
    ].join("");
    el.activeRunTrainLink.href = "/train/";
    el.activeRunPlayLink.href = "/sim2sim/";
    return;
  }
  const progress = run.progress || {};
  const policy = playablePolicy(run);
  const percent = progressPercent(run);
  const live = isLiveRun(run);
  const recommended = !live && quickItems[0]?.runId === run.id ? quickItems[0] : null;
  el.activeRunHeading.textContent = live ? "当前训练" : "推荐权重";
  el.activeRunBadge.className = `status-badge ${escapeAttr(run.status)}`;
  el.activeRunBadge.textContent = runStatusLabel(run.status);
  el.activeRunHint.textContent = live
    ? liveRunHint(run, policy)
    : `可直接进入 Sim2Sim：${recommended?.algorithmName || displayAlgorithmName(run)} / ${policyIterationLabel(policy, run)}`;
  const taskLabel = recommended?.taskId || displayTaskName(run);
  const iterationLabel = policy
    ? (recommended?.iterLabel || policyIterationLabel(policy, run))
    : progress.iteration ? `第 ${progress.iteration} 轮` : "等待 ONNX";
  el.activeRunTitle.textContent = `${recommended?.robotName || displayRobotName(run)} / ${recommended?.algorithmName || displayAlgorithmName(run)}`;
  el.activeRunMeta.textContent = `${taskLabel} / ${shortRunId(run.id)} / ${iterationLabel} / ${formatTime(run.updated_at)}`;
  el.activeRunMeta.title = run.id;
  el.activeRunProgressBar.style.width = `${percent}%`;
  el.activeRunMetrics.innerHTML = [
    metric("进度", progress.iteration && progress.max_iterations ? `${progress.iteration}/${progress.max_iterations}` : `${percent}%`),
    metric("最新 ONNX", policy ? policyIterationLabel(policy, run) : run.latest_policy ? "健康检查未通过" : "等待导出"),
    metric("地形等级", progress.terrain_level == null ? "-" : Number(progress.terrain_level).toFixed(2)),
    metric("同步差", exportLagLabel(run, policy)),
  ].join("");
  el.activeRunTrainLink.href = `/train/?run_id=${encodeURIComponent(run.id)}`;
  setOptionalLink(el.activeRunPlayLink, {
    enabled: Boolean(policy),
    href: policy ? sim2simHref(run, policy, quickPlayOptionsForRun(run, algorithmInfoForRun(run, algorithmList))) : "#",
    text: policy ? "播放 ONNX" : "等待 ONNX",
  });
}

function renderAdapters(opsAlgorithms, fallbackAlgorithms, error) {
  if (opsAlgorithms?.adapters?.length) {
    const available = opsAlgorithms.adapters.filter((adapter) => adapterTrainable(adapter) && !isAmpAlgorithm(adapter.name)).length;
    el.adapterHint.textContent = `${available} 个算法已开放训练，能力持续更新`;
    el.adapterList.innerHTML = opsAlgorithms.adapters.map(adapterRow).join("");
    return;
  }
  if (fallbackAlgorithms.length) {
    el.adapterHint.textContent = error instanceof ApiError ? "已开放算法训练，详细能力正在同步" : "内置算法已开放训练，能力持续更新";
    el.adapterList.innerHTML = fallbackAlgorithms.map((algo) => adapterRow(fallbackAdapter(algo))).join("");
    return;
  }
  el.adapterHint.textContent = "没有算法数据";
  el.adapterList.innerHTML = `<div class="home-empty">暂无算法。</div>`;
}

function renderRecentRuns(runList, algorithmList = []) {
  const rows = runList.slice(0, 6);
  if (!rows.length) {
    el.recentRuns.innerHTML = `<div class="home-empty">暂无训练任务。</div>`;
    return;
  }
  el.recentRuns.innerHTML = rows.map((run) => {
    const policy = playablePolicy(run);
    const progress = run.progress || {};
    const playHref = policy ? sim2simHref(run, policy, quickPlayOptionsForRun(run, algorithmInfoForRun(run, algorithmList))) : "#";
    const title = `${displayAlgorithmName(run)} / ${displayTaskName(run)}`;
    const policyText = policy ? policyIterationLabel(policy, run) : run.latest_policy ? "ONNX 健康检查未通过" : "等待 ONNX";
    const subtitle = [displayRobotName(run), shortRunId(run.id), stageLabel(progress.stage) || runStatusLabel(run.status), policyText]
      .filter(Boolean)
      .join(" / ");
    return `
      <article class="home-run-row">
        <div>
          <strong>${escapeHtml(title)}</strong>
          <span title="${escapeAttr(run.id)}">${escapeHtml(subtitle)}</span>
        </div>
        <span class="status-badge ${escapeAttr(run.status)}">${escapeHtml(runStatusLabel(run.status))}</span>
        <div class="home-row-actions">
          <a class="btn" href="/train/?run_id=${encodeURIComponent(run.id)}">日志</a>
          <a class="btn ${policy ? "" : "disabled"}" href="${playHref}" ${policy ? "" : 'aria-disabled="true" tabindex="-1"'}>${policy ? "仿真" : "等待 ONNX"}</a>
        </div>
      </article>
    `;
  }).join("");
}

function setOptionalLink(link, { enabled, href, text }) {
  link.href = href;
  link.textContent = text;
  link.classList.toggle("disabled", !enabled);
  if (enabled) {
    link.removeAttribute("aria-disabled");
    link.removeAttribute("tabindex");
  } else {
    link.setAttribute("aria-disabled", "true");
    link.setAttribute("tabindex", "-1");
  }
}

function pickActiveRun(runList, quickItems = []) {
  const priority = ["running", "evaluating", "queued"];
  for (const status of priority) {
    const match = runList.find((run) => run.status === status);
    if (match) return match;
  }
  const recommended = quickItems[0]?.runId;
  if (recommended) {
    const match = runList.find((run) => run.id === recommended);
    if (match) return match;
  }
  return runList.find((run) => playablePolicy(run)) || runList[0] || null;
}

function isLiveRun(run) {
  return ["running", "evaluating", "queued"].includes(run?.status);
}

function subtitleForRun(run) {
  if (isLiveRun(run)) {
    return `当前${runStatusLabel(run.status)}：${stageLabel(run.progress?.stage) || displayTaskName(run)}`;
  }
  const policy = playablePolicy(run);
  if (policy) {
    return `最新可播放策略：${displayTaskName(run)} / ${policyIterationLabel(policy, run)}`;
  }
  return `最近任务${runStatusLabel(run.status)}：${stageLabel(run.progress?.stage) || displayTaskName(run)}`;
}

function demoExperienceItems(demos) {
  const order = new Map([["go2", 0], ["amp_cts", 1], ["y1", 2], ["w1w", 3]]);
  return [...demos]
    .filter((demo) => order.has(String(demo?.id || "").toLowerCase()))
    .sort((a, b) => order.get(String(a.id).toLowerCase()) - order.get(String(b.id).toLowerCase()))
    .map((demo) => {
      const demoId = String(demo.id).toLowerCase();
      const iteration = Number(demo.checkpoint_iteration);
      const hasIteration = Number.isFinite(iteration) && iteration > 0;
      const taskLabel = {
        go2: "Go2 官方速度跟踪",
        amp_cts: "P1 · AMP-CTS（MPC）",
        y2: "Y2 轮足速度跟踪",
        y1: "Y1 轮足速度跟踪",
        w1w: "W1W 轮足速度跟踪",
      }[demoId] || demo.task_name || "速度跟踪";
      return {
        href: demo.url || `/sim2sim/?demo=${encodeURIComponent(demo.id)}`,
        demoId,
        runId: demo.run_id || "",
        robotId: demo.robot_id || "",
        taskId: taskLabel,
        algorithmName: readableAlgorithmName(demo.algorithm_name || "MoE-CTS"),
        robotName: demo.robot_name || String(demo.id).toUpperCase(),
        iterLabel: hasIteration ? `第 ${iteration} 轮` : "内置检查点",
        badgeClass: "ready",
        badgeText: "Demo",
        subLabel: hasIteration ? `公开演示 / 第 ${iteration} 轮` : "公开演示 / 内置权重",
        live: false,
        liveMeta: "",
      };
    });
}

function mergeDemoItems(demos, personalItems) {
  const demoRuns = new Set(demos.map((item) => item.runId).filter(Boolean));
  return [...demos, ...personalItems.filter((item) => !demoRuns.has(item.runId))];
}

function quickExperienceItems(runList, algorithmList, robotList) {
  const algorithmInfo = new Map(algorithmList.map((algo) => [
    algo.id,
    {
      name: algo.manifest?.display_name || algo.manifest?.name || algo.name || algo.id,
      sim2sim: algo.manifest?.capabilities?.sim2sim === true,
      deployment: algo.manifest?.capabilities?.deployment || algo.status || "",
      pretrained: algo.manifest?.capabilities?.pretrained_policy === true,
      tasks: Array.isArray(algo.manifest?.tasks) ? algo.manifest.tasks : [],
      manifest: algo.manifest || {},
    },
  ]));
  const robotNames = new Map((robotList || []).map((robot) => [robot.id, robot.name || robot.id]));
  robotNames.set("rbt_builtin_go2", "Unitree Go2");
  robotNames.set("go2", "Unitree Go2");
  robotNames.set("rbt_builtin_fsdog1", "FSDog1");
  robotNames.set("fsdog1", "FSDog1");
  const playable = runList
    .filter((run) => playablePolicy(run) && !isSmokePolicy(run))
    .sort((a, b) => quickRunScore(b, algorithmInfo) - quickRunScore(a, algorithmInfo));
  const byAlgorithm = new Map();
  for (const run of playable) {
    if (!byAlgorithm.has(run.algorithm_id)) byAlgorithm.set(run.algorithm_id, run);
  }
  return Array.from(byAlgorithm.values()).map((run) => {
    const policy = playablePolicy(run);
    const iterValue = policy?.checkpoint_iteration ?? checkpointIterationFromPath(policy?.checkpoint);
    const info = algorithmInfo.get(run.algorithm_id) || {};
    const smoke = isSmokePolicy(run);
    const iterLabel = policyIterationLabel(policy, run);
    const quick = quickPlayOptionsForRun(run, info);
    return {
      href: sim2simHref(run, policy, quick),
      runId: run.id,
      taskId: displayTaskName(run),
      algorithmName: displayAlgorithmName(run, info.name),
      robotName: quickRobotDisplayName(run, quick, robotNames.get(run.robot_id)),
      iterLabel: smoke ? `${iterLabel} · 验证` : iterLabel,
      badgeClass: smoke ? "partial" : "ready",
      badgeText: smoke ? "验证" : isLiveRun(run) ? "训练中" : "可播放",
      subLabel: quickItemSubLabel(run, info, iterValue),
      live: isLiveRun(run),
      liveMeta: quickLiveMeta(run, policy),
    };
  });
}

function quickRunScore(run, algorithmInfo) {
  const policy = playablePolicy(run) || run.latest_policy || {};
  const iter = Number(policy.checkpoint_iteration ?? checkpointIterationFromPath(policy.checkpoint) ?? 0);
  const info = algorithmInfo.get(run.algorithm_id) || {};
  const statusScore = run.status === "succeeded" ? 3000 : ["running", "evaluating"].includes(run.status) ? 1800 : 1000;
  const deploymentScore = info.deployment === "ready" ? 900 : info.deployment === "partial" ? 300 : 0;
  const simScore = info.sim2sim ? 900 : 0;
  const pretrainedScore = info.pretrained ? 500 : 0;
  const preferredRobotScore = runMatchesPreferredRobot(run, preferredRobotForRun(run, info)) ? 1200 : 0;
  const smokePenalty = isSmokePolicy(run) ? 2600 : 0;
  const freshness = Number(policy.created_at ?? run.updated_at ?? 0) / 1_000_000_000;
  return statusScore + deploymentScore + simScore + pretrainedScore + preferredRobotScore + Math.min(iter, 20000) / 20 + freshness - smokePenalty;
}

function prioritizeRecommendedQuickItem(items, recommendedPlay, runList, algorithmList, robotList) {
  const policy = recommendedPlay?.policy;
  const runId = recommendedPlay?.run_id;
  if (!runId || !policy?.id || !policy?.onnx_url) return items;
  const apiRun = recommendedPlay?.run || {};
  const run = {
    ...apiRun,
    ...(runList.find((item) => item.id === runId) || {}),
    id: runId,
    playable_policy: policy,
    latest_policy: policy,
  };
  if (isSmokePolicy({ ...run, playable_policy: policy, latest_policy: policy })) return items;
  const algorithm = algorithmList.find((item) => item.id === run.algorithm_id);
  const robot = robotList.find((item) => item.id === run.robot_id);
  const quick = quickPlayOptionsForRun(run, {
    manifest: algorithm?.manifest || {},
    tasks: Array.isArray(algorithm?.manifest?.tasks) ? algorithm.manifest.tasks : [],
  });
  const recommended = {
    href: sim2simHref(run, policy, quick),
    runId,
    taskId: displayTaskName(run) || "recommended",
    algorithmName: displayAlgorithmName(run, algorithm?.manifest?.name || algorithm?.name || "recommended"),
    robotName: quickRobotDisplayName(run, quick, recommendedPlay.robot?.name || robot?.name),
    iterLabel: policyIterationLabel(policy, run),
    badgeClass: "ready",
    badgeText: "推荐",
    subLabel: quickItemSubLabel(run, {
      name: algorithm?.manifest?.display_name || algorithm?.manifest?.name || algorithm?.name || "",
      deployment: algorithm?.manifest?.capabilities?.deployment || algorithm?.status || "",
      pretrained: algorithm?.manifest?.capabilities?.pretrained_policy === true,
    }, policy.checkpoint_iteration ?? checkpointIterationFromPath(policy.checkpoint)),
  };
  const rest = items.filter((item) => item.runId !== runId);
  return [recommended, ...rest];
}

function quickItemSubLabel(run, info = {}, iterValue = null) {
  const parts = [];
  if (info.deployment) parts.push(deploymentLabel(info.deployment, info.name));
  if (info.pretrained) parts.push("官方/内置权重");
  if (run.status) parts.push(runStatusLabel(run.status));
  if (iterValue !== null && iterValue !== undefined) parts.push(`第 ${iterValue} 轮`);
  return parts.filter(Boolean).join(" / ");
}

function isSmokePolicy(run) {
  const policy = playablePolicy(run) || run.latest_policy || {};
  const iter = Number(policy.checkpoint_iteration ?? checkpointIterationFromPath(policy.checkpoint) ?? 0);
  const maxIterations = Number(run.hyperparams?.max_iterations ?? 0);
  return (Number.isFinite(iter) && iter > 0 && iter <= 10) || (Number.isFinite(maxIterations) && maxIterations > 0 && maxIterations <= 10);
}

function policyIterationLabel(policy, run = null) {
  const iter = policyIterationValue(policy);
  if (iter === null && isPretrainedRun(run)) return "预训练权重";
  return iter !== null ? `第 ${iter} 轮` : "已训练权重";
}

function policyIterationValue(policy) {
  const raw = policy?.checkpoint_iteration ?? checkpointIterationFromPath(policy?.checkpoint);
  if (raw === null || raw === undefined || raw === "") return null;
  const value = Number(raw);
  return Number.isFinite(value) ? value : null;
}

function isPretrainedRun(run) {
  if (!run) return false;
  const maxIterations = Number(run.hyperparams?.max_iterations);
  return Number.isFinite(maxIterations) && maxIterations <= 0;
}

function liveRunHint(run, policy) {
  const progress = run.progress || {};
  const parts = [stageLabel(progress.stage) || "训练状态更新中"];
  if (policy) parts.push(`最新可播放 ${policyIterationLabel(policy, run)}`);
  const lag = exportLag(run, policy);
  if (lag !== null && lag > 0) parts.push(`训练领先 ONNX ${lag} 轮`);
  if (progress.terrain_level != null) parts.push(`地形 ${Number(progress.terrain_level).toFixed(2)}`);
  return parts.join(" · ");
}

function quickLiveMeta(run, policy) {
  if (!isLiveRun(run)) return "";
  const progress = run.progress || {};
  const parts = [];
  if (progress.iteration && progress.max_iterations) parts.push(`训练 ${progress.iteration}/${progress.max_iterations}`);
  if (policy) parts.push(`最新 ONNX ${policyIterationLabel(policy, run)}`);
  const lag = exportLag(run, policy);
  if (lag !== null && lag > 0) parts.push(`领先 ${lag} 轮`);
  return parts.join(" · ");
}

function exportLagLabel(run, policy) {
  if (!policy) return "-";
  const lag = exportLag(run, policy);
  if (lag === null) return "-";
  return lag <= 0 ? "已同步" : `${lag} 轮`;
}

function exportLag(run, policy) {
  const progress = run.progress || {};
  const trainIter = Number(progress.iteration);
  const policyIter = policyIterationValue(policy);
  if (!Number.isFinite(trainIter) || policyIter === null) return null;
  return Math.max(0, trainIter - policyIter);
}

function stageLabel(value) {
  const text = String(value || "").trim();
  if (!text) return "";
  const train = text.match(/^training\s+(\d+)\/(\d+)$/i);
  if (train) return `训练 ${train[1]}/${train[2]}`;
  const evaluating = text.match(/^evaluating\s+(.+)$/i);
  if (evaluating) return `评估 ${evaluating[1]}`;
  const exporting = text.match(/^exporting\s+(.+)$/i);
  if (exporting) return `导出 ${exporting[1]}`;
  return text
    .replace(/^queued$/i, "排队中")
    .replace(/^running$/i, "训练中")
    .replace(/^succeeded$/i, "已完成")
    .replace(/^failed$/i, "失败")
    .replace(/^canceled$/i, "已停止")
    .replace(/^cancelled$/i, "已停止");
}

function deploymentLabel(value, algorithmName = "") {
  if (isAmpAlgorithm(algorithmName)) return "开发中";
  const key = String(value || "").toLowerCase();
  const known = {
    ready: "已验证",
    partial: "持续优化",
    experimental: "开放体验",
    blocked: "开发中",
    invalid: "暂未开放",
    legacy: "兼容模式",
  };
  return known[key] || value || "";
}

function runStatusLabel(value) {
  const key = String(value || "").toLowerCase();
  const known = {
    queued: "排队中",
    running: "训练中",
    evaluating: "评估中",
    succeeded: "已完成",
    failed: "失败",
    cancelled: "已停止",
    canceled: "已停止",
    stopped: "已停止",
    partial: "部分完成",
    ready: "就绪",
  };
  return known[key] || value || "-";
}

function sim2simHref(run, policy, quick = {}) {
  const params = new URLSearchParams({ run_id: run.id, policy: policy.id });
  const iterValue = policy.checkpoint_iteration ?? checkpointIterationFromPath(policy.checkpoint);
  if (iterValue !== undefined && iterValue !== null && iterValue !== "") {
    params.set("iter", String(iterValue));
  }
  const terrain = simTerrainParam(runQuickTerrain(run) || quick.quick_terrain || quick.terrain);
  if (terrain) params.set("terrain", terrain);
  const autoplay = quickAutoplay(quick);
  if (autoplay !== null) params.set("autoplay", autoplay ? "1" : "0");
  const robot = quickRobotParam(quick);
  if (robot) params.set("robot", robot);
  params.set("v", String(policy.created_at || run.updated_at || Date.now()));
  return `/sim2sim/?${params.toString()}`;
}

function quickPlayOptionsForRun(run, info = {}) {
  const task = Array.isArray(info.tasks)
    ? info.tasks.find((item) => item.id === run?.task_id) || info.tasks[0] || {}
    : {};
  const artifacts = {
    ...(info.manifest?.artifacts || {}),
    ...(task.artifacts || {}),
  };
  const preview = task.preview || {};
  return {
    ...preview,
    quick_terrain: artifacts.quick_terrain || artifacts.sim2sim_terrain || preview.quick_terrain || "",
    quick_autoplay: artifacts.quick_autoplay,
  };
}

function preferredRobotForRun(run, info = {}) {
  return normalizePreviewRobot(quickPlayOptionsForRun(run, info).robot);
}

function runMatchesPreferredRobot(run, robotKey) {
  if (!robotKey) return false;
  const haystack = [
    run?.robot_id,
    run?.robot_name,
    run?.robot_snapshot?.name,
    run?.robot_snapshot?.urdf_ref,
  ].map((item) => String(item || "").toLowerCase()).join(" ");
  if (robotKey === "fsdog1") return haystack.includes("fsdog");
  if (robotKey === "go2") return haystack.includes("go2");
  return haystack.includes(robotKey);
}

function quickRobotParam(quick = {}) {
  return normalizePreviewRobot(quick.robot || quick.quick_robot || quick.robot_asset);
}

function quickRobotDisplayName(run, quick = {}, fallback = "") {
  const robot = quickRobotParam(quick);
  return robot ? readableRobotName(robot) : displayRobotName(run, fallback);
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

function algorithmInfoForRun(run, algorithmList = []) {
  const algorithm = (algorithmList || []).find((item) => item.id === run?.algorithm_id);
  return {
    manifest: algorithm?.manifest || {},
    tasks: Array.isArray(algorithm?.manifest?.tasks) ? algorithm.manifest.tasks : [],
  };
}

function runQuickTerrain(run) {
  const artifacts = run?.task_snapshot?.artifacts;
  if (artifacts && typeof artifacts === "object") {
    return artifacts.quick_terrain || artifacts.sim2sim_terrain || "";
  }
  return "";
}

function quickAutoplay(quick = {}) {
  if (quick.quick_autoplay === undefined || quick.quick_autoplay === null) return null;
  if (typeof quick.quick_autoplay === "string") {
    return !["0", "false", "no", "off"].includes(quick.quick_autoplay.trim().toLowerCase());
  }
  return quick.quick_autoplay !== false;
}

function simTerrainParam(value) {
  const raw = String(value || "").trim().toLowerCase();
  if (!raw) return "";
  const normalized = raw.replace(/\.xml$/i, "").replace(/[-\s]+/g, "_");
  const aliases = {
    slope: "cross_slope",
    rough: "stairs",
    rough_terrain: "stairs",
    stairs: "stairs",
    obstacle: "cross_stairs",
    obstacles: "cross_stairs",
    agility: "cross_stairs",
    cross_stairs: "cross_stairs",
    cross_slope: "cross_slope",
    parkour: "race_track",
    jump: "race_track",
    jumping: "race_track",
    race_track: "race_track",
    flat: "flat",
  };
  return aliases[normalized] || normalized;
}

function isPolicyPlayable(policy) {
  if (!policy?.id || !policy?.onnx_url) return false;
  const status = String(policy.health?.status || "pass").toLowerCase();
  return status === "pass" || status === "ready";
}

function playablePolicy(run) {
  if (isPolicyPlayable(run?.playable_policy)) return run.playable_policy;
  if (isPolicyPlayable(run?.latest_policy)) return run.latest_policy;
  return null;
}

function checkpointIterationFromPath(path) {
  const name = String(path || "").split(/[\\/]/).pop() || "";
  const match = name.match(/(?:model|checkpoint|ckpt|iter|iteration)[_-]?(\d+)\b/i) || name.match(/^(\d+)\D*$/);
  return match ? Number(match[1]) : null;
}

function adapterRow(adapter) {
  const task = Array.isArray(adapter.tasks) ? adapter.tasks[0] || {} : {};
  const deployment = adapter.deployment || adapter.status || "blocked";
  const missing = Array.isArray(adapter.missing) ? adapter.missing : [];
  const statusText = adapterStatusLabel(adapter, deployment, task);
  return `
    <article class="home-adapter-row ${escapeAttr(deployment)}">
      <div>
        <strong>${escapeHtml(adapter.name || "-")}</strong>
        <span>${escapeHtml(adapter.version || "-")} / ${escapeHtml(task.name || task.id || "default")}</span>
      </div>
      <span class="status-badge ${deployment === "partial" ? "partial" : deployment === "ready" ? "ready" : "failed"}">${escapeHtml(statusText)}</span>
      <div class="home-cap-list">
        ${cap("训练", task.train)}
        ${cap("继续", task.resume)}
        ${cap("导出", task.onnx_export)}
        ${cap("仿真", task.sim2sim)}
        ${cap("预览", task.preview_video)}
      </div>
      ${missing.length ? `<small>待补：${escapeHtml(missing.join(" / "))}</small>` : ""}
    </article>
  `;
}

function fallbackAdapter(algo) {
  const manifest = algo?.manifest || {};
  const task = Array.isArray(manifest.tasks) ? manifest.tasks[0] || {} : {};
  const caps = { ...(manifest.capabilities || {}), ...(task.capabilities || {}) };
  return {
    name: manifest.display_name || manifest.name || algo.name,
    version: algo.version,
    status: algo.status,
    deployment: algo.status === "ready"
      ? (caps.deployment || (caps.sim2sim === false ? "partial" : "experimental"))
      : (algo.status || "blocked"),
    tasks: [{
      name: task.name || task.id || "default",
      train: algo.status === "ready" && caps.train !== false,
      resume: caps.resume === true,
      onnx_export: caps.onnx_export !== false,
      sim2sim: caps.sim2sim !== false,
      preview_video: caps.preview_video === true,
    }],
    missing: [],
  };
}

function adapterStatusLabel(adapter, deployment, task) {
  if (isAmpAlgorithm(adapter?.name)) return "开发中";
  const base = deploymentLabel(deployment, adapter?.name);
  if (!adapterTrainable(adapter, task)) return base;
  if (String(deployment).toLowerCase() === "ready") return "可训练 · 已验证";
  if (String(deployment).toLowerCase() === "partial") return "可训练 · 持续优化";
  return base;
}

function adapterTrainable(adapter, task = null) {
  const tasks = Array.isArray(adapter?.tasks) ? adapter.tasks : [];
  if (task) return task.train === true;
  return tasks.some((item) => item?.train === true) || (adapter?.status === "ready" && !tasks.length);
}

function isAmpAlgorithm(value) {
  return String(value || "").toLowerCase().replace(/[^a-z0-9]+/g, "_").includes("amp_cts");
}

function cap(label, ok) {
  return `<span class="home-cap ${ok ? "ok" : "miss"}">${escapeHtml(label)}</span>`;
}

function systemRow(label, value) {
  return `<div class="home-system-row"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`;
}

function countTile(label, value) {
  return `<div class="home-count"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`;
}

function metric(label, value) {
  return `<div class="home-metric"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`;
}

function progressPercent(run) {
  const progress = run.progress || {};
  const iter = Number(progress.iteration);
  const max = Number(progress.max_iterations);
  if (Number.isFinite(iter) && Number.isFinite(max) && max > 0) {
    return Math.max(0, Math.min(100, Math.round((iter / max) * 100)));
  }
  const percent = Number(progress.percent);
  return Number.isFinite(percent) ? Math.max(0, Math.min(100, percent)) : 0;
}

function fulfilled(result) {
  return result.status === "fulfilled" ? result.value : null;
}

function arrayValue(result) {
  return result.status === "fulfilled" && Array.isArray(result.value) ? result.value : [];
}

function formatTime(ts) {
  if (!ts) return "-";
  return new Date(ts * 1000).toLocaleString("zh-CN", { hour12: false });
}

function shortRunId(id) {
  const text = String(id || "");
  if (!text) return "-";
  return text.length > 18 ? `${text.slice(0, 12)}...${text.slice(-6)}` : text;
}

function readableAlgorithmName(id) {
  const raw = String(id || "").toLowerCase().replace(/^alg_builtin_/, "");
  const known = {
    go2_rl_gym: "Go2 RL Gym",
    wheel_leg_rl_gym: "Wheel-Leg MoE-CTS",
    wheel_leg_gait_rl_gym: "Wheel-Leg Gait MoE-CTS",
    wheel_leg_gait_hip_degradation: "Wheel-Leg Gait Full-Torque MoE-CTS",
    wheel_leg_jump_rl_gym: "Wheel-Leg Jump MoE-CTS",
    wheel_leg_high_speed: "Wheel-Leg High-Speed",
    amp_cts: "P1 · AMP-CTS",
    np3o: "NP3O",
    quadrupedal_agility: "Quadrupedal Agility",
    parkour: "Robot Parkour",
    omni_jump: "Omni-Jump",
  };
  return known[raw] || raw || "-";
}

function readableRobotName(id) {
  const raw = String(id || "").replace(/^rbt_builtin_/, "");
  const known = {
    go2: "Unitree Go2",
    fsdog1: "FSDog1",
    s07: "P1",
    y2: "Y2 Wheel-Leg",
    y1: "Y1 Wheel-Leg",
    w1w: "W1W Wheel-Leg",
  };
  return known[raw] || raw || "-";
}

function displayAlgorithmName(run, fallback = "") {
  return readableAlgorithmName(run?.algorithm_name || fallback || run?.algorithm_id || "-");
}

function displayRobotName(run, fallback = "") {
  return run?.robot_name || fallback || readableRobotName(run?.robot_id);
}

function displayTaskName(run) {
  const explicit = run?.task_name || "";
  if (explicit && explicit !== "default") return explicit;
  const taskId = String(run?.task_id || "");
  if (taskId && taskId !== "default") return readableTaskName(taskId, run);
  return readableTaskName(taskId || "default", run);
}

function readableTaskName(taskId, run) {
  const raw = String(taskId || "").toLowerCase();
  const algorithm = String(run?.algorithm_name || run?.algorithm_id || "").toLowerCase().replace(/^alg_builtin_/, "");
  const known = {
    s07_amp_cts: "P1 · AMP-CTS",
    go2_moe_cts: "Go2 速度跟踪",
    y2_moe_cts: "Y2 轮足速度跟踪",
    y1_moe_cts: "Y1 轮足速度跟踪",
    w1w_moe_cts: "W1W 轮足速度跟踪",
    go2_np3o_velocity: "NP3O 速度跟踪",
    go2_tsc_agility: "Go2 敏捷地形",
    go2_rough_parkour: "Go2 跑酷地形",
    go2_omni_jump: "Go2 全向跳跃",
    go1_omni_jump: "Go1 全向跳跃",
  };
  if (raw === "w1w_moe_cts" && algorithm === "wheel_leg_high_speed") {
    return "Wheel-Leg High-Speed";
  }
  if (raw === "wheel_leg_gait_moe_cts" && algorithm === "wheel_leg_gait_rl_gym") {
    return "Wheel-Leg Gait MoE-CTS";
  }
  if (raw === "wheel_leg_gait_hip_degradation_moe_cts" && algorithm === "wheel_leg_gait_hip_degradation") {
    return "Wheel-Leg Gait Full-Torque MoE-CTS";
  }
  if (known[raw]) return known[raw];
  if (raw === "default") {
    if (algorithm.includes("go2_rl_gym")) return "Go2 速度跟踪";
    if (algorithm.includes("np3o")) return "NP3O 速度跟踪";
  }
  return taskId || "默认任务";
}

function escapeAttr(s) { return String(s).replace(/[^a-zA-Z0-9_-]/g, ""); }
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
