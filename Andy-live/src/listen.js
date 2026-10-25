// Turns the sound of a mock interviewer's question into a suggested answer.
async function listenAnswer({ audio, transcribe, answer }) {
    const heard = await transcribe(audio);
    if (!heard.success) return { success: false, error: heard.error };

    const question = String(heard.text || '').trim();
    if (!question) {
        return { success: false, error: 'I did not hear a question. Check that the mock app plays through the speakers, then try again.' };
    }

    const reply = await answer(question);
    if (!reply.success) return reply;
    return { success: true, question, result: reply.result };
}

module.exports = { listenAnswer };
