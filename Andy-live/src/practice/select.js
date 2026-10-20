const api = {
    pickQuestion(bank, role, topic, usedIds, pick) {
        const matches = bank.filter(question => question.topic === topic && question.roles.includes(role));
        if (matches.length === 0) return null;

        const unused = matches.filter(question => !usedIds.includes(question.id));
        const candidates = unused.length ? unused : matches;
        return pick ? pick(candidates) : candidates[0];
    }
};

if (typeof module !== 'undefined') module.exports = api; else window.PracticeSelect = api;
