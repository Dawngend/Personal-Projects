document.addEventListener('DOMContentLoaded', async () => {
    const setupModal = document.getElementById('setupModal');
    const setupBtn = document.getElementById('setupBtn');
    const saveSetupBtn = document.getElementById('saveSetupBtn');
    const toggleStealthBtn = document.getElementById('toggleStealthBtn');
    const jdInput = document.getElementById('jdInput');
    const resumeSelect = document.getElementById('resumeSelect');
    const queryInput = document.getElementById('queryInput');
    const forcedProviderSelect = document.getElementById('forcedProviderSelect');
    const responseOutput = document.getElementById('responseOutput');
    const providerTag = document.getElementById('providerTag');
    const latencyTag = document.getElementById('latencyTag');
    const activeRoleBadge = document.getElementById('activeRoleBadge');

    let isStealth = false;

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

    const setResponse = (message, className = '') => {
        responseOutput.replaceChildren();
        const paragraph = document.createElement('p');
        paragraph.textContent = message;
        if (className) paragraph.className = className;
        responseOutput.appendChild(paragraph);
    };

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

    toggleStealthBtn.addEventListener('click', () => {
        isStealth = !isStealth;
        window.api.setIgnoreMouseEvents(isStealth);
        toggleStealthBtn.textContent = isStealth ? '👁️ Stealth ON' : '👁️ Click-Through';
        toggleStealthBtn.style.borderColor = isStealth ? '#10b981' : 'rgba(255, 255, 255, 0.15)';
    });

    queryInput.addEventListener('keydown', async (e) => {
        if (e.key === 'Enter') {
            const query = queryInput.value.trim();
            if (!query) return;

            queryInput.value = '';
            const forcedProvider = forcedProviderSelect.value;

            setResponse('Routing query to the AI engine…', 'placeholder-text');
            providerTag.textContent = 'Thinking...';
            latencyTag.textContent = '';

            const res = await window.api.sendQuery(query, forcedProvider);

            if (res.success && res.result) {
                const { provider, model, text, latencyMs } = res.result;
                providerTag.textContent = `${provider} (${model})`;
                latencyTag.textContent = `${latencyMs}ms`;
                responseOutput.textContent = text;
            } else {
                providerTag.textContent = 'Error';
                setResponse(res.error || 'Failed to generate response', 'error-text');
            }
        }
    });

    window.api.onRoleChanged(({ role, name }) => {
        activeRoleBadge.textContent = name;
        setResponse(`${name} enabled. ${role === 'mle' ? 'Focus: ML systems and MLOps.' : role === 'backend' ? 'Focus: reliability and scalable systems.' : 'Focus: data, experimentation, and impact.'}`, 'success-text');
    });
});
