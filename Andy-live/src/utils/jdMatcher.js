const fs = require('fs');
const path = require('path');

const RESUMES_DIR = 'D:/Resumes';

/**
 * Lists all available markdown resumes in D:\Resumes
 */
function getAvailableResumes() {
    try {
        if (!fs.existsSync(RESUMES_DIR)) return [];
        const files = fs.readdirSync(RESUMES_DIR);
        return files
            .filter(f => f.endsWith('.md') && f !== 'SKILL.md' && f !== 'README.md')
            .map(f => ({
                fileName: f,
                filePath: path.join(RESUMES_DIR, f),
                displayName: f.replace('Dawn_Andrei_Pamesa_', '').replace('_Resume.md', '').replace(/_/g, ' ')
            }));
    } catch (err) {
        console.error('[jdMatcher] Error listing resumes:', err);
        return [];
    }
}

/**
 * Scans resumes to auto-detect the best matching resume based on Job Description text keywords
 */
function autoDetectResume(jdText) {
    const resumes = getAvailableResumes();
    if (resumes.length === 0) return null;

    const jdLower = jdText.toLowerCase();
    let bestMatch = resumes[0];
    let maxScore = -1;

    for (const res of resumes) {
        let score = 0;
        const nameLower = res.fileName.toLowerCase();
        
        if (jdLower.includes('machine learning') || jdLower.includes('mle') || jdLower.includes('llm')) {
            if (nameLower.includes('mle') || nameLower.includes('python_llm')) score += 5;
        }
        if (jdLower.includes('data scientist') || jdLower.includes('fraud') || jdLower.includes('kobold')) {
            if (nameLower.includes('data_scientist') || nameLower.includes('fraud')) score += 5;
        }
        if (jdLower.includes('backend') || jdLower.includes('architect') || jdLower.includes('database')) {
            if (nameLower.includes('dba') || nameLower.includes('developer')) score += 5;
        }
        if (jdLower.includes('bvnk') || jdLower.includes('qa')) {
            if (nameLower.includes('bvnk') || nameLower.includes('qa')) score += 5;
        }

        if (score > maxScore) {
            maxScore = score;
            bestMatch = res;
        }
    }

    return bestMatch;
}

/**
 * Builds the personalized system prompt integrating Global SKILL.md + Selected Target Resume + Job Description
 */
function buildPersonalizedPrompt(jdText, selectedResumePath = null) {
    let globalSkill = '';
    const skillPath = path.join(RESUMES_DIR, 'SKILL.md');
    if (fs.existsSync(skillPath)) {
        globalSkill = fs.readFileSync(skillPath, 'utf8');
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
`.trim();
}

module.exports = {
    getAvailableResumes,
    autoDetectResume,
    buildPersonalizedPrompt
};
