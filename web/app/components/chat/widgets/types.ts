// web/app/components/chat/widgets/types.ts
export type CardOption = {
  value: string;
  label: string;
  description?: string;
  icon?: string | null;
};

export type CardGridHint = {
  widget_type: "card_grid";
  field_name: string;
  title: string;
  options: CardOption[];
  columns?: number;
  // When true the widget tracks a Set of picks and only fires onSelect on
  // Submit, sending a comma-joined string of values + a human-readable label.
  // Used by M2 phase3 gap selection where users routinely pick 2-3 gaps.
  multi_select?: boolean;
};

// SP4: list_editor variant
export type ListItem = {
  id: string;
  text: string;
  sub_items?: ListItem[];
  meta?: Record<string, unknown>;
};

export type ListEditorHint = {
  widget_type: "list_editor";
  field_name: string;
  title: string;
  initial_items: ListItem[];
  allow_nested?: boolean;
  confirm_label?: string;
  reset_label?: string;
};

// flow_chart variant — design merge (2026-06). The M3 conceptual_model
// widget used to be two separate bubbles (list_editor for paths, then
// another list_editor for scale items per construct). Splitting them
// produced an empty-second-widget bug and asked the user to repeat the
// same construct list twice. flow_chart ships nodes (constructs with
// attached Likert items) + edges (hypothesis paths with effect_type) in
// one canvas so structure + measurement co-exist. Mirrors Survify's
// AdvanceModelType. Confirm emits {nodes:[...], edges:[...]} which is
// the new on-the-wire shape for the `conceptual_model` schema field.
export type FlowChartNode = {
  id: string;
  label: string;
  questions: string[];
};

export type FlowChartEdge = {
  id: string;
  source: string;
  target: string;
  hypothesis: string;
  effect_type: "positive" | "negative";
};

export type FlowChartHint = {
  widget_type: "flow_chart";
  field_name: string;
  title: string;
  initial_nodes: FlowChartNode[];
  initial_edges: FlowChartEdge[];
  confirm_label?: string;
  reset_label?: string;
};

// Foundational citations panel (Home.html design). Surfaces a structured
// view of seminal papers grouped by theoretical camp, each with a page-
// cited quote and clickable DOI / PDF links. Emitted by the v3 agent via
// the `[PAPERS] {json} [/PAPERS]` marker (see agent/runtime.py).
export type PapersPanelPaper = {
  id: string;                  // stable id (used by onCite/onFlag callbacks)
  author: string;              // first-author or "Author et al."
  year: number | string;
  title: string;
  venue?: string;              // journal/conference name
  vol?: string;                // volume/issue/pages
  doi?: string;                // bare DOI ("10.1016/…") — UI prepends https://doi.org/
  pdf_url?: string;            // direct PDF link; UI appends #page=N when page is set
  cites?: number;              // citation count
  page?: number;               // page the quote came from
  quote?: string;              // the page-cited extract (rendered as a blockquote)
  seminal?: boolean;           // adds the ⭐ corner badge
};

export type PapersPanelCamp = {
  id: string;                  // stable id (used for collapse state)
  label: string;               // ALL-CAPS header text ("STIMULUS-ORGANISM-RESPONSE")
  papers: PapersPanelPaper[];
};

export type PapersPanelHint = {
  widget_type: "papers_panel";
  title?: string;              // header label (defaults to "Foundational citations")
  style?: string;              // citation-style label shown top-right ("APA 7")
  indexed_count?: number;      // shown next to the seminal count
  footer_note?: string;        // small line in the footer strip
  camps: PapersPanelCamp[];
};


// User-message attachment chips. Persisted on the user Message row
// (tool_calls_json) by chat_v3.send_message_v3 so MessageBubble can render
// linked-file chips on reload. Not interactive — pure display.
export type AttachmentChipMeta = {
  upload_id: string;
  filename: string;
  size_bytes?: number | null;
  mime_type?: string | null;
};

export type AttachmentsHint = {
  attachments: AttachmentChipMeta[];
};

// Export artifact download card (Claude-artifact style). Emitted by the v3
// runtime when export_docx succeeds, persisted on the assistant Message so the
// DOCX/PDF download links appear IN the chat message, not only the panel.
export type ExportArtifact = {
  kind: string;              // "docx" | "pdf"
  download_url: string;      // /api/v1/projects/{pid}/exports/{filename}
  size_bytes?: number;
  s3_key?: string;
};

export type ExportArtifactsHint = {
  widget_type: "export_artifacts";
  artifacts: ExportArtifact[];
};

// Reconstructed upstream modules (backfill). Emitted when the
// backfill_upstream_modules tool infers the earlier steps behind a student's
// existing work. Each item is a CANDIDATE the student confirms/edits inline;
// confirm posts to /mid-journey-import/confirm (needs the project id, threaded
// from ChatPane). `items` mirrors ReconstructedModule from ../ReconstructedModules.
export type ReconstructedModuleItem = {
  module: string;
  candidate: Record<string, unknown>;
  rationale?: string | null;
  ready_to_confirm: boolean;
  review: string[];
};

export type ReconstructedModulesHint = {
  widget_type: "reconstructed_modules";
  items: ReconstructedModuleItem[];
  /** What the tool actually committed per module. A backfill too thin to earn
   *  a `done` lands `in_progress`, and the card says so rather than showing
   *  every module as finished. */
  saved?: { module: string; status: string }[];
};

// A single turn can emit several widgets (e.g. an export download card AND a
// papers panel). When there's more than one, the backend wraps them in this so
// none clobbers another; WidgetRenderer expands it.
export type MultiHint = {
  widget_type: "multi";
  widgets: WidgetHint[];
};

// Discriminated union — future variants (e.g. canvas_editor) land here.
export type WidgetHint =
  | CardGridHint
  | ListEditorHint
  | FlowChartHint
  | PapersPanelHint
  | AttachmentsHint
  | ExportArtifactsHint
  | ReconstructedModulesHint
  | MultiHint;

export type WidgetSelectHandler = (
  fieldName: string,
  value: string,
  label: string,
) => void;
