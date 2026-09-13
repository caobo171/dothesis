import { describe, expect, test } from "vitest";
import {
  conceptualModelSvg, layoutConceptualModel, moderatedPath, parseModelFlowchart,
} from "./conceptualModelLayout";

const NODES = [
  { id: "EXP", label: "Chuyên môn của influencer", type: "independent" },
  { id: "INT", label: "Ý định du lịch", type: "mediator" },
  { id: "DEC", label: "Quyết định du lịch", type: "dependent" },
  { id: "INC", label: "Thu nhập", type: "moderator" },
];
const EDGES = [
  { effect: "direct", source: "EXP", target: "INT", hypothesis: "H1: +" },
  { effect: "direct", source: "INT", target: "DEC", hypothesis: "H7: +" },
  { effect: "direct", source: "INC", target: "DEC", hypothesis: "H8: +" },
  { effect: "moderates", source: "INC", target: "INT",
    hypothesis: "H9: moderates INT→DEC" },
];

const at = (l: ReturnType<typeof layoutConceptualModel>, id: string) =>
  l!.boxes.find(b => b.id === id)!;

describe("layoutConceptualModel", () => {
  test("puts each node one column past what feeds it", () => {
    const l = layoutConceptualModel(NODES, EDGES)!;
    expect(at(l, "EXP").x).toBeLessThan(at(l, "INT").x);
    expect(at(l, "INT").x).toBeLessThan(at(l, "DEC").x);
  });

  test("a moderator does not push the node it moderates into another column", () => {
    // Depth is computed over SOLID edges only. Counting the moderation edge
    // would shove INT right of its own predictors and bend every arrow.
    const l = layoutConceptualModel(NODES, EDGES)!;
    const withoutMod = layoutConceptualModel(NODES, EDGES.slice(0, 3))!;
    expect(at(l, "INT").x).toBe(at(withoutMod, "INT").x);
  });

  test("the moderator's arrow lands ON the moderated path, not on a box", () => {
    const l = layoutConceptualModel(NODES, EDGES)!;
    const dashed = l.arrows.filter(a => a.dashed);
    expect(dashed).toHaveLength(1);

    const h7 = l.arrows.find(a => a.label === "H7")!;
    const midpoint = { x: (h7.from.x + h7.to.x) / 2, y: (h7.from.y + h7.to.y) / 2 };
    expect(dashed[0].to).toEqual(midpoint);
    // Not into INT's or DEC's box edge — that would be a different hypothesis.
    expect(dashed[0].to.x).not.toBe(at(l, "DEC").x);
  });

  test("the moderator's own direct effect is still a solid arrow", () => {
    const l = layoutConceptualModel(NODES, EDGES)!;
    const h8 = l.arrows.find(a => a.label === "H8")!;
    expect(h8.dashed).toBe(false);
    expect(h8.to.x).toBe(at(l, "DEC").x);
  });

  test("labels are shortened to the hypothesis id", () => {
    const l = layoutConceptualModel(NODES, EDGES)!;
    expect(l.arrows.map(a => a.label).sort()).toEqual(["H1", "H7", "H8", "H9"]);
  });

  test("the two arrows leaving the moderator do not start at the same point", () => {
    const l = layoutConceptualModel(NODES, EDGES)!;
    const h8 = l.arrows.find(a => a.label === "H8")!;
    const h9 = l.arrows.find(a => a.label === "H9")!;
    expect(h9.from.y).not.toBe(h8.from.y);
  });

  test("a long construct name wraps instead of overflowing its box", () => {
    const l = layoutConceptualModel(NODES, EDGES)!;
    expect(at(l, "EXP").lines.length).toBeGreaterThan(1);
    expect(at(l, "INT").lines).toEqual(["Ý định du lịch"]);
  });

  test("a model with no drawable relationship is not a figure", () => {
    expect(layoutConceptualModel(NODES, [])).toBeNull();
    expect(layoutConceptualModel([], EDGES)).toBeNull();
  });

  test("an edge naming an unknown node is skipped, not crashed on", () => {
    const l = layoutConceptualModel(NODES, [
      ...EDGES, { effect: "direct", source: "GHOST", target: "INT", hypothesis: "H99" },
    ])!;
    expect(l.arrows.map(a => a.label)).not.toContain("H99");
  });
});

describe("moderatedPath", () => {
  const valid = new Set(["INT", "DEC", "INC"]);
  const pairs: [string, string][] = [["INT", "DEC"]];

  test("reads the path out of the hypothesis text", () => {
    expect(moderatedPath({ hypothesis: "H9: moderates INT→DEC" }, pairs, valid))
      .toEqual(["INT", "DEC"]);
  });

  test("falls back to what leaves the anchor node when no path is named", () => {
    expect(moderatedPath({ target: "INT", hypothesis: "H9" }, pairs, valid))
      .toEqual(["INT", "DEC"]);
  });

  test("returns null rather than guessing when nothing connects", () => {
    expect(moderatedPath({ target: "INC", hypothesis: "H9" }, [], valid)).toBeNull();
  });
});

describe("parseModelFlowchart", () => {
  // Verbatim shape the agent writes into its chat replies.
  const AGENT_WROTE = [
    "flowchart LR",
    '  EXP["Chuyên môn"]',
    '  INT["Ý định du lịch"]',
    '  DEC["Quyết định du lịch"]',
    '  INC["Thu nhập"]',
    "  EXP -->|H1: +| INT",
    "  INT -->|H7: +| DEC",
    "  INC -->|H8: +| DEC",
    "  INC -.->|H9: điều tiết INT → DEC| INT",
  ].join("\n");

  test("reads the model back out of a hand-written flowchart", () => {
    const model = parseModelFlowchart(AGENT_WROTE)!;
    expect(model.nodes.map(n => n.id)).toEqual(["EXP", "INT", "DEC", "INC"]);
    expect(model.edges).toHaveLength(4);
  });

  test("a dotted arrow is a moderation, and lands on the path it names", () => {
    const model = parseModelFlowchart(AGENT_WROTE)!;
    const l = layoutConceptualModel(model.nodes, model.edges)!;
    const dashed = l.arrows.filter(a => a.dashed);
    expect(dashed).toHaveLength(1);

    const h7 = l.arrows.find(a => a.label === "H7")!;
    expect(dashed[0].to).toEqual({
      x: (h7.from.x + h7.to.x) / 2, y: (h7.from.y + h7.to.y) / 2,
    });
  });

  test("infers the outcome node so it is tinted like the exported figure", () => {
    const model = parseModelFlowchart(AGENT_WROTE)!;
    const byId = Object.fromEntries(model.nodes.map(n => [n.id, n.type]));
    expect(byId.DEC).toBe("dependent");
    expect(byId.INT).toBe("");      // INT has outgoing edges — a mediator
  });

  test("hands back anything it has no layout for", () => {
    // Mermaid keeps these; we must not half-render a diagram we cannot draw.
    expect(parseModelFlowchart("sequenceDiagram\n  A->>B: hi")).toBeNull();
    expect(parseModelFlowchart("flowchart LR\n  subgraph S\n  A --> B\n  end")).toBeNull();
    expect(parseModelFlowchart("flowchart LR\n  A --> B\n  classDef x fill:#fff")).toBeNull();
    expect(parseModelFlowchart("")).toBeNull();
  });

  test("a lone node with no relationship is not a model", () => {
    expect(parseModelFlowchart('flowchart LR\n  A["only"]')).toBeNull();
  });
});

describe("conceptualModelSvg", () => {
  test("escapes label text rather than trusting it as markup", () => {
    const svg = conceptualModelSvg(
      [{ id: "A", label: '<script>x</script> & "q"' }, { id: "B", label: "B" }],
      [{ source: "A", target: "B", hypothesis: "H1" }],
    )!;
    expect(svg).not.toContain("<script>");
    expect(svg).toContain("&lt;script&gt;");
    expect(svg).toContain("&amp;");
  });

  test("is null for a model with nothing to draw", () => {
    expect(conceptualModelSvg([], [])).toBeNull();
  });
});

describe("construct abbreviations", () => {
  test("each box carries its code above the name", () => {
    const l = layoutConceptualModel(NODES, EDGES)!;
    expect(at(l, "EXP").code).toBe("EXP");
    expect(at(l, "EXP").lines[0]).toContain("Chuyên môn");

    const svg = conceptualModelSvg(NODES, EDGES)!;
    expect(svg).toContain(">EXP<");
    expect(svg).toContain(">INT<");
  });

  test("no code line when the id IS the name — that would print it twice", () => {
    const plain = [{ id: "Alpha", label: "Alpha" }, { id: "Beta", label: "Beta" }];
    const l = layoutConceptualModel(plain, [{ source: "Alpha", target: "Beta" }])!;
    expect(l.boxes.every(b => b.code === "")).toBe(true);
  });

  test("the box is tall enough for a code plus a wrapped name", () => {
    const l = layoutConceptualModel(NODES, EDGES)!;
    const tallest = Math.max(...l.boxes.map(b => b.lines.length));
    // 30 for the code line + 32 per name line must fit inside the box.
    expect(30 + tallest * 32).toBeLessThanOrEqual(l.boxH);
  });
});

describe("the shape the agent actually writes", () => {
  // Copied verbatim out of a stored assistant message. The agent declares both
  // nodes ON the edge line — `EXP[Chuyên môn] -->|H1: +| INT[Ý định du lịch]` —
  // not above it. A parser that required bare ids matched none of these lines,
  // so the whole diagram fell back to Mermaid and kept the old notation.
  const REAL = [
    "flowchart LR",
    "    EXP[Chuyên môn] -->|H1: +| INT[Ý định du lịch]",
    "    ATT[Độ thu hút] -->|H2: +| INT",
    "    ECONN[Kết nối cảm xúc] -->|H3: +| INT",
    "    INSP[Truyền cảm hứng] -->|H4: +| INT",
    "    TRUST[Sự tin cậy] -->|H5: +| INT",
    "    SIMI[Sự tương đồng] -->|H6: +| INT",
    "    INT -->|H7: +| DEC[Quyết định du lịch]",
    "    INC[Thu nhập] -->|H8: +| DEC",
    "    INC -.->|H9: điều tiết INT → DEC| INT",
  ].join("\n");

  test("is parsed, with every construct keeping its name", () => {
    const m = parseModelFlowchart(REAL)!;
    expect(m).not.toBeNull();
    const byId = Object.fromEntries(m.nodes.map(n => [n.id, n.label]));
    expect(byId).toMatchObject({
      EXP: "Chuyên môn", INT: "Ý định du lịch", DEC: "Quyết định du lịch",
      INC: "Thu nhập", SIMI: "Sự tương đồng",
    });
  });

  test("a later bare mention does not blank the name the first line gave it", () => {
    // `INT` appears with its label once and bare six times.
    expect(parseModelFlowchart(REAL)!.nodes.find(n => n.id === "INT")!.label)
      .toBe("Ý định du lịch");
  });

  test("and the moderator lands on the path, not on the mediator box", () => {
    const m = parseModelFlowchart(REAL)!;
    const l = layoutConceptualModel(m.nodes, m.edges)!;
    const dashed = l.arrows.filter(a => a.dashed);
    expect(dashed).toHaveLength(1);
    const h7 = l.arrows.find(a => a.label === "H7")!;
    expect(dashed[0].to).toEqual({
      x: (h7.from.x + h7.to.x) / 2, y: (h7.from.y + h7.to.y) / 2,
    });
  });

  test("every box still carries its code", () => {
    const m = parseModelFlowchart(REAL)!;
    const svg = conceptualModelSvg(m.nodes, m.edges)!;
    for (const code of ["EXP", "ATT", "ECONN", "INSP", "TRUST", "SIMI", "INT", "INC", "DEC"]) {
      expect(svg).toContain(`>${code}<`);
    }
  });
});

describe("how the figure is sized", () => {
  test("leaves sizing to the attribute, never an inline style", () => {
    const svg = conceptualModelSvg(NODES, EDGES)!;
    // The viewer's expand overlay fits the diagram by overriding width/height
    // from CSS. An inline style outranks a class, so `style="width:100%"` here
    // made the Fit button do nothing and the model opened taller than the
    // screen with no way to see it whole.
    expect(svg).not.toMatch(/style="[^"]*width/);
    expect(svg).not.toMatch(/style="[^"]*height/);
    expect(svg).toContain('width="100%"');
  });

  test("carries a viewBox, so height follows from the aspect ratio", () => {
    const svg = conceptualModelSvg(NODES, EDGES)!;
    const l = layoutConceptualModel(NODES, EDGES)!;
    expect(svg).toContain(`viewBox="0 0 ${l.width} ${l.height}"`);
    // Only the ROOT tag — the arrowhead markers legitimately carry their own.
    const root = svg.slice(0, svg.indexOf(">") + 1);
    expect(root).not.toMatch(/\sheight=/);
  });
});
