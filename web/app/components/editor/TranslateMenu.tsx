"use client";

import { useState } from "react";


const _LANGUAGES: { code: string; label: string }[] = [
  { code: "en", label: "English" },
  { code: "vi", label: "Vietnamese" },
  { code: "fr", label: "French" },
  { code: "es", label: "Spanish" },
  { code: "de", label: "German" },
  { code: "zh", label: "Chinese" },
  { code: "ja", label: "Japanese" },
  { code: "ko", label: "Korean" },
];


type Props = {
  defaultLang: string;
  onConfirm: (targetLang: string) => void;
  onClose: () => void;
};


// Small popover with target-language picker. Default value is whatever the
// project's m1_topic.language is.
export function TranslateMenu({ defaultLang, onConfirm, onClose }: Props) {
  const [lang, setLang] = useState(defaultLang || "en");

  return (
    <div role="dialog" aria-label="Translate selection" className="bg-white border border-purple-300 rounded-md shadow-lg p-3 w-56 z-50">
      <label className="text-xs text-gray-600 mb-1 block">Target language</label>
      <select value={lang} onChange={e => setLang(e.target.value)}
              className="w-full text-sm px-2 py-1 border border-gray-200 rounded mb-2">
        {_LANGUAGES.map(l => <option key={l.code} value={l.code}>{l.label}</option>)}
      </select>
      <div className="flex justify-end gap-2">
        <button type="button" onClick={onClose}
                className="text-xs px-3 py-1 text-gray-600 hover:bg-gray-100 rounded">
          Cancel
        </button>
        <button type="button" onClick={() => { onConfirm(lang); onClose(); }}
                className="text-xs px-3 py-1 bg-purple-600 text-white rounded hover:bg-purple-700">
          Translate
        </button>
      </div>
    </div>
  );
}
