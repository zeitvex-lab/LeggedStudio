/**
 * Legged Studio - Electron 启动器
 * 参考：ComfyUI-aki 和 online_tools 的启动方式
 * 简化版：快速启动，无复杂检测
 */

const { app, BrowserWindow, shell } = require('electron');
const { spawn } = require('child_process');
const path = require('path');

let mainWindow;
let pythonProcess;

const BACKEND_PORT = 8765;

/**
 * 创建主窗口
 */
function createWindow() {
    mainWindow = new BrowserWindow({
        width: 1400,
        height: 900,
        backgroundColor: '#0f0f1e',
        title: 'Legged Studio',
        webPreferences: {
            nodeIntegration: false,
            contextIsolation: true,
        },
        show: false,
    });

    // 加载本地文件
    const dashboardPath = path.join(__dirname, '..', 'web', 'dashboard.html');
    mainWindow.loadFile(dashboardPath);

    mainWindow.once('ready-to-show', () => {
        mainWindow.show();
        console.log('[Electron] Window shown');
    });

    mainWindow.on('closed', () => {
        mainWindow = null;
    });

    // 开发模式：打开 DevTools
    // mainWindow.webContents.openDevTools();
}

/**
 * 启动 Python 后端
 */
function startBackend() {
    console.log('[Electron] Starting Python backend...');

    const pythonCmd = 'python';
    const serverScript = path.join(__dirname, '..', 'backend', 'api_complete.py');

    pythonProcess = spawn(pythonCmd, [serverScript], {
        stdio: 'ignore', // 忽略输出，避免编码问题
        cwd: path.join(__dirname, '..'),
        detached: false,
    });

    console.log(`[Electron] Backend started (PID: ${pythonProcess.pid})`);

    pythonProcess.on('error', (err) => {
        console.error('[Electron] Failed to start backend:', err);
    });

    pythonProcess.on('close', (code) => {
        console.log(`[Electron] Backend exited with code ${code}`);
    });
}

/**
 * App 生命周期
 */
app.on('ready', () => {
    console.log('[Electron] App ready');

    // 先创建窗口
    createWindow();

    // 延迟启动后端（避免窗口卡顿）
    setTimeout(() => {
        startBackend();
    }, 500);
});

app.on('window-all-closed', () => {
    // 关闭后端
    if (pythonProcess) {
        console.log('[Electron] Killing backend...');
        try {
            pythonProcess.kill();
        } catch (e) {
            console.error('[Electron] Failed to kill backend:', e);
        }
    }

    if (process.platform !== 'darwin') {
        app.quit();
    }
});

app.on('activate', () => {
    if (mainWindow === null) {
        createWindow();
    }
});

app.on('before-quit', () => {
    if (pythonProcess) {
        try {
            pythonProcess.kill();
        } catch (e) {
            // 忽略
        }
    }
});

// 错误处理
process.on('uncaughtException', (error) => {
    console.error('[Electron] Uncaught exception:', error);
});

console.log('[Electron] Legged Studio starting...');
