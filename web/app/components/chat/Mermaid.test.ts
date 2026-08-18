import { describe, expect, test } from "vitest";

import { normalizeMermaidSource } from "./Mermaid";

describe("normalizeMermaidSource", () => {
  test("quotes generated labels containing theory abbreviations", () => {
    const source = "flowchart TD\nB1[Perceived Usefulness<br>(TAM)] --> B";
    expect(normalizeMermaidSource(source)).toContain(
      'B1["Perceived Usefulness<br/>(TAM)"] --> B',
    );
  });

  test("keeps already quoted labels unchanged", () => {
    const source = 'flowchart TD\nB1["Perceived Usefulness (TAM)"] --> B';
    expect(normalizeMermaidSource(source)).toBe(source);
  });

  test("renames subgraphs that collide with node ids", () => {
    const source = [
      "flowchart TD",
      "A[Input] --> B[Outcome]",
      "subgraph B[Outcome factors]",
      "B1[Usefulness] --> B",
      "end",
      "style B fill:#f9f",
    ].join("\n");

    const normalized = normalizeMermaidSource(source);
    expect(normalized).toContain('subgraph cluster_B["Outcome factors"]');
    expect(normalized).toContain('B["Outcome"]');
    expect(normalized).toContain("style B fill:#f9f");
  });
});
