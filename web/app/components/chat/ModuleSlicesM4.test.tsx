import { describe, expect, test } from "vitest";
import { render, screen } from "@testing-library/react";
import { LocaleProvider } from "@/app/lib/i18n/LocaleProvider";
import { M4Body } from "./ModuleSlices";

function renderEn(ui: React.ReactElement) {
  return render(<LocaleProvider initialLocale="en" hasCookie>{ui}</LocaleProvider>);
}

describe("M4Body", () => {
  test("shows outline and structured results summary", () => {
    renderEn(
      <M4Body
        data={{
          data_type_detected: "survey",
          analysis_outline: "Measurement model then structural model",
          analysis_results: {
            descriptives: { n: 350 },
            hypothesis_tests: [
              { id: "H1", decision: "supported" },
              { id: "H2", decision: "not supported" },
            ],
            measurement_model: {},
            structural_model: {},
          },
        }}
      />,
    );
    expect(screen.getByText(/survey/i)).toBeTruthy();
    expect(screen.getByText(/Measurement model then structural model/)).toBeTruthy();
    expect(screen.getByText(/4 tables · 1\/2 hypotheses supported · n = 350/)).toBeTruthy();
  });

  test("shows text-only results from imports", () => {
    renderEn(
      <M4Body
        data={{
          analysis_results: "H1 supported (beta=0.41, p<0.001).",
        }}
      />,
    );
    expect(screen.getByText(/H1 supported/)).toBeTruthy();
  });

  test("empty slice explains soft-lock without hiding the section", () => {
    renderEn(<M4Body data={{}} />);
    expect(screen.getByText(/No M4 data committed yet/)).toBeTruthy();
    expect(screen.getByText(/jump in anytime/i)).toBeTruthy();
  });
});
