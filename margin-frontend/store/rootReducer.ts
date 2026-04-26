import { combineReducers } from '@reduxjs/toolkit';
import authReducer from './slices/authSlice';
import creditReducer from './slices/creditSlice';
import humanizerReducer from './slices/humanizerSlice';

const rootReducer = combineReducers({
  auth: authReducer,
  credit: creditReducer,
  humanizer: humanizerReducer,
});

export type RootState = ReturnType<typeof rootReducer>;
export default rootReducer;
