// web/app/components/chat/widgets/synthesize.ts
import type { ListItem } from "./types";

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
  };
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

    default:
      // Generic bulleted fallback for unknown fields.
      return items.map(i => `- ${i.text}`).join("\n");
  }
}
