import { algorithms, ApiError, meta, ops, robots, runs } from "../shared/api.js?v=ops-cleanup-local-1";

const el = {
  refresh: document.getElementById("refreshButton"),
  artifactRefresh: document.getElementById("artifactRefreshButton"),
  algorithmRefresh: document.getElementById("algorithmRefreshButton"),
  queueRefresh: document.getElementById("queueRefreshButton"),
  markOrphans: document.getElementById("markOrphansButton"),
  notice: document.getElementById("opsNotice"),
  summaryBadge: document.getElementById("summaryBadge"),
  summaryTitle: document.getElementById("summaryTitle"),
  summaryText: document.getElementById("summaryText"),
  lastChecked: document.getElementById("lastChecked"),
  countGrid: document.getElementById("countGrid"),
  checkList: document.getElementById("checkList"),
  productionGuide: document.getElementById("productionGuide"),
  copyEnv: document.getElementById("copyEnvButton"),
  remoteDetail: document.getElementById("remoteDetail"),
  queuePanel: document.getElementById("queuePanel"),
  artifactPanel: document.getElementById("artifactPanel"),
  algorithmPanel: document.getElementById("algorithmPanel"),
};

init();

function init() {
  el.refresh.addEventListener("click", load);
  el.artifactRefresh.addEventListener("click", loadArtifacts);
  el.algorithmRefresh.addEventListener("click", loadAlgorithms);
  el.queueRefresh.addEventListener("click", loadQueue);
  el.markOrphans.addEventListener("click", markOrphans);
  el.copyEnv?.addEventListener("click", copyProductionEnv);
  load();
  loadQueue();
  loadArtifacts();
  loadAlgorithms();
}

document.addEventListener("click", (event) => {
  const target = event.target instanceof Element ? event.target.closest("[data-action]") : null;
  if (!target) return;
  const action = target.getAttribute("data-action");
  if (action === "cleanup-local-artifacts") {
    event.preventDefault();
    cleanupLocalArtifacts(target);
  } else if (action === "cleanup-remote-checkpoints") {
    event.preventDefault();
    cleanupRemoteCheckpoints(target);
  }
});

async function load() {
  setLoading();
  try {
    const data = await ops.preflight();
    render(data);
  } catch (error) {
    if (isAccessError(error)) {
      renderAccessError(error);
      return;
    }
    if (error instanceof ApiError && error.status === 404) {
      try {
        render(await fallbackPreflight(error));
        return;
      } catch (fallbackError) {
        renderError(fallbackError);
        return;
      }
    }
    renderError(error);
  }
}

async function loadArtifacts() {
  el.artifactRefresh.disabled = true;
  el.artifactPanel.innerHTML = `<div class="ops-empty">盘点中...</div>`;
  try {
    const cleanupPlanPromise = typeof ops.artifactCleanupPlan === "function"
      ? ops.artifactCleanupPlan().catch(() => null)
      : Promise.resolve(null);
    const [data, cleanupPlan] = await Promise.all([
      ops.artifacts(),
      cleanupPlanPromise,
    ]);
    renderArtifacts(data, cleanupPlan);
  } catch (error) {
    if (isAccessError(error)) {
      el.artifactPanel.innerHTML = accessPanelMarkup(error, "产物盘点");
      return;
    }
    const message = error instanceof ApiError && error.status === 404
      ? "当前后端还没有加载产物盘点接口；重启 web-only 服务后可用。"
      : (error instanceof ApiError ? error.message : "产物盘点失败");
    el.artifactPanel.innerHTML = `<div class="ops-empty error">${escapeHtml(message)}</div>`;
  } finally {
    el.artifactRefresh.disabled = false;
  }
}

async function loadAlgorithms() {
  el.algorithmRefresh.disabled = true;
  el.algorithmPanel.innerHTML = `<div class="ops-empty">读取适配清单...</div>`;
  try {
    const data = await ops.algorithms();
    renderAlgorithms(data);
  } catch (error) {
    if (isAccessError(error)) {
      el.algorithmPanel.innerHTML = accessPanelMarkup(error, "算法适配清单");
      return;
    }
    const message = error instanceof ApiError && error.status === 404
      ? "当前后端还没有加载算法适配清单接口；新版 web-only 服务可直接查看。"
      : (error instanceof ApiError ? error.message : "算法适配清单读取失败");
    el.algorithmPanel.innerHTML = `<div class="ops-empty error">${escapeHtml(message)}</div>`;
  } finally {
    el.algorithmRefresh.disabled = false;
  }
}

async function loadQueue() {
  el.queueRefresh.disabled = true;
  el.queuePanel.innerHTML = `<div class="ops-empty">读取队列状态...</div>`;
  try {
    const data = await ops.queue();
    renderQueue(data);
  } catch (error) {
    if (isAccessError(error)) {
      el.queuePanel.innerHTML = accessPanelMarkup(error, "队列状态");
      return;
    }
    const message = error instanceof ApiError && error.status === 404
      ? "当前后端还没有加载队列状态接口；重启 web-only 服务后可用。"
      : (error instanceof ApiError ? error.message : "队列状态读取失败");
    el.queuePanel.innerHTML = `<div class="ops-empty error">${escapeHtml(message)}</div>`;
  } finally {
    el.queueRefresh.disabled = false;
  }
}

function renderArtifacts(data, cleanupPlan = null) {
  const runItems = Array.isArray(data.runs) ? data.runs.slice(0, 8) : [];
  const retentionCounts = data.retention_counts || {};
  const retentionBytes = data.retention_bytes || {};
  el.artifactPanel.innerHTML = `
    <div class="artifact-summary">
      <div><span>总计</span><strong>${formatBytes(data.total_bytes || 0)}</strong></div>
      <div><span>本地 runs</span><strong>${formatBytes(data.local_runs_bytes || 0)}</strong></div>
      <div><span>事件日志</span><strong>${formatBytes(data.event_logs_bytes || 0)}</strong></div>
      <div><span>ONNX</span><strong>${formatBytes(data.policy_bytes || 0)}</strong></div>
      <div><span>远程 ckpt</span><strong>${formatBytes(data.remote_checkpoint_bytes || 0)}</strong></div>
    </div>
    <div class="artifact-retention">
      <div class="artifact-retention-head">
        <span class="ops-state ${retentionCounts.cleanup ? "warn" : retentionCounts.review ? "warn" : "pass"}">${escapeHtml(retentionCounts.cleanup ? "CLEANUP" : retentionCounts.review ? "REVIEW" : "PROTECT")}</span>
        <p>${escapeHtml(retentionSummary(data))}</p>
      </div>
      <div class="artifact-retention-bars">
        <div class="artifact-retention-bar protect"><strong>${escapeHtml(retentionCounts.protect || 0)}</strong><span>${formatBytes(retentionBytes.protect || 0)}</span></div>
        <div class="artifact-retention-bar review"><strong>${escapeHtml(retentionCounts.review || 0)}</strong><span>${formatBytes(retentionBytes.review || 0)}</span></div>
        <div class="artifact-retention-bar cleanup"><strong>${escapeHtml(retentionCounts.cleanup || 0)}</strong><span>${formatBytes(retentionBytes.cleanup || 0)}</span></div>
      </div>
      <div class="artifact-retention-foot">
        <span>oldest ${escapeHtml(formatAge(data.oldest_run_age_seconds || 0))}</span>
        <span>preview ${formatBytes(data.preview_bytes || 0)}</span>
        <span>uploads ${formatBytes(data.temporary_upload_bytes || 0)}</span>
      </div>
    </div>
    ${cleanupPlan ? cleanupPlanMarkup(cleanupPlan) : ""}
    <div class="artifact-list">
      ${runItems.length ? runItems.map(artifactRow).join("") : `<div class="ops-empty">没有运行产物。</div>`}
    </div>
  `;
}

function artifactRow(run) {
  const retention = String(run.retention_state || "protect");
  const reasons = Array.isArray(run.retention_reasons) ? run.retention_reasons : [];
  return `
    <article class="artifact-row ${escapeAttr(retention)}">
      <div>
        <strong>${escapeHtml(run.run_id)}</strong>
        <span>${escapeHtml(run.status)} / ${escapeHtml(run.stage || "-")}</span>
      </div>
      <div class="artifact-row-meta">
        <span class="ops-state ${stateForRetention(retention)}">${escapeHtml(retention.toUpperCase())}</span>
        <span>${escapeHtml(formatAge(run.age_seconds || 0))}</span>
      </div>
      <dl>
        <dt>local</dt><dd>${formatBytes(run.local_bytes || 0)}</dd>
        <dt>onnx</dt><dd>${escapeHtml(run.policy_count || 0)} / ${formatBytes(run.policy_bytes || 0)}</dd>
        <dt>ckpt</dt><dd>${escapeHtml(run.remote_checkpoint_count || 0)} / ${formatBytes(run.remote_checkpoint_bytes || 0)}</dd>
        <dt>total</dt><dd>${formatBytes(run.total_bytes || 0)}</dd>
        <dt>latest</dt><dd>${escapeHtml(run.latest_checkpoint_iteration ?? "-")}</dd>
      </dl>
      ${reasons.length ? `<p class="artifact-reasons">${escapeHtml(reasons.join(" / "))}</p>` : ""}
    </article>
  `;
}

function cleanupPlanMarkup(plan) {
  const rows = Array.isArray(plan.runs) ? plan.runs.slice(0, 4) : [];
  const remoteRows = Array.isArray(plan.remote_checkpoint_runs) ? plan.remote_checkpoint_runs.slice(0, 4) : [];
  const empty = !rows.length;
  const reclaim = Number(plan.local_reclaim_bytes || 0);
  const remoteFiles = Number(plan.remote_checkpoint_file_count || 0);
  return `
    <div class="artifact-cleanup-plan ${empty ? "empty" : ""}">
      <div class="artifact-cleanup-head">
        <span class="ops-state ${empty ? "pass" : "warn"}">${empty ? "DRY RUN" : "CLEANUP PLAN"}</span>
        <p>${empty
          ? "暂无需要优先清理的 run；这里只有只读计划，不会删除文件。"
          : `${escapeHtml(plan.candidate_count || rows.length)} 个候选，预计本地可回收 ${formatBytes(reclaim)}。执行时会跳过仍有健康可播放 ONNX 的 run。`}</p>
      </div>
      <div class="artifact-cleanup-metrics">
        <div><span>local</span><strong>${formatBytes(plan.local_reclaim_bytes || 0)}</strong></div>
        <div><span>event log</span><strong>${formatBytes(plan.event_log_reclaim_bytes || 0)}</strong></div>
        <div><span>ONNX</span><strong>${formatBytes(plan.policy_reclaim_bytes || 0)}</strong></div>
        <div><span>remote ckpt</span><strong>${formatBytes(plan.remote_reclaim_bytes || 0)}</strong></div>
      </div>
      ${rows.length ? `<div class="artifact-cleanup-list">${rows.map(cleanupPlanRow).join("")}</div>` : ""}
      ${empty ? "" : `
        <div class="artifact-cleanup-actions">
          <button class="btn-danger" type="button" data-action="cleanup-local-artifacts" data-limit="${escapeAttr(String(rows.length || 1))}">清理本地产物</button>
          <span>只删除本地 run 目录，不删除数据库记录和远程 checkpoint。</span>
        </div>
      `}
      <div class="artifact-remote-plan ${remoteFiles ? "" : "empty"}">
        <div class="artifact-cleanup-head">
          <span class="ops-state ${remoteFiles ? "warn" : "pass"}">REMOTE CKPT</span>
          <p>${remoteFiles
            ? `${escapeHtml(plan.remote_checkpoint_candidate_count || remoteRows.length)} 个 run 有旧 checkpoint，保留最新 ${escapeHtml(plan.remote_checkpoint_keep || 2)} 个，预计远程可回收 ${formatBytes(plan.remote_checkpoint_reclaim_bytes || 0)}。`
            : `远程 checkpoint 配额正常，默认每个 cleanup run 保留最新 ${escapeHtml(plan.remote_checkpoint_keep || 2)} 个。`}</p>
        </div>
        <div class="artifact-cleanup-metrics">
          <div><span>candidate runs</span><strong>${escapeHtml(plan.remote_checkpoint_candidate_count || 0)}</strong></div>
          <div><span>old ckpt</span><strong>${escapeHtml(remoteFiles)}</strong></div>
          <div><span>keep latest</span><strong>${escapeHtml(plan.remote_checkpoint_keep || 2)}</strong></div>
          <div><span>remote reclaim</span><strong>${formatBytes(plan.remote_checkpoint_reclaim_bytes || 0)}</strong></div>
        </div>
        ${remoteRows.length ? `<div class="artifact-cleanup-list">${remoteRows.map(remoteCheckpointRow).join("")}</div>` : ""}
        ${remoteFiles ? `
          <div class="artifact-cleanup-actions">
            <button class="btn-danger" type="button" data-action="cleanup-remote-checkpoints" data-limit="${escapeAttr(String(plan.remote_checkpoint_candidate_count || 1))}" data-keep="${escapeAttr(String(plan.remote_checkpoint_keep || 2))}">清理远程旧 ckpt</button>
            <span>只删除 cleanup run 中超过保留数的旧 checkpoint，不删除最新 checkpoint。</span>
          </div>
        ` : ""}
      </div>
    </div>
  `;
}

function cleanupPlanRow(run) {
  const reasons = Array.isArray(run.retention_reasons) ? run.retention_reasons.join(" / ") : "";
  return `
    <div class="artifact-cleanup-row">
      <strong>${escapeHtml(run.run_id)}</strong>
      <span>${escapeHtml(run.status || "-")} / ${formatBytes(run.total_bytes || 0)} / ${escapeHtml(formatAge(run.age_seconds || 0))}</span>
      ${reasons ? `<small>${escapeHtml(reasons)}</small>` : ""}
    </div>
  `;
}

function remoteCheckpointRow(run) {
  const files = Array.isArray(run.delete_files) ? run.delete_files : [];
  const first = files[0]?.path ? files[0].path.split("/").pop() : "";
  return `
    <div class="artifact-cleanup-row">
      <strong>${escapeHtml(run.run_id || "-")}</strong>
      <span>${escapeHtml(run.status || "-")} / delete ${escapeHtml(run.delete_count || 0)} / reclaim ${formatBytes(run.reclaim_bytes || 0)}</span>
      ${first ? `<small>first old ckpt: ${escapeHtml(first)}</small>` : ""}
    </div>
  `;
}

function retentionSummary(data) {
  const counts = data.retention_counts || {};
  const bytes = data.retention_bytes || {};
  if (counts.cleanup) {
    return `${counts.cleanup} 个 run 可优先清理，回收约 ${formatBytes(bytes.cleanup || 0)}`;
  }
  if (counts.review) {
    return `${counts.review} 个 run 建议复查保留，受保护 ${counts.protect || 0} 个`;
  }
  return "当前产物都在保护区";
}

function stateForRetention(state) {
  if (state === "cleanup") return "fail";
  if (state === "review") return "warn";
  return "pass";
}

function renderQueue(data) {
  const counts = data.counts || {};
  const worker = data.worker || {};
  const leases = Array.isArray(data.worker_leases) ? data.worker_leases : [];
  const activeRuns = Array.isArray(data.active_runs) ? data.active_runs : [];
  const terminalRuns = Array.isArray(data.recent_terminal_runs) ? data.recent_terminal_runs : [];
  const remoteProcesses = Array.isArray(data.remote_processes) ? data.remote_processes : [];
  const remoteProcessItems = Array.isArray(data.remote_process_items) ? data.remote_process_items : [];
  const workerMode = worker.embedded ? "embedded" : "external";
  el.queuePanel.innerHTML = `
    <div class="queue-summary">
      <div><span>active</span><strong>${escapeHtml(counts.active || 0)}</strong></div>
      <div><span>queued</span><strong>${escapeHtml(counts.queued || 0)}</strong></div>
      <div><span>running</span><strong>${escapeHtml(counts.running || 0)}</strong></div>
      <div><span>remote proc</span><strong>${escapeHtml(data.remote_process_count || 0)}</strong></div>
    </div>
    <div class="queue-worker">
      <span class="ops-state ${worker.embedded ? "warn" : "pass"}">${escapeHtml(workerMode.toUpperCase())}</span>
      <p>poll ${escapeHtml(worker.poll_interval_seconds ?? "-")}s / idle guard ${worker.require_idle_remote ? "on" : "off"} / orphan startup ${worker.mark_orphaned_runs_on_startup ? "on" : "off"}</p>
    </div>
    <h3 class="queue-title">GPU lease</h3>
    <div class="queue-lease-list">
      ${leases.length ? leases.map(leaseRow).join("") : `<div class="ops-empty compact">没有本地 worker lease。</div>`}
    </div>
    <h3 class="queue-title">活动任务</h3>
    <div class="queue-list">
      ${activeRuns.length ? activeRuns.map(queueRunRow).join("") : `<div class="ops-empty">现在没有排队或运行中的任务。</div>`}
    </div>
    <h3 class="queue-title">最近结束</h3>
    <div class="queue-list">
      ${terminalRuns.length ? terminalRuns.map(queueRunRow).join("") : `<div class="ops-empty">还没有最近结束的任务。</div>`}
    </div>
    <h3 class="queue-title">远程训练进程</h3>
    ${remoteProcessItems.length
      ? `<div class="queue-process-grid">${remoteProcessItems.map(remoteProcessRow).join("")}</div>`
      : `<pre class="queue-processes">${escapeHtml(remoteProcesses.length ? remoteProcesses.join("\n") : "未检测到 platform_train.py 进程")}</pre>`}
  `;
}

function remoteProcessRow(item) {
  const cpu = item.cpu_percent === null || item.cpu_percent === undefined ? "-" : `${Number(item.cpu_percent).toFixed(1)}%`;
  const mem = item.mem_percent === null || item.mem_percent === undefined ? "-" : `${Number(item.mem_percent).toFixed(1)}%`;
  const rss = item.rss_mb === null || item.rss_mb === undefined ? "-" : `${Number(item.rss_mb).toFixed(1)} MB`;
  const command = item.command || item.raw || "-";
  return `
    <article class="queue-process-card">
      <div class="queue-process-head">
        <strong>PID ${escapeHtml(item.pid || "-")}</strong>
        <span>${escapeHtml(item.state || "-")}</span>
      </div>
      <dl>
        <dt>run</dt><dd>${escapeHtml(item.run_id || "-")}</dd>
        <dt>time</dt><dd>${escapeHtml(item.etime || "-")}</dd>
        <dt>cpu</dt><dd>${escapeHtml(cpu)}</dd>
        <dt>rss</dt><dd>${escapeHtml(rss)}</dd>
        <dt>mem</dt><dd>${escapeHtml(mem)}</dd>
        <dt>ppid</dt><dd>${escapeHtml(item.ppid || "-")}</dd>
      </dl>
      <pre title="${escapeAttr(command)}">${escapeHtml(command)}</pre>
    </article>
  `;
}

function leaseRow(lease) {
  const active = lease.active ? "active" : "expired";
  const expires = Number.isFinite(Number(lease.expires_in_seconds))
    ? `${formatAge(Math.abs(lease.expires_in_seconds))}${lease.expires_in_seconds < 0 ? " ago" : ""}`
    : "-";
  return `
    <article class="queue-lease ${escapeAttr(active)}">
      <span class="ops-state ${lease.active ? "pass" : "warn"}">${escapeHtml(active.toUpperCase())}</span>
      <div>
        <strong>${escapeHtml(lease.name || "-")}</strong>
        <p>${escapeHtml(lease.owner || "-")}</p>
      </div>
      <dl>
        <dt>run</dt><dd>${escapeHtml(lease.run_id || "-")}</dd>
        <dt>seen</dt><dd>${escapeHtml(formatAge(lease.age_seconds || 0))}</dd>
        <dt>expires</dt><dd>${escapeHtml(expires)}</dd>
      </dl>
    </article>
  `;
}

function queueRunRow(run) {
  const status = String(run.status || "unknown");
  const pct = run.percent == null ? "-" : `${Math.round(Number(run.percent))}%`;
  const playableIter = run.playable_policy_iteration ?? "ONNX";
  const latestIter = run.latest_policy_iteration ?? "ONNX";
  const policyIter = run.playable_policy_id ? playableIter : latestIter;
  const policyHealth = run.playable_policy_health || run.latest_policy_health || (run.latest_policy_id ? "unknown" : "-");
  const latestBad = run.latest_policy_id && run.playable_policy_id && run.latest_policy_id !== run.playable_policy_id;
  const heartbeatText = heartbeatDisplay(run);
  const playHref = run.playable_policy_id ? sim2simHref(run) : "";
  return `
    <article class="queue-row ${escapeAttr(status)}">
      <div class="queue-row-head">
        <a href="/train/?run_id=${encodeURIComponent(run.run_id)}">${escapeHtml(run.run_id)}</a>
        <span class="ops-state ${stateForRun(status)}">${escapeHtml(status.toUpperCase())}</span>
      </div>
      <p>${escapeHtml(run.robot || "-")} / ${escapeHtml(run.algorithm || "-")} / ${escapeHtml(run.stage || run.task_id || "-")}${run.cancel_requested ? " / cancel requested" : ""}</p>
      <dl>
        <dt>progress</dt><dd>${escapeHtml(pct)}</dd>
        <dt>policy</dt><dd>${escapeHtml(policyIter)}${latestBad ? ` <small>latest ${escapeHtml(latestIter)} bad</small>` : ""}</dd>
        <dt>health</dt><dd class="policy-health ${escapeAttr(policyHealth)}">${escapeHtml(policyHealth)}</dd>
        <dt>age</dt><dd>${escapeHtml(formatAge(run.age_seconds || 0))}</dd>
        <dt>heartbeat</dt><dd>${escapeHtml(heartbeatText)}</dd>
      </dl>
      ${playHref ? `<a class="queue-play-link" href="${escapeAttrUrl(playHref)}">Sim2Sim ${escapeHtml(policyIter)}</a>` : ""}
    </article>
  `;
}

function heartbeatDisplay(run) {
  if (run.heartbeat_age_seconds != null) {
    const phase = run.heartbeat_phase ? ` / ${run.heartbeat_phase}` : "";
    return `${formatAge(run.heartbeat_age_seconds)}${phase}`;
  }
  if (["running", "evaluating"].includes(String(run.status || ""))) {
    return `updated ${formatAge(run.age_seconds || 0)} ago`;
  }
  return "-";
}

function sim2simHref(run) {
  const params = new URLSearchParams({ run_id: run.run_id, policy: run.playable_policy_id });
  if (run.playable_policy_iteration !== undefined && run.playable_policy_iteration !== null) {
    params.set("iter", String(run.playable_policy_iteration));
  }
  params.set("v", String(Math.round(run.updated_at || Date.now())));
  return `/sim2sim/?${params.toString()}`;
}

function stateForRun(status) {
  if (["succeeded"].includes(status)) return "pass";
  if (["failed", "canceled"].includes(status)) return "fail";
  return "warn";
}

function renderAlgorithms(data) {
  const adapters = Array.isArray(data.adapters) ? data.adapters : [];
  el.algorithmPanel.innerHTML = `
    <div class="adapter-summary">
      <div><span>成熟适配</span><strong>${escapeHtml(data.ready_count || 0)}</strong></div>
      <div><span>需补齐</span><strong>${escapeHtml(data.partial_count || 0)}</strong></div>
      <div><span>阻塞</span><strong>${escapeHtml(data.blocked_count || 0)}</strong></div>
    </div>
    <div class="adapter-list">
      ${adapters.length ? adapters.map(adapterRow).join("") : `<div class="ops-empty">没有算法适配记录。</div>`}
    </div>
  `;
}

function adapterRow(adapter) {
  const tasks = Array.isArray(adapter.tasks) ? adapter.tasks : [];
  const task = tasks[0] || {};
  const missing = Array.isArray(adapter.missing) ? adapter.missing : [];
  const status = String(adapter.deployment || adapter.status || "experimental");
  return `
    <article class="adapter-row ${escapeAttr(status)}">
      <div class="adapter-head">
        <div>
          <strong>${escapeHtml(adapter.name || adapter.algorithm_id)}</strong>
          <span>${escapeHtml(adapter.version || "-")} / ${escapeHtml(task.name || task.id || "no task")}</span>
        </div>
        <span class="ops-state ${stateForDeployment(status)}">${escapeHtml(status.toUpperCase())}</span>
      </div>
      <div class="adapter-cap-grid">
        ${cap("训练", task.train)}
        ${cap("继续", task.resume)}
        ${cap("导出", task.onnx_export)}
        ${cap("仿真", task.sim2sim)}
        ${cap("权重", task.pretrained_policy)}
        ${cap("预览", task.preview_video)}
      </div>
      ${quickPlayMarkup(task)}
      ${missing.length ? `<p class="adapter-missing">待补：${escapeHtml(missing.join(" / "))}</p>` : ""}
      ${task.notes?.length ? `<p class="adapter-note">${escapeHtml(task.notes[0])}</p>` : ""}
    </article>
  `;
}

function quickPlayMarkup(task) {
  const status = String(task.quick_play || (task.sim2sim ? "waiting" : "unsupported"));
  const state = status === "ready" ? "pass" : (status === "waiting" ? "warn" : "fail");
  const iter = task.quick_play_iteration == null ? "ONNX" : `第 ${task.quick_play_iteration} 轮`;
  const terrain = task.quick_play_terrain ? ` / ${task.quick_play_terrain}` : "";
  const autoplay = task.quick_play_autoplay === false ? " / 手动启动" : "";
  const reason = {
    ready: `${iter}${terrain}${autoplay}`,
    waiting: "等待可播放 ONNX",
    unsupported: "暂不支持 Sim2Sim",
  }[status] || (task.quick_play_reason || status);
  const href = status === "ready" && task.quick_play_url ? String(task.quick_play_url) : "";
  return `
    <div class="adapter-quick-play ${escapeAttr(status)}">
      <span class="ops-state ${state}">快速体验</span>
      <div>
        <strong>${escapeHtml(reason)}</strong>
        ${href ? `<a href="${escapeAttrUrl(href)}">打开 Sim2Sim</a>` : ""}
      </div>
    </div>
  `;
}

function cap(label, ok) {
  return `<span class="adapter-cap ${ok ? "ok" : "miss"}">${escapeHtml(label)}</span>`;
}

function stateForDeployment(status) {
  if (status === "ready") return "pass";
  if (status === "partial") return "warn";
  return "fail";
}

async function markOrphans() {
  if (!window.confirm("确认将 15 分钟以上没有 worker 心跳的活动任务标记为失败？")) return;
  el.markOrphans.disabled = true;
  showNotice("正在标记没有 worker 接管的非终态任务...", "warn");
  try {
    const result = await ops.markOrphanedRuns();
    showNotice(`已处理 ${result.affected || 0} 个任务。`, "pass");
    await load();
    await loadQueue();
  } catch (error) {
    if (isAccessError(error)) {
      showNotice(accessMessage(error), "fail");
      return;
    }
    const message = error instanceof ApiError && error.status === 404
      ? "当前后端还没有加载 ops 修复接口；重启 web-only 服务后可用。"
      : (error instanceof ApiError ? error.message : "标记失败");
    showNotice(message, "fail");
  } finally {
    el.markOrphans.disabled = false;
  }
}

async function cleanupLocalArtifacts(button) {
  const limit = Number(button?.getAttribute("data-limit") || 12);
  const ok = confirm("将删除 cleanup 候选的本地 run 目录；仍有健康可播放 ONNX 的 run 会自动跳过。继续吗？");
  if (!ok) return;
  button.disabled = true;
  showNotice("正在清理本地历史产物...", "warn");
  try {
    const result = await ops.cleanupLocalArtifacts({
      confirm: "cleanup-local-artifacts",
      limit,
    });
    showNotice(
      `已清理 ${result.cleaned_count || 0} 个 run，跳过 ${result.skipped_count || 0} 个，回收 ${formatBytes(result.local_reclaim_bytes || 0)}。`,
      "pass",
    );
    await loadArtifacts();
    await load();
    await loadQueue();
  } catch (error) {
    if (isAccessError(error)) {
      showNotice(accessMessage(error), "fail");
      return;
    }
    showNotice(error instanceof ApiError ? error.message : "本地产物清理失败", "fail");
  } finally {
    button.disabled = false;
  }
}

async function cleanupRemoteCheckpoints(button) {
  const limit = Number(button?.getAttribute("data-limit") || 12);
  const keepLatest = Number(button?.getAttribute("data-keep") || 2);
  const ok = confirm(`将删除 cleanup run 中超过最新 ${keepLatest} 个保留数的远程旧 checkpoint。继续吗？`);
  if (!ok) return;
  button.disabled = true;
  showNotice("正在清理远程旧 checkpoint...", "warn");
  try {
    const result = await ops.cleanupRemoteCheckpoints({
      confirm: "cleanup-remote-checkpoints",
      keep_latest: keepLatest,
      limit,
    });
    showNotice(
      `已删除 ${result.deleted_file_count || 0} 个远程 checkpoint，跳过 ${result.skipped_count || 0} 个，预计回收 ${formatBytes(result.remote_reclaim_bytes || 0)}。`,
      "pass",
    );
    await loadArtifacts();
    await load();
  } catch (error) {
    if (isAccessError(error)) {
      showNotice(accessMessage(error), "fail");
      return;
    }
    showNotice(error instanceof ApiError ? error.message : "远程 checkpoint 清理失败", "fail");
  } finally {
    button.disabled = false;
  }
}

function showNotice(message, status) {
  el.notice.hidden = false;
  el.notice.className = `ops-notice ${status}`;
  el.notice.textContent = message;
}

function setLoading() {
  el.refresh.disabled = true;
  el.summaryBadge.className = "ops-state warn";
  el.summaryBadge.textContent = "checking";
  el.summaryTitle.textContent = "正在检查";
  el.summaryText.textContent = "正在读取平台和远程服务器状态。";
  el.checkList.innerHTML = `<div class="ops-empty">检查中...</div>`;
}

function render(data) {
  el.refresh.disabled = false;
  const status = data.summary?.status || "warn";
  el.summaryBadge.className = `ops-state ${status}`;
  el.summaryBadge.textContent = status.toUpperCase();
  el.summaryTitle.textContent = summaryTitle(status);
  el.summaryText.textContent = summaryText(status);
  el.lastChecked.textContent = formatTime(data.summary?.checked_at);
  el.countGrid.innerHTML = countsMarkup(data.summary?.counts || {});
  el.checkList.innerHTML = (data.checks || []).map(checkMarkup).join("");
  renderProductionGuide(data);
  el.remoteDetail.textContent = remoteText(data.checks || []);
}

function renderError(error) {
  el.refresh.disabled = false;
  const message = error instanceof ApiError ? error.message : "上线检查请求失败";
  el.summaryBadge.className = "ops-state fail";
  el.summaryBadge.textContent = "FAIL";
  el.summaryTitle.textContent = "检查不可用";
  el.summaryText.textContent = message;
  el.checkList.innerHTML = `<div class="ops-empty error">${escapeHtml(message)}</div>`;
  if (el.productionGuide) {
    el.productionGuide.innerHTML = `<div class="ops-empty error">${escapeHtml(message)}</div>`;
  }
  el.remoteDetail.textContent = "无远程资源数据";
}

function renderAccessError(error) {
  el.refresh.disabled = false;
  const status = error instanceof ApiError ? error.status : 401;
  const message = accessMessage(error);
  el.summaryBadge.className = "ops-state fail";
  el.summaryBadge.textContent = status === 403 ? "FORBIDDEN" : "LOGIN";
  el.summaryTitle.textContent = status === 403 ? "需要管理员权限" : "需要登录";
  el.summaryText.textContent = message;
  el.lastChecked.textContent = "-";
  el.countGrid.innerHTML = "";
  el.checkList.innerHTML = accessPanelMarkup(error, "上线检查");
  if (el.productionGuide) el.productionGuide.innerHTML = accessPanelMarkup(error, "生产配置向导");
  if (el.remoteDetail) el.remoteDetail.textContent = "管理员登录后才会执行远程 SSH/GPU 只读探针。";
  showNotice(message, "fail");
}

function isAccessError(error) {
  return error instanceof ApiError && (error.status === 401 || error.status === 403);
}

function accessMessage(error) {
  if (error instanceof ApiError && error.status === 403) {
    return "当前账号不是管理员，无法查看上线检查、队列、远程资源和产物盘点。";
  }
  return "上线检查包含远程资源、产物和任务状态，只允许管理员查看。请先登录管理员账号。";
}

function accessPanelMarkup(error, subject) {
  const status = error instanceof ApiError ? error.status : 401;
  const loginHref = `/login/?next=${encodeURIComponent(location.pathname + location.search)}`;
  return `
    <div class="ops-access-empty">
      <span class="ops-state fail">${status === 403 ? "FORBIDDEN" : "LOGIN"}</span>
      <strong>${escapeHtml(subject)}需要管理员权限</strong>
      <p>${escapeHtml(accessMessage(error))}</p>
      ${status === 401 ? `<a class="btn" href="${escapeAttrUrl(loginHref)}">去登录</a>` : ""}
    </div>
  `;
}

function renderProductionGuide(data) {
  if (!el.productionGuide) return;
  const checks = Array.isArray(data.checks) ? data.checks : [];
  const envText = productionEnvTemplate(data);
  const gateText = productionGateCommand();
  el.productionGuide.dataset.env = envText;
  const actions = productionActions(checks, data.summary || {});
  el.productionGuide.innerHTML = `
    <div class="production-priority">
      ${actions.map((item, index) => `
        <div class="${escapeAttr(item.state)}">
          <strong>${index + 1}</strong>
          <span>${escapeHtml(item.text)}</span>
        </div>
      `).join("")}
    </div>
    <pre class="production-env">${escapeHtml(envText)}</pre>
    <div class="production-gate">
      <strong>上线门禁命令</strong>
      <pre>${escapeHtml(gateText)}</pre>
    </div>
    <p class="production-note">模板中的 CHANGE_ME 必须在服务器上替换；不要使用临时 root 密码或默认 admin 密码上线。</p>
  `;
}

function productionActions(checks, summary) {
  const byId = new Map(checks.map((check) => [check.id, check]));
  const item = (state, text) => ({ state, text });
  const databaseReady = (byId.get("database")?.status || "warn") === "pass"
    && (byId.get("database_migrations")?.status || "warn") === "pass"
    && (byId.get("database_backups")?.status || "warn") === "pass";
  const logsReady = (byId.get("structured_logging")?.status || "warn") === "pass";
  return [
    item((summary.env || "") === "production" ? "pass" : "warn", "切换 PLATFORM_ENV=production，并把 web/worker 都用同一套 env 启动。"),
    item((byId.get("secrets")?.status || "warn") === "pass" ? "pass" : "warn", "生成新的 JWT secret、强 admin 密码和独立 GPU SSH key。"),
    item((byId.get("auth_policy")?.status || byId.get("auth_required")?.status || "warn") === "pass" ? "pass" : "warn", "关闭自助注册，开启登录鉴权与 HTTPS cookie secure。"),
    item((byId.get("remote_ssh_policy")?.status || "warn") === "pass" ? "pass" : "warn", "把远程 root+临时密码换成非 root 用户、私钥和 known_hosts 严格校验。"),
    item(databaseReady ? "pass" : "warn", "正式多人使用前切到 Postgres，先备份数据库，再运行 Alembic upgrade head。"),
    item(logsReady ? "pass" : "warn", "生产环境使用 PLATFORM_LOG_FORMAT=json，方便按 request_id 检索 web/worker 日志。"),
  ];
}

function productionEnvTemplate(data) {
  const checks = Array.isArray(data.checks) ? data.checks : [];
  const byId = new Map(checks.map((check) => [check.id, check]));
  const remote = byId.get("remote_ssh")?.detail || {};
  const currentHost = String(remote.host || "");
  const currentPort = Number(remote.port || 0);
  const host = currentHost && currentHost !== "183.147.142.40" ? currentHost : "CHANGE_ME_GPU_HOST";
  const port = currentPort && currentPort !== 30465 ? currentPort : "CHANGE_ME_GPU_PORT";
  return [
    "# Locomotion Platform production env",
    "PLATFORM_ENV=production",
    "PLATFORM_HOST=127.0.0.1",
    "PLATFORM_PORT=8071",
    "PLATFORM_DATABASE_URL=postgresql+psycopg://CHANGE_ME_USER:CHANGE_ME_PASSWORD@127.0.0.1:5432/locomotion_platform",
    "PLATFORM_STORAGE_DIR=/var/lib/locomotion-platform/storage",
    "PLATFORM_RESOURCES_DIR=/var/lib/locomotion-platform/resources",
    "PLATFORM_BACKUP_DIR=/var/lib/locomotion-platform/backups",
    "PLATFORM_JWT_SECRET=CHANGE_ME_RANDOM_32_PLUS_BYTES",
    "PLATFORM_ADMIN_USERNAME=admin",
    "PLATFORM_ADMIN_PASSWORD=CHANGE_ME_STRONG_PASSWORD",
    "PLATFORM_REQUIRE_AUTH=true",
    "PLATFORM_REGISTRATION_OPEN=false",
    "PLATFORM_COOKIE_SECURE=true",
    "PLATFORM_EMBEDDED_WORKER=false",
    "PLATFORM_MARK_ORPHANED_RUNS_ON_STARTUP=false",
    "PLATFORM_LOG_FORMAT=json",
    "PLATFORM_LOG_LEVEL=INFO",
    `PLATFORM_REMOTE_HOST=${host}`,
    `PLATFORM_REMOTE_PORT=${port}`,
    "PLATFORM_REMOTE_USER=locomotion-worker",
    "PLATFORM_REMOTE_PASSWORD=",
    "PLATFORM_REMOTE_KEY_FILENAME=/etc/locomotion-platform/gpu_id_ed25519",
    "PLATFORM_REMOTE_KNOWN_HOSTS=/etc/locomotion-platform/known_hosts",
    "PLATFORM_REMOTE_STRICT_HOST_KEY_CHECKING=true",
    "PLATFORM_REMOTE_PLATFORM_ROOT=/home/locomotion-worker/locomotion_platform",
    "PLATFORM_CORS_ORIGINS=[\"https://CHANGE_ME_DOMAIN\"]",
    "PLATFORM_ALLOWED_HOSTS=[\"CHANGE_ME_DOMAIN\",\"127.0.0.1\",\"localhost\"]",
  ].join("\n");
}

function productionGateCommand() {
  return [
    "cd /opt/locomotion-platform",
    "./.venv/bin/python deploy/backup-database.py /etc/locomotion-platform/platform.env",
    "PLATFORM_DATABASE_URL=\"$(grep '^PLATFORM_DATABASE_URL=' /etc/locomotion-platform/platform.env | cut -d= -f2-)\" \\",
    "  ./.venv/bin/python -m alembic upgrade head",
    "./.venv/bin/python deploy/check-production-env.py \\",
    "  /etc/locomotion-platform/platform.env \\",
    "  --web-service /etc/systemd/system/locomotion-platform-web.service \\",
    "  --worker-service /etc/systemd/system/locomotion-platform-worker.service \\",
    "  --nginx-config /etc/nginx/sites-enabled/locomotion-platform.conf \\",
    "  --require-backup",
  ].join("\n");
}

async function copyProductionEnv() {
  const text = el.productionGuide?.dataset.env || "";
  if (!text) {
    showNotice("No production env template is ready yet.", "warn");
    return;
  }
  showNotice("Copying production env template...", "warn");
  try {
    let copied = false;
    if (navigator.clipboard?.writeText) {
      copied = await Promise.race([
        navigator.clipboard.writeText(text).then(() => true),
        new Promise((resolve) => setTimeout(() => resolve(false), 900)),
      ]);
    }
    if (!copied) copied = copyTextFallback(text);
    showNotice(
      copied ? "Production env template copied." : "Browser copy is blocked; select the env template manually.",
      copied ? "pass" : "warn",
    );
  } catch (_) {
    const copied = copyTextFallback(text);
    showNotice(
      copied ? "Production env template copied." : "Browser copy is blocked; select the env template manually.",
      copied ? "pass" : "warn",
    );
  }
}

function copyTextFallback(text) {
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.left = "-9999px";
  textarea.style.top = "0";
  document.body.appendChild(textarea);
  textarea.select();
  let ok = false;
  try {
    ok = document.execCommand("copy");
  } catch (_) {
    ok = false;
  }
  textarea.remove();
  return ok;
}

async function fallbackPreflight(originalError) {
  const [healthResult, robotsResult, algorithmsResult, runsResult] = await Promise.allSettled([
    meta.health(),
    robots.list(),
    algorithms.list(),
    runs.list(),
  ]);
  const health = valueOrNull(healthResult);
  const robotList = valueOrEmpty(robotsResult);
  const algoList = valueOrEmpty(algorithmsResult);
  const runList = valueOrEmpty(runsResult);
  const readyAlgorithms = algoList.filter((algo) => algo.status === "ready");
  const nonterminal = runList.filter((run) => ["queued", "running", "evaluating"].includes(run.status));
  const lifecycle = fallbackLifecycle(nonterminal);
  const counts = {
    robots: robotList.length,
    algorithms: algoList.length,
    ready_algorithms: readyAlgorithms.length,
    runs: runList.length,
    nonterminal_runs: nonterminal.length,
    policies: runList.filter((run) => run.playable_policy || run.latest_policy).length,
  };
  const checks = [
    {
      id: "ops_endpoint",
      label: "完整上线检查接口",
      status: "warn",
      message: "/api/ops/preflight 还没有加载；训练服务不重启时使用兼容检查。",
      detail: { reason: originalError.message },
    },
    {
      id: "health",
      label: "后端健康",
      status: health?.status === "ok" ? "pass" : "fail",
      message: health?.status === "ok" ? "后端基础接口正常" : "后端健康接口不可用",
      detail: health || {},
    },
    {
      id: "environment",
      label: "运行环境",
      status: health?.env === "production" ? "pass" : "warn",
      message: health?.env === "production" ? "已启用 production 配置" : "当前不是 production，上线前需要切换环境变量。",
      detail: { env: health?.env || "unknown" },
    },
    {
      id: "worker_mode",
      label: "训练 Worker",
      status: health?.worker?.embedded === false ? "pass" : "warn",
      message: health?.worker?.embedded === false
        ? "已配置外部 worker"
        : "当前后端没有暴露外部 worker 状态；上线前需要关闭 web 内嵌 worker。",
      detail: health?.worker || { embedded_worker: "unknown" },
    },
    {
      id: "robot_catalog",
      label: "机器人配置",
      status: robotList.length ? "pass" : "fail",
      message: robotList.length ? `已注册 ${robotList.length} 个机器人配置` : "没有可训练的机器人配置",
      detail: { robots: robotList.map((robot) => ({ id: robot.id, name: robot.name })) },
    },
    {
      id: "algorithm_catalog",
      label: "算法适配",
      status: readyAlgorithms.length ? "pass" : "fail",
      message: readyAlgorithms.length ? `ready 算法 ${readyAlgorithms.length} 个` : "没有 ready 状态算法",
      detail: { algorithms: algoList.map((algo) => ({ id: algo.id, name: algo.name, status: algo.status })) },
    },
    {
      id: "run_lifecycle",
      label: "训练任务状态",
      status: lifecycle.issue_count ? "warn" : "pass",
      message: lifecycle.message,
      detail: lifecycle,
    },
    {
      id: "remote_deep_check",
      label: "远程 SSH/GPU 深度检查",
      status: "warn",
      message: "需要完整 ops 接口加载后才能执行只读 SSH 探针。",
      detail: health?.remote || {},
    },
  ];
  const summaryStatus = checks.some((check) => check.status === "fail")
    ? "fail"
    : checks.some((check) => check.status === "warn") ? "warn" : "pass";
  return {
    summary: {
      status: summaryStatus,
      checked_at: Date.now() / 1000,
      env: health?.env || "unknown",
      counts,
    },
    checks,
  };
}

function fallbackLifecycle(runList) {
  const now = Date.now() / 1000;
  const thresholds = {
    updated_stale_seconds: 15 * 60,
    heartbeat_stale_seconds: 5 * 60,
    onnx_lag_warn_iterations: 250,
  };
  const stale_runs = [];
  const heartbeat_stale_runs = [];
  const onnx_lagging_runs = [];
  let healthy_live_runs = 0;
  for (const run of runList) {
    const progress = run.progress || {};
    const updated = Number(run.updated_at || run.created_at || now);
    const heartbeatAt = numberOrNull(progress.heartbeat_at);
    const heartbeatAge = heartbeatAt == null ? null : Math.max(0, Math.round(now - heartbeatAt));
    const trainIter = numberOrNull(progress.iteration);
    const policy = run.playable_policy || run.latest_policy || null;
    const policyIter = numberOrNull(policy?.checkpoint_iteration) ?? checkpointIterationFromPath(policy?.checkpoint);
    const lag = trainIter != null && policyIter != null ? Math.max(0, trainIter - policyIter) : null;
    const item = {
      id: run.id,
      status: run.status,
      stage: progress.stage,
      iteration: trainIter,
      max_iterations: numberOrNull(progress.max_iterations),
      updated_at: run.updated_at,
      updated_age_seconds: Math.max(0, Math.round(now - updated)),
      heartbeat_at: heartbeatAt,
      heartbeat_age_seconds: heartbeatAge,
      heartbeat_phase: progress.heartbeat_phase || null,
      latest_policy_iteration: policyIter,
      onnx_lag_iterations: lag,
    };
    if (item.updated_age_seconds > thresholds.updated_stale_seconds) stale_runs.push(item);
    if (["running", "evaluating"].includes(String(run.status || "")) && (heartbeatAge == null || heartbeatAge > thresholds.heartbeat_stale_seconds)) {
      heartbeat_stale_runs.push(item);
    }
    if (["running", "evaluating"].includes(String(run.status || "")) && lag != null && lag > thresholds.onnx_lag_warn_iterations) {
      onnx_lagging_runs.push(item);
    }
    if (["running", "evaluating"].includes(String(run.status || "")) && heartbeatAge != null && heartbeatAge <= thresholds.heartbeat_stale_seconds) {
      healthy_live_runs += 1;
    }
  }
  const issue_count = stale_runs.length + heartbeat_stale_runs.length + onnx_lagging_runs.length;
  let message = "没有长时间卡住的非终态任务";
  if (heartbeat_stale_runs.length) message = "存在 heartbeat 停止更新的训练任务";
  else if (onnx_lagging_runs.length) message = "存在 ONNX 导出明显落后训练轮数的任务";
  else if (stale_runs.length) message = "存在长时间未更新的非终态任务";
  else if (runList.length) message = `${healthy_live_runs}/${runList.length} 个活动任务 heartbeat 正常，ONNX 导出未明显落后`;
  return {
    nonterminal_runs: runList.length,
    healthy_live_runs,
    issue_count,
    thresholds,
    stale_runs,
    heartbeat_stale_runs,
    onnx_lagging_runs,
    message,
  };
}

function valueOrNull(result) {
  return result.status === "fulfilled" ? result.value : null;
}

function valueOrEmpty(result) {
  return result.status === "fulfilled" && Array.isArray(result.value) ? result.value : [];
}

function numberOrNull(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function checkpointIterationFromPath(path) {
  const name = String(path || "").split(/[\\/]/).pop() || "";
  const match = name.match(/(?:model|checkpoint|ckpt|iter|iteration)[_-]?(\d+)\b/i) || name.match(/^(\d+)\D*$/);
  return match ? Number(match[1]) : null;
}

function summaryTitle(status) {
  if (status === "pass") return "可以进入上线候选";
  if (status === "fail") return "还有阻塞项";
  return "有上线风险需要处理";
}

function summaryText(status) {
  if (status === "pass") return "核心配置、存储、远程和任务状态都通过了当前检查。";
  if (status === "fail") return "至少有一个检查项失败，上线前需要先处理。";
  return "平台能运行，但还有开发态配置或容量、任务状态风险。";
}

function countsMarkup(counts) {
  const items = [
    ["registered_users", "注册用户"],
    ["verified_users", "邮箱已验证"],
    ["robots", "机器人"],
    ["ready_algorithms", "ready 算法"],
    ["runs", "训练任务"],
    ["nonterminal_runs", "运行中"],
    ["playable_policy_runs", "可播放策略"],
  ];
  return items.map(([key, label]) => `
    <div class="ops-count">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(counts[key] ?? 0)}</strong>
    </div>
  `).join("");
}

function checkMarkup(check) {
  const detail = usefulDetail(check.detail || {});
  const structured = check.id === "run_lifecycle" ? runLifecycleMarkup(check.detail || {}) : "";
  return `
    <article class="ops-check ${escapeAttr(check.status)}">
      <div class="ops-check-main">
        <span class="ops-dot"></span>
        <div>
          <h3>${escapeHtml(check.label)}</h3>
          <p>${escapeHtml(check.message)}</p>
        </div>
      </div>
      <span class="ops-state ${escapeAttr(check.status)}">${escapeHtml(String(check.status).toUpperCase())}</span>
      ${structured}
      ${detail ? `<pre class="ops-check-detail">${escapeHtml(detail)}</pre>` : ""}
    </article>
  `;
}

function runLifecycleMarkup(detail) {
  const thresholds = detail.thresholds || {};
  const hasDetailedSignals = Boolean(
    detail.thresholds
    || detail.healthy_live_runs != null
    || detail.issue_count != null
    || Array.isArray(detail.heartbeat_stale_runs)
    || Array.isArray(detail.onnx_lagging_runs),
  );
  const groups = [
    ["heartbeat_stale_runs", "Heartbeat 停止", "fail"],
    ["onnx_lagging_runs", "ONNX 滞后", "warn"],
    ["stale_runs", "页面/DB 久未更新", "warn"],
  ];
  const rows = groups.flatMap(([key, label, state]) =>
    (Array.isArray(detail[key]) ? detail[key] : []).map((run) => ({ ...run, issue: label, state })));
  if (!rows.length && !detail.nonterminal_runs) return "";
  return `
    <div class="run-life-panel">
      <div class="run-life-summary">
        <div><span>活动任务</span><strong>${escapeHtml(detail.nonterminal_runs || 0)}</strong></div>
        <div><span>heartbeat 正常</span><strong>${escapeHtml(detail.healthy_live_runs || 0)}</strong></div>
        <div><span>问题项</span><strong>${escapeHtml(detail.issue_count || rows.length || 0)}</strong></div>
        <div><span>ONNX 阈值</span><strong>${escapeHtml(thresholds.onnx_lag_warn_iterations ?? 250)} 轮</strong></div>
      </div>
      ${rows.length
        ? `<div class="run-life-list">${rows.slice(0, 8).map(runLifecycleRow).join("")}</div>`
        : `<p class="run-life-ok">${hasDetailedSignals ? "活动任务 heartbeat 正常，ONNX 导出没有明显落后。" : "当前后端尚未返回 heartbeat / ONNX 细分诊断；重载新版服务后这里会显示更精确的训练健康状态。"}</p>`}
    </div>
  `;
}

function runLifecycleRow(run) {
  const hb = run.heartbeat_age_seconds == null ? "-" : formatAge(run.heartbeat_age_seconds);
  const updated = run.updated_age_seconds == null ? "-" : formatAge(run.updated_age_seconds);
  const iter = run.iteration == null ? "-" : `${run.iteration}${run.max_iterations ? `/${run.max_iterations}` : ""}`;
  const onnx = run.latest_policy_iteration == null ? "-" : `第 ${run.latest_policy_iteration} 轮`;
  const lag = run.onnx_lag_iterations == null ? "-" : `${run.onnx_lag_iterations} 轮`;
  return `
    <div class="run-life-row ${escapeAttr(run.state || "warn")}">
      <span class="ops-state ${escapeAttr(run.state || "warn")}">${escapeHtml(run.issue || "检查")}</span>
      <div>
        <strong>${escapeHtml(run.id || "-")}</strong>
        <small>${escapeHtml(run.status || "-")} / ${escapeHtml(run.stage || "-")}</small>
      </div>
      <dl>
        <dt>iter</dt><dd>${escapeHtml(iter)}</dd>
        <dt>ONNX</dt><dd>${escapeHtml(onnx)}</dd>
        <dt>lag</dt><dd>${escapeHtml(lag)}</dd>
        <dt>heartbeat</dt><dd>${escapeHtml(hb)}</dd>
        <dt>updated</dt><dd>${escapeHtml(updated)}</dd>
      </dl>
    </div>
  `;
}

function usefulDetail(detail) {
  const clone = { ...detail };
  if (Array.isArray(clone.processes)) {
    clone.processes = clone.processes.map((line) => line.length > 150 ? `${line.slice(0, 150)}...` : line);
  }
  delete clone.thresholds;
  delete clone.heartbeat_stale_runs;
  delete clone.onnx_lagging_runs;
  delete clone.stale_runs;
  delete clone.healthy_live_runs;
  delete clone.issue_count;
  const text = JSON.stringify(clone, null, 2);
  return text === "{}" ? "" : text;
}

function remoteText(checks) {
  const picked = checks.filter((check) => String(check.id || "").startsWith("remote_"));
  if (!picked.length) return "没有远程检查结果";
  return picked.map((check) => {
    const header = `[${String(check.status).toUpperCase()}] ${check.label}: ${check.message}`;
    const detail = usefulDetail(check.detail || {});
    return detail ? `${header}\n${detail}` : header;
  }).join("\n\n");
}

function formatTime(ts) {
  if (!ts) return "-";
  return new Date(ts * 1000).toLocaleString("zh-CN", { hour12: false });
}

function formatBytes(bytes) {
  const n = Number(bytes || 0);
  if (!Number.isFinite(n) || n <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const index = Math.min(units.length - 1, Math.floor(Math.log(n) / Math.log(1024)));
  const value = n / (1024 ** index);
  return `${value >= 10 || index === 0 ? value.toFixed(0) : value.toFixed(1)} ${units[index]}`;
}

function formatAge(seconds) {
  const n = Math.max(0, Number(seconds || 0));
  if (n < 60) return `${Math.round(n)}s`;
  if (n < 3600) return `${Math.round(n / 60)}m`;
  if (n < 86400) return `${Math.round(n / 3600)}h`;
  return `${Math.round(n / 86400)}d`;
}

function escapeAttr(s) { return String(s).replace(/[^a-zA-Z0-9_-]/g, ""); }
function escapeAttrUrl(s) { return String(s).replace(/"/g, "%22"); }
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
