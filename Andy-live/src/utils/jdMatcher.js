const fs = require('fs');
const path = require('path');

// Andy Brain vault is the canonical, actively-maintained source. D:\Resumes
// mirrors it but also still holds ~17 retired per-company tailored resumes
// that were explicitly marked Rejected once the strategy consolidated to two
// masters (2026-08-13) - listing that whole directory risked auto-selecting
// a stale/rejected variant for personalization.
const VAULT_CAREER_DIR = 'D:/Andy_Brain/01_Career_and_Resume';
const PERSONAL_CONTEXT_PATH = path.join(VAULT_CAREER_DIR, 'Dawn_Personal_Context.md');

const MASTER_RESUMES = [
    { fileName: 'Dawn_Andrei_Pamesa_Resume.md', displayName: 'General (AI/ML/Data Science)' },
    { fileName: 'Dawn_Andrei_Pamesa_Data_Engineering_Backend_Resume.md', displayName: 'Data Engineering / Backend' }
];

/**
 * Lists the two current active master resumes from the Andy Brain vault.
 * Deliberately not a directory listing - see MASTER_RESUMES comment above.
 */
function getAvailableResumes() {
    return MASTER_RESUMES
        .map(r => ({ ...r, filePath: path.join(VAULT_CAREER_DIR, r.fileName) }))
        .filter(r => fs.existsSync(r.filePath));
}

/**
 * Picks between the two active masters based on Job Description keywords.
 * Backend/data-engineering signal -> the backend master; anything else
 * (including plain ML/AI/Data Science signal) -> the general master, which
 * is the deliberate default per the resume strategy.
 */
function autoDetectResume(jdText) {
    const resumes = getAvailableResumes();
    if (resumes.length === 0) return null;

    const jdLower = jdText.toLowerCase();
    const backendSignal = /\b(backend|back-end|database|data engineer|data engineering|infrastructure|devops|distributed systems|architect)\b/;
    if (backendSignal.test(jdLower)) {
        const backend = resumes.find(r => r.fileName.includes('Data_Engineering_Backend'));
        if (backend) return backend;
    }

    return resumes.find(r => r.fileName === 'Dawn_Andrei_Pamesa_Resume.md') || resumes[0];
}

/**
 * Builds the personalized system prompt integrating the vault's canonical
 * Dawn_Personal_Context.md + Selected Target Resume + Job Description.
 */
function buildPersonalizedPrompt(jdText, selectedResumePath = null, role = 'default') {
    let globalSkill = '';
    if (fs.existsSync(PERSONAL_CONTEXT_PATH)) {
        globalSkill = fs.readFileSync(PERSONAL_CONTEXT_PATH, 'utf8');
    }

    let targetResumeContent = '';
    let chosenResumeFile = selectedResumePath;

    if (!chosenResumeFile || !fs.existsSync(chosenResumeFile)) {
        const detected = autoDetectResume(jdText);
        if (detected) chosenResumeFile = detected.filePath;
    }

    if (chosenResumeFile && fs.existsSync(chosenResumeFile)) {
        targetResumeContent = fs.readFileSync(chosenResumeFile, 'utf8');
    }

    const roleInstruction = {
        mle: 'Prioritize ML systems, model evaluation, MLOps, and pragmatic AI trade-offs.',
        backend: 'Prioritize reliable backend design, data integrity, observability, scalability, and security.',
        ds: 'Prioritize data quality, experimentation, statistical reasoning, and measurable business impact.',
        default: 'Adapt to the interviewer’s domain while remaining technically precise.'
    }[role] || 'Adapt to the interviewer’s domain while remaining technically precise.';

    return `
You are Dawn Andrei Pamesa's discreet real-time interview & technical teleprompter assistant.
Respond ONLY in 1-3 bullet points or clean Markdown code blocks that Dawn can directly speak or use live.

--- DAWN'S GLOBAL SKILL & PROJECT PROFILE ---
${globalSkill}

--- ACTIVE TARGET ROLE RESUME ---
${targetResumeContent}

--- TARGET JOB DESCRIPTION (REQUIREMENTS & CONTEXT) ---
${jdText}

--- TELEPROMPTER RESPONSE RULES ---
1. Frame answers using Dawn's real verified metrics & project names (ForgeAI, BANGON, Sophy, Andy's Hub, Dzuka Agri, FlyRank AI).
2. Directly solve or answer the interviewer's question in 1–3 short spoken bullet points.
3. Be direct, authoritative, and tailored strictly to the Job Description requirements.
4. Active interview mode: ${roleInstruction}
`.trim();
}

module.exports = {
    getAvailableResumes,
    autoDetectResume,
    buildPersonalizedPrompt
};
