const { app, BrowserWindow, ipcMain, globalShortcut } = require('electron');
const path = require('path');
require('dotenv').config({ path: path.join(__dirname, '../.env') });

const SmartAIRouter = require('./utils/smartRouter');
const { getAvailableResumes, buildPersonalizedPrompt } = require('./utils/jdMatcher');

let mainWindow = null;
const router = new SmartAIRouter();

function createWindow() {
    mainWindow = new BrowserWindow({
        width: 850,
        height: 600,
        x: 50,
        y: 50,
        transparent: true,
        frame: false,
        alwaysOnTop: true,
        skipTaskbar: false,
        webPreferences: {
            preload: path.join(__dirname, 'preload.js'),
            nodeIntegration: false,
            contextIsolation: true
        }
    });

    mainWindow.setAlwaysOnTop(true, 'screen-saver');
    mainWindow.loadFile(path.join(__dirname, 'renderer/index.html'));

    registerGlobalHotkeys();
}

function registerGlobalHotkeys() {
    globalShortcut.register('CommandOrControl+Shift+1', () => {
        if (mainWindow) mainWindow.webContents.send('role-changed', { role: 'mle', name: 'ML / AI Engineer Mode' });
    });

    globalShortcut.register('CommandOrControl+Shift+2', () => {
        if (mainWindow) mainWindow.webContents.send('role-changed', { role: 'backend', name: 'Backend Systems Architect Mode' });
    });

    globalShortcut.register('CommandOrControl+Shift+3', () => {
        if (mainWindow) mainWindow.webContents.send('role-changed', { role: 'ds', name: 'Data Scientist Mode' });
    });
}

ipcMain.handle('get-resumes', async () => {
    return getAvailableResumes();
});

ipcMain.handle('setup-session', async (event, { jdText, resumePath }) => {
    const prompt = buildPersonalizedPrompt(jdText, resumePath);
    router.setSystemPrompt(prompt);
    return { success: true, promptSnippet: prompt.substring(0, 300) + '...' };
});

ipcMain.handle('send-query', async (event, { query, forcedProvider }) => {
    try {
        const result = await router.routeQuery(query, null, null, forcedProvider);
        return { success: true, result };
    } catch (err) {
        return { success: false, error: err.message };
    }
});

ipcMain.on('set-ignore-mouse-events', (event, ignore) => {
    if (mainWindow) {
        if (ignore) {
            mainWindow.setIgnoreMouseEvents(true, { forward: true });
        } else {
            mainWindow.setIgnoreMouseEvents(false);
        }
    }
});

app.whenReady().then(createWindow);

app.on('will-quit', () => {
    globalShortcut.unregisterAll();
});

app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') app.quit();
});
