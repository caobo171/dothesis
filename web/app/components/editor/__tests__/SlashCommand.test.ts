import { describe, it, expect } from "vitest";
import { getSlashItems } from "../extensions/SlashCommand";


describe("getSlashItems — slash menu filter", () => {
  it("returns the full palette for an empty query", () => {
    const items = getSlashItems("");
    expect(items.length).toBeGreaterThan(5);
    expect(items.map(i => i.title)).toContain("Heading 1");
  });

  it("matches on title (case-insensitive)", () => {
    const items = getSlashItems("head");
    expect(items.map(i => i.title)).toEqual(["Heading 1", "Heading 2", "Heading 3"]);
  });

  it("matches on aliases", () => {
    expect(getSlashItems("h2").map(i => i.title)).toEqual(["Heading 2"]);
    expect(getSlashItems("unordered").map(i => i.title)).toEqual(["Bullet list"]);
    expect(getSlashItems("hr").map(i => i.title)).toEqual(["Divider"]);
  });

  it("returns nothing for an unmatched query", () => {
    expect(getSlashItems("zzzzz")).toEqual([]);
  });
});
