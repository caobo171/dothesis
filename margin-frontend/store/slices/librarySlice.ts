import { createSlice, PayloadAction } from '@reduxjs/toolkit';

interface LibraryState {
  selectedFolderId: string | null;
}

const initialState: LibraryState = {
  selectedFolderId: null,
};

const librarySlice = createSlice({
  name: 'library',
  initialState,
  reducers: {
    selectFolder(state, action: PayloadAction<string | null>) {
      state.selectedFolderId = action.payload;
    },
  },
});

export const { selectFolder } = librarySlice.actions;
export default librarySlice.reducer;
