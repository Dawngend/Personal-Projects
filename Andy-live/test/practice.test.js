const test = require('node:test');
const assert = require('node:assert/strict');

const questions = require('../src/practice/questions');
const { pickQuestion } = require('../src/practice/select');
const { buildFeedbackMessages, parseFeedback } = require('../src/practice/feedback');
const { transcribeAnswer, requestFeedback } = require('../src/practice/service');
const { summarize, toMarkdown } = require('../src/practice/summary');
const { isAllowedRequest, isAllowedCheck } = require('../src/practice/permissions');
const { stopRecording } = require('../src/practice/recorder');

const goodFeedback = {
    scores: { structure: 4, terms: 3, correctness: 5, calculations: 2 },
    strengths: ['Clear example'],
    fixes: ['Show the calculation'],
    tighterAnswer: 'A shorter answer.',
    followUp: 'How would you verify that?'
};

test('question bank has 12 questions per topic, unique IDs, and valid roles', () => {
    assert.equal(questions.length, 48);
    assert.equal(new Set(questions.map(question => question.id)).size, 48);
    for (const topic of ['stats', 'ml', 'llm', 'behavioral']) {
        assert.equal(questions.filter(question => question.topic === topic).length, 12);
    }
    for (const question of questions) {
        assert.ok(question.id);
        assert.ok(question.text);
        assert.ok(Array.isArray(question.roles) && question.roles.length > 0);
        assert.ok(question.roles.every(role => ['mle', 'ds', 'backend'].includes(role)));
    }
    assert.ok(questions.some(question => question.roles.length > 1));
});

test('question selection filters by role and topic, avoids repeats, and restarts', () => {
    const bank = [
        { id: 'a', topic: 'stats', roles: ['ds'] },
        { id: 'b', topic: 'stats', roles: ['ds', 'mle'] },
        { id: 'c', topic: 'ml', roles: ['ds'] }
    ];
    assert.equal(pickQuestion(bank, 'ds', 'stats', []).id, 'a');
    assert.equal(pickQuestion(bank, 'ds', 'stats', ['a']).id, 'b');
    assert.equal(pickQuestion(bank, 'ds', 'stats', ['a', 'b']).id, 'a');
    assert.equal(pickQuestion(bank, 'mle', 'stats', []).id, 'b');
    assert.equal(pickQuestion(bank, 'backend', 'stats', []), null);
    assert.equal(pickQuestion(bank, 'ds', 'stats', [], list => list[1]).id, 'b');
});

test('feedback prompt contains the interview context and JSON rubric', () => {
    const messages = buildFeedbackMessages({ role: 'ds', topic: 'stats', question: 'Why?', answer: 'Because.' });
    assert.equal(messages.length, 2);
    assert.equal(messages[0].role, 'system');
    assert.match(messages[0].content, /JSON only/);
    assert.match(messages[0].content, /calculations/);
    assert.match(messages[1].content, /Role: ds\nTopic: stats\nQuestion: Why\?\nAnswer: Because\./);
});

test('parseFeedback accepts good JSON and rejects each required invalid shape', () => {
    assert.deepEqual(parseFeedback(JSON.stringify(goodFeedback)), goodFeedback);
    assert.match(parseFeedback('{').error, /JSON/);
    assert.ok(parseFeedback(JSON.stringify({ ...goodFeedback, scores: { ...goodFeedback.scores, terms: 6 } })).error);
    assert.ok(parseFeedback(JSON.stringify({ ...goodFeedback, scores: { ...goodFeedback.scores, terms: 0 } })).error);
    assert.ok(parseFeedback(JSON.stringify({ ...goodFeedback, strengths: undefined })).error);
    assert.ok(parseFeedback(JSON.stringify({ ...goodFeedback, fixes: undefined })).error);
    assert.ok(parseFeedback(JSON.stringify({ ...goodFeedback, followUp: undefined })).error);
});

test('requestFeedback sends the specified Groq request and parses feedback', async () => {
    let request;
    const groq = { chat: { completions: { create: async value => {
        request = value;
        return { choices: [{ message: { content: JSON.stringify(goodFeedback) } }] };
    } } } };
    assert.deepEqual(await requestFeedback({ groq, role: 'ds', topic: 'stats', question: 'Q', answer: 'A' }),
        { success: true, feedback: goodFeedback });
    assert.equal(request.model, 'openai/gpt-oss-20b');
    assert.deepEqual(request.response_format, { type: 'json_object' });
    assert.equal(request.max_tokens, 700);
    assert.equal(request.messages[1].content, 'Role: ds\nTopic: stats\nQuestion: Q\nAnswer: A');
    assert.equal((await requestFeedback({ groq: null })).success, false);
    assert.equal((await requestFeedback({ groq: { chat: { completions: { create: async () => {
        throw new Error('offline');
    } } } } })).error, 'offline');
    const invalidGroq = {
        chat: { completions: { create: async () => ({ choices: [{ message: { content: '{' } }] }) } }
    };
    assert.equal((await requestFeedback({ groq: invalidGroq })).success, false);
});

test('transcribeAnswer enforces 5 MB and passes the exact file and model', async () => {
    let fileCall;
    let transcriptionCall;
    const toFile = async (...args) => {
        fileCall = args;
        return { upload: true };
    };
    const groq = { audio: { transcriptions: { create: async request => {
        transcriptionCall = request;
        return { text: 'spoken answer' };
    } } } };
    const audio = new Uint8Array([1, 2, 3]);
    assert.deepEqual(await transcribeAnswer({ groq, toFile, audio }), { success: true, text: 'spoken answer' });
    assert.deepEqual(fileCall, [Buffer.from(audio), 'answer.webm', { type: 'audio/webm' }]);
    assert.deepEqual(transcriptionCall, { file: { upload: true }, model: 'whisper-large-v3-turbo' });
    assert.deepEqual(await transcribeAnswer({ groq, toFile, audio: audio.buffer }),
        { success: true, text: 'spoken answer' });

    let called = false;
    const oversized = await transcribeAnswer({
        groq,
        toFile: async () => { called = true; },
        audio: new ArrayBuffer(5 * 1024 * 1024 + 1)
    });
    assert.equal(oversized.success, false);
    assert.match(oversized.error, /5 MB/);
    assert.equal(called, false);
    assert.equal((await transcribeAnswer({ groq: null, toFile, audio })).success, false);
    assert.equal((await transcribeAnswer({ groq, toFile: async () => { throw new Error('upload failed'); }, audio })).error,
        'upload failed');
    assert.equal((await transcribeAnswer({ groq: { audio: { transcriptions: { create: async () => {
        throw new Error('transcription failed');
    } } } }, toFile, audio })).error, 'transcription failed');
});

test('summary skips failed feedback, sorts tied habits by rubric order, and uses only below-4 scores', () => {
    const second = { ...goodFeedback, scores: { structure: 2, terms: 3, correctness: 5, calculations: 4 } };
    const summary = summarize([goodFeedback, null, second]);
    assert.deepEqual(summary.averages, { structure: 3, terms: 3, correctness: 5, calculations: 3 });
    assert.deepEqual(summary.habits, ['structure', 'terms', 'calculations']);
    assert.match(toMarkdown(summary), /structure: 3\.0\/5/);
    assert.match(toMarkdown(summary), /Habits to work on: structure, terms, calculations/);

    assert.deepEqual(summarize([]), { averages: {}, habits: [] });
    assert.deepEqual(summarize([null]), { averages: {}, habits: [] });
    assert.match(toMarkdown(summarize([])), /Habits to work on: none/);
    const high = summarize([{ scores: { structure: 4, terms: 4, correctness: 5, calculations: 5 } }]);
    assert.deepEqual(high.habits, []);
});

test('permission rules allow audio capture only in each Electron callback shape', () => {
    assert.equal(isAllowedRequest('media', { mediaTypes: ['audio'] }), true);
    assert.equal(isAllowedRequest('media', { mediaTypes: ['audio', 'video'] }), false);
    assert.equal(isAllowedRequest('media', { mediaTypes: ['video'] }), false);
    assert.equal(isAllowedRequest('display-capture', { mediaTypes: ['audio'] }), false);
    assert.equal(isAllowedRequest('media', {}), false);
    assert.equal(isAllowedCheck('media', { mediaType: 'audio' }), true);
    assert.equal(isAllowedCheck('media', { mediaType: 'video' }), false);
    assert.equal(isAllowedCheck('display-capture', { mediaType: 'audio' }), false);
    assert.equal(isAllowedCheck('media', {}), false);
});

test('stopRecording stops the recorder and every stream track, clears state, and is safe twice', () => {
    let recorderStops = 0;
    let trackStops = 0;
    const state = {
        recorder: { state: 'recording', stop() { recorderStops++; } },
        stream: { getTracks: () => [
            { stop() { trackStops++; } },
            { stop() { trackStops++; } }
        ] }
    };
    const micStates = [];
    const ui = { setMicLive: value => micStates.push(value) };
    stopRecording(state, ui);
    stopRecording(state, ui);
    assert.equal(recorderStops, 1);
    assert.equal(trackStops, 2);
    assert.equal(state.recorder, null);
    assert.equal(state.stream, null);
    assert.deepEqual(micStates, [false, false]);
});
