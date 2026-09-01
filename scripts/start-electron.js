const { spawn } = require('child_process');

// Some Python/Node environments export ELECTRON_RUN_AS_NODE globally.  The
// launcher must clear it so Electron loads the app runtime instead of plain
// Node, while preserving all other user environment variables.
const electron = require('electron');
const env = { ...process.env };
delete env.ELECTRON_RUN_AS_NODE;
if (process.argv.includes('--dev')) env.NODE_ENV = 'development';

const child = spawn(electron, ['.'], {
    cwd: process.cwd(),
    env,
    stdio: 'inherit',
    windowsHide: false,
});

child.on('error', (error) => {
    console.error(`Unable to start Electron: ${error.message}`);
    process.exitCode = 1;
});
child.on('exit', (code, signal) => {
    if (signal) {
        process.kill(process.pid, signal);
    } else {
        process.exitCode = code ?? 1;
    }
});
