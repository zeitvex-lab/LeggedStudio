const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('leggedStudio', {
    startBackend: () => ipcRenderer.invoke('backend:start'),
    stopBackend: () => ipcRenderer.invoke('backend:stop'),
    checkBackend: () => ipcRenderer.invoke('backend:check'),
    backendUrl: () => ipcRenderer.invoke('backend:url'),
    getPaths: () => ipcRenderer.invoke('launcher:paths'),
    getSettings: () => ipcRenderer.invoke('settings:get'),
    updateSettings: (value) => ipcRenderer.invoke('settings:update', value),
    probePython: (executable) => ipcRenderer.invoke('environment:probe', executable),
    prepareEnvironment: () => ipcRenderer.invoke('environment:prepare'),
    openPath: (key) => ipcRenderer.invoke('path:open', key),
    openExternal: (url) => ipcRenderer.invoke('external:open', url),
    minimize: () => ipcRenderer.invoke('window:minimize'),
    toggleMaximize: () => ipcRenderer.invoke('window:toggle-maximize'),
    close: () => ipcRenderer.invoke('window:close'),
    onBackendLog: (listener) => {
        const handler = (_event, message) => listener(message);
        ipcRenderer.on('backend-log', handler);
        return () => ipcRenderer.removeListener('backend-log', handler);
    },
    onBackendStatus: (listener) => {
        const handler = (_event, running) => listener(running);
        ipcRenderer.on('backend-status', handler);
        return () => ipcRenderer.removeListener('backend-status', handler);
    },
});
