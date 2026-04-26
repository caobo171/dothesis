import { createSlice, PayloadAction } from '@reduxjs/toolkit';
import { RawUser } from '@/store/types';

interface AuthState {
  profile: RawUser | null;
}

const initialState: AuthState = {
  profile: null,
};

const authSlice = createSlice({
  name: 'auth',
  initialState,
  reducers: {
    loadProfile(state, action: PayloadAction<RawUser | null>) {
      state.profile = action.payload;
    },
  },
});

export const { loadProfile } = authSlice.actions;
export default authSlice.reducer;
