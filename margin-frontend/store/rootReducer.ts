import { combineReducers } from '@reduxjs/toolkit';
import authReducer from './slices/authSlice';
import creditReducer from './slices/creditSlice';
import humanizerReducer from './slices/humanizerSlice';
import autoCiteReducer from './slices/autoCiteSlice';
import libraryReducer from './slices/librarySlice';

const rootReducer = combineReducers({
  auth: authReducer,
  credit: creditReducer,
  humanizer: humanizerReducer,
  autoCite: autoCiteReducer,
  library: libraryReducer,
});

export type RootState = ReturnType<typeof rootReducer>;
export default rootReducer;
