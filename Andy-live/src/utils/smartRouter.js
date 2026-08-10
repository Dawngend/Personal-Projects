const { Groq } = require('groq-sdk');
const { GoogleGenAI } = require('@google/genai');

class SmartAIRouter {
    constructor() {
        this.groq = process.env.GROQ_API_KEY ? new Groq({ apiKey: process.env.GROQ_API_KEY }) : null;
        this.gemini = process.env.GEMINI_API_KEY ? new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY }) : null;
        this.systemPrompt = '';
    }

    setSystemPrompt(prompt) {
        this.systemPrompt = prompt;
    }

    getConfiguredProviders() {
        return {
            groq: Boolean(this.groq),
            gemini: Boolean(this.gemini),
        };
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
        if (typeof userQuery !== 'string' || !userQuery.trim()) {
            throw new Error('Enter an interview question before sending.');
        }

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
                    result = await this.callGroq('openai/gpt-oss-120b', sysPrompt, userQuery, 400);
                    break;

                case 'HARD_CODING':
                    result = await this.callGroq('openai/gpt-oss-120b', sysPrompt, userQuery, 500);
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
            console.error(`[SmartRouter] Provider error for ${intent}:`, err.message);
            result = await this.tryFallback(intent, sysPrompt, userQuery, err);
        }

        result.latencyMs = Date.now() - startTime;
        return result;
    }

    async tryFallback(failedIntent, sysPrompt, userQuery, originalError) {
        const fallbackCalls = [];
        if (failedIntent !== 'FAST_TALKING_POINTS' && failedIntent !== 'GROQ' && this.groq) {
            fallbackCalls.push(() => this.callGroq('openai/gpt-oss-20b', sysPrompt, userQuery, 150));
        }
        if (failedIntent !== 'SEARCH_REQUIRED' && failedIntent !== 'GEMINI_SEARCH' && this.gemini) {
            fallbackCalls.push(() => this.callGeminiFlash('gemini-3.6-flash', sysPrompt, userQuery, 200, false));
        }
        for (const fallback of fallbackCalls) {
            try {
                const result = await fallback();
                result.provider += ' (fallback)';
                return result;
            } catch (fallbackError) {
                console.error('[SmartRouter] Fallback provider error:', fallbackError.message);
            }
        }

        return {
            provider: 'Configuration required',
            model: 'No available provider',
            text: `Unable to reach an AI provider. Configure the required API key in .env, then restart Andy Live. (${originalError.message})`
        };
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
            text: res.choices?.[0]?.message?.content || 'The provider returned an empty response.'
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
            text: response.text || 'The provider returned an empty response.'
        };
    }

}

module.exports = SmartAIRouter;
