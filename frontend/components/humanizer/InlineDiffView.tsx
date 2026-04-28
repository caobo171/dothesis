'use client';

import React from 'react';

// Renders the rewritten document with the original text shown inline as
// strikethrough and the replacement text wrapped in a highlighted box.
//
// Reconstruction algorithm:
//   We walk through the original input from left to right. For each entry in
//   the changes array (assumed to be in input order), we find the first
//   occurrence of `change.original` at or after our cursor. Text between the
//   cursor and the match emits as plain. The match emits as a diff pair.
//   Anything left after the loop trails as plain.
//
// If a change can't be located in the source (e.g. the model rewrote into a
// different shape than its diff suggested), we fall back to showing it as a
// pure insertion at the current cursor.

type Change = { original: string; replacement: string; reason?: string };

type Props = {
  inputText: string;
  changes: Change[];
};

type Segment =
  | { kind: 'plain'; text: string }
  | { kind: 'diff'; original: string; replacement: string };

function buildSegments(inputText: string, changes: Change[]): Segment[] {
  const segments: Segment[] = [];
  let cursor = 0;
  for (const ch of changes) {
    const orig = ch.original || '';
    const repl = ch.replacement || '';
    if (!orig && !repl) continue;
    if (orig) {
      // Find the next occurrence at or after the cursor.
      const idx = inputText.indexOf(orig, cursor);
      if (idx >= 0) {
        if (idx > cursor) {
          segments.push({ kind: 'plain', text: inputText.slice(cursor, idx) });
        }
        segments.push({ kind: 'diff', original: orig, replacement: repl });
        cursor = idx + orig.length;
        continue;
      }
    }
    // Pure insertion or unmatched original — just show the replacement as new.
    segments.push({ kind: 'diff', original: '', replacement: repl });
  }
  if (cursor < inputText.length) {
    segments.push({ kind: 'plain', text: inputText.slice(cursor) });
  }
  return segments;
}

export function InlineDiffView({ inputText, changes }: Props) {
  // No changes at all (or the backend didn't send a diff): the output is
  // visually identical to the input. Render plain.
  if (!changes || changes.length === 0) {
    return <div className="text-sm text-ink leading-relaxed whitespace-pre-wrap">{inputText}</div>;
  }

  const segments = buildSegments(inputText, changes);

  return (
    <div className="text-sm text-ink leading-relaxed whitespace-pre-wrap">
      {segments.map((seg, i) => {
        if (seg.kind === 'plain') {
          return <span key={i}>{seg.text}</span>;
        }
        return (
          <span key={i} className="inline">
            {seg.original && (
              <span className="line-through text-ink-muted/50 mr-0.5" title={seg.original}>
                {seg.original}
              </span>
            )}
            {seg.replacement && (
              <span
                className="bg-primary/10 text-ink rounded px-0.5 decoration-primary"
                title="Rewritten"
              >
                {seg.replacement}
              </span>
            )}
          </span>
        );
      })}
    </div>
  );
}

export default InlineDiffView;
