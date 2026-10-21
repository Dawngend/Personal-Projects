const items = ['structure', 'terms', 'correctness', 'calculations'];

const summaryApi = {
    summarize(results) {
        const scored = results.filter(result => result && result.scores);
        if (scored.length === 0) return { averages: {}, habits: [] };

        const averages = {};
        for (const item of items) {
            averages[item] = scored.reduce((sum, result) => sum + result.scores[item], 0) / scored.length;
        }
        const habits = items.filter(item => averages[item] < 4)
            .sort((a, b) => averages[a] - averages[b])
            .slice(0, 3);
        return { averages, habits };
    },

    toMarkdown(summary) {
        const lines = ['# Practice Summary'];
        for (const item of items) {
            if (item in summary.averages) lines.push(`- ${item}: ${summary.averages[item].toFixed(1)}/5`);
        }
        lines.push('', `Habits to work on: ${summary.habits.length ? summary.habits.join(', ') : 'none'}`);
        return lines.join('\n');
    }
};

if (typeof module !== 'undefined') module.exports = summaryApi; else window.PracticeSummary = summaryApi;
