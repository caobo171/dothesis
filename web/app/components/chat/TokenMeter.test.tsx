import { describe, expect, test } from "vitest";
import { render, screen } from "@testing-library/react";
import { TokenMeter } from "./TokenMeter";


describe("TokenMeter", () => {
  test("shows credits remaining", () => {
    render(<TokenMeter credits={12500} />);
    expect(screen.getByText(/12,500/)).toBeTruthy();
  });

  test("warns when low (< 5000)", () => {
    render(<TokenMeter credits={3000} />);
    const el = screen.getByTestId("token-meter");
    expect(el).toHaveClass("text-red-600");
  });

  test("ok when high (>= 5000)", () => {
    render(<TokenMeter credits={50000} />);
    const el = screen.getByTestId("token-meter");
    expect(el).not.toHaveClass("text-red-600");
  });
});
