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
};

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
    },
    setCurrentStage(state, action: PayloadAction<string>) {
      state.currentStage = action.payload;
    },
    resetOutput(state) {
      state.outputText = '';
      state.changes = [];
      state.aiScoreIn = 0;
      state.aiScoreOut = 0;
      state.currentJobId = null;
      state.currentStage = '';
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
} = humanizerSlice.actions;
export default humanizerSlice.reducer;
