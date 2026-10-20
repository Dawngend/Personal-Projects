const { buildFeedbackMessages, parseFeedback } = require('./feedback');

async function transcribeAnswer({ groq, toFile, audio }) {
    try {
        if (!groq) throw new Error('Groq client is unavailable');
        if (audio.byteLength > 5 * 1024 * 1024) throw new Error('Audio exceeds 5 MB');
        const file = await toFile(Buffer.from(audio), 'answer.webm', { type: 'audio/webm' });
        const result = await groq.audio.transcriptions.create({ file, model: 'whisper-large-v3-turbo' });
        return { success: true, text: result.text };
    } catch (error) {
        return { success: false, error: error.message };
    }
}

async function requestFeedback({ groq, role, topic, question, answer }) {
    try {
        if (!groq) throw new Error('Groq client is unavailable');
        const result = await groq.chat.completions.create({
            model: 'openai/gpt-oss-20b',
            messages: buildFeedbackMessages({ role, topic, question, answer }),
            response_format: { type: 'json_object' },
            max_tokens: 700
        });
        const feedback = parseFeedback(result.choices[0].message.content);
        if (feedback.error) throw new Error(feedback.error);
        return { success: true, feedback };
    } catch (error) {
        return { success: false, error: error.message };
    }
}

module.exports = { transcribeAnswer, requestFeedback };
