"use client";

import { useCallback, useEffect, useReducer, useRef } from "react";

export type SSEEvent = {
  type: string;
  [key: string]: unknown;
};

export type StreamState = {
  events: SSEEvent[];
  inflight: boolean;
  error: Error | null;
};

export type UseStreamApi = {
  state: StreamState;
  start: (url: string, init?: RequestInit) => Promise<void>;
  cancel: () => void;
};

type Action =
  | { type: "start" }
  | { type: "event"; event: SSEEvent }
  | { type: "error"; error: Error }
  | { type: "end" }
  | { type: "reset" };

function reducer(state: StreamState, action: Action): StreamState {
  switch (action.type) {
    case "start": return { events: [], inflight: true, error: null };
    case "event": return { ...state, events: [...state.events, action.event] };
    case "error": return { ...state, inflight: false, error: action.error };
    case "end":   return { ...state, inflight: false };
    case "reset": return { events: [], inflight: false, error: null };
  }
}

export function useStream(): UseStreamApi {
  const [state, dispatch] = useReducer(reducer, {
    events: [], inflight: false, error: null,
  });
  const abortRef = useRef<AbortController | null>(null);

  const start = useCallback(async (url: string, init: RequestInit = {}) => {
    // Abort any in-flight request before starting a new one
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    dispatch({ type: "start" });

    try {
      const res = await fetch(url, { ...init, signal: ctrl.signal });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        // Bail out immediately if cancelled while we were waiting on a read
        if (ctrl.signal.aborted) return;
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        // Extract complete SSE frames delimited by double newline
        let sep;
        while ((sep = buffer.indexOf("\n\n")) >= 0) {
          const frame = buffer.slice(0, sep);
          buffer = buffer.slice(sep + 2);
          const dataLine = frame.split("\n").find(l => l.startsWith("data: "));
          if (!dataLine) continue;
          try {
            const event = JSON.parse(dataLine.slice(6)) as SSEEvent;
            dispatch({ type: "event", event });
            // Terminal event types signal end of stream
            if (event.type === "done" || event.type === "job_done") {
              dispatch({ type: "end" });
              return;
            }
          } catch {
            // Malformed JSON frame — skip silently, do not surface parse errors
          }
        }
      }
      dispatch({ type: "end" });
    } catch (e) {
      // AbortError is not an error condition — it's intentional cancellation
      if ((e as Error).name === "AbortError") return;
      dispatch({ type: "error", error: e as Error });
    }
  }, []);

  const cancel = useCallback(() => {
    abortRef.current?.abort();
    dispatch({ type: "end" });
  }, []);

  // Abort on unmount to avoid state updates on a dead component
  useEffect(() => () => abortRef.current?.abort(), []);

  return { state, start, cancel };
}
