import { describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { server } from "../../../tests/setup";
import { AutoThesisModal } from "./AutoThesisModal";
import { LocaleProvider } from "../../lib/i18n/LocaleProvider";

// The modal reads its derived-topic copy through useT, so every render needs a
// provider — the workspace copy is still hardcoded English, the derived one is
// not (a Vietnamese student is the one most likely to see it).
const renderModal = (props: Parameters<typeof AutoThesisModal>[0]) =>
  render(
    <LocaleProvider initialLocale="en" hasCookie>
      <AutoThesisModal {...props} />
    </LocaleProvider>,
  );


describe("AutoThesisModal", () => {
  test("fetches estimate and renders it", async () => {
    server.use(
      http.post("*/api/v1/projects/p1/runs/estimate", () =>
        HttpResponse.json({ estimated_tokens: 18500, credit_balance: 50000, sufficient_credit: true }),
      ),
    );
    renderModal({
      open: true, projectId: "p1", defaultTopic: "Leadership",
      onClose: () => {}, onConfirm: () => {},
    });
    await waitFor(() => expect(screen.getByText(/18,500/)).toBeTruthy());
    expect(screen.getByText(/50,000/)).toBeTruthy();
  });

  test("confirm fires callback with topic", async () => {
    server.use(
      http.post("*/api/v1/projects/p1/runs/estimate", () =>
        HttpResponse.json({ estimated_tokens: 100, credit_balance: 1000, sufficient_credit: true }),
      ),
    );
    const onConfirm = vi.fn();
    renderModal({
      open: true, projectId: "p1", defaultTopic: "seed",
      onClose: () => {}, onConfirm,
    });
    await waitFor(() => expect(screen.getByDisplayValue("seed")).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: /^auto thesis$/i }));
    await waitFor(() => expect(onConfirm).toHaveBeenCalledWith("seed"));
  });

  // Derived topic: the student never typed this sentence, so the dialog stops
  // being a start-the-run gate and becomes "is this what your thesis is
  // about?". The token estimate goes away — it is noise at the one moment they
  // need to read one line carefully — but the credit BLOCK must not.
  test("a derived topic is presented for confirmation, without the token estimate", async () => {
    server.use(
      http.post("*/api/v1/projects/p1/runs/estimate", () =>
        HttpResponse.json({ estimated_tokens: 20350, credit_balance: 997220, sufficient_credit: true }),
      ),
    );
    const onConfirm = vi.fn();
    renderModal({
      open: true, projectId: "p1", derived: true,
      defaultTopic: "Ảnh hưởng của đặc điểm KOLs đến hành vi mua sắm",
      onClose: () => {}, onConfirm,
    });
    await waitFor(() => expect(
      screen.getByDisplayValue(/Ảnh hưởng của đặc điểm KOLs/)).toBeTruthy());
    expect(screen.getByText(/we read your files/i)).toBeTruthy();
    expect(screen.getByText(/not right\? edit it\./i)).toBeTruthy();
    expect(screen.queryByText(/20,350/)).toBeNull();
    expect(screen.queryByText(/997,220/)).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /write my thesis/i }));
    await waitFor(() => expect(onConfirm).toHaveBeenCalledWith(
      "Ảnh hưởng của đặc điểm KOLs đến hành vi mua sắm"));
  });

  test("a derived topic still refuses to start when the balance can't cover it", async () => {
    server.use(
      http.post("*/api/v1/projects/p1/runs/estimate", () =>
        HttpResponse.json({ estimated_tokens: 20350, credit_balance: 12, sufficient_credit: false }),
      ),
    );
    renderModal({
      open: true, projectId: "p1", derived: true, defaultTopic: "A topic",
      onClose: () => {}, onConfirm: () => {},
    });
    await waitFor(() => expect(screen.getByText(/not enough credits/i)).toBeTruthy());
    expect(screen.getByRole("button", { name: /write my thesis/i })).toBeDisabled();
  });

  test("does not render when open=false", () => {
    renderModal({
      open: false, projectId: "p1", defaultTopic: "",
      onClose: () => {}, onConfirm: () => {},
    });
    expect(screen.queryByText(/auto thesis/i)).toBeNull();
  });
});
