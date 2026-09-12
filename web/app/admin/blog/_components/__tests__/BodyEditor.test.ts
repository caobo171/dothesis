/**
 * The body editor's job is to hand back the same post it was given.
 *
 * The rich canvas parses markdown into nodes and serializes them back, so
 * anything the serializer cannot express is LOST on save — silently, in the
 * author's own post. These assert the constructs a DoThesis blog body is
 * actually made of survive the trip, and that the one construct that cannot
 * (raw HTML, because the extension runs `html: false`) is detected instead of
 * quietly eaten.
 */
import { Editor } from "@tiptap/core";
import { Table, TableCell, TableHeader, TableRow } from "@tiptap/extension-table";
import StarterKit from "@tiptap/starter-kit";
import { Markdown } from "tiptap-markdown";
import { describe, expect, it } from "vitest";

import { bodyHasRawHtml } from "../BodyEditor";

/** The same extension set BodyEditor mounts. */
function roundTrip(markdown: string): string {
  const editor = new Editor({
    extensions: [
      StarterKit,
      Markdown.configure({ html: false }),
      Table.configure({ resizable: true }),
      TableRow,
      TableHeader,
      TableCell,
    ],
    content: markdown,
  });
  return editor.storage.markdown.getMarkdown();
}

describe("markdown round-trip", () => {
  it("keeps headings as headings", () => {
    expect(roundTrip("## What is methodology\n\nSome prose."))
      .toContain("## What is methodology");
  });

  it("keeps an internal link, which is the whole interlinking strategy", () => {
    const md = "See [what is scientific research](/blog/en/what-is-scientific-research-0011).";
    expect(roundTrip(md)).toContain("(/blog/en/what-is-scientific-research-0011)");
  });

  it("keeps a GFM table", () => {
    const md = "| Method | Use |\n| --- | --- |\n| EFA | Structure |";
    const out = roundTrip(md);
    expect(out).toContain("| Method | Use |");
    expect(out).toContain("| EFA | Structure |");
  });

  it("keeps lists, emphasis and inline code", () => {
    const out = roundTrip("- **bold** item\n- *italic* item\n- `p < 0.05`");
    expect(out).toContain("**bold**");
    expect(out).toContain("*italic*");
    expect(out).toContain("`p < 0.05`");
  });

  it("keeps a fenced code block and its language", () => {
    const out = roundTrip("```r\nlibrary(psych)\n```");
    expect(out).toContain("```r");
    expect(out).toContain("library(psych)");
  });

  it("keeps a blockquote", () => {
    expect(roundTrip("> Methodology explains the logic.")).toContain("> Methodology explains the logic.");
  });
});

describe("raw HTML detection", () => {
  it("flags HTML the serializer would drop", () => {
    expect(bodyHasRawHtml('Text <div class="note">aside</div> more')).toBe(true);
    expect(bodyHasRawHtml("Line<br>break")).toBe(true);
  });

  it("does not flag a maths comparison", () => {
    // The reason this is a tag list and not a `<` scan: statistics prose is
    // full of them, and locking an author out of the rich editor over "p <
    // 0.05" would be a bug in the guard, not a save.
    expect(bodyHasRawHtml("The result was significant (p < 0.05) across groups."))
      .toBe(false);
  });

  it("does not flag tags inside code, which render as code", () => {
    expect(bodyHasRawHtml("Use ```\n<div>example</div>\n``` in your template")).toBe(false);
    expect(bodyHasRawHtml("The `<br>` tag forces a line break.")).toBe(false);
  });

  it("passes an ordinary post", () => {
    expect(bodyHasRawHtml("## Heading\n\nProse with [a link](/blog/en/x) and a list:\n\n- one\n"))
      .toBe(false);
  });
});
