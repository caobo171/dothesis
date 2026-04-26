'use client';

import { useDispatch, useSelector } from 'react-redux';
import { RootState } from '@/store/rootReducer';
import { selectFolder } from '@/store/slices/librarySlice';
import { useFolders } from '@/hooks/library';
import { clsx } from 'clsx';
import { useState } from 'react';
import { toast } from 'react-toastify';
import Fetch from '@/lib/core/fetch/Fetch';
import { Code } from '@/lib/core/Constants';

export function FolderSidebar() {
  const dispatch = useDispatch();
  const { selectedFolderId } = useSelector((s: RootState) => s.library);
  const { folders, mutate } = useFolders();
  const [newFolderName, setNewFolderName] = useState('');
  const [creating, setCreating] = useState(false);

  const handleCreate = async () => {
    if (!newFolderName.trim()) return;
    setCreating(true);
    const res = await Fetch.postWithAccessToken<any>('/api/library/folders/create', {
      name: newFolderName,
    });
    if (res.data.code === Code.Success) {
      mutate();
      setNewFolderName('');
    } else {
      toast.error(res.data.message);
    }
    setCreating(false);
  };

  return (
    <div className="w-56 border-r border-rule bg-white flex flex-col">
      <div className="p-3 border-b border-rule">
        <h3 className="text-xs font-semibold text-ink-soft">Folders</h3>
      </div>

      <div className="flex-1 overflow-auto p-2 space-y-0.5">
        <button
          onClick={() => dispatch(selectFolder(null))}
          className={clsx(
            'w-full text-left px-3 py-2 rounded-lg text-sm transition',
            selectedFolderId === null ? 'bg-bg-blue text-primary font-medium' : 'text-ink-soft hover:bg-bg-soft'
          )}
        >
          All citations
        </button>

        {folders.map((folder: any) => (
          <button
            key={folder._id}
            onClick={() => dispatch(selectFolder(folder._id))}
            className={clsx(
              'w-full text-left px-3 py-2 rounded-lg text-sm transition flex items-center gap-2',
              selectedFolderId === folder._id
                ? 'bg-bg-blue text-primary font-medium'
                : 'text-ink-soft hover:bg-bg-soft'
            )}
          >
            <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ backgroundColor: folder.color }} />
            <span className="truncate flex-1">{folder.name}</span>
            <span className="text-xs text-ink-muted">{folder.citationCount || 0}</span>
          </button>
        ))}
      </div>

      <div className="p-3 border-t border-rule">
        <div className="flex gap-1">
          <input
            type="text"
            value={newFolderName}
            onChange={(e) => setNewFolderName(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleCreate()}
            placeholder="New folder..."
            className="flex-1 px-2 py-1.5 rounded border border-rule text-xs outline-none focus:border-primary"
          />
          <button
            onClick={handleCreate}
            disabled={creating || !newFolderName.trim()}
            className="px-2 py-1.5 bg-primary text-white rounded text-xs disabled:opacity-50"
          >
            +
          </button>
        </div>
      </div>
    </div>
  );
}
