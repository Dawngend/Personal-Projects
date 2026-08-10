const { Groq } = require('groq-sdk');

class SmartAIRouter {
    constructor() {
        this.groq = process.env.GROQ_API_KEY ? new Groq({ apiKey: process.env.GROQ_API_KEY }) : null;
        this.systemPrompt = '';
    }

    setSystemPrompt(prompt) {
        this.systemPrompt = prompt;
    }

    getConfiguredProviders() {
        return {
            groq: Boolean(this.groq),
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

    async routeQuery(userQuery, customPrompt = null, imageInput = null, forcedProvider = null) {
        if (typeof userQuery !== 'string' || !userQuery.trim()) {
            throw new Error('Enter an interview question before sending.');
        }

        const sysPrompt = customPrompt || this.systemPrompt || 'Answer in 1-3 bullet points.';
        const intent = forcedProvider ? forcedProvider.toUpperCase() : this.classifyIntent(userQuery, Boolean(imageInput));
        
        const startTime = Date.now();
        let result = { provider: '', model: '', text: '', latencyMs: 0 };

        try {
            switch (intent) {
                case 'FAST_TALKING_POINTS':
                case 'GROQ':
                    result = await this.callGroq('openai/gpt-oss-20b', sysPrompt, userQuery, 150, null, 'low');
                    break;

                case 'SEARCH_REQUIRED': {
                    result = await this.callGroq(
                        'openai/gpt-oss-20b',
                        `${sysPrompt}\n\nDo not claim live or current web information. State this limit briefly, then give durable guidance based on the user's question.`,
                        userQuery,
                        150,
                        null,
                        'low'
                    );
                    result.text = `Note: I do not have live web access, so I cannot verify current information.\n\n${result.text}`;
                    break;
                }

                case 'SYSTEM_DESIGN':
                    result = await this.callGroq('openai/gpt-oss-20b', sysPrompt, userQuery, 150, null, 'low');
                    break;

                case 'HARD_CODING':
                    result = await this.callGroq(
                        'qwen/qwen3.6-27b',
                        `${sysPrompt}\n\nFast Interview Mode: give the algorithm, complexity, and only a short code skeleton or critical lines. Keep the answer speakable and avoid extended derivations.`,
                        userQuery,
                        150
                    );
                    break;

                case 'DEEP_REASONING':
                    result = await this.callGroq('openai/gpt-oss-20b', sysPrompt, userQuery, 150, null, 'low');
                    break;

                case 'VISION':
                    result = await this.callGroq('qwen/qwen3.6-27b', sysPrompt, userQuery, 300, imageInput);
                    break;

                default:
                    result = await this.callGroq('openai/gpt-oss-20b', sysPrompt, userQuery, 150, null, 'low');
            }
        } catch (err) {
            console.error(`[SmartRouter] Provider error for ${intent}:`, err.message);
            result = await this.tryFallback(intent, sysPrompt, userQuery, err);
        }

        result.latencyMs = Date.now() - startTime;
        return result;
    }

    async tryFallback(failedIntent, sysPrompt, userQuery, originalError) {
        if (failedIntent === 'VISION') {
            return {
                provider: 'Vision unavailable',
                model: 'qwen/qwen3.6-27b',
                text: `The screenshot could not be analyzed. Choose a valid PNG, JPG, JPEG, or WEBP image under 4 MB and try again. (${originalError.message})`
            };
        }

        const fallbackCalls = [];
        if (failedIntent !== 'FAST_TALKING_POINTS' && failedIntent !== 'GROQ' && this.groq) {
            fallbackCalls.push(() => this.callGroq('openai/gpt-oss-20b', sysPrompt, userQuery, 150, null, 'low'));
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

    async callGroq(modelName, sysPrompt, userQuery, maxTokens, imageInput = null, reasoningEffort = null) {
        if (!this.groq) throw new Error('GROQ_API_KEY is not configured in .env');
        const userContent = imageInput
            ? [
                { type: 'text', text: userQuery },
                {
                    type: 'image_url',
                    image_url: {
                        url: `data:${imageInput.mimeType};base64,${imageInput.data.toString('base64')}`
                    }
                }
            ]
            : userQuery;
        const request = {
            model: modelName,
            messages: [
                { role: 'system', content: sysPrompt },
                { role: 'user', content: userContent }
            ],
            max_tokens: maxTokens
        };
        if (reasoningEffort || modelName === 'qwen/qwen3.6-27b') request.reasoning_effort = reasoningEffort || 'none';

        const res = await this.groq.chat.completions.create(request);
        return {
            provider: 'Groq Cloud',
            model: modelName,
            text: res.choices?.[0]?.message?.content || 'The provider returned an empty response.'
        };
    }

    async createDebugPrompt(errorMessage, context = {}) {
        const redact = value => String(value || '')
            .replace(/\b(?:gsk|sk|AIza)[A-Za-z0-9_-]{12,}\b/g, '[REDACTED]')
            .slice(0, 4000);
        const contextText = Object.entries(context)
            .map(([key, value]) => `${key}: ${redact(value)}`)
            .join('\n');
        return this.callGroq(
            'openai/gpt-oss-20b',
            'Create a concise Markdown debugging prompt for Codex or Claude Code. Include observed behavior, relevant context, reproduction steps, expected behavior, and a request for the smallest safe fix. Output only the ready-to-paste prompt. Never include secrets or suggest bypassing safeguards.',
            `Observed error or failure:\n${redact(errorMessage)}\n\nContext:\n${contextText || 'No additional context provided.'}`,
            350,
            null,
            'low'
        );
    }

    async createDeepHandoffPrompt(question, context = {}) {
        const redact = value => String(value || '')
            .replace(/\b(?:gsk|sk|AIza)[A-Za-z0-9_-]{12,}\b/g, '[REDACTED]')
            .slice(0, 6000);
        const contextText = Object.entries(context)
            .map(([key, value]) => `${key}: ${redact(value)}`)
            .join('\n');
        return this.callGroq(
            'openai/gpt-oss-20b',
            'Create a complete Markdown handoff prompt for Codex or Claude Code to deeply solve a technical interview question. Include the exact question, supplied context, assumptions to validate, desired rigorous output, trade-offs, and a request for a concise spoken summary. Output only the ready-to-paste prompt. Never include secrets or suggest bypassing safeguards.',
            `Technical interview question:\n${redact(question)}\n\nContext:\n${contextText || 'No additional context provided.'}`,
            350,
            null,
            'low'
        );
    }

}

module.exports = SmartAIRouter;
