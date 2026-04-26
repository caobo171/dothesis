import { createSlice, PayloadAction } from '@reduxjs/toolkit';
import { Claim, CiteSource } from '@/store/types';

interface AutoCiteState {
  jobId: string | null;
  status: string;
  style: string;
  claims: Claim[];
  sources: CiteSource[];
  inputText: string;
}

const initialState: AutoCiteState = {
  jobId: null,
  status: 'idle',
  style: 'apa',
  claims: [],
  sources: [],
  inputText: '',
};

const autoCiteSlice = createSlice({
  name: 'autoCite',
  initialState,
  reducers: {
    setStyle(state, action: PayloadAction<string>) {
      state.style = action.payload;
    },
    setCiteInput(state, action: PayloadAction<string>) {
      state.inputText = action.payload;
    },
    startJob(state, action: PayloadAction<string>) {
      state.jobId = action.payload;
      state.status = 'pending';
      state.claims = [];
      state.sources = [];
    },
    updateStatus(state, action: PayloadAction<string>) {
      state.status = action.payload;
    },
    setResults(state, action: PayloadAction<{ claims: Claim[]; sources: CiteSource[] }>) {
      state.claims = action.payload.claims;
      state.sources = action.payload.sources;
      state.status = 'done';
    },
    acceptClaim(state, action: PayloadAction<{ claimIndex: number; sourceId: string }>) {
      const claim = state.claims[action.payload.claimIndex];
      if (claim) {
        claim.sourceId = action.payload.sourceId;
        claim.status = 'cited';
      }
    },
    removeClaim(state, action: PayloadAction<number>) {
      const claim = state.claims[action.payload];
      if (claim) {
        claim.sourceId = null;
        claim.status = 'pending';
      }
    },
    resetCite(state) {
      Object.assign(state, initialState);
    },
  },
});

export const {
  setStyle,
  setCiteInput,
  startJob,
  updateStatus,
  setResults,
  acceptClaim,
  removeClaim,
  resetCite,
} = autoCiteSlice.actions;
export default autoCiteSlice.reducer;
