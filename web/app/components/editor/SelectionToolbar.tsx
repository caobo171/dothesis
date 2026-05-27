"use client";


type Props = {
  onParaphrase: () => void;
  onTranslate: () => void;
  onCite: () => void;
};


// Pure presentation. The parent (ChapterEditor) mounts this inside TipTap's
// BubbleMenu, which handles visibility based on selection state.
export function SelectionToolbar({ onParaphrase, onTranslate, onCite }: Props) {
  return (
    <div className="inline-flex items-center gap-1 bg-gray-900 text-white text-xs rounded-md shadow-lg p-1">
      <button type="button" onClick={onParaphrase} className="px-2 py-1 hover:bg-gray-700 rounded">
        ✎ Paraphrase
      </button>
      <span className="text-gray-500">·</span>
      <button type="button" onClick={onTranslate} className="px-2 py-1 hover:bg-gray-700 rounded">
        🌐 Translate
      </button>
      <span className="text-gray-500">·</span>
      <button type="button" onClick={onCite} className="px-2 py-1 hover:bg-gray-700 rounded">
        📎 Cite
      </button>
    </div>
  );
}
