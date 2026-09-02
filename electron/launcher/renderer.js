const api = window.leggedStudio;
const state = { backendRunning: false, provisioning: false, health: null, assets: null, training: null, settings: null, paths: null, runtimeProfile: null, gpus: [], gpuError: '' };

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

function toast(message, kind = 'info') {
    const element = $('#toast');
    element.textContent = message;
    element.dataset.kind = kind;
    element.classList.add('visible');
    window.clearTimeout(toast.timer);
    toast.timer = window.setTimeout(() => element.classList.remove('visible'), 3200);
}

function log(message) {
    handleProvisionLog(message);
    const output = $('#console-output');
    output.textContent += `${message}`;
    output.scrollTop = output.scrollHeight;
    const activity = $('#activity-list');
    const empty = activity.querySelector('.empty-state');
    if (empty) empty.remove();
    const item = document.createElement('div');
    item.className = 'activity-item';
    item.innerHTML = `<span class="activity-dot"></span><span>${String(message).trim()}</span>`;
    activity.prepend(item);
    while (activity.children.length > 5) activity.lastElementChild.remove();
}

const sizeUnits = { B: 1, KiB: 1024, MiB: 1024 ** 2, GiB: 1024 ** 3 };

function sizeToBytes(value, unit) {
    return Math.round(value * (sizeUnits[unit] || 1));
}

function fmtSize(bytes, suffix = '') {
    if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(2)} GiB${suffix}`;
    return `${(bytes / 1024 ** 2).toFixed(1)} MiB${suffix}`;
}

function fmtDuration(seconds) {
    const total = Math.max(0, Math.round(seconds));
    const h = Math.floor(total / 3600);
    const m = Math.floor((total % 3600) / 60);
    const s = total % 60;
    if (h > 0) return `${h}分${m}秒`;
    if (m > 0) return `${m}分${s}秒`;
    return `${s}秒`;
}

const prov = {
    active: false,
    stage: '',
    targetPercent: 25,
    shownPercent: 0,
    announcedBytes: 0,
    doneBytes: 0,
    doneFiles: 0,
    pending: new Map(),
    startedAt: 0,
    lastAction: '',
    ticker: null,
};

function provStart() {
    prov.active = true;
    prov.stage = 'bootstrap';
    prov.targetPercent = 25;
    prov.shownPercent = 0;
    prov.announcedBytes = 0;
    prov.doneBytes = 0;
    prov.doneFiles = 0;
    prov.pending.clear();
    prov.startedAt = Date.now();
    prov.lastAction = '';
    $('#runtime-progress-meta').textContent = '';
    window.clearInterval(prov.ticker);
    prov.ticker = window.setInterval(provTick, 200);
}

function provStop() {
    prov.active = false;
    window.clearInterval(prov.ticker);
    prov.ticker = null;
}

function provSetStage(progress) {
    prov.stage = progress.stage;
    if (progress.percent > 0) prov.targetPercent = progress.percent;
}

function provDownloadFrac() {
    if (prov.announcedBytes <= 0) return null;
    return Math.min(1, prov.doneBytes / prov.announcedBytes);
}

function provTick() {
    if (!prov.active) return;
    const elapsed = (Date.now() - prov.startedAt) / 1000;
    let target = prov.targetPercent;
    if (prov.stage === 'dependencies' && prov.targetPercent < 80) {
        const frac = provDownloadFrac();
        if (frac !== null) {
            target = 25 + Math.round(frac * 53);
        } else {
            target = Math.min(69, 25 + Math.round((elapsed / 60) * 44));
        }
    }
    prov.shownPercent += (target - prov.shownPercent) * 0.12;
    if (Math.abs(target - prov.shownPercent) < 0.4) prov.shownPercent = target;
    const shown = Math.round(prov.shownPercent);
    $('#runtime-progress-bar').value = shown;
    $('#runtime-progress-value').textContent = `${shown}%`;
    const meta = [];
    if (prov.stage === 'dependencies') {
        if (prov.lastAction) meta.push(prov.lastAction);
        if (prov.announcedBytes > 0) meta.push(`已下载 ${fmtSize(prov.doneBytes)} / ${fmtSize(prov.announcedBytes)} · ${prov.doneFiles} 个包`);
        if (prov.doneBytes > 0 && elapsed > 1) meta.push(`速度 ${fmtSize(prov.doneBytes / elapsed, '/s')}`);
    }
    meta.push(`用时 ${fmtDuration(elapsed)}`);
    $('#runtime-progress-meta').textContent = meta.join(' · ');
}

function handleProvisionLog(message) {
    if (!prov.active) return;
    for (const raw of String(message).split(/\r?\n/)) {
        const text = raw.trim();
        if (!text) continue;
        let match;
        if ((match = text.match(/^Downloading\s+(.+?)\s+\(([\d.]+)\s*(B|KiB|MiB|GiB)\)\s*$/i))) {
            const size = sizeToBytes(Number(match[2]), match[3]);
            prov.pending.set(match[1], size);
            prov.announcedBytes += size;
            prov.lastAction = `正在下载 ${match[1]}（${fmtSize(size)}）`;
        } else if ((match = text.match(/^\s*Downloaded\s+(.+)$/))) {
            const name = match[1].trim();
            const size = prov.pending.get(name);
            if (size) prov.doneBytes += size;
            prov.pending.delete(name);
            prov.doneFiles += 1;
            prov.lastAction = `已下载 ${name}`;
        } else if (/^Prepared\s+\d+\s+packages/.test(text)) {
            prov.lastAction = '依赖下载完成，正在解压安装…';
        } else if ((match = text.match(/^Installed\s+(\d+)\s+packages/))) {
            prov.lastAction = `依赖安装完成（${match[1]} 个包）`;
        }
    }
}

function setCard(name, value, status = 'pending') {
    const card = document.querySelector(`[data-status-card="${name}"]`);
    if (!card) return;
    card.querySelector('strong').textContent = value;
    card.querySelector('.status-dot').className = `status-dot ${status}`;
}

function setBackendAvailability(running) {
    state.backendRunning = Boolean(running);
    $$('[data-requires-backend]').forEach((button) => { button.disabled = !state.backendRunning; });
    $('#open-web').disabled = !state.backendRunning;
    $('#open-web-training').disabled = !state.backendRunning;
}

function requireBackend() {
    if (state.backendRunning) return true;
    toast('请先启动控制平面', 'warning');
    return false;
}

function renderHealth(health) {
    state.health = health;
    const features = health?.features || [];
    setCard('backend', health?.status === 'ok' ? '运行中' : '异常', health?.status === 'ok' ? 'ready' : 'error');
    setBackendAvailability(health?.status === 'ok');
    $('#backend-value').textContent = health?.status === 'ok' ? '运行中' : '未启动';
    log(`[health] backend v${health?.version || 'unknown'} · ${features.length} features\n`);
}

async function fetchJson(route) {
    if (!state.backendRunning) throw new Error('Control plane is not running');
    const base = await api.backendUrl();
    const response = await fetch(`${base}${route}`);
    if (!response.ok) throw new Error(`${route}: HTTP ${response.status}`);
    return response.json();
}

function renderEnvironment(payload) {
    const control = payload?.control_plane;
    const adapter = payload?.adapters?.mjlab;
    const pythonReady = control?.status === 'running' && control?.python_target_match !== false;
    setCard('python', control?.python_version || '不可用', pythonReady ? 'ready' : 'error');
    setCard('adapter', adapter?.status === 'installed' ? 'MJLab 就绪' : '未安装', adapter?.status === 'installed' ? 'ready' : 'pending');
    $('#python-value').textContent = control?.python_version || '不可用';
    $('#adapter-value').textContent = adapter?.status === 'installed' ? 'MJLab 就绪' : '未安装';
}

function renderAssets(payload) {
    state.assets = payload || {};
    const bySize = payload?.by_size || {};
    const total = payload?.total ?? payload?.count ?? '—';
    setCard('assets', total === '—' ? '等待检查' : `${total} 个`, total === '—' ? 'pending' : 'ready');
    $('#assets-value').textContent = total === '—' ? '等待检查' : `${total} 个`;
    $('#asset-metrics').innerHTML = [['总资产', total], ['小型 S', bySize.S ?? '—'], ['中型 M', bySize.M ?? '—'], ['大型 L', bySize.L ?? '—']]
        .map(([label, value]) => `<div class="metric"><span>${label}</span><strong>${value}</strong></div>`).join('');
    const families = payload?.families || [];
    $('#asset-summary').innerHTML = `<div class="summary-line"><span>可用家族</span><strong>${families.length ? families.join(' · ') : '暂无数据'}</strong></div><div class="summary-line"><span>运动构型</span><strong>${Object.entries(payload?.by_locomotion || {}).map(([key, value]) => `${key}: ${value}`).join(' · ') || '暂无数据'}</strong></div>`;
}

function renderTraining(tasks) {
    const items = Array.isArray(tasks) ? tasks : (Array.isArray(tasks?.tasks) ? tasks.tasks : []);
    state.training = items;
    if (items.length === 0) {
        $('#training-summary').innerHTML = '<div class="empty-state">暂无训练任务。</div>';
        return;
    }
    $('#training-summary').innerHTML = `<table><thead><tr><th>任务</th><th>机器人</th><th>状态</th><th>进度</th></tr></thead><tbody>${items.map((task) => `<tr><td>${task.task_id || task.id || '—'}</td><td>${task.robot || task.contract_id || '—'}</td><td><span class="badge">${task.status || 'unknown'}</span></td><td>${task.progress == null ? '—' : `${Math.round(task.progress * 100)}%`}</td></tr>`).join('')}</tbody></table>`;
}

async function refreshState(showToast = false) {
    const checked = await api.checkBackend();
    setBackendAvailability(checked.ok);
    if (!checked.ok) {
        setCard('backend', '未启动', 'pending');
        setCard('python', state.runtimeProfile?.installed ? `已配置 ${state.runtimeProfile.python}` : '未配置', state.runtimeProfile?.installed ? 'ready' : 'pending');
        setCard('adapter', state.runtimeProfile?.installed ? '待服务验证' : '未配置', 'pending');
        setCard('assets', '待服务启动', 'pending');
        if (showToast) toast('控制平面尚未启动', 'warning');
        return;
    }
    renderHealth(checked.health);
    const results = await Promise.allSettled([
        fetchJson('/api/system/environment'),
        fetchJson('/api/assets/summary'),
        fetchJson('/api/training/list'),
    ]);
    if (results[0].status === 'fulfilled') renderEnvironment(results[0].value);
    else { setCard('python', '状态读取失败', 'error'); setCard('adapter', '状态读取失败', 'error'); }
    if (results[1].status === 'fulfilled') renderAssets(results[1].value);
    else setCard('assets', '状态读取失败', 'error');
    if (results[2].status === 'fulfilled') renderTraining(results[2].value);
    if (showToast) toast('状态已刷新', 'success');
}

async function startBackend() {
    if (state.provisioning) {
        toast('运行环境仍在配置中', 'warning');
        return;
    }
    const button = $('#start-backend');
    button.disabled = true;
    button.textContent = '准备工作区…';
    log('[launcher] preparing workspace and runtime\n');
    const prepared = await api.setupEnvironment();
    if (!prepared.ok) {
        setBackendAvailability(false);
        setCard('python', '未就绪', 'error');
        button.disabled = false;
        button.textContent = '▶ 启动控制平面';
        log(`[error] environment preparation failed: ${prepared.error}\n`);
        toast(`环境准备失败: ${prepared.error}`, 'error');
        return;
    }
    $('#workspace-detail').textContent = prepared.directories.join(' · ');
    button.textContent = '检查运行时…';
    button.textContent = '启动控制平面…';
    const result = await api.startBackend();
    if (result.ok) {
        state.backendRunning = true;
        button.textContent = '✓ 控制平面运行中';
        renderHealth(result.health);
        await refreshState();
        await api.openExternal(`${await api.backendUrl()}/web/workbench.html`);
        toast('控制平面已启动', 'success');
    } else {
        setBackendAvailability(false);
        button.disabled = false;
        button.textContent = '▶ 启动控制平面';
        log(`[error] ${result.error}\n`);
        toast(result.error, 'error');
    }
}

async function probePython(showToast = false) {
    const result = await api.probePython($('#python-path-input').value.trim() || undefined);
    $('#python-runtime-path').textContent = result.executable || '不可用';
    const missing = Object.entries(result.dependencies || {}).filter(([, value]) => value !== 'true').map(([key]) => key);
    $('#python-runtime-detail').textContent = result.ok
        ? `${result.version} · ${result.implementation}${result.targetMatch ? ' · 符合 3.12 策略' : ' · 与 3.12 策略不一致'}${missing.length ? ` · 缺少 ${missing.join(', ')}` : ' · 控制平面依赖齐全'}`
        : `检测失败：${result.error}`;
    $('#python-runtime-detail').dataset.state = result.ok && result.targetMatch && result.dependenciesReady ? 'ready' : 'warning';
    if (showToast) toast(result.ok && result.dependenciesReady ? 'Python 与控制平面依赖检测完成' : 'Python/依赖检测存在问题', result.ok && result.dependenciesReady ? 'success' : 'warning');
    return result;
}

async function loadSettings(runProbe = true) {
    state.settings = await api.getSettings();
    $('#python-path-input').value = state.settings.pythonPath || '';
    $('#backend-port-input').value = state.settings.backendPort || 8765;
    const device = state.settings.torchDevice === 'cpu' ? 'cpu' : 'gpu';
    $$('input[name="torch-device"]').forEach((radio) => { radio.checked = radio.value === device; });
    if (runProbe) await probePython();
}

async function saveSettings() {
    const backendPort = Number($('#backend-port-input').value);
    if (!Number.isInteger(backendPort) || backendPort < 1024 || backendPort > 65535) {
        toast('服务端口必须是 1024–65535 之间的整数', 'error');
        return;
    }
    state.settings = await api.updateSettings({
        autoStartBackend: false,
        pythonPath: $('#python-path-input').value,
        backendPort,
        torchDevice: $('input[name="torch-device"]:checked')?.value || 'gpu',
    });
    $('#backend-url').textContent = await api.backendUrl();
    await probePython();
    toast('设置已保存', 'success');
}

async function prepareEnvironment() {
    const result = await api.prepareEnvironment();
    $('#workspace-detail').textContent = result.ok ? result.directories.join(' · ') : `初始化失败：${result.error}`;
    toast(result.ok ? '工作区目录已准备' : '工作区初始化失败', result.ok ? 'success' : 'error');
}

async function configureRuntime() {
    const buttons = [$('#configure-runtime'), $('#configure-runtime-settings')];
    state.provisioning = true;
    $('#runtime-progress').hidden = false;
    $('#runtime-progress-bar').value = 0;
    $('#runtime-progress-value').textContent = '0%';
    provStart();
    buttons.forEach((button) => { button.disabled = true; button.textContent = '正在下载配置...'; });
    $('#start-backend').disabled = true;
    const device = $('input[name="torch-device"]:checked')?.value || 'gpu';
    const deviceLabel = device === 'cpu' ? 'CPU' : 'GPU';
    $('#runtime-profile-detail').textContent = `正在使用国内镜像安装 ${deviceLabel} Torch 与 MJLab`;
    log(`[runtime] starting on-demand Windows runtime setup (${deviceLabel})\n`);
    try {
        state.settings = await api.updateSettings({ ...state.settings, torchDevice: device });
    } catch (error) {
        toast(`保存设备选择失败：${error.message}`, 'error');
        buttons.forEach((button) => { button.disabled = false; button.textContent = button.id === 'configure-runtime' ? '配置运行环境' : '一键下载配置'; });
        state.provisioning = false;
        $('#start-backend').disabled = false;
        return;
    }
    const result = await api.provisionWindowsRuntime();
    buttons[0].textContent = '配置运行环境';
    buttons[1].textContent = '一键下载配置';
    buttons.forEach((button) => { button.disabled = false; });
    state.provisioning = false;
    $('#start-backend').disabled = false;
    if (!result.ok) {
        $('#runtime-profile-detail').textContent = `配置失败：${result.error}`;
        toast(result.error, 'error');
        return;
    }
    $('#runtime-profile-detail').textContent = `已安装 · Python 3.12.13 · Torch 2.11.0+${device === 'cpu' ? 'cpu' : 'cu128'} · MJLab 1.6.0 · ${deviceLabel}`;
    state.runtimeProfile = await api.runtimeProfile();
    state.settings = await api.getSettings();
    $('#python-path-input').value = state.settings.pythonPath || result.python;
    await probePython();
    toast(`${deviceLabel} 运行环境配置完成`, 'success');
}

async function loadGpus() {
    const result = await api.listGpus();
    state.gpus = result.ok ? (result.gpus || []) : [];
    state.gpuError = result.ok ? '' : result.error;
    syncDeviceDisplay();
}

async function pickPython() {
    const result = await api.pickPython();
    if (result.ok && result.path) {
        $('#python-path-input').value = result.path;
        state.settings = await api.getSettings();
        await probePython(true);
        toast(`已选择 Python：${result.path}`, 'success');
    } else {
        toast('已取消选择', 'info');
    }
}

function syncDeviceDisplay() {
    const device = $('input[name="torch-device"]:checked')?.value || 'gpu';
    const status = $('#device-name');
    const detail = $('#device-detail');
    if (device === 'cpu') {
        status.textContent = 'CPU';
        if (detail) detail.textContent = '使用 CPU 进行训练，无需 NVIDIA 显卡';
        return;
    }
    const names = (state.gpus || []).map((gpu) => gpu.name).filter(Boolean);
    status.textContent = names.length ? names[0] : '（未检测到显卡）';
    if (detail) detail.textContent = names.length ? `检测到显卡：${names.join('、')}` : '未检测到可用显卡，建议切换为 CPU';
}

async function stopBackend() {
    await api.stopBackend();
    setBackendAvailability(false);
    $('#start-backend').disabled = false;
    $('#start-backend').textContent = '▶ 启动控制平面';
    setCard('backend', '未启动', 'pending');
    log('[launcher] backend stopped\n');
    toast('控制平面已停止', 'info');
}

function activatePage(page) {
    $$('.nav-item').forEach((item) => item.classList.toggle('active', item.dataset.page === page));
    $$('.page').forEach((view) => view.classList.toggle('active', view.dataset.view === page));
    if (page === 'assets' && state.backendRunning && !state.assets) refreshState();
    if (page === 'training' && state.backendRunning) fetchJson('/api/training/list').then(renderTraining).catch(() => {});
}

$('#navigation').addEventListener('click', (event) => {
    const button = event.target.closest('.nav-item');
    if (button) activatePage(button.dataset.page);
});
$('#start-backend').addEventListener('click', startBackend);
$('#open-web').addEventListener('click', async () => { if (requireBackend()) api.openExternal(`${await api.backendUrl()}/web/workbench.html`); });
$('#open-web-training').addEventListener('click', async () => { if (requireBackend()) api.openExternal(`${await api.backendUrl()}/web/workbench.html`); });
$('#refresh-state').addEventListener('click', () => refreshState(true));
$('#load-assets').addEventListener('click', () => refreshState(true));
$('#load-training').addEventListener('click', () => refreshState(true));
$('#clear-console').addEventListener('click', () => { $('#console-output').textContent = ''; });
$('#console-open-logs').addEventListener('click', () => api.openPath('logs'));
$('#open-docs').addEventListener('click', () => api.openPath('docs'));
$('#open-root').addEventListener('click', () => api.openPath('root'));
$('#settings-open-root').addEventListener('click', () => api.openPath('root'));
$('#open-assets-workbench').addEventListener('click', async () => { if (requireBackend()) api.openExternal(`${await api.backendUrl()}/web/assets.html`); });
$('#open-artifacts-workbench').addEventListener('click', async () => { if (requireBackend()) api.openExternal(`${await api.backendUrl()}/web/artifacts.html`); });
$('#open-evaluation').addEventListener('click', async () => { if (requireBackend()) api.openExternal(`${await api.backendUrl()}/web/evaluation.html`); });
$('#probe-python').addEventListener('click', () => probePython(true));
$('#pick-python').addEventListener('click', pickPython);
$('#configure-runtime').addEventListener('click', configureRuntime);
$('#configure-runtime-settings').addEventListener('click', configureRuntime);
$('#save-settings').addEventListener('click', saveSettings);
$('#prepare-environment').addEventListener('click', prepareEnvironment);
$$('input[name="torch-device"]').forEach((radio) => radio.addEventListener('change', syncDeviceDisplay));
$$('[data-open-path]').forEach((button) => button.addEventListener('click', () => api.openPath(button.dataset.openPath)));
$('#minimize').addEventListener('click', () => api.minimize());
$('#maximize').addEventListener('click', () => api.toggleMaximize());
$('#close').addEventListener('click', () => api.close());

api.onBackendLog(log);
api.onBackendStatus((running) => {
    setBackendAvailability(running);
    if (!running) {
        setCard('backend', '未启动', 'pending');
    }
});
api.onRuntimeProgress((progress) => {
    const labels = {
        bootstrap: '检查内置安装组件',
        python: '准备 Python 3.12.13',
        dependencies: progress.percent < 80 ? '从国内镜像安装 Torch 与 MJLab' : '依赖安装完成',
        sources: '准备 MJLab 与 Unitree 源码快照',
        verify: '验证 Python、Torch 与 MJLab',
        complete: '运行环境配置完成',
        failed: '配置失败，请查看控制台日志',
    };
    $('#runtime-progress').hidden = false;
    if (progress.stage === 'complete' || progress.stage === 'failed') {
        provStop();
        const pct = progress.stage === 'complete' ? 100 : Math.round(prov.shownPercent || progress.percent || 0);
        $('#runtime-progress-bar').value = pct;
        $('#runtime-progress-value').textContent = `${pct}%`;
        $('#runtime-progress-title').textContent = progress.stage === 'failed' ? '配置失败' : '配置运行环境';
        $('#runtime-progress-message').textContent = labels[progress.stage] || progress.message || progress.stage;
        if (progress.stage === 'complete') {
            $('#runtime-progress-meta').textContent = `总用时 ${fmtDuration((Date.now() - prov.startedAt) / 1000)}`;
        }
        return;
    }
    provSetStage(progress);
    $('#runtime-progress-title').textContent = '配置运行环境';
    $('#runtime-progress-message').textContent = labels[progress.stage] || progress.message || progress.stage;
});

(async () => {
    const paths = await api.getPaths();
    state.paths = paths;
    $('#root-path').textContent = paths.root;
    $('#backend-url').textContent = await api.backendUrl();
    // Opening the desktop app is read-only. Preparation and probing happen
    // only after the user explicitly clicks Start.
    await loadSettings(false);
    const runtimeProfile = await api.runtimeProfile();
    state.runtimeProfile = runtimeProfile;
    const deviceLabel = runtimeProfile.device === 'cpu' ? 'CPU' : 'GPU';
    $('#runtime-profile-detail').textContent = runtimeProfile.installed
        ? `已安装 · ${deviceLabel} · Python ${runtimeProfile.python} · Torch ${runtimeProfile.torch} · MJLab ${runtimeProfile.mjlab}`
        : `按需配置 · ${deviceLabel} · ${runtimeProfile.packageIndex} · ${runtimeProfile.torchIndex}`;
    await loadGpus();
    log(`[launcher] root: ${paths.root}\n`);
    log(`[launcher] python: ${paths.python}\n`);
    await refreshState();
})();
