// web/app/components/chat/widgets/synthesize.ts
import type { FlowChartEdge, FlowChartNode, ListItem } from "./types";

/**
 * Build a natural-language user message from a widget selection.
 *
 * Backend's ModuleAgent._extract_answer parses free-text replies via an
 * LLM call into structured field values. We craft a sentence that's
 * unambiguous to that extractor and readable as a chat message.
 */
export function synthesizeWidgetSelection(
  fieldName: string,
  value: string,
  label: string,
): string {
  const descriptors: Record<string, string> = {
    field: `I'd like to study ${label}.`,
    research_type: `I'll use a ${label.toLowerCase()} approach.`,
    // Module confirmation widget — backend's _is_affirmative checks for "yes"
    // exactly, so send the raw value (which is always "yes" or "no") so the
    // click round-trips into the confirm/reject path without rephrasing.
    _confirm: value,
  };

  // W2/W5: M2 phase3 multi-select sends value="1,3" for picked gap IDs, or
  // free text from the Other input for a custom gap. Dispatch by whether
  // the value is purely digits + commas + whitespace.
  if (fieldName === "selected_gap_ids") {
    if (/^[\d,\s]+$/.test(value) && /\d/.test(value)) {
      const ids = value.split(",").map(v => v.trim()).filter(Boolean);
      const phrase = ids.length === 1
        ? `gap ${ids[0]}`
        : ids.slice(0, -1).map(i => `gap ${i}`).join(", ")
          + ` and gap ${ids[ids.length - 1]}`;
      return `I'll use ${phrase}.`;
    }
    // Free text — route to add_custom_gap. Phrase chosen so the LLM
    // classifier picks add_custom_gap unambiguously (matches the prompt
    // example for that action).
    return `Add a new gap: ${value}.`;
  }

  // W4: M2 phase4 reference verification. Preset values map cleanly; the
  // Other text input carries a page number that gets wrapped into the
  // 'page <n>' shape the backend regex extracts.
  if (fieldName === "reference_verify") {
    switch (value) {
      case "yes":
        return "Yes, the page is correct.";
      case "skip":
        return "Skip this reference.";
      case "skip_all":
        return "Skip all remaining references.";
      default: {
        // User typed a page number (possibly with 'p.' prefix). Strip non-
        // digits and re-emit as 'page N' so the classifier's `page\s+(\d+)`
        // regex extracts the corrected_page reliably.
        const n = (value.match(/\d+/) || [""])[0];
        if (!n) return `Correct page: ${value}.`;
        return `The correct page is page ${n}.`;
      }
    }
  }

  // W3: M2 phase2 confirm/refine/navigate. Preset values get mapped to the
  // intent classifier's confirm/navigate actions; any other (free-text) value
  // came from the Other text input and must route to refine.
  if (fieldName === "research_state_confirm") {
    switch (value) {
      case "confirm":
        return "Yes, this synthesis works — let's continue.";
      case "navigate":
        return "Go back to the literature search step.";
      default:
        // Free-form refinement from the Other input — keep the typed text
        // verbatim so the LLM can act on it.
        return `Refine the synthesis: ${value}.`;
    }
  }

  // W1/W5: M2 phase1 fork. Preset values map to confirm/skip per the phase1
  // intent context; anything else came from the Other text input and must
  // route to refine (the classifier maps 'something else' off the preset
  // path to refine).
  if (fieldName === "familiarize_choice") {
    switch (value) {
      case "use_papers":
        return "Yes, use my uploaded papers as sources.";
      case "ai_search":
        return "Please use AI search to find citations for me.";
      case "both":
        return "Use my uploaded papers and also add AI-discovered citations.";
      case "upload_first":
        return "I want to upload my own papers first — pause here.";
      default:
        return `Something else for the literature step: ${value}.`;
    }
  }

  return descriptors[fieldName] ?? label;
}


/**
 * Build a bulleted final-state message from a ListEditorWidget's confirmed
 * items. The agent's _extract_answer parses this back into structured data.
 *
 * Per-field formatters keep the output unambiguous to the LLM extractor.
 */
export function summarizeList(items: ListItem[], fieldName: string): string {
  switch (fieldName) {
    case "themes":
      return [
        "My themes are:",
        ...items.map(t => {
          const subs = (t.sub_items ?? []).map(s => s.text).join(", ");
          return subs ? `- ${t.text} (Sub: ${subs})` : `- ${t.text}`;
        }),
      ].join("\n");

    case "scale_items":
      return [
        "My scale items:",
        ...items.flatMap(c => [
          `Construct ${c.text}:`,
          ...(c.sub_items ?? []).map(i => `- ${i.text}`),
        ]),
      ].join("\n");

    case "purposive_criteria":
      return [
        "My sampling criteria:",
        ...items.map(c => `- ${c.text}`),
      ].join("\n");

    case "interview_guide":
      return [
        "My interview guide:",
        ...items.flatMap(q => [
          q.text,
          ...(q.sub_items ?? []).map(p => `  Probe: ${p.text}`),
        ]),
      ].join("\n");

    case "conceptual_model":
      return [
        "My conceptual model paths:",
        ...items.map(p => {
          const h = (p.meta?.hypothesis as string | undefined) ?? "";
          return h ? `- ${p.text} (${h})` : `- ${p.text}`;
        }),
      ].join("\n");

    case "analysis_outline":
    case "outline_quant":
    case "outline_qual":
      // Numbered list with inline thresholds for SP5 analysis outline fields.
      // If meta.thresholds is present, append " — {threshold}" to the item text.
      return [
        "My analysis outline:",
        ...items.map((s, i) => {
          const thresholds = (s.meta?.thresholds as string | undefined);
          return thresholds
            ? `${i + 1}. ${s.text} — ${thresholds}`
            : `${i + 1}. ${s.text}`;
        }),
      ].join("\n");

    case "objectives":
      // M1 — labeled header lets _extract_answer parse bulleted list[str]
      // unambiguously. Without the header the bare bullets read as a
      // clarifying question and extraction returns null → infinite loop.
      return [
        "My research objectives:",
        ...items.map(o => `- ${o.text}`),
      ].join("\n");

    case "research_questions":
      // Same labeled-header pattern as objectives. Each item is itself
      // phrased as a question ending in '?' which is what the LLM extractor
      // expects for this field's schema.
      return [
        "My research questions:",
        ...items.map(q => `- ${q.text}`),
      ].join("\n");

    default:
      // Generic bulleted fallback for unknown fields.
      return items.map(i => `- ${i.text}`).join("\n");
  }
}


/**
 * Build the final-state user message from a FlowChartWidget's confirmed graph.
 *
 * Design merge (2026-06): the M3 `conceptual_model` schema field now carries
 * both hypothesis paths AND per-construct Likert items. The chat message must
 * convey both halves so the backend's _extract_answer LLM call can rebuild
 * the merged {nodes:[{label, questions}], edges:[{...}]} shape from the text
 * alone. We emit two clearly-labeled sections (Paths / Scale items) mirroring
 * the prior two-widget formatters that the M3 extractor was already trained on.
 *
 * Format example:
 *   My conceptual model:
 *   Paths:
 *   - TL → EE (H1: TL positively affects EE)
 *   - TL → Trust [negative] (H2: TL inversely related to Trust)
 *   Scale items:
 *   Construct TL:
 *   - My supervisor inspires me.
 *   - My supervisor articulates a clear vision.
 *   Construct EE:
 *   - I feel engaged at work.
 */
export function summarizeFlowChart(
  nodes: FlowChartNode[],
  edges: FlowChartEdge[],
  _fieldName: string,
): string {
  const idToLabel = new Map<string, string>();
  nodes.forEach(n => idToLabel.set(n.id, n.label));

  const lines: string[] = ["My conceptual model:"];

  if (edges.length > 0) {
    lines.push("Paths:");
    edges.forEach(e => {
      const src = idToLabel.get(e.source) ?? e.source;
      const tgt = idToLabel.get(e.target) ?? e.target;
      // Negative direction is the exceptional case — tag it explicitly so the
      // M3 extractor doesn't fall back to positive (the silent default).
      // Positive paths stay untagged to keep the chat message readable.
      const direction = e.effect_type === "negative" ? " [negative]" : "";
      const h = e.hypothesis ? ` (${e.hypothesis})` : "";
      lines.push(`- ${src} → ${tgt}${direction}${h}`);
    });
  }

  const constructsWithQuestions = nodes.filter(
    n => Array.isArray(n.questions) && n.questions.length > 0,
  );
  if (constructsWithQuestions.length > 0) {
    lines.push("Scale items:");
    constructsWithQuestions.forEach(n => {
      lines.push(`Construct ${n.label}:`);
      n.questions.forEach(q => lines.push(`- ${q}`));
    });
  }

  return lines.join("\n");
}
