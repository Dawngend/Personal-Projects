function buildFeedbackMessages({ role, topic, question, answer }) {
    return [
        {
            role: 'system',
            content: 'You are an interviewer-coach for mock interview practice. Evaluate structure, precise terms, factual correctness, and explicit calculations. Return JSON only with this shape: { "scores": { "structure": 1, "terms": 1, "correctness": 1, "calculations": 1 }, "strengths": [], "fixes": [], "tighterAnswer": "", "followUp": "" }. Each score must be an integer from 1 to 5. Give one follow-up question in followUp.'
        },
        {
            role: 'user',
            content: `Role: ${role}\nTopic: ${topic}\nQuestion: ${question}\nAnswer: ${answer}`
        }
    ];
}

function parseFeedback(text) {
    let feedback;
    try {
        feedback = JSON.parse(text);
    } catch (error) {
        return { error: 'Invalid feedback JSON' };
    }

    if (!feedback || typeof feedback !== 'object' || !feedback.scores ||
        ['structure', 'terms', 'correctness', 'calculations'].some(key =>
            !Number.isInteger(feedback.scores[key]) || feedback.scores[key] < 1 || feedback.scores[key] > 5)) {
        return { error: 'Feedback scores must be integers from 1 to 5' };
    }
    if (!Array.isArray(feedback.strengths) || !Array.isArray(feedback.fixes)) {
        return { error: 'Feedback strengths and fixes must be arrays' };
    }
    if (typeof feedback.followUp !== 'string' || !feedback.followUp.trim()) {
        return { error: 'Feedback must include a follow-up question' };
    }
    return feedback;
}

module.exports = { buildFeedbackMessages, parseFeedback };
