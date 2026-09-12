import { PUBLIC_BASE } from "@/app/lib/api";
import { tokenStore } from "@/app/lib/tokenStore";

/**
 * Send an image to /admin/blog/upload-image and get back the permanent public
 * url to reference it by.
 *
 * Not apiFetch: that helper folds the token into a JSON body, which is the
 * right shape for every other route in this API and the wrong one for a
 * multipart upload — the file cannot be JSON. The token rides in the
 * Authorization header instead, the way routers/uploads.py has always accepted
 * it (`current_user` reads the header for exactly these multipart routes).
 *
 * The returned url is root-relative (`/api/v1/blog/image/<sha256>.<ext>`) and
 * content-addressed, so it is stable forever and safe to paste into a post body
 * that will outlive this session.
 */

/** Mirrors the server's `_IMAGE_EXT`. Checked here too so a wrong file is
 *  refused before it is uploaded rather than after. */
export const ACCEPTED_IMAGE_TYPES = ["image/png", "image/jpeg", "image/webp", "image/gif"];

export function isUploadableImage(file: File | null | undefined): boolean {
  return Boolean(file && ACCEPTED_IMAGE_TYPES.includes(file.type));
}

export class ImageUploadError extends Error {}

export async function uploadBlogImage(file: File): Promise<string> {
  if (!isUploadableImage(file)) {
    throw new ImageUploadError(
      `${file.type || "That file"} is not an image we can publish — use PNG, JPEG, WebP or GIF.`);
  }

  const form = new FormData();
  form.append("file", file, file.name);

  const token = tokenStore.get();
  const res = await fetch(`${PUBLIC_BASE}/admin/blog/upload-image`, {
    method: "POST",
    // No Content-Type header on purpose: the browser has to set it, because
    // only it knows the multipart boundary.
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: form,
  });

  let parsed: { url?: string; detail?: { error?: { message?: string } } } | null = null;
  try {
    parsed = await res.json();
  } catch {
    /* a proxy error page is not JSON; fall through to the status message */
  }

  if (!res.ok || !parsed?.url) {
    throw new ImageUploadError(
      parsed?.detail?.error?.message || `Upload failed (HTTP ${res.status})`);
  }
  return parsed.url;
}
