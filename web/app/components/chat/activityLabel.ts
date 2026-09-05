import type { MessageKey } from "@/app/lib/i18n/messages/en";

/**
 * Turn one activity beat from a run into a sentence a student can read.
 *
 * The runner writes `tool: <name>` (api/app/headless_entry.py, on every
 * `tool_start`), and that string is deliberately a machine fact: the partner
 * API reads it back as a run's `current`. It was also being rendered, verbatim,
 * on the screen a student watches for twenty minutes — a thesis in Vietnamese
 * with "tool: research_scout" as its only sign of life.
 *
 * So the event stays as it is and the translation happens here, at the edge,
 * where there is a locale.
 */
export const TOOL_LABEL_KEYS: Record<string, MessageKey> = {
  // M1-M2 — reading the field
  research_scout: "run.tool.research_scout",
  quick_sources: "run.tool.quick_sources",
  parse_reference: "run.tool.parse_reference",
  topic_feasibility: "run.tool.topic_feasibility",
  // M3 — instrument and sampling
  audit_instrument: "run.tool.audit_instrument",
  sampling_plan: "run.tool.sampling_plan",
  consent_notice: "run.tool.consent_notice",
  make_google_form_script: "run.tool.make_google_form_script",
  methods_preflight: "run.tool.methods_preflight",
  render_model_diagram: "run.tool.render_model_diagram",
  // M4 — the numbers
  run_stats: "run.tool.run_stats",
  check_thresholds: "run.tool.check_thresholds",
  parse_output_table: "run.tool.parse_output_table",
  parse_smartpls_export: "run.tool.parse_smartpls_export",
  render_verified_sections: "run.tool.render_verified_sections",
  // M5 — writing and shipping
  export_docx: "run.tool.export_docx",
  humanize_text: "run.tool.humanize_text",
  review_thesis: "run.tool.review_thesis",
  generate_committee_questions: "run.tool.generate_committee_questions",
  set_defense_date: "run.tool.set_defense_date",
  // Cross-cutting
  read_slice: "run.tool.read_slice",
  commit_slice: "run.tool.commit_slice",
  backfill_upstream_modules: "run.tool.backfill_upstream_modules",
  ingest_advisor_feedback: "run.tool.ingest_advisor_feedback",
  mark_feedback_addressed: "run.tool.mark_feedback_addressed",
  flag_blocker: "run.tool.flag_blocker",
  resolve_blocker: "run.tool.resolve_blocker",
};

const TOOL_PREFIX = "tool:";

export function activityLabel(text: string, t: (key: MessageKey) => string): string {
  if (!text) return text;
  if (!text.startsWith(TOOL_PREFIX)) return text;   // already a sentence
  const name = text.slice(TOOL_PREFIX.length).trim();
  // An unmapped name falls back rather than rendering: a tool added to
  // agent/runtime.py must not be able to put its internal id on screen just by
  // existing.
  return t(TOOL_LABEL_KEYS[name] ?? "run.tool.unknown");
}
