import { describe, expect, test } from "vitest";
import { render, screen } from "@testing-library/react";
import { LocaleProvider } from "@/app/lib/i18n/LocaleProvider";
import { M2Body, M3Body, readHypothesisText } from "./ModuleSlices";

function renderEn(ui: React.ReactElement) {
  return render(<LocaleProvider initialLocale="en" hasCookie>{ui}</LocaleProvider>);
}

/**
 * A hypothesis without a sentence field must still render as something.
 *
 * `hypothesisText` aliased seven possible sentence keys and fell back to an
 * em-dash. Two of the nine hypothesis shapes on the live database carry none
 * of those seven — they came from a backfill that inferred hypotheses FROM
 * reported SmartPLS paths, so what they have is a path, a direction and a
 * verdict. The card rendered "HYPOTHESES (9)" above nine blank rows, which
 * reads as broken and hid the β/t/p the student needs.
 */
describe("M2Body hypotheses", () => {
  test("composes a line from path + direction + status when there is no sentence", () => {
    // The exact shape stored for project 500319a8 on 2026-09-15.
    renderEn(
      <M2Body
        data={{
          hypotheses: [{
            id: "H1",
            path: "ATT -> INT",
            status: "được ủng hộ",
            direction: "dương",
            rationale: "Kết quả báo cáo β = 0.257, t = 7.490, p < 0.001.",
          }],
        }}
      />,
    );
    expect(screen.getByText(/ATT -> INT/)).toBeTruthy();
    expect(screen.queryByText("—")).toBeNull();
  });

  test("handles the source/target shape too", () => {
    renderEn(
      <M2Body data={{ hypotheses: [{ id: "H2", source: "EXP", target: "INT" }] }} />,
    );
    expect(screen.getByText(/EXP → INT/)).toBeTruthy();
  });

  test("uses `result` when there is no `status`", () => {
    renderEn(
      <M2Body
        data={{ hypotheses: [{ id: "H3", path: "TRUST -> INT", result: "supported" }] }}
      />,
    );
    expect(screen.getByText(/TRUST -> INT · supported/)).toBeTruthy();
  });

  test("a real sentence still wins over the composed line", () => {
    renderEn(
      <M2Body
        data={{
          hypotheses: [{
            id: "H4",
            statement: "Chuyên môn có tác động tích cực đến ý định du lịch.",
            path: "EXP -> INT",
          }],
        }}
      />,
    );
    expect(screen.getByText(/Chuyên môn có tác động tích cực/)).toBeTruthy();
  });

  test("an empty hypothesis object still falls back to em-dash", () => {
    renderEn(<M2Body data={{ hypotheses: [{ id: "H5" }] }} />);
    expect(screen.getByText("—")).toBeTruthy();
  });
});

/**
 * The M3 card is where a student actually reads their hypotheses, and it had
 * its OWN copy of this logic (`readHypothesisText`). Fixing only M2Body left
 * the M3 card rendering nine em-dashes on a project whose hypotheses carried
 * real β/t/p — which is exactly what the student reported, twice.
 */
describe("M3Body hypotheses", () => {
  const THREAD_C10F6D13 = [
    { id: "H1", path: "ATT -> INT", status: "được ủng hộ", direction: "dương",
      rationale: "Kết quả báo cáo β = 0.257, t = 7.490, p < 0.001." },
    { id: "H2", path: "EXP -> INT", status: "được ủng hộ", direction: "dương",
      rationale: "Kết quả báo cáo β = 0.269, t = 6.892, p < 0.001." },
    { id: "H3", path: "ECONN -> INT", status: "được ủng hộ", direction: "dương",
      rationale: "Kết quả báo cáo β = 0.382, t = 10.441, p < 0.001." },
  ];

  test("the M3 card renders path-shaped hypotheses, not em-dashes", () => {
    renderEn(<M3Body data={{ hypotheses: THREAD_C10F6D13 }} />);
    expect(screen.getByText(/ATT -> INT/)).toBeTruthy();
    expect(screen.getByText(/EXP -> INT/)).toBeTruthy();
    expect(screen.queryByText("—")).toBeNull();
  });

  test("both cards agree, because they share one implementation", () => {
    // The regression was two copies drifting. Pin that they are the same.
    const h = THREAD_C10F6D13[0];
    renderEn(<M3Body data={{ hypotheses: [h] }} />);
    expect(screen.getByText(new RegExp(readHypothesisText(h).slice(0, 12)))).toBeTruthy();
  });
});
