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

  // The workspace path — a topic the student typed, not one derived from their
  // uploads. This used to render a red balance beside a dead button and say
  // nothing about either: you could see the number was short, but not that it
  // was what blocked the run, nor what to do next. The numbers are the estimate
  // block's job; the sentence and the link are what make them actionable.
  test("a typed topic explains the short balance and offers the way out", async () => {
    server.use(
      http.post("*/api/v1/projects/p1/runs/estimate", () =>
        HttpResponse.json({ estimated_tokens: 17500, credit_balance: 13919, sufficient_credit: false }),
      ),
    );
    renderModal({
      open: true, projectId: "p1", defaultTopic: "AI shopping assistants",
      onClose: () => {}, onConfirm: () => {},
    });
    await waitFor(() => expect(screen.getByText(/17,500/)).toBeTruthy());
    // The estimate block still shows both numbers on this path...
    expect(screen.getByText(/13,919/)).toBeTruthy();
    // ...but they no longer stand alone.
    expect(screen.getByText(/not enough credits/i)).toBeTruthy();
    expect(document.body.textContent).toMatch(/3,581/);  // 17,500 − 13,919
    expect(screen.getByRole("link", { name: /top up credits/i })
      .getAttribute("href")).toBe("/credit");
    expect(screen.getByRole("button", { name: /^auto thesis$/i })).toBeDisabled();
  });

  test("does not render when open=false", () => {
    renderModal({
      open: false, projectId: "p1", defaultTopic: "",
      onClose: () => {}, onConfirm: () => {},
    });
    expect(screen.queryByText(/auto thesis/i)).toBeNull();
  });

  // Reading the uploads belongs HERE, not in one caller. ChatPane opens this
  // dialog from four places and only one of them derived a topic, so a student
  // who uploaded a finished results chapter and landed on an auto-mode thread
  // got an empty box asking them to retype the title sitting on page 1 of the
  // file they had just handed over. The other three surfaces cannot each
  // remember to do this; the dialog that needs the topic asks for it.
  describe("reading the topic out of the uploads", () => {
    const estimate = (id: string) =>
      http.post(`*/api/v1/projects/${id}/runs/estimate`, () =>
        HttpResponse.json({ estimated_tokens: 100, credit_balance: 9000, sufficient_credit: true }));

    test("fills an empty box from the uploaded files", async () => {
      server.use(
        estimate("p9"),
        http.post("*/api/v1/projects/p9/topic-from-uploads", () =>
          HttpResponse.json({
            research_title: "The Effects of Application Performance Expectations on App Adoption",
            source: "Results.docx",
          })),
      );
      renderModal({
        open: true, projectId: "p9", defaultTopic: "",
        onClose: () => {}, onConfirm: () => {},
      });
      await waitFor(() => expect(
        screen.getByDisplayValue(/Application Performance Expectations/)).toBeTruthy());
      // And it says where the sentence came from, because the student did not
      // write it and nothing about a prefilled box says they may correct it.
      expect(screen.getByText(/we read your files/i)).toBeTruthy();
      expect(screen.getByText(/not right\? edit it\./i)).toBeTruthy();
    });

    test("does not ask when a topic is already known", async () => {
      let asked = 0;
      server.use(
        estimate("p9"),
        http.post("*/api/v1/projects/p9/topic-from-uploads", () => {
          asked += 1;
          return HttpResponse.json({ research_title: "Something else" });
        }),
      );
      renderModal({
        open: true, projectId: "p9", defaultTopic: "A title the student typed",
        onClose: () => {}, onConfirm: () => {},
      });
      await waitFor(() => expect(screen.getByDisplayValue(/student typed/)).toBeTruthy());
      expect(asked).toBe(0);
    });

    test("leaves the box empty, and typable, when there is nothing to read", async () => {
      server.use(
        estimate("p9"),
        http.post("*/api/v1/projects/p9/topic-from-uploads", () =>
          HttpResponse.json({ research_title: null, source: null })),
      );
      renderModal({
        open: true, projectId: "p9", defaultTopic: "",
        onClose: () => {}, onConfirm: () => {},
      });
      // Falls back to the ask-the-student dialog rather than a derived one.
      await waitFor(() => expect(screen.getByText("Research topic")).toBeTruthy());
      expect(screen.queryByText(/we read your files/i)).toBeNull();
      expect((screen.getByRole("textbox") as HTMLTextAreaElement).value).toBe("");
    });

    test("a failed read does not block the student from typing one", async () => {
      server.use(
        estimate("p9"),
        http.post("*/api/v1/projects/p9/topic-from-uploads", () =>
          HttpResponse.json({ detail: "boom" }, { status: 500 })),
      );
      renderModal({
        open: true, projectId: "p9", defaultTopic: "",
        onClose: () => {}, onConfirm: () => {},
      });
      await waitFor(() => expect(screen.getByText("Research topic")).toBeTruthy());
      const box = screen.getByRole("textbox") as HTMLTextAreaElement;
      fireEvent.change(box, { target: { value: "typed by hand" } });
      expect(box.value).toBe("typed by hand");
      expect(screen.getByRole("button", { name: /^auto thesis$/i })).not.toBeDisabled();
    });
  });
});
