const { app, BrowserWindow, ipcMain, globalShortcut, dialog, clipboard } = require('electron');
const path = require('path');
const fs = require('fs');
require('dotenv').config({ path: path.join(__dirname, '../.env') });

const SmartAIRouter = require('./utils/smartRouter');
const { getAvailableResumes, buildPersonalizedPrompt } = require('./utils/jdMatcher');

let mainWindow = null;
const router = new SmartAIRouter();
const session = { jdText: '', resumePath: '', role: 'default' };
const selectedImagePaths = new Set();
const MAX_IMAGE_BYTES = 4 * 1024 * 1024;
const SUPPORTED_IMAGE_TYPES = new Map([
    ['.png', 'image/png'],
    ['.jpg', 'image/jpeg'],
    ['.jpeg', 'image/jpeg'],
    ['.webp', 'image/webp']
]);

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
        const allowedProviders = new Set(['', 'groq', 'gemini_search']);
        const provider = allowedProviders.has(forcedProvider) ? forcedProvider : '';
        const result = await router.routeQuery(String(query || '').slice(0, 12000), null, null, provider);
        return { success: true, result };
    } catch (err) {
        return { success: false, error: err.message };
    }
});

ipcMain.handle('select-image', async () => {
    const selection = await dialog.showOpenDialog(mainWindow, {
        title: 'Choose a screenshot to analyze',
        properties: ['openFile'],
        filters: [{ name: 'Images', extensions: ['png', 'jpg', 'jpeg', 'webp'] }]
    });
    if (selection.canceled || !selection.filePaths[0]) return { canceled: true };

    const imagePath = selection.filePaths[0];
    selectedImagePaths.add(imagePath);
    return { canceled: false, imagePath, name: path.basename(imagePath) };
});

ipcMain.handle('send-image-query', async (event, { query, imagePath, forcedProvider }) => {
    try {
        if (!selectedImagePaths.has(imagePath)) throw new Error('Select the screenshot again before analyzing it.');
        selectedImagePaths.delete(imagePath);

        const extension = path.extname(imagePath).toLowerCase();
        const mimeType = SUPPORTED_IMAGE_TYPES.get(extension);
        if (!mimeType) throw new Error('Use a PNG, JPG, JPEG, or WEBP screenshot.');

        const fileInfo = await fs.promises.stat(imagePath);
        if (!fileInfo.isFile() || fileInfo.size > MAX_IMAGE_BYTES) {
            throw new Error('Choose an image file smaller than 4 MB.');
        }

        const data = await fs.promises.readFile(imagePath);
        const result = await router.routeQuery(String(query || '').slice(0, 12000), null, { data, mimeType });
        return { success: true, result };
    } catch (err) {
        return { success: false, error: err.message };
    }
});

ipcMain.handle('copy-session-history', async (event, markdown) => {
    if (typeof markdown !== 'string' || !markdown.trim()) throw new Error('There is no session history to copy.');
    clipboard.writeText(markdown.slice(0, 1_000_000));
    return { success: true };
});

ipcMain.handle('export-session-history', async (event, markdown) => {
    if (typeof markdown !== 'string' || !markdown.trim()) throw new Error('There is no session history to export.');
    const selection = await dialog.showSaveDialog(mainWindow, {
        title: 'Export Andy Live session history',
        defaultPath: `andy-live-session-${new Date().toISOString().slice(0, 10)}.md`,
        filters: [{ name: 'Markdown', extensions: ['md'] }]
    });
    if (selection.canceled || !selection.filePath) return { canceled: true };
    await fs.promises.writeFile(selection.filePath, markdown.slice(0, 1_000_000), 'utf8');
    return { success: true, filePath: selection.filePath };
});

app.whenReady().then(createWindow);

app.on('will-quit', () => {
    globalShortcut.unregisterAll();
});

app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') app.quit();
});
