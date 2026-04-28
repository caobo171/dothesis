// backend/src/services/humanizer/postprocess/disfluency.ts

// Deterministic injection of human-style disfluencies. Targets the
// "AI is too perfect" signal: humans hedge, hesitate, self-correct, and
// occasionally write fragments. LLMs almost never do.
//
// Used standalone (M12) and could layer under any other method.

const HEDGES = [
  "I think", "I'd say", "arguably", "in a sense",
  "roughly speaking", "more or less", "broadly",
];

const ASIDES = [
  " — though that's a quibble",
  " (or near enough)",
  " — which surprised me",
];

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

export function injectDisfluencies(text: string, opts: { seed?: number; rate?: number } = {}): string {
  const rng = mulberry32(opts.seed ?? 1);
  // rate = probability of touching any given sentence; default ~25% so we
  // get one nudge per ~4 sentences without making the text feel performative.
  const rate = opts.rate ?? 0.25;

  const sentences = splitSentences(text);
  const out = sentences.map((s) => {
    if (rng() > rate) return s;
    const choice = rng();
    if (choice < 0.4) {
      // Hedge at the start.
      const h = HEDGES[Math.floor(rng() * HEDGES.length)];
      // Lowercase first letter of the sentence so the hedge flows in.
      const lower = s.charAt(0).toLowerCase() + s.slice(1);
      return `${h}, ${lower}`;
    }
    if (choice < 0.75) {
      // Aside before the terminal punctuation.
      const m = s.match(/^(.*?)([.!?]+)$/);
      if (!m) return s;
      const a = ASIDES[Math.floor(rng() * ASIDES.length)];
      return `${m[1]}${a}${m[2]}`;
    }
    // Fragment: split on a comma if available, leave first half as-is, put
    // a period after, capitalize and continue. Skip if no comma.
    const ci = s.indexOf(', ');
    if (ci < 0) return s;
    const left = s.slice(0, ci).trim();
    const right = s.slice(ci + 2).trim();
    if (left.split(/\s+/).length < 3 || right.split(/\s+/).length < 3) return s;
    const rightCap = right.charAt(0).toUpperCase() + right.slice(1);
    return `${left}. ${rightCap}`;
  });
  return out.join(' ');
}
