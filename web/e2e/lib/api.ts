// web/e2e/lib/api.ts
import fs from "node:fs";
import path from "node:path";
import type { APIRequestContext } from "@playwright/test";

export const API_BASE = "http://localhost:7143/api/v1";
export const WEB_ORIGIN = "http://localhost:3106";
export const AUTH_DIR = path.join(__dirname, "..", ".auth");

export type Session = { email: string; password: string; token: string; expiresAt: number };
export type Sessions = { main: Session; broke: Session };

export function loadSessions(): Sessions {
  return JSON.parse(fs.readFileSync(path.join(AUTH_DIR, "session.json"), "utf-8"));
}

// POST-only API (CLAUDE.md): every call is a POST; authed calls carry the
// token IN THE BODY (access_token), never a header/cookie.
export async function apiPost(
  rc: APIRequestContext, p: string, body: Record<string, unknown>,
): Promise<any> {
  const res = await rc.post(`${API_BASE}${p}`, { data: body });
  if (!res.ok()) throw new Error(`POST ${p} -> ${res.status()}: ${await res.text()}`);
  return res.json();
}

// POST /projects auto-creates the "Main" thread (chat.create_project), so a
// fresh chat surface is one call + one list away.
export async function createProjectWithThread(
  rc: APIRequestContext, token: string, name = "E2E project",
): Promise<{ projectId: string; threadId: string }> {
  const project = await apiPost(rc, "/projects", {
    access_token: token, name, field: null, language: "en", citation_style: "apa",
  });
  const threads = await apiPost(rc, `/projects/${project.id}/threads/list`, {
    access_token: token,
  });
  return { projectId: project.id as string, threadId: threads[0].id as string };
}
