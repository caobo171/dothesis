import { combineReducers } from '@reduxjs/toolkit';
import authReducer from './slices/authSlice';
import creditReducer from './slices/creditSlice';

const rootReducer = combineReducers({
  auth: authReducer,
  credit: creditReducer,
});

export type RootState = ReturnType<typeof rootReducer>;
export default rootReducer;
