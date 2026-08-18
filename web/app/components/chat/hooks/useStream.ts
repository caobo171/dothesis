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

export class StreamRequestError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "StreamRequestError";
    this.status = status;
  }
}

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
  // Holds a pending deferred-abort timer (see the unmount effect below).
  const unmountAbortTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const start = useCallback(async (url: string, init: RequestInit = {}) => {
    // Abort any in-flight request before starting a new one
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    dispatch({ type: "start" });

    try {
      const res = await fetch(url, { ...init, signal: ctrl.signal });
      if (!res.ok) {
        let message = `Request failed (HTTP ${res.status})`;
        try {
          const body = await res.json();
          message = body?.detail?.error?.message
            || body?.detail?.message
            || body?.detail
            || body?.error?.message
            || message;
        } catch {
          // Some proxy errors have an empty/non-JSON response; retain status.
        }
        throw new StreamRequestError(res.status, String(message));
      }
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
      // Decision: the chat layer must know delivery failed so it can remove
      // its optimistic message. Swallowing here made denied sends vanish after
      // briefly appearing, with the real error visible only in server logs.
      throw e;
    }
  }, []);

  const cancel = useCallback(() => {
    abortRef.current?.abort();
    dispatch({ type: "end" });
  }, []);

  // Abort on unmount to stop a stream the user navigated away from (it would
  // otherwise keep generating and charging credits). The abort is DEFERRED by
  // one tick: React StrictMode's dev mount→unmount→remount cycle would
  // otherwise kill a request that a fire-on-mount caller (the bootstrap
  // auto-send) just started — the immediate remount clears the pending timer
  // before it fires. A real unmount has no remount, so the abort still runs.
  useEffect(() => {
    if (unmountAbortTimer.current !== null) {
      clearTimeout(unmountAbortTimer.current);
      unmountAbortTimer.current = null;
    }
    return () => {
      unmountAbortTimer.current = setTimeout(() => abortRef.current?.abort(), 0);
    };
  }, []);

  return { state, start, cancel };
}
