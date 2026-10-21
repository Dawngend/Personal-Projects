document.addEventListener('DOMContentLoaded', () => {
    const TARGET_SECONDS = 120;

    const practiceBtn = document.getElementById('practiceBtn');
    const liveView = document.getElementById('liveView');
    const practiceView = document.getElementById('practiceView');
    const setupModal = document.getElementById('setupModal');
    const skipSetupBtn = document.getElementById('skipSetupBtn');
    const roleSelect = document.getElementById('practiceRole');
    const topicSelect = document.getElementById('practiceTopic');
    const nextBtn = document.getElementById('practiceNextBtn');
    const timerLabel = document.getElementById('practiceTimer');
    const questionText = document.getElementById('practiceQuestion');
    const speakBtn = document.getElementById('practiceSpeakBtn');
    const recordBtn = document.getElementById('practiceRecordBtn');
    const micLive = document.getElementById('practiceMicLive');
    const answerBox = document.getElementById('practiceAnswer');
    const message = document.getElementById('practiceMessage');
    const feedbackBtn = document.getElementById('practiceFeedbackBtn');
    const feedbackView = document.getElementById('practiceFeedback');
    const followUpBtn = document.getElementById('practiceFollowUpBtn');
    const summaryView = document.getElementById('practiceSummary');
    const copyBtn = document.getElementById('practiceCopyBtn');

    // The role is Practice's own choice; the global hotkeys do not change it.
    const state = {
        role: 'mle',
        topic: 'stats',
        current: null,
        usedIds: [],
        results: [],
        lastFeedback: null,
        recorder: null,
        stream: null,
        holding: false,
        timerId: null,
        startedAt: 0
    };

    const showMessage = (text, isError) => {
        message.textContent = text;
        message.classList.toggle('error-text', Boolean(isError));
        message.classList.toggle('hidden', !text);
    };

    const addLine = (parent, tag, text, className) => {
        const element = document.createElement(tag);
        element.textContent = text;
        if (className) element.className = className;
        parent.appendChild(element);
    };

    const addList = (parent, title, items) => {
        addLine(parent, 'h3', title);
        const list = document.createElement('ul');
        items.forEach(item => addLine(list, 'li', String(item)));
        parent.appendChild(list);
    };

    const formatTime = seconds => `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;

    const showTimer = seconds => {
        timerLabel.textContent = `${formatTime(seconds)} / ${formatTime(TARGET_SECONDS)}`;
        timerLabel.classList.toggle('over-target', seconds > TARGET_SECONDS);
    };

    const startTimer = () => {
        if (state.timerId) return;
        state.startedAt = Date.now();
        state.timerId = setInterval(() => showTimer(Math.floor((Date.now() - state.startedAt) / 1000)), 500);
    };

    const stopTimer = () => {
        clearInterval(state.timerId);
        state.timerId = null;
    };

    const resetTimer = () => {
        stopTimer();
        showTimer(0);
    };

    const recorderUi = {
        setMicLive(on) {
            micLive.classList.toggle('hidden', !on);
            recordBtn.classList.toggle('recording', on);
            speakBtn.disabled = on || !state.current;
        }
    };

    const stopMic = () => {
        state.holding = false;
        PracticeRecorder.stopRecording(state, recorderUi);
    };

    const showQuestion = question => {
        stopMic();
        speechSynthesis.cancel();
        state.current = question;
        state.lastFeedback = null;
        answerBox.value = '';
        feedbackView.classList.add('hidden');
        followUpBtn.classList.add('hidden');
        showMessage('', false);
        resetTimer();
        questionText.textContent = question ? question.text : 'No question for this role and topic yet. Pick another role or topic.';
        for (const button of [speakBtn, recordBtn, feedbackBtn]) button.disabled = !question;
        answerBox.disabled = !question;
    };

    const nextQuestion = () => {
        const pick = list => list[Math.floor(Math.random() * list.length)];
        const question = PracticeSelect.pickQuestion(PracticeQuestions, state.role, state.topic, state.usedIds, pick);
        if (question) state.usedIds.push(question.id);
        showQuestion(question);
    };

    const renderSummary = () => {
        summaryView.replaceChildren();
        copyBtn.disabled = state.results.length === 0;
        summaryView.classList.toggle('hidden', state.results.length === 0);
        if (state.results.length === 0) return;

        const summary = PracticeSummary.summarize(state.results);
        addLine(summaryView, 'h3', `Session summary (${state.results.length} answered)`);
        Object.entries(summary.averages).forEach(([item, average]) => addLine(summaryView, 'p', `${item}: ${average.toFixed(1)}/5`));
        addLine(summaryView, 'p', `Habits to work on: ${summary.habits.length ? summary.habits.join(', ') : 'none'}`);
    };

    const renderFeedback = feedback => {
        feedbackView.replaceChildren();
        const scores = Object.entries(feedback.scores).map(([item, score]) => `${item} ${score}/5`).join(' | ');
        addLine(feedbackView, 'p', scores, 'practice-scores');
        addList(feedbackView, 'Strengths', feedback.strengths);
        addList(feedbackView, 'Fixes', feedback.fixes);
        if (feedback.tighterAnswer) {
            addLine(feedbackView, 'h3', 'Tighter answer');
            addLine(feedbackView, 'p', feedback.tighterAnswer);
        }
        feedbackView.classList.remove('hidden');
        followUpBtn.classList.remove('hidden');
    };

    const getFeedback = async () => {
        const answer = answerBox.value.trim();
        if (!answer) {
            showMessage('Type or record an answer first.', true);
            return;
        }
        stopTimer();
        feedbackBtn.disabled = true;
        showMessage('Getting feedback...', false);
        const result = await window.api.practice.feedback({
            role: state.role,
            topic: state.topic,
            question: state.current.text,
            answer
        });
        feedbackBtn.disabled = false;
        if (!result.success) {
            showMessage(result.error, true);
            return;
        }
        showMessage('', false);
        state.lastFeedback = result.feedback;
        state.results.push(result.feedback);
        renderFeedback(result.feedback);
        renderSummary();
    };

    const transcribe = async blob => {
        showMessage('Transcribing...', false);
        const result = await window.api.practice.transcribe(await blob.arrayBuffer());
        if (!result.success) {
            showMessage(result.error, true);
            return;
        }
        showMessage('', false);
        const typed = answerBox.value.trim();
        answerBox.value = typed ? `${typed} ${result.text.trim()}` : result.text.trim();
    };

    const startRecording = async () => {
        let stream;
        try {
            stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        } catch (error) {
            state.holding = false;
            showMessage(`Microphone unavailable: ${error.message}`, true);
            return;
        }
        // The button may have been released while the browser was asking for the mic.
        if (!state.holding || state.recorder) {
            stream.getTracks().forEach(track => track.stop());
            return;
        }

        const chunks = [];
        const recorder = new MediaRecorder(stream, { mimeType: 'audio/webm;codecs=opus' });
        recorder.ondataavailable = event => chunks.push(event.data);
        recorder.onstop = () => {
            if (chunks.length) transcribe(new Blob(chunks, { type: 'audio/webm' }));
        };
        state.stream = stream;
        state.recorder = recorder;
        recorder.start();
        recorderUi.setMicLive(true);
        startTimer();
    };

    recordBtn.addEventListener('pointerdown', event => {
        if (state.holding || !state.current) return;
        state.holding = true;
        recordBtn.setPointerCapture(event.pointerId);
        speechSynthesis.cancel();
        showMessage('', false);
        startRecording();
    });
    recordBtn.addEventListener('pointerup', stopMic);
    recordBtn.addEventListener('pointercancel', stopMic);
    window.addEventListener('blur', stopMic);
    document.addEventListener('visibilitychange', () => {
        if (document.hidden) stopMic();
    });

    speakBtn.addEventListener('click', () => {
        if (!state.current) return;
        speechSynthesis.cancel();
        speechSynthesis.speak(new SpeechSynthesisUtterance(state.current.text));
    });

    answerBox.addEventListener('input', startTimer);
    feedbackBtn.addEventListener('click', getFeedback);
    nextBtn.addEventListener('click', nextQuestion);
    followUpBtn.addEventListener('click', () => {
        const followUp = state.lastFeedback.followUp;
        showQuestion({ id: 'follow-up', text: followUp });
    });

    roleSelect.addEventListener('change', () => {
        state.role = roleSelect.value;
        nextQuestion();
    });
    topicSelect.addEventListener('change', () => {
        state.topic = topicSelect.value;
        nextQuestion();
    });

    copyBtn.addEventListener('click', async () => {
        if (state.results.length === 0) return;
        await window.api.copyText(PracticeSummary.toMarkdown(PracticeSummary.summarize(state.results)));
        copyBtn.textContent = 'Copied';
        setTimeout(() => { copyBtn.textContent = 'Copy summary as Markdown'; }, 1500);
    });

    practiceBtn.addEventListener('click', () => {
        const opening = practiceView.classList.contains('hidden');
        if (!opening) stopMic();
        speechSynthesis.cancel();
        practiceView.classList.toggle('hidden', !opening);
        liveView.classList.toggle('hidden', opening);
        practiceBtn.setAttribute('aria-pressed', String(opening));
        if (opening && !state.current) nextQuestion();
    });

    // The setup modal covers the header on launch, so Practice needs a way past it.
    skipSetupBtn.addEventListener('click', () => setupModal.classList.add('hidden'));
});
