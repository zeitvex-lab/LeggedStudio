const { app, BrowserWindow, ipcMain, shell, dialog, Tray, nativeImage } = require('electron');
const { spawn, execFile } = require('child_process');
const path = require('path');
const fs = require('fs');
const http = require('http');
const net = require('net');
const crypto = require('crypto');

const DEFAULT_BACKEND_PORT = 8765;
const DOWNLOAD_RUNTIME_VERSION = 'windows-cuda-2026.09';
const EXPECTED_API_SCHEMA = 'legged-studio-api-1';
const IS_DEV = process.env.NODE_ENV === 'development' || !app.isPackaged;
const INSTANCE_ID = crypto.randomUUID();
let launcherWindow = null;
let pythonProcess = null;
let runtimeProvisionProcess = null;
let activeBackendPort = null;
let tray = null;
let trainingPollTimer = null;
let runningTasksCache = [];

// ---- T5.3：托盘 + Windows 任务栏进度 + 退出确认（报告 10 桌面壳约定） ----
const TRAY_ICON_PNG = 'iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAKklEQVR4nGNgYGD4z8DAwMDIhEGEgYGBgYGBgYGBgQEYhv//MzAwMDBAwWIAAJ3oB4TF14UxAAAAAElFTkSuQmCC';

function fetchTrainingTasks() {
    return requestJson('/api/training/list').catch(() => null);
}

function updateTrainingIndicators() {
    fetchTrainingTasks().then((payload) => {
        if (!payload || !Array.isArray(payload.tasks)) return;
        runningTasksCache = payload.tasks.filter((task) => {
            const status = String(task.status || '').toLowerCase();
            return status === 'running' || status === 'pending' || status === 'starting';
        });
        const fractions = runningTasksCache
            .map((task) => {
                const current = Number(task.current_iteration) || 0;
                const max = Number(task.max_iterations) || 0;
                return max > 0 ? Math.min(1, current / max) : 0;
            });
        const progress = fractions.length
            ? fractions.reduce((sum, value) => sum + value, 0) / fractions.length
            : -1;
        if (launcherWindow && !launcherWindow.isDestroyed()) {
            launcherWindow.setProgressBar(progress);
        }
        if (tray && !tray.isDestroyed()) {
            tray.setToolTip(fractions.length
                ? `Legged Studio · 训练中 ${runningTasksCache.length} 项（${Math.round(progress * 100)}%）`
                : 'Legged Studio · 后端运行中，无训练任务');
        }
    });
}

function startTrainingPolling() {
    if (trainingPollTimer) return;
    trainingPollTimer = setInterval(updateTrainingIndicators, 5000);
    updateTrainingIndicators();
}

function createTray() {
    if (tray || process.platform !== 'win32') return;
    tray = new Tray(nativeImage.createFromDataURL(`data:image/png;base64,${TRAY_ICON_PNG}`));
    tray.setToolTip('Legged Studio');
    tray.on('click', () => {
        if (launcherWindow && !launcherWindow.isDestroyed()) {
            launcherWindow.show();
            launcherWindow.focus();
        }
    });
}

async function confirmExitWithRunningTasks(event) {
    if (!runningTasksCache.length) return true;
    const detail = runningTasksCache.map((task) => {
        const current = Number(task.current_iteration) || 0;
        const max = Number(task.max_iterations) || 0;
        return `退出将终止 ${task.task_id}（${current}/${max}）——确认？`;
    }).join([String.fromCharCode(10)].join(''));
    const { response } = await dialog.showMessageBox({
        type: 'warning',
        message: '有训练任务正在运行',
        detail,
        buttons: ['取消', '终止并退出'],
        defaultId: 0,
        cancelId: 0,
    });
    if (response === 1) { runningTasksCache = []; return true; }
    return false;
}

function firstExisting(candidates) {
    const valid = candidates.filter(Boolean);
    return valid.find((candidate) => fs.existsSync(candidate)) || valid[0];
}

function findRuntimePython(runtimeRoot, executable) {
    const direct = path.join(runtimeRoot, executable);
    if (fs.existsSync(direct)) return direct;
    try {
        const entries = fs.readdirSync(runtimeRoot, { withFileTypes: true });
        for (const entry of entries) {
            if (!entry.isDirectory()) continue;
            const candidate = path.join(runtimeRoot, entry.name, executable);
            if (fs.existsSync(candidate)) return candidate;
            const scriptsCandidate = path.join(runtimeRoot, entry.name, process.platform === 'win32' ? 'Scripts' : 'bin', executable);
            if (fs.existsSync(scriptsCandidate)) return scriptsCandidate;
        }
    } catch {
        return null;
    }
    return null;
}

function resolvePaths() {
    const projectRoot = path.resolve(__dirname, '..', '..');
    const resourceRoot = process.resourcesPath || path.dirname(process.execPath);
    const packagedRoot = path.join(resourceRoot, 'app');
    const root = IS_DEV ? projectRoot : firstExisting([packagedRoot, path.dirname(process.execPath)]);
    const pythonExecutable = process.platform === 'win32' ? 'python.exe' : 'python';
    const venvBin = process.platform === 'win32' ? 'Scripts' : 'bin';
    const backend = firstExisting([
        path.join(root, 'backend', 'api_complete.py'),
        path.join(resourceRoot, 'app', 'backend', 'api_complete.py'),
        path.join(resourceRoot, 'backend', 'api_complete.py'),
    ]);
    const embeddedPython = findRuntimePython(path.join(root, 'runtime', 'python'), pythonExecutable);
    const python = firstExisting([
        embeddedPython,
        path.join(root, 'runtime', 'python', pythonExecutable),
        path.join(resourceRoot, 'runtime', 'python', pythonExecutable),
        path.join(projectRoot, 'runtime', 'python', pythonExecutable),
    ]);
    const inventory = firstExisting([
        path.join(root, 'QUADRUPED_ASSET_INVENTORY.json'),
        path.join(projectRoot, 'QUADRUPED_ASSET_INVENTORY.json'),
        path.join(resourceRoot, 'app', 'QUADRUPED_ASSET_INVENTORY.json'),
    ]);
    const mjlabSource = firstExisting([
        path.join(root, 'runtime', 'mjlab_source'),
        path.join(root, 'vendor', 'mjlab'),
        path.join(projectRoot, '..', 'mjlab_new', 'mjlab'),
    ]);
    const mjlabExtension = firstExisting([
        path.join(root, 'runtime', 'mjlab_extension'),
        path.join(root, 'vendor', 'unitree_rl_mjlab'),
        path.join(projectRoot, '..', 'uni_rl', 'unitree_rl_mjlab'),
    ]);
    return {
        root,
        backend,
        python: python,
        logs: path.join(root, 'logs'),
        docs: path.join(root, 'docs'),
        output: path.join(root, 'output'),
        assets: inventory,
        inventory,
        mjlabSource,
        mjlabExtension,
    };
}

const PATHS = resolvePaths();

const DEFAULT_SETTINGS = {
    autoStartBackend: false,
    pythonPath: '',
    backendPort: DEFAULT_BACKEND_PORT,
    torchDevice: 'gpu',
};

function settingsPath() {
    return path.join(app.getPath('userData'), 'settings.json');
}

function readSettings() {
    try {
        const value = JSON.parse(fs.readFileSync(settingsPath(), 'utf8'));
        return { ...DEFAULT_SETTINGS, ...value };
    } catch {
        return { ...DEFAULT_SETTINGS };
    }
}

function writeSettings(value) {
    const backendPort = Number(value?.backendPort ?? DEFAULT_BACKEND_PORT);
    if (!Number.isInteger(backendPort) || backendPort < 1024 || backendPort > 65535) {
        throw new Error('Backend port must be an integer between 1024 and 65535');
    }
    const next = {
        autoStartBackend: Boolean(value?.autoStartBackend),
        pythonPath: typeof value?.pythonPath === 'string' ? value.pythonPath.trim() : '',
        backendPort,
        torchDevice: value?.torchDevice === 'cpu' ? 'cpu' : 'gpu',
    };
    fs.mkdirSync(path.dirname(settingsPath()), { recursive: true });
    fs.writeFileSync(settingsPath(), JSON.stringify(next, null, 2), 'utf8');
    return next;
}

function configuredBackendPort() {
    const port = Number(readSettings().backendPort);
    return Number.isInteger(port) && port >= 1024 && port <= 65535 ? port : DEFAULT_BACKEND_PORT;
}

function ensureWorkspaceDirectories() {
    const workspace = PATHS.workspace || path.join(app.getPath('userData'), 'workspace');
    PATHS.workspace = workspace;
    for (const directory of [PATHS.logs, PATHS.output, workspace]) {
        fs.mkdirSync(directory, { recursive: true });
    }
    return [PATHS.logs, workspace, PATHS.output];
}

function configureWritablePaths() {
    const userData = app.getPath('userData');
    PATHS.logs = path.join(userData, 'logs');
    PATHS.output = path.join(userData, 'output');
    PATHS.workspace = path.join(userData, 'workspace');
    PATHS.runtime = path.join(userData, 'runtime');
    refreshDownloadedRuntimePaths();
}

function refreshDownloadedRuntimePaths() {
    if (!PATHS.runtime) return false;
    const executable = process.platform === 'win32' ? 'python.exe' : 'python';
    const downloadedPython = findRuntimePython(path.join(PATHS.runtime, 'python'), executable);
    if (downloadedPython && fs.existsSync(downloadedPython)) PATHS.python = downloadedPython;
    const downloadedSource = path.join(PATHS.runtime, 'mjlab_source');
    const downloadedExtension = path.join(PATHS.runtime, 'mjlab_extension');
    const runtimeManifest = path.join(PATHS.runtime, 'runtime-manifest.json');
    if (fs.existsSync(downloadedSource)) PATHS.mjlabSource = downloadedSource;
    if (fs.existsSync(downloadedExtension)) PATHS.mjlabExtension = downloadedExtension;
    return Boolean(downloadedPython && fs.existsSync(downloadedSource) && fs.existsSync(downloadedExtension) && fs.existsSync(runtimeManifest));
}

function getRuntimeDevice() {
    const device = readSettings().torchDevice;
    return device === 'cpu' ? 'cpu' : 'gpu';
}

function detectGpus() {
    return new Promise((resolve) => {
        const script = path.join(PATHS.root, 'scripts', 'provision_windows_runtime.ps1');
        if (process.platform !== 'win32' || !fs.existsSync(script)) {
            resolve({ ok: false, gpus: [], error: 'GPU detection is available on Windows only.' });
            return;
        }
        execFile('powershell.exe', ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', script, '-DetectGpus'], {
            windowsHide: true,
            timeout: 15000,
            maxBuffer: 1024 * 1024 * 2,
        }, (error, stdout, stderr) => {
            if (error) {
                resolve({ ok: false, gpus: [], error: stderr.trim() || error.message });
                return;
            }
            const line = stdout.trim().split(/\r?\n/).filter((item) => item.trim().startsWith('[')).pop();
            try {
                const gpus = line ? JSON.parse(line) : [];
                resolve({ ok: true, gpus });
            } catch {
                resolve({ ok: false, gpus: [], error: 'Unable to parse GPU detection output' });
            }
        });
    });
}

function provisionWindowsRuntime() {
    if (process.platform !== 'win32') {
        return Promise.resolve({ ok: false, error: 'This runtime profile is available for Windows only.' });
    }
    if (runtimeProvisionProcess && runtimeProvisionProcess.exitCode === null) {
        return Promise.resolve({ ok: false, error: 'Runtime provisioning is already running.' });
    }
    const script = path.join(PATHS.root, 'scripts', 'provision_windows_runtime.ps1');
    if (!fs.existsSync(script)) {
        return Promise.resolve({ ok: false, error: `Runtime provisioner not found: ${script}` });
    }
    const target = PATHS.runtime || path.join(app.getPath('userData'), 'runtime');
    const bootstrap = path.join(PATHS.root, 'bootstrap');
    const device = getRuntimeDevice();
    ensureWorkspaceDirectories();
    emit('backend-log', `[runtime] profile ${DOWNLOAD_RUNTIME_VERSION} (${device})\n`);
    emit('backend-log', `[runtime] download target: ${target}\n`);
    return new Promise((resolve) => {
        runtimeProvisionProcess = spawn('powershell.exe', ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', script, '-TargetRoot', target, '-BootstrapRoot', bootstrap, '-Device', device], {
            cwd: PATHS.root,
            windowsHide: true,
            stdio: ['ignore', 'pipe', 'pipe'],
            env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
        });
        let stdoutBuffer = '';
        runtimeProvisionProcess.stdout.on('data', (data) => {
            stdoutBuffer += data.toString();
            const lines = stdoutBuffer.split(/\r?\n/);
            stdoutBuffer = lines.pop() || '';
            for (const line of lines) {
                const progress = line.match(/^::progress::(\w+)\|(\d+)\|(.*)$/);
                if (progress) {
                    emit('runtime-progress', { stage: progress[1], percent: Number(progress[2]), message: progress[3] });
                } else if (line) {
                    const trimmed = line.trim();
                    if (trimmed.startsWith('DEBUG ') || trimmed.startsWith('WARN ')) continue;
                    emit('backend-log', `${line}\n`);
                }
            }
        });
        let stderrBuffer = '';
        runtimeProvisionProcess.stderr.on('data', (data) => {
            stderrBuffer += data.toString();
            const lines = stderrBuffer.split(/\r?\n/);
            stderrBuffer = lines.pop() || '';
            for (const line of lines) {
                const trimmed = line.trim();
                if (!trimmed || trimmed.startsWith('DEBUG ') || trimmed.startsWith('WARN ')) continue;
                emit('backend-log', `${line}\n`);
            }
        });
        runtimeProvisionProcess.on('error', (error) => {
            runtimeProvisionProcess = null;
            resolve({ ok: false, error: error.message });
        });
        runtimeProvisionProcess.on('close', (code) => {
            if (stdoutBuffer) emit('backend-log', `${stdoutBuffer}\n`);
            if (stderrBuffer) {
                const trimmed = stderrBuffer.trim();
                if (trimmed && !trimmed.startsWith('DEBUG ') && !trimmed.startsWith('WARN ')) emit('backend-log', `${stderrBuffer}\n`);
            }
            runtimeProvisionProcess = null;
            if (code !== 0) {
                emit('runtime-progress', { stage: 'failed', percent: 0, message: `配置失败，退出码 ${code}` });
                resolve({ ok: false, error: `Runtime provisioning exited with code ${code}. See Console for details.` });
                return;
            }
            const ready = refreshDownloadedRuntimePaths();
            if (!ready) {
                resolve({ ok: false, error: 'Runtime download completed but required files are missing.' });
                return;
            }
            const current = readSettings();
            writeSettings({ ...current, pythonPath: PATHS.python });
            emit('runtime-progress', { stage: 'complete', percent: 100, message: '运行环境配置完成' });
            resolve({ ok: true, python: PATHS.python, runtime: PATHS.runtime, profile: DOWNLOAD_RUNTIME_VERSION, device });
        });
    });
}

function probePython(executable) {
    return new Promise((resolve) => {
        execFile(executable || PATHS.python, ['-c', 'import importlib.util,platform,sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"); print(platform.python_implementation()); print(";".join(f"{m}={bool(importlib.util.find_spec(m))}" for m in ("fastapi","uvicorn","pydantic")))'], { windowsHide: true, timeout: 5000 }, (error, stdout, stderr) => {
            if (error) {
                resolve({ ok: false, executable: executable || PATHS.python, error: stderr.trim() || error.message });
                return;
            }
            const lines = stdout.trim().split(/\r?\n/).filter(Boolean);
            const dependencies = Object.fromEntries((lines[2] || '').split(';').filter(Boolean).map((item) => {
                const [key, value] = item.split('=');
                return [key, String(value).toLowerCase()];
            }));
            resolve({ ok: true, executable: executable || PATHS.python, version: lines[0] || 'unknown', implementation: lines[1] || 'unknown', target: '3.12', targetMatch: /^3\.12\./.test(lines[0] || ''), dependencies, dependenciesReady: Object.values(dependencies).every((value) => value === 'true') });
        });
    });
}

function installPythonDependencies(executable) {
    const requirements = path.join(PATHS.root, 'backend', 'requirements.txt');
    if (!fs.existsSync(requirements)) {
        return Promise.resolve({ ok: false, error: `requirements file not found: ${requirements}` });
    }
    emit('backend-log', `[launcher] installing control-plane dependencies from ${requirements}`);
    return new Promise((resolve) => {
        execFile(executable, ['-m', 'pip', 'install', '--break-system-packages', '-r', requirements], {
            windowsHide: true,
            timeout: 300000,
            maxBuffer: 1024 * 1024 * 8,
            env: { ...process.env, PYTHONUTF8: '1', PYTHONIOENCODING: 'utf-8' },
        }, (error, stdout, stderr) => {
            if (stdout) emit('backend-log', stdout);
            if (stderr) emit('backend-log', stderr);
            resolve(error ? { ok: false, error: stderr.trim() || error.message } : { ok: true });
        });
    });
}

async function setupEnvironment({ installDependencies = true } = {}) {
    const directories = ensureWorkspaceDirectories();
    const configuredPython = readSettings().pythonPath;
    const executable = configuredPython || PATHS.python;
    let probe = await probePython(executable);
    let installed = false;
    if (!probe.ok) {
        return { ok: false, directories, python: probe, installed, error: `Python 3.12 runtime is not configured: ${probe.error || executable}` };
    }
    if (!probe.targetMatch) {
        return { ok: false, directories, python: probe, installed, error: `Python ${probe.version} is unsupported. Configure the pinned Python 3.12 runtime first.` };
    }
    if (probe.ok && !probe.dependenciesReady && installDependencies) {
        const install = await installPythonDependencies(executable);
        installed = install.ok;
        if (install.ok) probe = await probePython(executable);
        else return { ok: false, directories, python: probe, installed, error: install.error };
    }
    return { ok: probe.ok && probe.dependenciesReady, directories, python: probe, installed, error: probe.ok ? undefined : probe.error };
}

function emit(channel, payload) {
    if (launcherWindow && !launcherWindow.isDestroyed()) {
        launcherWindow.webContents.send(channel, payload);
    }
}

function requestJson(route, port = activeBackendPort || configuredBackendPort()) {
    return new Promise((resolve, reject) => {
        const request = http.request({
            hostname: '127.0.0.1',
            port,
            path: route,
            method: 'GET',
            timeout: 1500,
            headers: { Accept: 'application/json' },
        }, (response) => {
            let body = '';
            response.setEncoding('utf8');
            response.on('data', (chunk) => { body += chunk; });
            response.on('end', () => {
                if (response.statusCode < 200 || response.statusCode >= 300) {
                    reject(new Error(`backend returned HTTP ${response.statusCode}`));
                    return;
                }
                try {
                    resolve(JSON.parse(body));
                } catch (error) {
                    reject(new Error(`invalid backend response: ${error.message}`));
                }
            });
        });
        request.on('error', reject);
        request.on('timeout', () => request.destroy(new Error('backend health check timed out')));
        request.end();
    });
}

async function backendHealth(port = activeBackendPort || configuredBackendPort(), requireCurrentInstance = false) {
    const health = await requestJson('/health', port);
    if (health?.app_id !== 'legged-studio' || health?.api_schema !== EXPECTED_API_SCHEMA) {
        throw new Error(`端口 ${port} 已被其它或不兼容的服务占用，请更换端口或结束该进程后重试`);
    }
    if (requireCurrentInstance && health?.instance_id !== INSTANCE_ID) {
        throw new Error(`端口 ${port} 上是另一个 Legged Studio 后端实例（非本次启动），已拒绝连接；请结束旧进程后重试`);
    }
    return health;
}

async function waitForBackend(port, timeoutMs = 10000) {
    const deadline = Date.now() + timeoutMs;
    let lastError = null;
    while (Date.now() < deadline) {
        try {
            return await backendHealth(port, true);
        } catch (error) {
            lastError = error;
            await new Promise((resolve) => setTimeout(resolve, 250));
        }
    }
    throw lastError || new Error('backend did not become ready');
}

function assertPortAvailable(port) {
    return new Promise((resolve, reject) => {
        const server = net.createServer();
        server.unref();
        server.once('error', (error) => reject(new Error(`Port ${port} is unavailable: ${error.code || error.message}`)));
        server.listen({ host: '127.0.0.1', port, exclusive: true }, () => server.close(resolve));
    });
}

function stopStaleWindowsBackend(port, health) {
    if (process.platform !== 'win32' || !IS_DEV) return Promise.resolve(false);
    if (health?.app_id !== 'legged-studio' || health?.api_schema !== EXPECTED_API_SCHEMA) return Promise.resolve(false);
    return new Promise((resolve, reject) => {
        const script = [
            `$connection = Get-NetTCPConnection -State Listen -LocalPort ${Number(port)} -ErrorAction SilentlyContinue | Select-Object -First 1`,
            'if (-not $connection) { exit 0 }',
            '$process = Get-CimInstance Win32_Process -Filter ("ProcessId=" + $connection.OwningProcess)',
            'if (-not $process -or $process.CommandLine -notmatch "backend\\.api_complete:app") { exit 7 }',
            'Stop-Process -Id $connection.OwningProcess -Force',
        ].join('; ');
        execFile('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command', script], {
            windowsHide: true,
            timeout: 10000,
        }, (error) => {
            if (error) {
                reject(new Error(`Unable to stop stale Legged Studio backend on port ${port}`));
                return;
            }
            emit('backend-log', `[launcher] stopped stale backend on port ${port}\n`);
            resolve(true);
        });
    });
}

async function waitForPortRelease(port, timeoutMs = 5000) {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
        try {
            await assertPortAvailable(port);
            return;
        } catch {
            await new Promise((resolve) => setTimeout(resolve, 150));
        }
    }
    throw new Error(`Port ${port} did not become available after stopping the stale backend`);
}

function createLauncherWindow() {
    launcherWindow = new BrowserWindow({
        width: 1440,
        height: 900,
        minWidth: 1120,
        minHeight: 720,
        backgroundColor: '#10151b',
        title: 'Legged Studio',
        frame: false,
        show: false,
        webPreferences: {
            preload: path.join(__dirname, 'preload.js'),
            contextIsolation: true,
            nodeIntegration: false,
            sandbox: true,
        },
    });

    launcherWindow.loadFile(path.join(__dirname, 'index.html'));
    launcherWindow.once('ready-to-show', () => launcherWindow.show());
    launcherWindow.on('closed', () => { launcherWindow = null; });
    launcherWindow.on('close', async (event) => {
        if (runningTasksCache.length) {
            const proceed = await confirmExitWithRunningTasks(event);
            if (!proceed) event.preventDefault();
        }
    });
}

async function startBackend() {
    const port = configuredBackendPort();
    if (pythonProcess && pythonProcess.exitCode === null) {
        return waitForBackend(activeBackendPort || port, 2500);
    }
    try {
        const health = await backendHealth(port);
        if (health.instance_id === INSTANCE_ID) {
            activeBackendPort = port;
            emit('backend-status', true);
            return health;
        }
        await stopStaleWindowsBackend(port, health);
        await waitForPortRelease(port);
    } catch {
        // No compatible service is listening yet; continue with local startup.
    }
    await assertPortAvailable(port);
    if (!fs.existsSync(PATHS.backend)) {
        throw new Error(`找不到后端入口: ${PATHS.backend}`);
    }

    const setup = await setupEnvironment({ installDependencies: true });
    if (!setup.ok) {
        throw new Error(setup.error || 'Python runtime or control-plane dependencies are unavailable');
    }
    // Provisioning can replace PATHS.python, so resolve the executable only
    // after setup has completed.
    const configuredPython = readSettings().pythonPath;
    const pythonExecutable = configuredPython || PATHS.python;
    emit('backend-log', `[launcher] starting backend: ${PATHS.backend}`);
    emit('backend-log', `[launcher] python: ${pythonExecutable}`);
    pythonProcess = spawn(pythonExecutable, ['-m', 'uvicorn', 'backend.api_complete:app', '--host', '127.0.0.1', '--port', String(port)], {
        cwd: PATHS.root,
        stdio: ['ignore', 'pipe', 'pipe'],
        windowsHide: true,
        env: {
            ...process.env,
            PYTHONIOENCODING: 'utf-8',
            PYTHONUNBUFFERED: '1',
            LEGGED_STUDIO_DATA_DIR: app.getPath('userData'),
            LEGGED_STUDIO_INSTANCE_ID: INSTANCE_ID,
            LEGGED_STUDIO_WORKSPACE: PATHS.workspace || path.join(app.getPath('userData'), 'workspace'),
            LEGGED_STUDIO_OUTPUT: PATHS.output,
            LEGGED_STUDIO_MJLAB_SOURCE: PATHS.mjlabSource,
            LEGGED_STUDIO_MJLAB_EXTENSION: PATHS.mjlabExtension,
            LEGGED_STUDIO_MJLAB_PYTHON: PATHS.python,
            LEGGED_STUDIO_RUNTIME_PYTHON: PATHS.python,
        },
    });

    pythonProcess.stdout.on('data', (data) => emit('backend-log', data.toString()));
    pythonProcess.stderr.on('data', (data) => emit('backend-log', data.toString()));
    pythonProcess.on('error', (error) => emit('backend-log', `[launcher] ${error.message}`));
    pythonProcess.on('close', (code) => {
        emit('backend-log', `[launcher] backend exited with code ${code}`);
        pythonProcess = null;
        activeBackendPort = null;
        emit('backend-status', false);
    });

    const health = await waitForBackend(port);
    activeBackendPort = port;
    emit('backend-status', true);
    createTray();
    startTrainingPolling();
    return health;
}

async function stopBackend() {
    if (!pythonProcess) {
        return false;
    }
    const pid = pythonProcess.pid;
    emit('backend-log', `[launcher] stopping backend process ${pid}`);
    if (process.platform === 'win32') {
        spawn('taskkill', ['/pid', String(pid), '/t', '/f'], { windowsHide: true, stdio: 'ignore' });
    } else {
        pythonProcess.kill('SIGTERM');
    }
    pythonProcess = null;
    activeBackendPort = null;
    emit('backend-status', false);
    return true;
}

function safeOpenPath(key) {
    const allowed = { root: PATHS.root, backend: PATHS.backend, logs: PATHS.logs, docs: PATHS.docs, output: PATHS.output, assets: PATHS.assets, inventory: PATHS.inventory };
    const target = allowed[key];
    if (!target) throw new Error(`unsupported path key: ${key}`);
    const existing = fs.existsSync(target) ? target : PATHS.root;
    return shell.openPath(existing);
}

ipcMain.handle('backend:start', async () => {
    try {
        const health = await startBackend();
        return { ok: true, health };
    } catch (error) {
        emit('backend-status', false);
        return { ok: false, error: error.message };
    }
});

ipcMain.handle('backend:stop', async () => ({ ok: await stopBackend() }));
ipcMain.handle('backend:check', async () => {
    try { return { ok: true, health: await backendHealth(undefined, true) }; }
    catch { return { ok: false }; }
});
ipcMain.handle('backend:url', () => `http://127.0.0.1:${activeBackendPort || configuredBackendPort()}`);

// 面板注册表投影（Phase 7 插件化 v2.1）：桌面导航 = 同一注册表的 desktop 过滤投影；
// 控制面不可达时返回 null（renderer 用静态清单兜底——诚实降级，不假跑）。
ipcMain.handle('panels:registry', async () => {
  const port = activeBackendPort || configuredBackendPort();
  try {
    const response = await fetch(`http://127.0.0.1:${port}/api/panels`, { signal: AbortSignal.timeout(3000) });
    if (!response.ok) return null;
    const payload = await response.json();
    if (!payload?.success || !Array.isArray(payload.navigation)) return null;
    return payload.navigation.filter((item) => !item.disabled);
  } catch { return null; }
});
ipcMain.handle('launcher:paths', () => ({ ...PATHS, backend: PATHS.backend, python: PATHS.python }));
ipcMain.handle('launcher:version', () => {
    // 版本唯一真值源是仓库根 VERSION（与 release-check / 后端 version.py 同源）
    try {
        return fs.readFileSync(path.join(app.getAppPath(), 'VERSION'), 'utf8').trim();
    } catch {
        return 'unknown';
    }
});
ipcMain.handle('settings:get', () => readSettings());
ipcMain.handle('settings:update', (_event, value) => writeSettings(value));
ipcMain.handle('environment:probe', async (_event, executable) => probePython(executable || readSettings().pythonPath || PATHS.python));
ipcMain.handle('environment:prepare', () => {
    try {
        return { ok: true, directories: ensureWorkspaceDirectories() };
    } catch (error) {
        return { ok: false, directories: [], error: error.message };
    }
});
ipcMain.handle('environment:setup', async () => {
    try {
        return await setupEnvironment({ installDependencies: true });
    } catch (error) {
        return { ok: false, directories: [], error: error.message };
    }
});
ipcMain.handle('environment:provision-windows', () => provisionWindowsRuntime());
ipcMain.handle('environment:gpu-list', () => detectGpus());
ipcMain.handle('environment:runtime-profile', () => {
    const device = getRuntimeDevice();
    const torch = device === 'cpu' ? '2.11.0+cpu' : '2.11.0+cu128';
    const torchIndex = device === 'cpu' ? 'PyTorch 官方 CPU' : '上海交大 PyTorch cu128';
    return {
        id: DOWNLOAD_RUNTIME_VERSION,
        platform: 'win32-x64',
        device,
        torch,
        python: '3.12.13',
        uv: '0.11.8',
        mjlab: '1.6.0',
        mujoco: '3.11.0',
        unitree: '1425b15',
        packageIndex: '清华 PyPI',
        torchIndex,
        installed: refreshDownloadedRuntimePaths(),
        root: PATHS.runtime,
    };
});
ipcMain.handle('settings:pick-python', async (event) => {
    const filtered = process.platform === 'win32'
        ? [{ name: 'Python 可执行文件', extensions: ['exe'] }]
        : [{ name: 'Python 可执行文件', extensions: ['*'] }];
    const options = {
        title: '选择 Python 可执行文件',
        properties: ['openFile'],
        filters: filtered,
        defaultPath: readSettings().pythonPath || undefined,
    };
    const result = await dialog.showOpenDialog(event.sender, options);
    if (result.canceled || !result.filePaths.length) return { ok: false, path: '' };
    const selected = result.filePaths[0];
    const settings = readSettings();
    writeSettings({ ...settings, pythonPath: selected });
    return { ok: true, path: selected };
});
ipcMain.handle('path:open', (_event, key) => safeOpenPath(key));
ipcMain.handle('external:open', (_event, url) => {
    if (typeof url !== 'string' || !/^https?:\/\//i.test(url)) throw new Error('only http(s) URLs are allowed');
    return shell.openExternal(url);
});
ipcMain.handle('window:minimize', () => launcherWindow?.minimize());
ipcMain.handle('window:toggle-maximize', () => {
    if (!launcherWindow) return false;
    if (launcherWindow.isMaximized()) launcherWindow.unmaximize();
    else launcherWindow.maximize();
    return launcherWindow.isMaximized();
});
ipcMain.handle('window:close', () => app.quit());

app.whenReady().then(() => {
    configureWritablePaths();
    createLauncherWindow();
});
app.on('activate', () => { if (!launcherWindow) createLauncherWindow(); });
app.on('before-quit', () => {
    if (pythonProcess) stopBackend();
    if (runtimeProvisionProcess && runtimeProvisionProcess.exitCode === null) runtimeProvisionProcess.kill();
});
app.on('window-all-closed', () => { if (process.platform !== 'darwin') app.quit(); });

process.on('uncaughtException', (error) => emit('backend-log', `[launcher] uncaught exception: ${error.message}`));
