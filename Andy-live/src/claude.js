const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawn } = require('child_process');

const VOICE_PATH = 'D:/Andy_Brain/01_Career_and_Resume/Dawn_Writing_Voice.md';
const TIMEOUT_MS = 90000;
const MAX_QUESTION_CHARS = 12000;

// These rules replace the bullet-point rule in the Setup JD prompt.
const RULES = `--- ANSWER RULES (these override any bullet-point rule above) ---
Answer as Dawn, in the first person, in plain spoken sentences. Hard limit: four sentences and 80 words. Stop after the fourth sentence, even when the question has several parts.
Open with the answer in one declarative sentence and no warm-up.
Narrate steps as "First, then, then, finally". Never number the steps.
Put concrete detail in short inline parentheses.
Use "Therefore" or "so" instead of "Consequently". No em dashes.
Use only facts that appear in her resume or the job description. Never invent a number or a project.
If the question is unclear, say so in one line.`;

function buildClaudePrompt({ sessionPrompt, voiceText, question }) {
    const parts = [sessionPrompt];
    if (voiceText) parts.push(`--- How Dawn talks and writes ---\n${voiceText}`);
    parts.push(RULES, `--- Interviewer question ---\n${question}`);
    return parts.filter(Boolean).join('\n\n');
}

function readVoiceText(readFile = fs.readFileSync) {
    try {
        return String(readFile(VOICE_PATH, 'utf8'));
    } catch (error) {
        return '';
    }
}

async function answerWithClaude({ run, sessionPrompt, voiceText, question, model = 'sonnet' }) {
    const asked = String(question || '').trim().slice(0, MAX_QUESTION_CHARS);
    if (!asked) return { success: false, error: 'Enter an interview question before sending.' };
    if (!sessionPrompt) return { success: false, error: 'Run Setup JD first, so I know your resume and the job.' };

    const startedAt = Date.now();
    try {
        const text = await run(buildClaudePrompt({ sessionPrompt, voiceText, question: asked }));
        return { success: true, result: { provider: 'claude', model, text, latencyMs: Date.now() - startedAt } };
    } catch (error) {
        return { success: false, error: error.message };
    }
}

// The whole prompt goes in on stdin: Windows command lines are too short for a long job description.
function makeClaudeRunner({ model = 'sonnet', spawnFn = spawn } = {}) {
    return prompt => new Promise((resolve, reject) => {
        const workDir = fs.mkdtempSync(path.join(os.tmpdir(), 'andy-live-'));
        // Remove API keys so Claude Code uses the login on this PC, not a billed key.
        const env = { ...process.env };
        delete env.ANTHROPIC_API_KEY;
        delete env.ANTHROPIC_AUTH_TOKEN;

        const args = ['-p', '--model', model, '--tools', '', '--disable-slash-commands', '--no-session-persistence', '--setting-sources', 'project'];
        const child = spawnFn(process.env.CLAUDE_CLI_PATH || 'claude', args, { cwd: workDir, env, shell: false });

        let stdout = '';
        let stderr = '';
        let finished = false;
        const finish = (settle, value) => {
            if (finished) return;
            finished = true;
            clearTimeout(timer);
            fs.rmSync(workDir, { recursive: true, force: true });
            settle(value);
        };
        const timer = setTimeout(() => {
            child.kill();
            finish(reject, new Error('Claude took longer than 90 seconds. Try again.'));
        }, TIMEOUT_MS);

        child.stdout.on('data', chunk => { stdout += chunk; });
        child.stderr.on('data', chunk => { stderr += chunk; });
        child.on('error', error => {
            const notFound = error.code === 'ENOENT' || error.code === 'EINVAL';
            finish(reject, new Error(notFound ? 'Claude Code was not found. Install it or set CLAUDE_CLI_PATH to claude.exe.' : error.message));
        });
        child.on('close', code => {
            if (code === 0) finish(resolve, stdout.trim());
            else finish(reject, new Error(stderr.trim().split('\n')[0] || `Claude exited with code ${code}.`));
        });
        child.stdin.on('error', () => {});
        child.stdin.end(prompt);
    });
}

module.exports = { buildClaudePrompt, readVoiceText, answerWithClaude, makeClaudeRunner };
