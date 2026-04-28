import { AIServiceManager } from '@/services/ai/ai.service.manager';
import { GeminiService } from '@/services/ai/gemini.service';
import { OpenAIService } from '@/services/ai/openai.service';
import { HumanizeJobModel } from '@/models/HumanizeJob';
import { AIDetectorEngine } from '@/services/ai-detector';

// Decision (v6): Switched rewrite step from GPT → Gemini.
// GPTZero 4.4b is a neural model trained heavily on GPT outputs, so GPT-5.5 rewrites
// are detected regardless of prompt quality (100% AI confidence even with aggressive prompts).
// Additionally, GPT-5.5 silently ignores temperature/presencePenalty/frequencyPenalty params,
// so we had no control over output variation. Gemini properly supports temperature and
// has a different token distribution that GPTZero is less tuned to detect.
// GPT is kept for the critic step only (analysis, not generation).
const GEMINI_MODEL = 'gemini-3-flash-preview';
const OPENAI_MODEL = 'gpt-5.5';

// Decision: Ban list of words/phrases that AI detectors flag instantly.
// Sources: GPTZero docs, walterwrites.ai, thehumanizeai.pro (April 2026).
// These words have statistically elevated frequency in LLM output vs human writing.
// Updated (v5): Added formulaic sentence patterns GPTZero flags as "Formulaic Flow"
// and "Artificial Simplicity" — simple clause-chaining with 'and'/'but' connectors.
const BANNED_WORDS: string[] = [
  // Overused AI verbs
  'delve', 'leverage', 'utilize', 'harness', 'streamline', 'underscore',
  'foster', 'spearhead', 'navigate', 'capitalize', 'embark', 'unlock',
  'empower', 'facilitate', 'optimize', 'pave the way',
  // Inflated AI adjectives/adverbs
  'pivotal', 'robust', 'innovative', 'seamless', 'cutting-edge',
  'multifaceted', 'comprehensive', 'crucially', 'notably', 'importantly',
  'significantly', 'groundbreaking', 'remarkable', 'transformative',
  // AI filler nouns/phrases
  'landscape', 'realm', 'tapestry', 'synergy', 'testament', 'underpinnings',
  'beacon', 'treasure trove', 'myriad', 'game changer', 'paradigm shift',
  'cornerstone', 'catalyst',
  // AI transition/filler phrases
  'furthermore', 'moreover', 'in conclusion', "it's worth noting",
  'it should be mentioned', "in today's world", "in today's fast-paced world",
  'at the forefront of', 'bridging the gap', 'push the boundaries',
  'lay the groundwork', 'in terms of', 'subsequently', 'accordingly',
  'in essence', 'plays a crucial role', 'it is important to note',
  'it is evident that', 'this demonstrates', 'this highlights',
  // Formulaic AI sentence structures (GPTZero "Formulaic Flow" signal)
  ', and it ', ', but it ', ', and this ', ', but this ',
  'has really changed how', 'has fundamentally changed',
  'has significantly impacted', 'has transformed the way',
];

// Decision: AI models inject hidden Unicode characters that detectors flag.
// Em dash (U+2014) is the most common — ChatGPT overuses it heavily.
// Zero-width spaces and special spaces are used as invisible watermarks.
function stripBannedCharacters(text: string): string {
  return text
    .replace(/\u2014/g, ' — ')  // Em dash → spaced em dash (keeps readability, avoids ChatGPT's no-space style)
    .replace(/\u200B/g, '')     // Zero-width space → strip
    .replace(/\u202F/g, ' ')    // Narrow no-break space → normal space
    .replace(/\u2003/g, ' ');   // Em space → normal space
}

// Decision (v5): Post-processing pass to catch formulaic patterns the LLM still produces.
// GPTZero flags ", and it" / ", but it" chains as "Formulaic Flow" even when the prompt
// says not to use them. This regex-based cleanup is a safety net.
function postProcessFormulaic(text: string): string {
  let result = text;

  // Break ", and it " / ", and this " chains into separate sentences
  result = result.replace(/, and (it|this|these|those|they) /gi, (match, pronoun) => {
    // Capitalize the pronoun for new sentence
    return '. ' + pronoun.charAt(0).toUpperCase() + pronoun.slice(1) + ' ';
  });

  // Break ", but it " / ", but this " chains into separate sentences
  result = result.replace(/, but (it|this|these|those|they) /gi, (match, pronoun) => {
    return '. ' + pronoun.charAt(0).toUpperCase() + pronoun.slice(1) + ' ';
  });

  return result;
}

type TokenStep = {
  step: 'preprocess' | 'critic' | 'humanizer';
  model: string;
  iteration: number;
  inputTokens: number;
  outputTokens: number;
};

type TokenUsage = {
  steps: TokenStep[];
  totalInputTokens: number;
  totalOutputTokens: number;
};

type PipelineResult = {
  rewrittenText: string;
  changes: Array<{ original: string; replacement: string; reason: string }>;
  aiScoreIn: number;
  aiScoreOut: number;
  tokenUsage: TokenUsage;
  iterations: number;
};

// Decision (v4): Switched from rule-based to persona-based tone instructions.
// Previous versions gave 8+ explicit rules which the LLM followed UNIFORMLY,
// creating new detectable patterns. GPTZero flagged "Artificial Simplicity",
// "Rigid Guidance", "Predictable Syntax" — all caused by uniform rule-following.
// Now each tone defines a specific person with naturally varied writing habits.
// Decision (v5): Personas now explicitly include grammar habits and sensory writing tendencies.
// GPTZero flagged v4 output for "Lacks Creative Grammar" and "Functional Word Choice"
// because the personas didn't produce enough grammatical variety or experiential language.
const TONE_INSTRUCTIONS: Record<string, string> = {
  // Decision (v6): Reduced hedging in all personas. GPTZero flagged v5 output as
  // "Speculative Focus" and "Uncertain Language" because every persona was adding caveats.
  // New personas are CONFIDENT first, with only occasional doubt.
  academic:
    'You are a 28-year-old PhD candidate who genuinely cares about this topic. You write with CONFIDENCE — you\'ve done the reading and you know what the evidence says. You make strong claims: "The data is unambiguous" / "This finding upends the conventional wisdom." Sometimes your sentences get too long because you\'re excited about an idea, sometimes you cut yourself short. You have a habit of starting sentences with "What the data actually shows is..." or "Having read dozens of papers on this..." or inverting word order for emphasis ("Rarely do we see..." / "Not once in the dataset..."). You mix technical analysis with vivid concrete examples — you don\'t just say "outcomes improved", you describe what that looked like in the lab. You only hedge on the ONE thing you genuinely aren\'t sure about — everything else, you state with authority.',
  casual:
    'You are a smart college senior explaining this topic to a classmate over coffee. You know the material and you\'re confident about it — you don\'t waffle. You make direct statements: "Yeah, it\'s a big deal" / "Look, the numbers don\'t lie." You interrupt yourself with asides in parentheses or dashes, and you ground abstract ideas with concrete images ("picture a teacher at midnight, still grading"). Sometimes you go on tangents, sometimes you oversimplify, sometimes you say something surprisingly insightful. You never chain clauses with ", and" — you either use a dash, a semicolon, or just start a new sentence. You avoid sounding uncertain — if you don\'t know something, you just skip it rather than speculating.',
  persuasive:
    'You are an experienced journalist writing an opinion piece. You have a STRONG point of view and you commit to it. You make declarative statements: "This policy failed." / "The evidence leaves no room for debate." Your writing has rhythm — you build momentum with long, clause-heavy sentences then stop dead. Short sentence. Then pick up again. You lead paragraphs with provocative claims, not wishy-washy qualifications. You use concrete imagery and analogies instead of abstractions — "a half-empty server room" not "declining infrastructure". You sometimes invert word order for emphasis: "Gone are the days when..." / "Nowhere is this more visible than..." You only concede ONE counterargument per paragraph, and even then you rebut it.',
};

const LENGTH_INSTRUCTIONS: Record<string, string> = {
  match: 'Keep the output approximately the same length as the input.',
  shorter: 'Make the output about 15% shorter than the input. Be more concise.',
  longer: 'Make the output about 15% longer. Add more detail and elaboration.',
};

function buildHumanizePrompt(tone: string, strength: number, lengthMode: string): string {
  const toneInstr = TONE_INSTRUCTIONS[tone] || TONE_INSTRUCTIONS.academic;
  const lengthInstr = LENGTH_INSTRUCTIONS[lengthMode] || LENGTH_INSTRUCTIONS.match;

  // Decision: Strength 31-70 was changed from "preserve structure" to "MUST restructure"
  // because the old wording caused LLMs to only do lazy word swaps (e.g. "các" → "những"),
  // which produced only -6% score drops. GPTZero still detected these as AI.
  const strengthDesc =
    strength <= 30
      ? 'Make LIGHT edits. Fix the most obvious AI-sounding phrases, add some sentence length variation, and remove blatant AI transitions. Keep most of the original wording.'
      : strength <= 70
        ? 'Make SUBSTANTIAL edits. You MUST restructure sentences — do NOT just swap individual words. Split long sentences into short+long pairs. Merge short sentences. Change sentence order within paragraphs. Replace AI transitions with natural flow. Add hedging and human voice. Every sentence should read noticeably different from the original.'
        : 'Do a COMPLETE rewrite. Rewrite every sentence from scratch as if you were a human expert writing about this topic for the first time. The output should share zero sentence structures with the input while preserving all facts and arguments.';

  // Decision (v5): Upgraded from 3 principles to 4 principles targeting GPTZero's
  // specific detection signals: "Lacks Creative Grammar", "Formulaic Flow",
  // "Artificial Simplicity", "Lacks Complexity", "Functional Word Choice".
  // Added explicit grammar transformation techniques and sensory language requirements.
  return `${toneInstr}

Rewrite the text below in your own voice. ${strengthDesc}

${lengthInstr}

=== FOUR PRINCIPLES (internalize these, don't follow mechanically) ===

1. CREATIVE GRAMMAR — defeat "Lacks Creative Grammar" detection
   GPTZero flags standard Subject-Verb-Object order as AI. You MUST use varied grammatical constructions:
   - INVERSIONS: "Rarely do we see..." / "Not until the data came in did anyone realize..." / "Gone are the days when..."
   - FRONTED ADVERBIALS: "Deep in the weeds of the methodology, a problem lurks." / "Halfway through the analysis, something clicked."
   - CLEFT SENTENCES: "What surprised me was..." / "It was the third variable that broke everything."
   - APPOSITIVES: "The model — a hastily trained transformer with questionable data — performed worse than expected."
   - PARTICIPIAL PHRASES: "Having spent three months on this, I can say..."  / "Trained on biased data, the system predictably failed."
   - ABSOLUTE CONSTRUCTIONS: "The results in hand, the team pivoted." / "All things considered, this changes the picture."
   DO NOT use the same grammatical trick twice in a row. Alternate between these and normal SVO.

2. BREAK FORMULAIC FLOW — defeat "Formulaic Flow" and "Artificial Simplicity" detection
   GPTZero flags clauses chained with 'and'/'but' as formulaic. NEVER write ", and it..." or ", but it..." patterns.
   Instead:
   - USE SEMICOLONS to join related ideas: "The data looked clean; the conclusions were anything but."
   - USE PARENTHETICAL ASIDES: "The growth rate (which, honestly, nobody expected) held steady."
   - USE DASHES FOR INTERRUPTION: "Teachers started adopting the tools — reluctantly at first — and the results shocked everyone."
   - EMBED SUBORDINATE CLAUSES: "Because the sample size was tiny, a fact the authors buried in a footnote, the headline finding deserves skepticism."
   - SPLIT INTO INDEPENDENT SENTENCES instead of chaining: Replace "X, and Y, but Z" with "X. Y? Actually, Z."
   - VARY CONNECTORS: instead of 'and'/'but', use 'though', 'yet', 'still', 'only', 'except', 'which means', 'so', 'granted', 'sure', 'mind you'

3. INTELLECTUAL DEPTH + SENSORY LANGUAGE — defeat "Lacks Complexity" and "Functional Word Choice" detection
   GPTZero flags text that is linear (one idea per sentence) and uses only functional/action words.
   - LAYER MULTIPLE IDEAS per sentence: "The dropout rate — 23% in urban schools, nearly double in rural ones — tells a story the ministry's press release conveniently omitted."
   - USE SENSORY AND EXPERIENTIAL LANGUAGE: Instead of "Teachers plan lessons", write "Anyone who's sat through a late-night lesson-planning session, coffee going cold, knows the reality behind that statistic."
   - USE CONCRETE IMAGERY: "spreadsheets glowing at midnight", "a half-empty lecture hall", "the stack of ungraded papers"
   - MIX ABSTRACT AND CONCRETE: Follow an abstract claim immediately with a specific, tangible example

   CRITICAL BALANCE — defeat "Speculative Focus" and "Uncertain Language" detection:
   GPTZero flags text that hedges TOO MUCH as AI. You must balance:
   - 70% of sentences should be CONFIDENT and ASSERTIVE: "The data is clear." / "This changes everything." / "Schools had no choice."
   - 30% can hedge or question: "Whether that holds up long-term is another story."
   - NEVER use more than 2 hedging phrases ("might", "could", "perhaps", "it seems") per paragraph
   - Make DEFINITIVE CLAIMS backed by the data, then occasionally question ONE specific aspect
   - Avoid speculating about future outcomes unless the original text explicitly does so

4. PRESERVE ALL FACTS
   Keep every factual claim, number, data point, and argument from the original. Do not invent information. You may add brief rhetorical reactions to facts but never fabricate data or speculate beyond what the original states.

=== WHAT TO AVOID ===

These patterns are INSTANTLY detectable by GPTZero:
- Starting 3+ sentences the same way (e.g., all starting with subject-verb)
- Every sentence being roughly the same length (vary between 4 and 35+ words)
- Chaining clauses with ", and" / ", but" — this is the #1 "Formulaic Flow" trigger
- Using transitions systematically ("Firstly... Secondly..." or "Còn về... Thêm vào đó...")
- Explaining things the same way each time (claim → evidence → conclusion, repeated)
- Consistent register — either all formal OR all casual throughout
- Listing facts without reacting to them or questioning them
- Using only functional verbs (plan, set, mark, show, change) — mix in experiential and sensory language
- Simple sentence structures throughout — MUST include at least 2 complex/compound-complex sentences per paragraph

=== OUTPUT FORMAT ===

Respond with valid JSON only. No markdown, no code fences:
{
  "rewrittenText": "the full rewritten text as plain text",
  "changes": [
    { "original": "phrase from input", "replacement": "rewritten phrase", "reason": "brief reason" }
  ]
}

List every changed phrase in the changes array.`;
}

// Decision (v5): Preprocess prompt now explicitly targets GPTZero's grammar and flow
// signals. Previous version only varied length/order — GPTZero still flagged the output
// for "Lacks Creative Grammar" and "Formulaic Flow" because the SVO patterns survived.
function buildPreprocessPrompt(): string {
  return `You are a text structure editor. Your job is to restructure text for natural sentence variety — NOT to rewrite content or vocabulary.

=== RULES ===

1. VARY SENTENCE LENGTHS DRASTICALLY
   - Mix very short sentences (3-8 words) with long ones (25-40 words)
   - Never have 3 consecutive sentences of similar length
   - Split overly long sentences. Merge overly short ones where natural.
   - Include at least one fragment or ultra-short sentence per paragraph

2. BREAK GRAMMATICAL MONOTONY
   - If multiple sentences follow Subject-Verb-Object, restructure at least half:
     * Move adverbials/prepositional phrases to the front: "In the 2024 data, a pattern emerged..."
     * Use inversions: "Rarely does this happen..." / "Not once did the study mention..."
     * Start with participial phrases: "Looking at the numbers, ..."
     * Use cleft constructions: "What matters here is..." / "It was X that caused Y"
   - Break ", and" / ", but" clause chains — replace with semicolons, dashes, or separate sentences
   - Convert some statements to questions: "So what does this actually mean?"

3. REORDER WITHIN PARAGRAPHS
   - Where logical, change the order of sentences within a paragraph
   - Lead with a different point than the original when it still makes sense
   - Occasionally move the conclusion/reaction BEFORE the evidence

4. PRESERVE EVERYTHING ELSE
   - Keep all facts, numbers, arguments, and meaning exactly as-is
   - Keep the same language (if Vietnamese, output Vietnamese; if English, output English)
   - Do NOT rewrite vocabulary or tone — only restructure

Output the restructured text as plain text. No JSON, no markdown.`;
}

// Decision (v5): Critic prompt now includes GPTZero's exact detection categories:
// "Lacks Creative Grammar", "Formulaic Flow", "Artificial Simplicity",
// "Lacks Complexity", "Functional Word Choice". These are the flags that v4 missed.
function buildCriticPrompt(): string {
  const bannedList = BANNED_WORDS.join(', ');
  return `You are an expert AI text detector specializing in GPTZero's detection methodology. Analyze the provided text and identify specific patterns that GPTZero would flag.

Scan for these issues (ordered by GPTZero priority):

- **lacks_creative_grammar**: Sentences follow standard Subject-Verb-Object word order with no creative deviations. GPTZero specifically flags this. Look for: all sentences starting with a noun/pronoun subject, no inversions, no fronted adverbials, no cleft sentences, no participial openers.

- **formulaic_flow**: Clauses connected with simple 'and'/'but' conjunctions creating a predictable logical flow. GPTZero calls this "Formulaic Flow". Look for: ", and it...", ", but it...", ", and this...", chains of clauses with the same connector.

- **artificial_simplicity**: Sentence structures that are too simple — basic SVO with conjunctions, no embedded clauses, no parenthetical asides, no complex grammar. GPTZero flags this even in "casual" rewrites.

- **lacks_complexity**: Linear single-theme sentences. Each sentence covers one idea in one direction. No layering of multiple perspectives, no digressions, no embedded reactions.

- **functional_word_choice**: Word choice focuses only on actions/events (plan, set, mark, show, change, impact) rather than imagery, sensory details, or personal experiences. GPTZero flags this as "Functional Word Choice".

- **speculative_focus**: Too many speculative/hypothetical elements — "might", "could", "perhaps", "it seems", focusing on potential outcomes and future implications. GPTZero flags this as AI humanization. Real humans make confident assertions.

- **uncertain_language**: Pervasive uncertainty and lack of conclusions. Every sentence hedges instead of committing. Humans state things confidently most of the time.

- **uniform_length**: Sentences of similar length creating a predictable rhythm.
- **predictable_transition**: Smooth logical connectors used systematically.
- **repetitive_opening**: Multiple sentences starting with the same pattern.
- **consistent_register**: Uniform formality level — no natural register mixing.
- **lack_personality**: No personal opinion, humor, rhetorical questions, or tangential observations.
- **banned_word**: Any occurrence of these known AI-flagged words/phrases: ${bannedList}

IMPORTANT: Be extremely strict. If even one sentence has standard SVO with no creative deviation, flag it. GPTZero analyzes EVERY sentence individually.

For each issue found, provide the exact location (quote the text), describe the problem, and suggest a specific fix.

Respond with valid JSON only:
{
  "issues": [
    {
      "type": "lacks_creative_grammar | formulaic_flow | artificial_simplicity | lacks_complexity | functional_word_choice | uniform_length | predictable_transition | repetitive_opening | consistent_register | lack_personality | banned_word",
      "location": "exact quote from text",
      "description": "what makes this detectable",
      "suggestion": "specific fix — provide a concrete rewritten version"
    }
  ],
  "overallAssessment": "1-2 sentence summary of how AI-detectable this text is, specifically from GPTZero's perspective"
}`;
}

// Decision (v5): Added specific GPTZero counter-instructions to the critique rewrite prompt.
// The critic now identifies GPTZero-specific flags, and the humanizer must fix each one
// with the exact technique specified (inversion, cleft, sensory language, etc.).
function buildHumanizerWithCritiquePrompt(
  tone: string,
  strength: number,
  lengthMode: string,
  critique: string
): string {
  const basePrompt = buildHumanizePrompt(tone, strength, lengthMode);
  const bannedList = BANNED_WORDS.join(', ');

  return `${basePrompt}

=== CRITIC FEEDBACK (fix ALL of these issues — this is your TOP PRIORITY) ===

${critique}

=== GPTZERO-SPECIFIC FIXES (apply these techniques for each flagged issue type) ===

- "lacks_creative_grammar" → Rewrite the flagged sentence using an inversion, fronted adverbial, cleft sentence, or participial opener. Do NOT keep standard SVO.
- "formulaic_flow" → Break the ", and" / ", but" chain. Use a semicolon, a dash, a parenthetical, or split into separate sentences.
- "artificial_simplicity" → Add an embedded clause, a parenthetical aside, or a subordinate clause. The sentence must have at least 2 levels of grammatical nesting.
- "lacks_complexity" → Layer a second idea, a reaction, or a counterpoint into the sentence. One sentence should touch 2+ angles.
- "functional_word_choice" → Replace at least one functional verb/noun with sensory or experiential language. "Teachers plan lessons" → "Anyone who's stared at a blank lesson template at 11pm knows..."
- "speculative_focus" → Replace speculative language with CONFIDENT assertions. "This might impact..." → "This changes...". Remove "could", "might", "perhaps" and state things directly.
- "uncertain_language" → Add definitive conclusions. "It seems that..." → "The data is clear:" / "The numbers speak for themselves."

=== BANNED WORDS (NEVER use any of these) ===

${bannedList}

If any of these words appear in the input, replace them with natural alternatives. Never introduce any of these words in your rewrite.`;
}

function buildAiScorePrompt(): string {
  return `You are an expert AI text detector. Analyze the text for specific linguistic markers that distinguish AI-generated writing from human writing.

Evaluate these dimensions individually (score each 0-100):

1. **Vocabulary uniformity**: AI tends to use consistent register and avoids colloquialisms, slang, or unexpected word choices. Humans mix registers and use idiosyncratic phrasing.
2. **Sentence structure variety**: AI often produces sentences of similar length and complexity with parallel constructions. Humans vary sentence length more naturally, including very short and very long sentences.
3. **Transitional patterns**: AI overuses smooth logical connectors ("Furthermore", "Additionally", "Moreover", "In addition"). Humans use fewer transitions and sometimes make abrupt topic shifts.
4. **Hedging and filler**: Humans use more filler words, self-corrections, and natural hedging ("kind of", "I think", "well"). AI hedging sounds formulaic ("it is worth noting", "it should be mentioned").
5. **Personality and voice**: Human writing has a distinctive voice with opinions, humor, or personal perspective. AI writing is polished but personality-neutral.
6. **Repetitive phrasing**: AI often repeats structural patterns across paragraphs. Look for templated sentence openings or list-like enumeration.

Respond with valid JSON only:
{
  "scores": { "vocabulary": <0-100>, "structure": <0-100>, "transitions": <0-100>, "hedging": <0-100>, "personality": <0-100>, "repetition": <0-100> },
  "score": <weighted average 0-100>,
  "reasoning": "brief explanation of key signals found"
}

Score guide: 0-20 = very human, 21-40 = mostly human, 41-60 = mixed, 61-80 = likely AI, 81-100 = almost certainly AI.
Be precise and differentiate carefully. Small phrasing changes CAN shift scores — pay close attention to word-level naturalness.`;
}

export class HumanizerService {
  static buildSystemPrompt(tone: string, strength: number, lengthMode: string): string {
    return buildHumanizePrompt(tone, strength, lengthMode);
  }

  static buildAiScoreSystemPrompt(): string {
    return buildAiScorePrompt();
  }

  static async checkAiScore(text: string): Promise<number> {
    const result = await AIDetectorEngine.detect(text);
    return result.score;
  }

  static async humanize(
    text: string,
    tone: string,
    strength: number,
    lengthMode: string
  ): Promise<{ rewrittenText: string; changes: Array<{ original: string; replacement: string; reason: string }> }> {
    const ai = AIServiceManager.getInstance();
    const systemPrompt = buildHumanizePrompt(tone, strength, lengthMode);

    // Decision: Destructure { text: result } because chat() now returns AIChatResult
    // with { text, usage } instead of a plain string. Task 3 will rewrite this method.
    const { text: result } = await ai.tryWithFallback('humanize', async (service) => {
      return service.chat(systemPrompt, text, {
        // Decision: Temperature raised from 0.7 → 0.9 to increase output creativity.
        // At 0.7 the LLM produced overly safe/polished text that GPTZero flagged as
        // "Mechanical Precision" and "Lacks Creativity". Higher temp = more variation.
        temperature: 0.9,
        maxTokens: 4096,
        jsonMode: true,
      });
    });

    try {
      return JSON.parse(result);
    } catch {
      return { rewrittenText: result, changes: [] };
    }
  }

  static async humanizeStream(
    text: string,
    tone: string,
    strength: number,
    lengthMode: string,
    onChunk: (chunk: string) => void
  ): Promise<string> {
    const ai = AIServiceManager.getInstance();
    const systemPrompt = buildHumanizePrompt(tone, strength, lengthMode);

    return ai.tryWithFallback('humanize-stream', async (service) => {
      return service.chatStream(systemPrompt, text, onChunk, {
        temperature: 0.9,
        maxTokens: 4096,
      });
    });
  }

  static async humanizePipeline(
    text: string,
    tone: string,
    strength: number,
    lengthMode: string,
    onStage?: (stage: string, data: any) => void
  ): Promise<PipelineResult> {
    const tokenSteps: TokenStep[] = [];

    const addTokenStep = (step: TokenStep) => {
      tokenSteps.push(step);
    };

    // --- Input AI score ---
    console.log('[Humanizer] Pipeline started | tone=%s strength=%d length=%s words=%d', tone, strength, lengthMode, text.split(/\s+/).length);
    const aiScoreIn = await this.checkAiScore(text);
    console.log('[Humanizer] Input AI score: %d', aiScoreIn);
    onStage?.('ai_score_in', { score: aiScoreIn });

    // --- Stage 1: Gemini Preprocess ---
    onStage?.('stage', { stage: 'preprocessing' });

    const preprocessPrompt = buildPreprocessPrompt();
    const preprocessResult = await GeminiService.chat(preprocessPrompt, text, {
      temperature: 0.7,
      maxTokens: 4096,
    });

    // Decision: Strip banned Unicode characters after Gemini output.
    // Gemini may introduce em dashes and special spaces in its restructuring.
    let currentText = stripBannedCharacters(preprocessResult.text);
    console.log('[Humanizer] Gemini preprocess done | in=%d out=%d tokens', preprocessResult.usage.inputTokens, preprocessResult.usage.outputTokens);
    addTokenStep({
      step: 'preprocess',
      model: GEMINI_MODEL,
      iteration: 0,
      inputTokens: preprocessResult.usage.inputTokens,
      outputTokens: preprocessResult.usage.outputTokens,
    });

    // --- Iterative Loop: Critic -> Humanizer -> Score ---
    // Decision (v5): Lowered target from 30 → 25 and added 1 more iteration.
    // GPTZero requires more aggressive rewriting to pass — 3 iterations at target 30
    // was leaving text in the "mixed" zone where GPTZero still flags individual sentences.
    const MAX_ITERATIONS = 4;
    const TARGET_SCORE = 25;
    let bestResult = { text: currentText, score: 100, changes: [] as any[] };
    let iterations = 0;

    for (let i = 1; i <= MAX_ITERATIONS; i++) {
      iterations = i;

      // Stage 2: GPT Critic
      onStage?.('stage', { stage: 'critiquing', iteration: i });
      console.log('[Humanizer] Calling GPT critic (pass %d)...', i);

      const criticPrompt = buildCriticPrompt();
      const criticResult = await OpenAIService.chat(criticPrompt, currentText, {
        temperature: 0.3,
        maxTokens: 2048,
        jsonMode: true,
      });
      console.log('[Humanizer] Critic pass %d done | in=%d out=%d tokens | issues=%s', i, criticResult.usage.inputTokens, criticResult.usage.outputTokens, (() => { try { return JSON.parse(criticResult.text).issues?.length ?? '?'; } catch { return '?'; } })());
      addTokenStep({
        step: 'critic',
        model: OPENAI_MODEL,
        iteration: i,
        inputTokens: criticResult.usage.inputTokens,
        outputTokens: criticResult.usage.outputTokens,
      });

      // Stage 3: Rewrite — using Gemini (not GPT)
      // Decision (v6): GPTZero 4.4b is trained on GPT outputs, so we use Gemini for
      // rewrites. Gemini supports temperature properly and has a different token distribution.
      onStage?.('stage', { stage: 'rewriting', iteration: i });

      const humanizerPrompt = buildHumanizerWithCritiquePrompt(
        tone,
        strength,
        lengthMode,
        criticResult.text
      );

      // Decision (v6): Random temperature between 0.8-1.0 per iteration to prevent
      // consistent output distribution. Each pass feels slightly different.
      const rewriteTemp = 0.8 + Math.random() * 0.2;
      const humanizerResult = await GeminiService.chat(humanizerPrompt, currentText, {
        temperature: rewriteTemp,
        maxTokens: 4096,
        jsonMode: true,
      });
      console.log('[Humanizer] Rewrite pass %d [Gemini temp=%.2f] done | in=%d out=%d tokens', i, rewriteTemp, humanizerResult.usage.inputTokens, humanizerResult.usage.outputTokens);
      addTokenStep({
        step: 'humanizer',
        model: GEMINI_MODEL,
        iteration: i,
        inputTokens: humanizerResult.usage.inputTokens,
        outputTokens: humanizerResult.usage.outputTokens,
      });

      // Parse humanizer output
      let rewrittenText = humanizerResult.text;
      let changes: any[] = [];
      try {
        const parsed = JSON.parse(humanizerResult.text);
        rewrittenText = parsed.rewrittenText || humanizerResult.text;
        changes = parsed.changes || [];
      } catch {
        // If not valid JSON, use raw text
      }

      // Strip banned characters and fix formulaic patterns in output
      rewrittenText = stripBannedCharacters(rewrittenText);
      rewrittenText = postProcessFormulaic(rewrittenText);
      currentText = rewrittenText;

      // Score check
      const score = await this.checkAiScore(currentText);
      console.log('[Humanizer] Score after pass %d: %d (target < %d, best so far: %d)', i, score, TARGET_SCORE, Math.min(score, bestResult.score));
      onStage?.('score', { score, iteration: i });

      // Track best result
      if (score < bestResult.score) {
        bestResult = { text: currentText, score, changes };
      }

      // Exit if target reached
      if (score < TARGET_SCORE) {
        console.log('[Humanizer] Target reached! Exiting after %d iteration(s)', i);
        break;
      }
    }

    // Build final token usage summary
    const totalInputTokens = tokenSteps.reduce((sum, s) => sum + s.inputTokens, 0);
    const totalOutputTokens = tokenSteps.reduce((sum, s) => sum + s.outputTokens, 0);

    console.log('[Humanizer] Pipeline complete | iterations=%d | score: %d → %d | tokens: in=%d out=%d', iterations, aiScoreIn, bestResult.score, totalInputTokens, totalOutputTokens);
    tokenSteps.forEach((s) => console.log('[Humanizer]   %s (iter %d) [%s] in=%d out=%d', s.step, s.iteration, s.model, s.inputTokens, s.outputTokens));

    return {
      rewrittenText: bestResult.text,
      changes: bestResult.changes,
      aiScoreIn,
      aiScoreOut: bestResult.score,
      tokenUsage: {
        steps: tokenSteps,
        totalInputTokens,
        totalOutputTokens,
      },
      iterations,
    };
  }

  // Credit cost formula. 2× the original (was 1/100 with min 1), so 1 credit
  // per 50 words with a minimum of 2 per run. Frontend mirrors this exact
  // formula in HumBoard.tsx — keep them in lockstep.
  static calculateCredits(wordCount: number): number {
    return Math.max(2, Math.ceil(wordCount / 50));
  }
}
