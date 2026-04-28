// backend/src/services/humanizer/methods/types.ts

// Shared shape for every humanizer method in the bake-off. Keeping methods
// behind a uniform interface lets the bench harness dispatch by id without
// caring about each method's internal pipeline.

export type MethodOptions = {
  tone: string;        // 'academic' | 'casual' | etc, mirrors HumanizerService
  strength: number;    // 0-100, mirrors HumanizerService
  lengthMode: string;  // 'match' | 'shorter' | 'longer'
};

export type MethodTokenStep = {
  step: string;        // free-form label, e.g. 'gemini_critic', 'gpt_paraphrase'
  model: string;
  inputTokens: number;
  outputTokens: number;
};

export type MethodResult = {
  output: string;
  tokenSteps: MethodTokenStep[];
};

export type HumanizerMethod = {
  id: string;          // 'M0' | 'M1' | ... | 'M8'
  description: string; // short human label
  run(input: string, opts: MethodOptions): Promise<MethodResult>;
};

// One row per (method, text) in the bench output JSON.
export type BenchRecord = {
  methodId: string;
  textId: string;
  scoreIn: number | null;       // Copyscape score on input, null if --copyscape false
  scoreOut: number | null;
  tokenSteps: MethodTokenStep[];
  totalInputTokens: number;
  totalOutputTokens: number;
  durationMs: number;
  output: string;
};
