const { app, BrowserWindow, ipcMain, globalShortcut } = require('electron');
const path = require('path');
require('dotenv').config({ path: path.join(__dirname, '../.env') });

const SmartAIRouter = require('./utils/smartRouter');
const { getAvailableResumes, buildPersonalizedPrompt } = require('./utils/jdMatcher');

let mainWindow = null;
const router = new SmartAIRouter();
const session = { jdText: '', resumePath: '', role: 'default' };

const ROLE_MODES = {
    mle: 'ML / AI Engineer Mode',
    backend: 'Backend Systems Architect Mode',
    ds: 'Data Scientist Mode'
};

function refreshSessionPrompt() {
    if (session.jdText) {
        router.setSystemPrompt(buildPersonalizedPrompt(session.jdText, session.resumePath, session.role));
    }
}

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
    Object.entries({ 'CommandOrControl+Shift+1': 'mle', 'CommandOrControl+Shift+2': 'backend', 'CommandOrControl+Shift+3': 'ds' })
        .forEach(([accelerator, role]) => {
            const registered = globalShortcut.register(accelerator, () => {
                session.role = role;
                refreshSessionPrompt();
                mainWindow?.webContents.send('role-changed', { role, name: ROLE_MODES[role] });
            });
            if (!registered) console.warn(`[Andy Live] Unable to register global shortcut: ${accelerator}`);
        });
}

ipcMain.handle('get-resumes', async () => {
    return getAvailableResumes();
});

ipcMain.handle('setup-session', async (event, { jdText, resumePath }) => {
    if (typeof jdText !== 'string' || !jdText.trim()) throw new Error('A job description is required.');
    session.jdText = jdText.trim().slice(0, 30000);
    session.resumePath = typeof resumePath === 'string' ? resumePath : '';
    const prompt = buildPersonalizedPrompt(session.jdText, session.resumePath, session.role);
    router.setSystemPrompt(prompt);
    return { success: true, promptSnippet: prompt.substring(0, 300) + '...', configuredProviders: router.getConfiguredProviders() };
});

ipcMain.handle('send-query', async (event, { query, forcedProvider }) => {
    try {
        const allowedProviders = new Set(['', 'groq', 'gemini_search', 'claude', 'openai']);
        const provider = allowedProviders.has(forcedProvider) ? forcedProvider : '';
        const result = await router.routeQuery(String(query || '').slice(0, 12000), null, null, provider);
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
