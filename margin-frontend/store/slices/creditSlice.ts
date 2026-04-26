import { createSlice, PayloadAction } from '@reduxjs/toolkit';

interface CreditState {
  balance: number;
}

const initialState: CreditState = {
  balance: 0,
};

const creditSlice = createSlice({
  name: 'credit',
  initialState,
  reducers: {
    setBalance(state, action: PayloadAction<number>) {
      state.balance = action.payload;
    },
  },
});

export const { setBalance } = creditSlice.actions;
export default creditSlice.reducer;
