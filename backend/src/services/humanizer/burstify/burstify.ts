// backend/src/services/humanizer/burstify/burstify.ts

// Deterministic transform that widens sentence-length variance. Targets the
// burstiness signal directly: detectors trained on LLM output expect uniform
// 12-18 word sentences, so we build outliers in both directions.
//
// Strategy: for each pair of adjacent sentences, with seeded probability
//   - merge them with a connector ("and", ";", "—")
//   - or fragment the longer one by clause split
// Roughly 30% of pairs touched, balanced merges and splits.

type Opts = { seed?: number };

function mulberry32(seed: number) {
  return function() {
    let t = seed += 0x6D2B79F5;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function splitSentences(text: string): string[] {
  return (text.match(/[^.!?]+[.!?]+(?:\s+|$)/g) || [text]).map(s => s.trim()).filter(Boolean);
}

function stripTrailingPunct(s: string): { body: string; punct: string } {
  const m = s.match(/^(.*?)([.!?]+)$/);
  if (!m) return { body: s, punct: '.' };
  return { body: m[1].trim(), punct: m[2] };
}

function fragmentSentence(s: string, _rng: () => number): string[] {
  // Try to split on a comma into two pieces; only split if both pieces have ≥3 words.
  const { body, punct } = stripTrailingPunct(s);
  const commaIdx = body.indexOf(', ');
  if (commaIdx < 0) return [s];
  const left = body.slice(0, commaIdx).trim();
  const right = body.slice(commaIdx + 2).trim();
  if (left.split(/\s+/).length < 3 || right.split(/\s+/).length < 3) return [s];
  // Capitalize the right side's first letter.
  const rightCap = right.charAt(0).toUpperCase() + right.slice(1);
  return [`${left}.`, `${rightCap}${punct}`];
}

function mergeSentences(a: string, b: string, rng: () => number): string {
  const { body: aBody } = stripTrailingPunct(a);
  const { body: bBody, punct: bPunct } = stripTrailingPunct(b);
  // Lowercase b's first letter so the merged sentence reads cleanly.
  const bLower = bBody.charAt(0).toLowerCase() + bBody.slice(1);
  const connectors = [', and ', '; ', ' — '];
  const c = connectors[Math.floor(rng() * connectors.length)];
  return `${aBody}${c}${bLower}${bPunct}`;
}

export function burstify(text: string, opts: Opts = {}): string {
  const rng = mulberry32(opts.seed ?? 1);
  const sentences = splitSentences(text);
  if (sentences.length < 2) return text;

  const out: string[] = [];
  let i = 0;
  while (i < sentences.length) {
    const cur = sentences[i];
    const next = sentences[i + 1];
    const r = rng();
    if (next && r < 0.30) {
      // Merge with neighbor
      out.push(mergeSentences(cur, next, rng));
      i += 2;
    } else if (cur.split(/\s+/).length > 12 && r < 0.60) {
      // Fragment a longer sentence
      out.push(...fragmentSentence(cur, rng));
      i += 1;
    } else {
      out.push(cur);
      i += 1;
    }
  }
  return out.join(' ');
}
