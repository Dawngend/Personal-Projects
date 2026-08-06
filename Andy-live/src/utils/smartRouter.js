const { Groq } = require('groq-sdk');
const { GoogleGenAI } = require('@google/genai');
const Anthropic = require('@anthropic-ai/sdk');
const OpenAI = require('openai');

class SmartAIRouter {
    constructor() {
        this.groq = process.env.GROQ_API_KEY ? new Groq({ apiKey: process.env.GROQ_API_KEY }) : null;
        this.gemini = process.env.GEMINI_API_KEY ? new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY }) : null;
        this.anthropic = process.env.ANTHROPIC_API_KEY ? new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY }) : null;
        this.openai = process.env.OPENAI_API_KEY ? new OpenAI({ apiKey: process.env.OPENAI_API_KEY }) : null;
        this.systemPrompt = '';
    }

    setSystemPrompt(prompt) {
        this.systemPrompt = prompt;
    }

    /**
     * Intent Classifier (~5ms heuristic execution time)
     */
    classifyIntent(text, hasImage = false) {
        if (hasImage) return 'VISION';

        const codeKeywords = /\b(code|function|algorithm|leetcode|binary tree|lru cache|sql|c\+\+|python|complexity|implement|dp|graph|refactor|thread|lock|async)\b/i;
        const systemDesignKeywords = /\b(system design|microservices|architecture|kafka|database schema|high availability|qps|sharding|load balancer|distributed|scaling)\b/i;
        const searchKeywords = /\b(recent news|company|funding|series|ceo|market trends|latest version|2026|acquired|investor|competitor)\b/i;
        const deepReasoningKeywords = /\b(explain why|step by step|trade-off|compare|evaluate|proof|analyze)\b/i;

        if (codeKeywords.test(text)) return 'HARD_CODING';
        if (systemDesignKeywords.test(text)) return 'SYSTEM_DESIGN';
        if (searchKeywords.test(text)) return 'SEARCH_REQUIRED';
        if (deepReasoningKeywords.test(text)) return 'DEEP_REASONING';

        return 'FAST_TALKING_POINTS'; // Default to Groq gpt-oss-20b for maximum speed
    }

    async routeQuery(userQuery, customPrompt = null, imageBuffer = null, forcedProvider = null) {
        const sysPrompt = customPrompt || this.systemPrompt || 'Answer in 1-3 bullet points.';
        const intent = forcedProvider ? forcedProvider.toUpperCase() : this.classifyIntent(userQuery, !!imageBuffer);
        
        const startTime = Date.now();
        let result = { provider: '', model: '', text: '', latencyMs: 0 };

        try {
            switch (intent) {
                case 'FAST_TALKING_POINTS':
                case 'GROQ':
                    result = await this.callGroq('openai/gpt-oss-20b', sysPrompt, userQuery, 150);
                    break;

                case 'SEARCH_REQUIRED':
                case 'GEMINI_SEARCH':
                    result = await this.callGeminiFlash('gemini-3.6-flash', sysPrompt, userQuery, 200, true);
                    break;

                case 'SYSTEM_DESIGN':
                case 'CLAUDE':
                    result = await this.callClaude('claude-sonnet-5', sysPrompt, userQuery, 400);
                    break;

                case 'HARD_CODING':
                case 'OPENAI':
                    result = await this.callOpenAI('gpt-5.6-soul', sysPrompt, userQuery, 500);
                    break;

                case 'DEEP_REASONING':
                    result = await this.callGroq('openai/gpt-oss-120b', sysPrompt, userQuery, 300);
                    break;

                case 'VISION':
                    result = await this.callGroq('qwen/qwen3.6-27b', sysPrompt, userQuery, 300);
                    break;

                default:
                    result = await this.callGroq('openai/gpt-oss-20b', sysPrompt, userQuery, 150);
            }
        } catch (err) {
            console.error(`[SmartRouter] Provider error for ${intent}, falling back:`, err.message);
            if (this.groq) {
                result = await this.callGroq('openai/gpt-oss-20b', sysPrompt, userQuery, 150);
            } else if (this.gemini) {
                result = await this.callGeminiFlash('gemini-3.6-flash', sysPrompt, userQuery, 200, false);
            } else {
                result = { provider: 'System Error', model: 'None', text: `Error processing query: ${err.message}`, latencyMs: 0 };
            }
        }

        result.latencyMs = Date.now() - startTime;
        return result;
    }

    async callGroq(modelName, sysPrompt, userQuery, maxTokens) {
        if (!this.groq) throw new Error('GROQ_API_KEY is not configured in .env');
        const res = await this.groq.chat.completions.create({
            model: modelName,
            messages: [
                { role: 'system', content: sysPrompt },
                { role: 'user', content: userQuery }
            ],
            max_tokens: maxTokens
        });
        return {
            provider: 'Groq Cloud',
            model: modelName,
            text: res.choices[0].message.content
        };
    }

    async callGeminiFlash(modelName, sysPrompt, userQuery, maxTokens, enableSearch = false) {
        if (!this.gemini) throw new Error('GEMINI_API_KEY is not configured in .env');
        const config = { maxOutputTokens: maxTokens };
        if (enableSearch) config.tools = [{ googleSearch: {} }];

        const response = await this.gemini.models.generateContent({
            model: modelName,
            contents: `${sysPrompt}\n\nUser Question: ${userQuery}`,
            config
        });
        return {
            provider: 'Google Gemini',
            model: modelName + (enableSearch ? ' (Search)' : ''),
            text: response.text
        };
    }

    async callClaude(modelName, sysPrompt, userQuery, maxTokens) {
        if (!this.anthropic) throw new Error('ANTHROPIC_API_KEY is not configured in .env');
        const response = await this.anthropic.messages.create({
            model: modelName,
            max_tokens: maxTokens,
            system: sysPrompt,
            messages: [{ role: 'user', content: userQuery }]
        });
        return {
            provider: 'Anthropic Claude',
            model: modelName,
            text: response.content[0].text
        };
    }

    async callOpenAI(modelName, sysPrompt, userQuery, maxTokens) {
        if (!this.openai) throw new Error('OPENAI_API_KEY is not configured in .env');
        const response = await this.openai.chat.completions.create({
            model: modelName,
            messages: [
                { role: 'system', content: sysPrompt },
                { role: 'user', content: userQuery }
            ],
            max_tokens: maxTokens
        });
        return {
            provider: 'OpenAI',
            model: modelName,
            text: response.choices[0].message.content
        };
    }
}

module.exports = SmartAIRouter;
