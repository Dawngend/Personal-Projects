const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('api', {
    getAvailableResumes: () => ipcRenderer.invoke('get-resumes'),
    setupSession: (jdText, resumePath) => ipcRenderer.invoke('setup-session', { jdText, resumePath }),
    sendQuery: (query, forcedProvider) => ipcRenderer.invoke('send-query', { query, forcedProvider }),
    selectImage: () => ipcRenderer.invoke('select-image'),
    sendImageQuery: (query, imagePath, forcedProvider) => ipcRenderer.invoke('send-image-query', { query, imagePath, forcedProvider }),
    copySessionHistory: (markdown) => ipcRenderer.invoke('copy-session-history', markdown),
    exportSessionHistory: (markdown) => ipcRenderer.invoke('export-session-history', markdown),
    copyText: (text) => ipcRenderer.invoke('copy-text', text),
    generateDebugPrompt: (errorMessage, context) => ipcRenderer.invoke('generate-debug-prompt', { errorMessage, context }),
    onModelResponse: (callback) => ipcRenderer.on('model-response', (event, data) => callback(data)),
    onRoleChanged: (callback) => ipcRenderer.on('role-changed', (event, data) => callback(data))
});
