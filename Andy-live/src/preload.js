const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('api', {
    getAvailableResumes: () => ipcRenderer.invoke('get-resumes'),
    setupSession: (jdText, resumePath) => ipcRenderer.invoke('setup-session', { jdText, resumePath }),
    sendQuery: (query, forcedProvider) => ipcRenderer.invoke('send-query', { query, forcedProvider }),
    onModelResponse: (callback) => ipcRenderer.on('model-response', (event, data) => callback(data)),
    onRoleChanged: (callback) => ipcRenderer.on('role-changed', (event, data) => callback(data))
});
