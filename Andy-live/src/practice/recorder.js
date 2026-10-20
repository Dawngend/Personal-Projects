const api = {
    stopRecording(state, ui) {
        if (state.recorder && state.recorder.state === 'recording') state.recorder.stop();
        if (state.stream) {
            for (const track of state.stream.getTracks()) track.stop();
        }
        state.stream = null;
        state.recorder = null;
        ui.setMicLive(false);
    }
};

if (typeof module !== 'undefined') module.exports = api; else window.PracticeRecorder = api;
