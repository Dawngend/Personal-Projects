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
});

test('router rejects an empty query before reaching a provider', async () => {
    const router = new SmartAIRouter();
    await assert.rejects(router.routeQuery('   '), /Enter an interview question/);
});

test('personalized prompts include the selected role framing', () => {
    const prompt = buildPersonalizedPrompt('Build reliable data systems.', null, 'backend');
    assert.match(prompt, /backend design, data integrity, observability, scalability, and security/i);
    assert.match(prompt, /Build reliable data systems/);
});
