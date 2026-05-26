// web/app/components/chat/widgets/synthesize.ts
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
