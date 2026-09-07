import { describe, expect, test } from "vitest";

import { paletteFor, titleFontSize } from "./og";

describe("paletteFor", () => {
  test("gives each of the nine categories its own hue", () => {
    const slugs = [
      "spss", "thong-ke", "khao-sat", "nghien-cuu-khoa-hoc", "khoa-luan-tot-nghiep",
      "smartpls", "phan-tich-du-lieu", "luan-van-thac-si", "mo-hinh-nghien-cuu",
    ];
    const seen = new Set(slugs.map((s) => paletteFor(s).from));
    expect(seen.size).toBe(slugs.length);
  });

  test("an unknown or absent category still gets a card", () => {
    expect(paletteFor(null).from).toMatch(/^#[0-9a-f]{6}$/i);
    expect(paletteFor("khong-co")).toEqual(paletteFor(undefined));
  });
});

describe("titleFontSize", () => {
  test("steps down as the title gets longer", () => {
    expect(titleFontSize("EFA là gì")).toBeGreaterThan(titleFontSize("x".repeat(70)));
    expect(titleFontSize("x".repeat(70))).toBeGreaterThan(titleFontSize("x".repeat(100)));
  });
});
