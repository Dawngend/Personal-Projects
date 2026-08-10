const test = require('node:test');
const assert = require('node:assert/strict');

const SmartAIRouter = require('../src/utils/smartRouter');
const { buildPersonalizedPrompt } = require('../src/utils/jdMatcher');

test('router classifies interview intents into the prescribed routes', () => {
    const router = new SmartAIRouter();

    assert.equal(router.classifyIntent('Explain the trade-off between queues and streams'), 'DEEP_REASONING');
    assert.equal(router.classifyIntent('Design a highly available microservices platform'), 'SYSTEM_DESIGN');
    assert.equal(router.classifyIntent('Implement an LRU cache in Python'), 'HARD_CODING');
    assert.equal(router.classifyIntent('What is the company’s latest funding?'), 'SEARCH_REQUIRED');
    assert.equal(router.classifyIntent('Tell me about yourself'), 'FAST_TALKING_POINTS');
    assert.equal(router.classifyIntent('What does this screenshot show?', true), 'VISION');
});

test('router rejects an empty query before reaching a provider', async () => {
    const router = new SmartAIRouter();
    await assert.rejects(router.routeQuery('   '), /Enter an interview question/);
});

test('vision failures do not silently fall back to a text-only answer', async () => {
    const router = new SmartAIRouter();
    const result = await router.tryFallback('VISION', '', '', new Error('invalid image data'));
    assert.equal(result.provider, 'Vision unavailable');
    assert.match(result.text, /could not be analyzed/i);
});

test('fresh-information requests always disclose that live web access is unavailable', async () => {
    const router = new SmartAIRouter();
    router.callGroq = async (model) => ({ provider: 'Groq Cloud', model, text: 'Durable guidance.' });

    const result = await router.routeQuery('What are the latest market trends?');

    assert.equal(result.model, 'openai/gpt-oss-20b');
    assert.match(result.text, /do not have live web access/i);
});

test('personalized prompts include the selected role framing', () => {
    const prompt = buildPersonalizedPrompt('Build reliable data systems.', null, 'backend');
    assert.match(prompt, /backend design, data integrity, observability, scalability, and security/i);
    assert.match(prompt, /Build reliable data systems/);
});
