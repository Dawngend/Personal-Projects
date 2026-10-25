const test = require('node:test');
const assert = require('node:assert/strict');
const { EventEmitter } = require('node:events');

const { buildClaudePrompt, readVoiceText, answerWithClaude, makeClaudeRunner } = require('../src/claude');

test('answerWithClaude returns the provider, model, text and latency', async () => {
    const reply = await answerWithClaude({ run: async () => 'I built it.', sessionPrompt: 'JD and resume', question: 'Tell me about yourself.', model: 'sonnet' });
    assert.equal(reply.success, true);
    assert.equal(reply.result.provider, 'claude');
    assert.equal(reply.result.model, 'sonnet');
    assert.equal(reply.result.text, 'I built it.');
    assert.equal(typeof reply.result.latencyMs, 'number');
});

test('answerWithClaude turns a thrown error into a failure with its message', async () => {
    const run = async () => { throw new Error('Claude took longer than 90 seconds. Try again.'); };
    const reply = await answerWithClaude({ run, sessionPrompt: 'JD', question: 'Why us?' });
    assert.deepEqual(reply, { success: false, error: 'Claude took longer than 90 seconds. Try again.' });
});

test('answerWithClaude refuses an empty question and a missing Setup JD without calling Claude', async () => {
    const run = async () => { throw new Error('should not be called'); };
    const empty = await answerWithClaude({ run, sessionPrompt: 'JD', question: '   ' });
    const noSetup = await answerWithClaude({ run, sessionPrompt: '', question: 'Why us?' });
    assert.equal(empty.success, false);
    assert.match(noSetup.error, /Setup JD/);
});

test('the prompt holds the session prompt, voice text, answer rules and the question', () => {
    const prompt = buildClaudePrompt({ sessionPrompt: 'RESUME AND JD', voiceText: 'Declarative opener.', question: 'What is leakage?' });
    for (const part of ['RESUME AND JD', 'How Dawn talks and writes', 'Declarative opener.', 'first person', 'Never invent a number', 'What is leakage?']) {
        assert.ok(prompt.includes(part), part);
    }
});

test('a very long session prompt still reaches run as one string', async () => {
    let seen = '';
    await answerWithClaude({ run: async prompt => { seen = prompt; return 'ok'; }, sessionPrompt: 'x'.repeat(60000), question: 'Why us?' });
    assert.ok(seen.length > 60000);
});

test('readVoiceText returns an empty string when the file is missing', () => {
    assert.equal(readVoiceText(() => { throw new Error('missing'); }), '');
    assert.equal(readVoiceText(() => 'her voice'), 'her voice');
});

function fakeSpawn({ stdout = '', code = 0, error = null }) {
    const calls = [];
    const spawnFn = (command, args, options) => {
        const child = new EventEmitter();
        child.stdout = new EventEmitter();
        child.stderr = new EventEmitter();
        child.stdin = Object.assign(new EventEmitter(), { end: input => { calls.push({ command, args, options, input }); } });
        child.kill = () => {};
        setImmediate(() => {
            if (error) return child.emit('error', error);
            child.stdout.emit('data', stdout);
            child.emit('close', code);
        });
        return child;
    };
    return { spawnFn, calls };
}

test('the runner sends the prompt on stdin, drops API keys and uses no shell', async () => {
    process.env.ANTHROPIC_API_KEY = 'sk-test';
    const { spawnFn, calls } = fakeSpawn({ stdout: ' the answer \n' });
    const text = await makeClaudeRunner({ spawnFn })('the prompt');
    delete process.env.ANTHROPIC_API_KEY;
    assert.equal(text, 'the answer');
    assert.equal(calls[0].input, 'the prompt');
    assert.equal(calls[0].options.shell, false);
    assert.equal(calls[0].options.env.ANTHROPIC_API_KEY, undefined);
    assert.ok(calls[0].args.includes('-p'));
});

test('the runner explains a missing claude program and a failed run', async () => {
    const missing = fakeSpawn({ error: Object.assign(new Error('spawn claude ENOENT'), { code: 'ENOENT' }) });
    await assert.rejects(makeClaudeRunner({ spawnFn: missing.spawnFn })('p'), /CLAUDE_CLI_PATH/);

    const failed = fakeSpawn({ code: 1 });
    await assert.rejects(makeClaudeRunner({ spawnFn: failed.spawnFn })('p'), /exited with code 1/);
});
