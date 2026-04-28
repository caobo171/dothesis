import { createSlice, PayloadAction } from '@reduxjs/toolkit';

interface HumanizerState {
  tone: string;
  strength: number;
  lengthMode: string;
  inputText: string;
  inputSource: 'paste' | 'upload' | 'url';
  outputText: string;
  changes: Array<{ original: string; replacement: string; reason: string }>;
  aiScoreIn: number;
  aiScoreOut: number;
  isProcessing: boolean;
  currentJobId: string | null;
  currentStage: string;
  // Highest pipeline step the backend has reported in this run.
  // -1 = not started; 0 = analyzing; 1 = detecting; 2 = rewriting.
  // Drives the three-step progress panel during processing.
  maxStepReached: number;
  // Output rendering mode toggled in the OutputPane header.
  // 'plain'  — show the rewritten text only.
  // 'inline' — show inline diff: strikethrough originals + boxed replacements.
  viewMode: 'plain' | 'inline';
}

const initialState: HumanizerState = {
  tone: 'academic',
  strength: 50,
  lengthMode: 'match',
  inputText: '',
  inputSource: 'paste',
  outputText: '',
  changes: [],
  aiScoreIn: 0,
  aiScoreOut: 0,
  isProcessing: false,
  currentJobId: null,
  currentStage: '',
  maxStepReached: -1,
  // Default to inline diff so users immediately see what changed
  viewMode: 'inline',
};

// Map a backend stage label to one of our three user-facing steps.
// Returns the step index, or -1 if the stage doesn't correspond to a step.
function stageToStep(stage: string): number {
  const s = stage.toLowerCase();
  if (s.includes('preprocess') || s.includes('analyz') || s.includes('ai_score')) return 0;
  if (s.includes('critiqu') || s.includes('detect')) return 1;
  if (s.includes('rewrit') || s.includes('scor')) return 2;
  return -1;
}

const humanizerSlice = createSlice({
  name: 'humanizer',
  initialState,
  reducers: {
    setTone(state, action: PayloadAction<string>) {
      state.tone = action.payload;
    },
    setStrength(state, action: PayloadAction<number>) {
      state.strength = action.payload;
    },
    setLengthMode(state, action: PayloadAction<string>) {
      state.lengthMode = action.payload;
    },
    setInputText(state, action: PayloadAction<string>) {
      state.inputText = action.payload;
    },
    setInputSource(state, action: PayloadAction<'paste' | 'upload' | 'url'>) {
      state.inputSource = action.payload;
    },
    setProcessing(state, action: PayloadAction<boolean>) {
      state.isProcessing = action.payload;
    },
    setResult(
      state,
      action: PayloadAction<{
        outputText: string;
        changes: Array<{ original: string; replacement: string; reason: string }>;
        aiScoreIn: number;
        aiScoreOut: number;
        jobId: string;
      }>
    ) {
      state.outputText = action.payload.outputText;
      state.changes = action.payload.changes;
      state.aiScoreIn = action.payload.aiScoreIn;
      state.aiScoreOut = action.payload.aiScoreOut;
      state.currentJobId = action.payload.jobId;
      state.isProcessing = false;
      // Auto-switch to inline view when changes are available
      if (action.payload.changes.length > 0) {
        state.viewMode = 'inline';
      }
    },
    setCurrentStage(state, action: PayloadAction<string>) {
      state.currentStage = action.payload;
      // Promote the step indicator monotonically — once we've passed
      // 'detecting', a stray 'analyzing' event shouldn't pull it back.
      const step = stageToStep(action.payload);
      if (step > state.maxStepReached) state.maxStepReached = step;
    },
    resetOutput(state) {
      state.outputText = '';
      state.changes = [];
      state.aiScoreIn = 0;
      state.aiScoreOut = 0;
      state.currentJobId = null;
      state.currentStage = '';
      state.maxStepReached = -1;
    },
    setViewMode(state, action: PayloadAction<'plain' | 'inline'>) {
      state.viewMode = action.payload;
    },
  },
});

export const {
  setTone,
  setStrength,
  setLengthMode,
  setInputText,
  setInputSource,
  setProcessing,
  setResult,
  resetOutput,
  setCurrentStage,
  setViewMode,
} = humanizerSlice.actions;
export default humanizerSlice.reducer;
