/**
 * Expert personas a student can consult mid-thread.
 *
 * The chat used to route through a single "master" agent that owned every
 * skill across M1–M5. The design moves to a chooser: the same backend
 * agent, but the user picks a specialist persona (Methodologist,
 * Statistician, Lit reviewer, …) for the turn. The picker biases the
 * agent's response by prefixing the user message with a persona directive
 * — no backend change, no extra token cost, and the conversation stays in
 * one thread.
 *
 * `modules` lists where the expert is suggested first. `sample` is the
 * one-line example shown under each row in the picker so a student knows
 * what to ask.
 */

export type ExpertId =
  | "methodologist"
  | "statistician"
  | "lit-reviewer"
  | "writing-coach"
  | "citations"
  | "peer-reviewer";

export type ModuleId = "M1" | "M2" | "M3" | "M4" | "M5";

export type Expert = {
  id: ExpertId;
  /** Single-glyph initial rendered inside a primary-blue square avatar. */
  avatar: string;
  name: string;
  /** One-line capability summary shown next to the name. */
  tagline: string;
  /** Modules this expert is the suggested specialist for. */
  modules: ModuleId[];
  /** Example question shown under the row in the picker. */
  sample: string;
  /** Persona directive prefixed to outgoing user messages while active. */
  directive: string;
};

export const EXPERTS: Expert[] = [
  {
    id: "methodologist",
    avatar: "M",
    name: "Methodologist",
    tagline: "Research design, paradigms, sampling logic",
    modules: ["M1", "M3"],
    sample: "Why PLS-SEM over CB-SEM here?",
    directive:
      "Answer as a Methodologist — focus on research design choices, " +
      "paradigm fit, sampling logic, and trade-offs between competing " +
      "designs. Justify each recommendation against the project's RQs.",
  },
  {
    id: "statistician",
    avatar: "Σ",
    name: "Statistician",
    tagline: "Tests, assumptions, effect sizes, interpretation",
    modules: ["M4"],
    sample: "Interpret these CFA loadings for me",
    directive:
      "Answer as a Statistician — call out assumptions, name the test, " +
      "report effect sizes alongside p-values, and explain what the " +
      "numbers mean for the hypotheses (not just whether they're significant).",
  },
  {
    id: "lit-reviewer",
    avatar: "¶",
    name: "Literature reviewer",
    tagline: "Camps, gaps, theoretical mapping",
    modules: ["M2"],
    sample: "Map my 41 papers into camps",
    directive:
      "Answer as a Literature reviewer — organize sources into theoretical " +
      "camps, surface defensible gaps with citations, and ground every " +
      "claim in a specific paper + page where possible.",
  },
  {
    id: "writing-coach",
    avatar: "§",
    name: "Writing coach",
    tagline: "Voice, structure, signposting, APA style",
    modules: ["M5"],
    sample: "Tighten my §2.3 paragraph",
    directive:
      "Answer as a Writing coach — critique voice, structure, and " +
      "signposting; rewrite for clarity in academic register; flag APA " +
      "style issues. Keep the student's argument, sharpen the prose.",
  },
  {
    id: "citations",
    avatar: "\"",
    name: "Citation manager",
    tagline: "DOI lookup, page verify, APA/IEEE formatting",
    modules: ["M2", "M5"],
    sample: "Verify all unverified page numbers",
    directive:
      "Answer as a Citation manager — resolve DOIs, verify page numbers, " +
      "normalize formatting to the project's citation style, and flag " +
      "anything you can't verify rather than fabricating it.",
  },
  {
    id: "peer-reviewer",
    avatar: "⚖",
    name: "Peer-review simulator",
    tagline: "Read like a reviewer — what would they ask?",
    modules: ["M2", "M3", "M5"],
    sample: "Stress-test my hypotheses",
    directive:
      "Answer as a Peer-review simulator — read adversarially. Name the " +
      "weakest claim, predict the reviewer's first objection, and suggest " +
      "the minimum change that would defuse it.",
  },
];

export function getExpert(id: string | null | undefined): Expert | undefined {
  if (!id) return undefined;
  return EXPERTS.find(e => e.id === id);
}

/**
 * Prefix the user's outgoing message with the expert's persona directive.
 * The agent sees the directive as the first paragraph of the user turn and
 * tunes its reply accordingly. We keep it user-visible (not hidden in a
 * system field) so the chat transcript is self-explanatory if the student
 * reads it later.
 */
export function applyExpertPersona(text: string, expert: Expert | undefined | null): string {
  if (!expert) return text;
  return `[Consulting ${expert.name}] ${expert.directive}\n\n${text}`;
}
