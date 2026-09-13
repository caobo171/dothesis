"use client";

import { conceptualModelSvg, type ModelEdge, type ModelNode }
  from "./conceptualModelLayout";

/**
 * The research model, drawn the way the exported thesis draws it.
 *
 * Replaces the Mermaid rendering. Mermaid chose its own layout and could not
 * put an arrow onto another arrow, so a moderator had to be faked with a
 * junction node and the on-screen picture never matched the Word figure — two
 * drawings of one model, disagreeing with each other.
 *
 * The markup comes from `conceptualModelSvg`, which the chat bubble's diagram
 * viewer uses too, so there is exactly one renderer behind every place this
 * model appears.
 */
export function ConceptualModelFigure(
  { nodes, edges }: { nodes: ModelNode[]; edges: ModelEdge[] },
) {
  const svg = conceptualModelSvg(nodes ?? [], edges ?? []);
  if (!svg) return null;
  // Our own markup, built from escaped labels — no caller-supplied HTML.
  return (
    <div
      data-testid="conceptual-model-figure"
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}
