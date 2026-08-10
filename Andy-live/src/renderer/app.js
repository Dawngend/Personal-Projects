document.addEventListener('DOMContentLoaded', async () => {
    const setupModal = document.getElementById('setupModal');
    const historyModal = document.getElementById('historyModal');
    const setupBtn = document.getElementById('setupBtn');
    const debugBtn = document.getElementById('debugBtn');
    const deepPromptBtn = document.getElementById('deepPromptBtn');
    const historyBtn = document.getElementById('historyBtn');
    const closeHistoryBtn = document.getElementById('closeHistoryBtn');
    const clearHistoryBtn = document.getElementById('clearHistoryBtn');
    const copyHistoryBtn = document.getElementById('copyHistoryBtn');
    const exportHistoryBtn = document.getElementById('exportHistoryBtn');
    const historyList = document.getElementById('historyList');
    const historyEmpty = document.getElementById('historyEmpty');
    const saveSetupBtn = document.getElementById('saveSetupBtn');
    const jdInput = document.getElementById('jdInput');
    const resumeSelect = document.getElementById('resumeSelect');
    const queryInput = document.getElementById('queryInput');
    const attachImageBtn = document.getElementById('attachImageBtn');
    const imageAttachment = document.getElementById('imageAttachment');
    const imageAttachmentName = document.getElementById('imageAttachmentName');
    const clearImageBtn = document.getElementById('clearImageBtn');
    const forcedProviderSelect = document.getElementById('forcedProviderSelect');
    const responseOutput = document.getElementById('responseOutput');
    const providerTag = document.getElementById('providerTag');
    const latencyTag = document.getElementById('latencyTag');
    const activeRoleBadge = document.getElementById('activeRoleBadge');
    let selectedImage = null;
    let latestFailure = null;
    let latestQuestion = null;
    const sessionHistory = [];

    const createHistoryMarkdown = () => {
        const lines = ['# Andy Live Session History', ''];
        sessionHistory.forEach((entry, index) => {
            lines.push(`## ${index + 1}. ${entry.timestamp}`);
            lines.push(`- **Mode:** ${entry.role}`);
            lines.push(`- **Provider:** ${entry.provider} (${entry.model})`);
            lines.push(`- **Latency:** ${entry.latencyMs}ms`);
            if (entry.imageName) lines.push(`- **Screenshot:** ${entry.imageName}`);
            lines.push('', `**Question**`, entry.query, '', `**Response**`, entry.response, '');
        });
        return lines.join('\n');
    };

    const renderHistory = () => {
        historyList.replaceChildren();
        historyEmpty.classList.toggle('hidden', sessionHistory.length > 0);
        sessionHistory.forEach((entry, index) => {
            const item = document.createElement('article');
            item.className = 'history-entry';
            const meta = document.createElement('p');
            meta.className = 'history-meta';
            meta.textContent = `${index + 1} · ${entry.timestamp} · ${entry.role} · ${entry.provider} · ${entry.latencyMs}ms${entry.imageName ? ` · ${entry.imageName}` : ''}`;
            const question = document.createElement('p');
            question.className = 'history-question';
            question.textContent = `Q: ${entry.query}`;
            const response = document.createElement('p');
            response.className = 'history-response';
            response.textContent = entry.response;
            item.append(meta, question, response);
            historyList.appendChild(item);
        });
    };

    try {
        const resumes = await window.api.getAvailableResumes();
        resumes.forEach(r => {
            const opt = document.createElement('option');
            opt.value = r.filePath;
            opt.textContent = r.displayName;
            resumeSelect.appendChild(opt);
        });
    } catch (err) {
        console.error('Failed to load resumes:', err);
    }

    setupBtn.addEventListener('click', () => {
        setupModal.classList.remove('hidden');
    });

    historyBtn.addEventListener('click', () => {
        renderHistory();
        historyModal.classList.remove('hidden');
    });

    closeHistoryBtn.addEventListener('click', () => historyModal.classList.add('hidden'));
    clearHistoryBtn.addEventListener('click', () => {
        sessionHistory.length = 0;
        renderHistory();
    });

    copyHistoryBtn.addEventListener('click', async () => {
        if (!sessionHistory.length) return;
        await window.api.copySessionHistory(createHistoryMarkdown());
        copyHistoryBtn.textContent = 'Copied';
        setTimeout(() => { copyHistoryBtn.textContent = 'Copy Markdown'; }, 1500);
    });

    exportHistoryBtn.addEventListener('click', async () => {
        if (!sessionHistory.length) return;
        const result = await window.api.exportSessionHistory(createHistoryMarkdown());
        if (!result.canceled) exportHistoryBtn.textContent = 'Exported';
        setTimeout(() => { exportHistoryBtn.textContent = 'Export Markdown'; }, 1500);
    });

    attachImageBtn.addEventListener('click', async () => {
        const selection = await window.api.selectImage();
        if (selection.canceled) return;
        selectedImage = selection;
        imageAttachmentName.textContent = `Screenshot attached: ${selection.name}`;
        imageAttachment.classList.remove('hidden');
    });

    clearImageBtn.addEventListener('click', () => {
        selectedImage = null;
        imageAttachment.classList.add('hidden');
    });

    const setResponse = (message, className = '') => {
        responseOutput.replaceChildren();
        const paragraph = document.createElement('p');
        paragraph.textContent = message;
        if (className) paragraph.className = className;
        responseOutput.appendChild(paragraph);
    };

    const recordFailure = (message, context = {}) => {
        latestFailure = { message, context };
        debugBtn.classList.remove('hidden');
    };

    const clearFailure = () => {
        latestFailure = null;
        debugBtn.classList.add('hidden');
    };

    debugBtn.addEventListener('click', async () => {
        if (!latestFailure) return;
        debugBtn.disabled = true;
        debugBtn.textContent = 'Generating…';
        try {
            const result = await window.api.generateDebugPrompt(latestFailure.message, latestFailure.context);
            if (!result.success) throw new Error(result.error || 'Unable to generate a debug prompt.');
            await window.api.copyText(result.prompt);
            responseOutput.textContent = result.prompt;
            providerTag.textContent = `${result.provider} (${result.model})`;
            latencyTag.textContent = 'Copied to clipboard';
            debugBtn.textContent = '✓ Debug prompt copied';
        } catch (err) {
            setResponse(err.message || 'Unable to generate a debug prompt.', 'error-text');
            debugBtn.textContent = '🛠️ Generate debug prompt';
        } finally {
            debugBtn.disabled = false;
        }
    });

    deepPromptBtn.addEventListener('click', async () => {
        if (!latestQuestion) return;
        deepPromptBtn.disabled = true;
        deepPromptBtn.textContent = 'Preparing…';
        try {
            const result = await window.api.generateDeepPrompt(latestQuestion.query, latestQuestion.context);
            if (!result.success) throw new Error(result.error || 'Unable to create a deep-thinking prompt.');
            await window.api.copyText(result.prompt);
            responseOutput.textContent = result.prompt;
            providerTag.textContent = `${result.provider} (${result.model})`;
            latencyTag.textContent = 'Copied for Codex / Claude Code';
            deepPromptBtn.textContent = '✓ Deep prompt copied';
        } catch (err) {
            setResponse(err.message || 'Unable to create a deep-thinking prompt.', 'error-text');
            deepPromptBtn.textContent = '🧠 Deep prompt';
        } finally {
            deepPromptBtn.disabled = false;
        }
    });

    saveSetupBtn.addEventListener('click', async () => {
        const jdText = jdInput.value.trim();
        const selectedResume = resumeSelect.value;
        if (!jdText) {
            alert('Please paste a Job Description.');
            return;
        }

        try {
            const res = await window.api.setupSession(jdText, selectedResume);
            if (res.success) {
                setupModal.classList.add('hidden');
                const configured = Object.values(res.configuredProviders || {}).filter(Boolean).length;
                setResponse(`AI teleprompter initialized. ${configured} provider${configured === 1 ? '' : 's'} configured.`, 'success-text');
            }
        } catch (err) {
            setResponse(err.message || 'Unable to initialize the session.', 'error-text');
        }
    });

    queryInput.addEventListener('keydown', async (e) => {
        if (e.key === 'Enter') {
            const query = queryInput.value.trim();
            if (!query) return;

            queryInput.value = '';
            const forcedProvider = forcedProviderSelect.value;
            const imageName = selectedImage?.name || null;

            setResponse('Routing query to the AI engine…', 'placeholder-text');
            providerTag.textContent = 'Thinking...';
            latencyTag.textContent = '';

            const res = selectedImage
                ? await window.api.sendImageQuery(query, selectedImage.imagePath, forcedProvider)
                : await window.api.sendQuery(query, forcedProvider);

            if (selectedImage) {
                selectedImage = null;
                imageAttachment.classList.add('hidden');
            }

            if (res.success && res.result) {
                const { provider, model, text, latencyMs } = res.result;
                providerTag.textContent = `${provider} (${model})`;
                latencyTag.textContent = `${latencyMs}ms`;
                responseOutput.textContent = text;
                if (provider === 'Configuration required' || provider === 'Vision unavailable') {
                    recordFailure(text, { provider, model, role: activeRoleBadge.textContent, query, imageName: imageName || 'none' });
                } else {
                    clearFailure();
                }
                latestQuestion = {
                    query,
                    context: {
                        role: activeRoleBadge.textContent,
                        provider,
                        model,
                        currentHudAnswer: text,
                        screenshot: imageName || 'none'
                    }
                };
                deepPromptBtn.classList.remove('hidden');
                sessionHistory.push({
                    timestamp: new Date().toLocaleTimeString(),
                    role: activeRoleBadge.textContent,
                    provider,
                    model,
                    latencyMs,
                    imageName,
                    query,
                    response: text
                });
            } else {
                providerTag.textContent = 'Error';
                const error = res.error || 'Failed to generate response';
                setResponse(error, 'error-text');
                recordFailure(error, { role: activeRoleBadge.textContent, query, imageName: imageName || 'none' });
            }
        }
    });

    window.api.onRoleChanged(({ role, name }) => {
        activeRoleBadge.textContent = name;
        setResponse(`${name} enabled. ${role === 'mle' ? 'Focus: ML systems and MLOps.' : role === 'backend' ? 'Focus: reliability and scalable systems.' : 'Focus: data, experimentation, and impact.'}`, 'success-text');
    });
});
