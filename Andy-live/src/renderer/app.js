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

    saveSetupBtn.addEventListener('click', async () => {
        const jdText = jdInput.value.trim();
        const selectedResume = resumeSelect.value;
        if (!jdText) {
            alert('Please paste a Job Description.');
            return;
        }

        const res = await window.api.setupSession(jdText, selectedResume);
        if (res.success) {
            setupModal.classList.add('hidden');
            responseOutput.innerHTML = `<p style="color: #10b981;">✅ AI Teleprompter Initialized with Job Description & Target Resume STAR Matrix!</p>`;
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

            responseOutput.innerHTML = `<p class="placeholder-text">⚡ Routing query to 2026 AI Engine...</p>`;
            providerTag.textContent = 'Thinking...';
            latencyTag.textContent = '';

            const res = await window.api.sendQuery(query, forcedProvider);

            if (res.success && res.result) {
                const { provider, model, text, latencyMs } = res.result;
                providerTag.textContent = `${provider} (${model})`;
                latencyTag.textContent = `${latencyMs}ms`;
                responseOutput.innerText = text;
            } else {
                providerTag.textContent = 'Error';
                responseOutput.innerHTML = `<p style="color: #ef4444;">❌ ${res.error || 'Failed to generate response'}</p>`;
            }
        }
    });

    window.api.onRoleChanged(({ role, name }) => {
        activeRoleBadge.textContent = name;
    });
});
