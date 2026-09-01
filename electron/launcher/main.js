const { app, BrowserWindow, ipcMain, shell } = require('electron');
const { spawn, execFile } = require('child_process');
const path = require('path');
const fs = require('fs');
const http = require('http');
const net = require('net');

const DEFAULT_BACKEND_PORT = 8765;
const IS_DEV = process.env.NODE_ENV === 'development' || !app.isPackaged;
let launcherWindow = null;
let pythonProcess = null;
let activeBackendPort = null;

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
        path.join(root, 'backend', 'api.py'),
        path.join(resourceRoot, 'app', 'backend', 'api_complete.py'),
        path.join(resourceRoot, 'backend', 'api_complete.py'),
    ]);
    const embeddedPython = findRuntimePython(path.join(root, 'runtime', 'python'), pythonExecutable);
    const python = firstExisting([
        embeddedPython,
        path.join(root, 'runtime', 'python', pythonExecutable),
        path.join(root, 'adapters', 'mjlab', '.venv', venvBin, pythonExecutable),
        path.join(root, 'adapters', 'mjlab_new', '.venv', venvBin, pythonExecutable),
        path.join(resourceRoot, 'runtime', 'python', pythonExecutable),
        path.join(projectRoot, 'runtime', 'python', pythonExecutable),
    ]);
    const inventory = firstExisting([
        path.join(root, 'QUADRUPED_ASSET_INVENTORY.json'),
        path.join(projectRoot, '..', 'QUADRUPED_ASSET_INVENTORY.json'),
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
        python: fs.existsSync(python) ? python : 'python',
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
}

function probePython(executable) {
    return new Promise((resolve) => {
        execFile(executable || PATHS.python, ['-c', 'import importlib.util,platform,sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"); print(platform.python_implementation()); print(";".join(f"{m}={bool(importlib.util.find_spec(m))}" for m in ("fastapi","uvicorn","pydantic")))'], { windowsHide: true, timeout: 5000 }, (error, stdout, stderr) => {
            if (error) {
                resolve({ ok: false, executable: executable || PATHS.python, error: stderr.trim() || error.message });
                return;
            }
            const lines = stdout.trim().split(/\r?\n/).filter(Boolean);
            const dependencies = Object.fromEntries((lines[2] || '').split(';').filter(Boolean).map((item) => item.split('=')));
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
        execFile(executable, ['-m', 'pip', 'install', '-r', requirements], {
            windowsHide: true,
            timeout: 300000,
            maxBuffer: 1024 * 1024 * 8,
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

async function backendHealth(port = activeBackendPort || configuredBackendPort()) {
    return requestJson('/health', port);
}

async function waitForBackend(port, timeoutMs = 10000) {
    const deadline = Date.now() + timeoutMs;
    let lastError = null;
    while (Date.now() < deadline) {
        try {
            return await backendHealth(port);
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
}

async function startBackend() {
    const port = configuredBackendPort();
    if (pythonProcess && pythonProcess.exitCode === null) {
        return waitForBackend(activeBackendPort || port, 2500);
    }
    try {
        const health = await backendHealth(port);
        activeBackendPort = port;
        emit('backend-status', true);
        return health;
    } catch {
        // No service is listening yet; continue with local startup.
    }
    await assertPortAvailable(port);
    if (!fs.existsSync(PATHS.backend)) {
        throw new Error(`找不到后端入口: ${PATHS.backend}`);
    }

    const configuredPython = readSettings().pythonPath;
    const pythonExecutable = configuredPython || PATHS.python;
    const setup = await setupEnvironment({ installDependencies: true });
    if (!setup.ok) {
        throw new Error(setup.error || 'Python runtime or control-plane dependencies are unavailable');
    }
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
    try { return { ok: true, health: await backendHealth() }; }
    catch { return { ok: false }; }
});
ipcMain.handle('backend:url', () => `http://127.0.0.1:${activeBackendPort || configuredBackendPort()}`);
ipcMain.handle('launcher:paths', () => ({ ...PATHS, backend: PATHS.backend, python: PATHS.python }));
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
app.on('before-quit', () => { if (pythonProcess) stopBackend(); });
app.on('window-all-closed', () => { if (process.platform !== 'darwin') app.quit(); });

process.on('uncaughtException', (error) => emit('backend-log', `[launcher] uncaught exception: ${error.message}`));
