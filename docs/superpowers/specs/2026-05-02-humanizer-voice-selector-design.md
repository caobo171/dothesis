# Humanizer Voice Selector + Per-User Voice Anchors

**Date:** 2026-05-02
**Status:** Design — ready for UI redesign + implementation planning
**Predecessor:** v13 handoff (`docs/superpowers/handoff/2026-05-02-humanizer-v12-m23-results.md`)
**Production state at design time:** M21 router-anchor (v12 unchanged)

---

## Why this exists

After v11, v12 (M23/M24/M25/M26), and the v13 multi-seed variance test, the following is settled:

1. **M21's anchor-mimicry approach is the right architecture.** It ships ~50–55% reliable passes on Sapling < 15 across the 12-text corpus.
2. **Prompt-engineering on top of M21 is exhausted.** Every variant tried (rules, critic, de-involve, two-stage, threshold-tuning) was within the LLM stochastic noise floor when measured across 3 seeds. Single-run "wins" were artifacts.
3. **Two failure modes remain.** (a) Texts that match an existing anchor poorly (especially tutorial / how-to / business memo registers), and (b) the LLM's irreducible statistical fingerprint, which detectors are trained on.
4. **The empirical principle from v11 still stands:** anchors must be statistically OUTSIDE the LLM training distribution. Period public-domain works qualify. Wikipedia/CC-licensed modern web does not. **Per-user idiosyncratic writing also qualifies and is the strongest possible signal** — the detector cannot have been trained on writing it has never seen.

This spec addresses both failure modes by making the anchor a deliberate, user-controlled choice:

- **MVP change:** surface the anchor selection in the humanize UI rather than always auto-routing. The user picks the register that matches what they're writing. "Let AI decide" is the default (preserves current M21 behavior).
- **Premium tier:** users can save 200–500 words of their own writing as a personal voice anchor. That anchor becomes one of the options in their menu and produces output that mimics *their* voice — categorically defeating detector training.

## Non-goals

- Not a new humanization method. The pipeline stays M21.
- Not a multi-anchor mixing system (parking M18-style anchor blending; doesn't help per the bench history).
- Not a per-user anchor *requirement* — it stays optional. Free users get the period anchors + auto-router exactly as today.
- Not a voice-style learning system that infers anchors from past humanize runs (privacy + complexity, not validated).
- Not adding more period anchors in this spec (path 2 from v11 handoff is a separate, parallel effort).

---

## What changes — at a glance

### Free tier (and current logged-in default)
- The humanize panel gets a **Voice** selector with 7 options:
  1. **Let AI decide** (default — current M21 router behavior)
  2. Formal academic
  3. Casual academic
  4. Argumentative
  5. Instructional / business-formal
  6. Modern opinion / reflection
  7. Personal narrative
- The `humanizePipeline()` API accepts an optional `voice` parameter. Unset/null → "Let AI decide" → router runs (today's behavior, fully backwards compatible).

### Premium tier (new)
- A new **My voice** section in the user profile lets users save up to 3 personal voice anchors (e.g. "Academic me", "Blog me", "Email me").
- Each personal anchor: 200–500 words of the user's own writing, plus a label.
- Once saved, the user's personal anchors appear as additional options in the Voice selector, above the built-in registers.
- **Pricing model placeholder:** premium tier — exact pricing TBD by the business owner. The technical spec assumes a binary `user.tier === 'premium'` flag; gating logic is one if-statement.

---

## User-facing flow

### Free user humanizes a text (typical case)

1. Pastes text into the humanize input.
2. Sees **Voice: Let AI decide** as the default in a dropdown above the "Humanize" button.
3. Clicks Humanize.
4. Pipeline runs M21 unchanged (router picks an anchor, anchored rewrite, polish).
5. Output appears with the AI-score badges (existing behavior).

The UX is identical to today *except* the dropdown is visible. Default behavior is unchanged.

### Free user picks a specific voice

1. Pastes text.
2. Opens **Voice** dropdown, sees the 7 options with one-line descriptions.
3. Picks "Argumentative" (for example).
4. Pipeline skips the router; uses the `argumentative` anchor directly.
5. Output appears.

### Premium user adds their personal voice

1. Goes to profile → **My voice** section.
2. Sees an empty slot (or up to 3 saved voices).
3. Clicks "Add a voice."
4. Pastes 200–500 words of their own writing into a textarea.
5. Adds a label like "My thesis voice."
6. Clicks "Save."
7. Frontend sends to `POST /me/voice-anchors` with `{ label, text }`.
8. Backend validates word count (200–500), strips obviously-AI text via the existing `StatisticalDetectionProvider` (warn user if score > 80 — "this looks like AI output, are you sure this is your writing?"), saves to user profile.
9. New voice appears in the **Voice** dropdown for all future humanizes.

### Premium user humanizes with their saved voice

1. Pastes text.
2. Opens **Voice** dropdown, sees their personal voice ("My thesis voice") as the first option above the period-anchor section.
3. Picks "My thesis voice."
4. Pipeline runs M21 with the user's anchor text injected in place of the picked anchor.
5. Output mimics the user's own writing style.

---

## Architecture

### Pipeline (no algorithmic change to M21)

```
HumanizePipeline(text, tone, strength, lengthMode, voice?)
  │
  ├─ AI score input (existing)
  │
  ▼
M21.run(text, { ..., voice })
  │
  ├─ strip AI-vocab
  │
  ├─ anchor selection:
  │     if voice === undefined or 'auto' → existing router LLM call
  │     if voice === 'academic_formal' (etc) → use that period anchor directly, NO router call
  │     if voice === `user:<anchor_id>` → load user's personal anchor text, use directly
  │
  ├─ Gemini rewrite anchored on the chosen text (unchanged prompt)
  │
  ├─ GPT polish anchored on the same (unchanged prompt)
  │
  ├─ strip AI-vocab
  │
  ▼
PipelineResult (existing shape, plus new field `anchorUsed` for transparency)
```

When the user picks explicitly, we **skip the router LLM call entirely** — saves ~$0.0002 per humanize and ~1 second of latency. (Three calls instead of M21's current four.)

### New components

#### Backend

1. **`UserVoiceAnchor` model** (new):
   ```ts
   {
     id: string;             // 'va_<userId>_<seq>'
     userId: string;
     label: string;          // user-supplied, max 60 chars
     text: string;           // 200–500 words validated
     createdAt: Date;
     wordCount: number;      // computed at save time, persisted for cheap menu render
   }
   ```
   Stored in user profile / Mongo collection alongside existing user fields.

2. **API routes** (additions to `backend/src/api/routes/me/`):
   - `GET /me/voice-anchors` → returns `UserVoiceAnchor[]` for the logged-in user
   - `POST /me/voice-anchors` `{ label, text }` → validate + create (premium-tier-gated)
   - `PATCH /me/voice-anchors/:id` `{ label?, text? }` → edit
   - `DELETE /me/voice-anchors/:id`
   - All gated by existing auth middleware. POST/PATCH gated additionally on `user.tier === 'premium'`.

3. **`humanize` route change** (modifies `backend/src/api/routes/humanize.ts`):
   - Accept `voice?: string` in request body. Values:
     - `undefined` or `'auto'` → today's router behavior
     - `'academic_formal' | 'academic_casual' | 'argumentative' | 'instructional' | 'user_modern' | 'user_narrative'` → period anchor by id
     - `'va_<id>'` → load user's `UserVoiceAnchor` and use its text
   - Validate the user owns any `va_*` id they pass; reject with 403 otherwise.
   - Pass through to `HumanizerService.humanizePipeline(..., voice)`.

4. **`HumanizerService.humanizePipeline` signature change**:
   - Add `voice?: string` last parameter.
   - When `voice` is set, pass it through to `M21.run()` (after extending `MethodOptions` with an optional `voice` field).

5. **`M21_router_anchor.ts` change** (modifies the production method):
   - Add early return inside `pickAnchor`: if `opts.voice` is set, look up the anchor from `ANCHORS` (by id) or load it as a UserVoiceAnchor (resolver injected via service).
   - The router LLM call only runs when `voice` is undefined/auto.
   - Token-step recording: when voice is user-picked, no `gemini_router` step in the result.

#### Frontend

6. **Voice selector component** (new, reusable):
   - Dropdown / segmented control depending on UI design choice.
   - Shows: user anchors (if any) at top in a separate group, then 7 built-in options.
   - Each option has a one-line description for hover/expanded view.
   - Default selection: `'auto'`.
   - Emits `onChange(voice: string)` to parent.

7. **Humanize panel update** (modifies the existing humanize page):
   - Voice selector positioned above the Humanize button, alongside the existing tone/strength/length controls.
   - On submit, sends `voice` in the API request.

8. **Profile / My voice page** (new):
   - List of saved anchors with label, word count, "edit"/"delete" actions.
   - "Add a voice" button → modal with textarea + label input.
   - Live word counter; submit disabled outside 200–500 range.
   - On save, POST to API; on success, reload list.
   - If user is not premium: section is locked with a "Premium feature" badge and an upgrade CTA.

#### Migration

9. **Backwards compatibility:**
   - All existing humanize calls without a `voice` parameter behave exactly as today (router runs).
   - No database migration needed for existing users — `UserVoiceAnchor` is a new collection that just doesn't have rows for existing users.
   - Existing humanize history records don't need backfill; the `voice` field is forward-only.

---

## Anchor option labels (proposed UI copy)

| Internal id | UI label | One-line description |
|---|---|---|
| `auto` | Let AI decide | Recommended. Picks the best register automatically. |
| `academic_formal` | Formal academic | Abstract, analytical. Philosophy, theory, technical exposition. |
| `academic_casual` | Casual academic | Educational, addressed to a reader. News articles, lectures. |
| `argumentative` | Argumentative | Polemic, opinion, taking a side. |
| `instructional` | Instructional | How-to guides, tutorials, business memos, formal procedures. |
| `user_modern` | Modern reflection | "What I think about X" — modern opinion writing. |
| `user_narrative` | Personal story | First-person experience, specific moments, blog posts. |
| `va_<id>` | (user-supplied label) | "Your saved voice from <date>" |

Labels are deliberately use-case-oriented, not author-oriented (no "Russell-style" or "Mill-style" jargon). Users care about *what they're writing*, not the source author of the anchor.

---

## Validation, edge cases, errors

- **Voice param doesn't match any known anchor or user va_id:** fall back to `auto` and log a warning. Don't error.
- **User passes a `va_*` id they don't own:** 403, "voice anchor not found." Don't reveal existence.
- **Premium user downgrades:** their saved voice anchors are NOT deleted (so they can re-upgrade). They cannot pick them in the humanize UI — the dropdown filters them out for non-premium. Admin can verify this is the desired behavior.
- **Word count out of range** (POST/PATCH): 400, "voice anchor must be between 200 and 500 words. You provided X."
- **Anchor text looks AI-generated** (statistical scorer score > 80): not blocked, but warn user before save: "this looks AI-generated. For best results, paste writing you composed yourself." User can override.
- **Anchor labels:** trimmed, max 60 chars, must be non-empty after trim. Allow Unicode (some users will use non-Latin labels).
- **Empty text after stripping:** rejected with 400.
- **Concurrent saves:** standard Mongo append; no cross-anchor invariants to enforce.

---

## Cost & latency impact

| Scenario | LLM calls | Cost vs today's M21 |
|---|---:|---|
| Today (auto) | 3 | baseline ($0.0025) |
| New default (auto) | 3 | identical |
| User picks period anchor | **2** | **−$0.0002** (router skipped) |
| User picks personal anchor | **2** | **−$0.0002** |

User-picked variants are slightly cheaper because we skip the router. Latency drops by ~1 second when user picks (no router round-trip).

Storage: each user voice anchor is ~3 KB. 3 anchors per premium user = ~9 KB. Negligible.

---

## Why this is the right next move

The v13 multi-seed variance test proved that prompt engineering on top of M21 is in the noise. The v11 Tier-1 experiment proved that "anchors must be statistically out of LLM distribution" is the load-bearing principle. **Per-user anchors are the strongest possible expression of that principle** — the user's writing is unique to them, so it's by definition out of any detector's training set.

The MVP voice-selector change is small (single dropdown + parameter pass-through) but it removes the only mystery in the current pipeline: when M21 fails, the user has no recourse. With voice selection, they can retry with a different anchor and get genuinely different output. That alone will lift perceived reliability even before per-user anchors land.

---

## Out of scope (explicit, for future work)

- **Multiple personal anchors per humanize** (anchor blending) — eliminated as M18.
- **Anchor recommendation from past humanize history** — privacy + complexity, separate spec.
- **Auto-detection of input register to pre-fill the voice selector** — could improve UX but adds an LLM call; defer.
- **Voice anchor sharing between users** — moderation problem, defer.
- **Voice quality scoring / preview** — show user a sample of how their voice anchor would rewrite a canned text. Nice-to-have, defer.

---

## Open questions for the next session

1. **Premium pricing & gating mechanism.** This spec assumes `user.tier === 'premium'` exists or will be added — confirm with the business side.
2. **Voice-anchor word-count thresholds.** 200–500 words is a guess based on the existing period anchors (each ~300 words). Could be wider (100–1000) or narrower (250–400). Worth a quick experiment with a test user's writing at different lengths.
3. **Storage choice.** Is the user profile in Mongo (matching project pattern) or somewhere else? Default assumption is Mongo collection alongside existing `User` records.
4. **Frontend framework patterns.** The Voice selector should match existing tone/strength control styling. Whoever does the UI work can decide on dropdown vs segmented vs cards.

---

## Implementation plan to be written separately

This spec stops at the "what" and "why." The "how" — task-by-task implementation — belongs in a follow-up plan document under `docs/superpowers/plans/`. The plan should cover:

1. Backend model + routes (api + persistence)
2. M21 modification + service layer changes
3. Frontend Voice selector component
4. Humanize panel integration
5. My-voice profile page (premium-gated)
6. Tests at each layer
7. Documentation update for the existing handoff to reflect the new state

Estimated implementation effort: **5–8 days** for one engineer end-to-end (backend ~2 days, frontend ~2 days, tests + polish + premium gating ~1–4 days depending on existing tier infrastructure).
