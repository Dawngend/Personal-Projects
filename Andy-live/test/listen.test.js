const test = require('node:test');
const assert = require('node:assert/strict');

const { listenAnswer } = require('../src/listen');

test('a failed transcription returns the error and never asks Claude', async () => {
    let asked = false;
    const reply = await listenAnswer({
        audio: new ArrayBuffer(8),
        transcribe: async () => ({ success: false, error: 'Groq client is unavailable' }),
        answer: async () => { asked = true; return { success: true, result: {} }; }
    });
    assert.deepEqual(reply, { success: false, error: 'Groq client is unavailable' });
    assert.equal(asked, false);
});

test('silence is reported and never asks Claude', async () => {
    let asked = false;
    const reply = await listenAnswer({
        audio: new ArrayBuffer(8),
        transcribe: async () => ({ success: true, text: '   ' }),
        answer: async () => { asked = true; return { success: true, result: {} }; }
    });
    assert.equal(reply.success, false);
    assert.match(reply.error, /did not hear/);
    assert.equal(asked, false);
});

test('a heard question is answered and returned with its text', async () => {
    const result = { provider: 'claude', model: 'sonnet', text: 'My answer.', latencyMs: 5 };
    let heardByClaude = '';
    const reply = await listenAnswer({
        audio: new ArrayBuffer(8),
        transcribe: async () => ({ success: true, text: ' Tell me about a project. ' }),
        answer: async question => { heardByClaude = question; return { success: true, result }; }
    });
    assert.equal(heardByClaude, 'Tell me about a project.');
    assert.deepEqual(reply, { success: true, question: 'Tell me about a project.', result });
});
