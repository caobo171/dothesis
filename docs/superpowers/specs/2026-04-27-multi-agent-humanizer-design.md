# Multi-Agent Humanizer Pipeline Design

## Overview

Replace the current single-pass humanization with a multi-agent pipeline that uses Gemini for structural preprocessing, GPT for critiquing and rewriting, and an iterative loop with AI score checking to produce text that consistently scores below 30 (very human) on AI detectors.

## Pipeline Flow

```
Input Text
    |
    v
+-------------------------------+
|  Stage 1: GEMINI PREPROCESS   |  (gemini-3-flash-preview)
|  - Vary sentence lengths      |
|  - Break parallel structures  |
|  - Strip banned characters    |
|  - Structural reshaping only  |
+---------------+---------------+
                |
                v
+-------------------------------+
|  Stage 2: GPT CRITIC          |  (gpt-5.5)
|  - Act as AI detector         |<-----------+
|  - Flag specific patterns     |            |
|  - Reference ban list         |            |
|  - Return structured JSON     |            |
+---------------+---------------+            |
                |                            |
                v                            |
+-------------------------------+            |
|  Stage 3: GPT HUMANIZER       |  (gpt-5.5)|
|  - Rewrite based on critique  |            |
|  - Apply persona tone         |            |
|  - Enforce ban list           |            |
|  - presence_penalty: 0.3      |            |
|  - frequency_penalty: 0.4     |            |
|  - temperature: 0.9           |            |
+---------------+---------------+            |
                |                            |
                v                            |
+-------------------------------+            |
|  SCORE CHECK (AIDetector)     |            |
|  score < 30  -> EXIT          |            |
|  iteration < 3 -> LOOP -------+            |
|  else -> return best result   |
+---------------+---------------+
                |
                v
          Final Output
    (+ token usage per model)
```

### Exit Conditions

- **Target score:** < 30 (very human)
- **Max iterations:** 3 (critic -> humanizer -> score = 1 iteration)
- **Best result tracking:** Each iteration, if the current score is the lowest seen, save that version. If max iterations reached without hitting < 30, return the best version.
- Gemini preprocessing runs once (not in the loop).

## Prompt Architecture

### Gemini Preprocessor Prompt

Focused purely on structural variation, not content rewriting:

- Vary sentence lengths drastically (mix 5-word sentences with 25+ word ones)
- Break parallel constructions
- Merge/split sentences to disrupt uniform rhythm
- Reorder sentences within paragraphs where logical
- Strip banned Unicode characters (em dash, zero-width spaces, etc.)
- Preserve all facts, meaning, and language (Vietnamese or English)
- No creative rewriting -- just structural reshaping

### GPT Critic Prompt

Acts as an AI detector. Returns structured JSON:

```json
{
  "issues": [
    {
      "type": "uniform_length | predictable_transition | repetitive_opening | consistent_register | vocabulary_uniformity | lack_personality | banned_word",
      "location": "sentence or phrase from text",
      "description": "what the problem is",
      "suggestion": "how to fix it"
    }
  ],
  "overallAssessment": "summary of how AI-detectable the text is"
}
```

References the BANNED_WORDS list -- flags any occurrences.

### GPT Humanizer Prompt

Takes the current text + the critic's JSON output. Applies:

- Existing persona-based tone instructions (academic/casual/persuasive)
- Strength and length instructions (carried over from current system)
- The 3 principles: unpredictability, intellectual depth, preserve facts
- Ban list as a hard constraint
- Critic feedback as specific rewrite targets

Output format: Same JSON as current system `{ "rewrittenText": "...", "changes": [...] }`. The humanizer prompt instructs GPT to return this format so the final pipeline result includes both the rewritten text and the change list.

### API Parameters (GPT Humanizer Step)

| Parameter | Value | Reason |
|-----------|-------|--------|
| temperature | 0.9 | Increase output creativity, less predictable token choices |
| presence_penalty | 0.3 | Encourage branching into new concepts |
| frequency_penalty | 0.4 | Discourage word repetition, more dynamic flow |
| max_completion_tokens | 4096 | Sufficient for most texts |

## Ban List

### BANNED_WORDS

Configurable array in `humanizer.service.ts`, injected into prompts.

**Overused AI verbs:**
delve, leverage, utilize, harness, streamline, underscore, foster, spearhead, navigate, capitalize, embark, unlock, empower, facilitate, optimize, pave the way

**Inflated AI adjectives/adverbs:**
pivotal, robust, innovative, seamless, cutting-edge, multifaceted, comprehensive, crucially, notably, importantly, significantly, groundbreaking

**AI filler nouns/phrases:**
landscape, realm, tapestry, synergy, testament, underpinnings, beacon, treasure trove, myriad, game changer, paradigm shift

**AI transition/filler phrases:**
furthermore, moreover, in conclusion, it's worth noting, it should be mentioned, in today's world, in today's fast-paced world, at the forefront of, bridging the gap, push the boundaries, lay the groundwork, in terms of, subsequently, accordingly, in essence

### BANNED_CHARACTERS

Characters to strip/replace during Gemini preprocessing:

| Character | Unicode | Action |
|-----------|---------|--------|
| Em dash -- | U+2014 | Replace with comma or hyphen contextually |
| Zero-width space | U+200B | Strip |
| Narrow no-break space | U+202F | Replace with normal space |
| Em space | U+2003 | Replace with normal space |

## Token Tracking

### HumanizeJob Model Changes

Add `tokenUsage` field:

```typescript
tokenUsage: {
  steps: [
    {
      step: 'preprocess' | 'critic' | 'humanizer',
      model: string,       // e.g., 'gemini-3-flash-preview', 'gpt-5.5'
      iteration: number,   // 0 for preprocess, 1-3 for loop steps
      inputTokens: number,
      outputTokens: number
    }
  ],
  totalInputTokens: number,
  totalOutputTokens: number
}
```

### AI Service Return Type Change

All `chat()` methods return `AIChatResult` instead of `string`:

```typescript
type AIChatResult = {
  text: string;
  usage: { inputTokens: number; outputTokens: number }
}
```

**Token sources:**
- OpenAI: `response.usage.prompt_tokens` / `response.usage.completion_tokens`
- Gemini: `response.usageMetadata.promptTokenCount` / `response.usageMetadata.candidatesTokenCount`

`chatStream()` methods remain unchanged (return `string`).

**Breaking change:** All callers of `.chat()` need updating to destructure `{ text }`.

## Transport-Agnostic Pipeline

### Core Method

```typescript
static async humanizePipeline(
  text: string,
  tone: string,
  strength: number,
  lengthMode: string,
  onStage?: (stage: string, data: any) => void
): Promise<{
  rewrittenText: string;
  changes: any[];
  aiScoreIn: number;
  aiScoreOut: number;
  tokenUsage: TokenUsage;
  iterations: number;
}>
```

- `onStage` callback is optional. SSE route uses it to send events. Queue workers can use it for logging or ignore it.
- The method has no transport dependencies (no `req`, `res`, no SSE).

### SSE Route (`/humanize/run`)

Existing endpoint. Calls `humanizePipeline()` with an `onStage` callback that writes SSE events:

- `{ type: 'stage', stage: 'preprocessing' }`
- `{ type: 'stage', stage: 'critiquing', iteration: 1 }`
- `{ type: 'stage', stage: 'rewriting', iteration: 1 }`
- `{ type: 'score', score: 45, iteration: 1 }`
- `{ type: 'stage', stage: 'critiquing', iteration: 2 }` (if looping)
- ...
- `{ type: 'done', jobId, rewrittenText, changes, aiScoreIn, aiScoreOut, tokenUsage, iterations, creditsUsed }`

### Sync Route (`/humanize/run-sync`)

New endpoint. Calls `humanizePipeline()` without `onStage`. Returns JSON response directly. Designed for queue worker integration.

## Sample Texts

### Backend

New endpoint: `GET /humanize/samples` (no auth required).

Returns a static `SAMPLE_TEXTS` array of 3-4 pre-generated AI-sounding texts:

1. **Academic essay** (~150 words) -- AI-generated paragraph about a research topic
2. **Blog post** (~120 words) -- AI-written casual/marketing content
3. **Research summary** (~150 words) -- AI-generated literature review style
4. **Persuasive argument** (~120 words) -- AI-written opinion piece

These are intentionally AI-sounding so users see a clear before/after effect.

Stored as a constant in a file (e.g., `constants/sample-texts.ts` or directly in the route).

### Frontend

Sample text buttons/chips above the text input area. User clicks one, it populates the input field.

## Files Changed

| File | Change |
|------|--------|
| `backend/src/services/humanizer.service.ts` | Add `humanizePipeline()`, ban lists, new prompts (critic, preprocessor), keep existing methods |
| `backend/src/services/ai/openai.service.ts` | `chat()` returns `AIChatResult`, add `presence_penalty`/`frequency_penalty` support |
| `backend/src/services/ai/gemini.service.ts` | `chat()` returns `AIChatResult` |
| `backend/src/services/ai/claude.service.ts` | `chat()` returns `AIChatResult` (consistency) |
| `backend/src/services/ai/ai.service.manager.ts` | Update types for new return format |
| `backend/src/models/HumanizeJob.ts` | Add `tokenUsage` field, add `iterations` field |
| `backend/src/api/routes/humanize.ts` | Update SSE route to use pipeline, add `/run-sync`, add `/samples` |
| Frontend humanizer page | Add sample text buttons |

## Non-Goals

- No LangChain or external orchestration framework
- No separate agent class files -- pipeline lives in `humanizer.service.ts`
- No streaming of intermediate rewrite iterations to the frontend
- No queue implementation yet (just queue-ready architecture)
