import { redirect } from "next/navigation";

/**
 * /tools has no page of its own any more — each tool is its own route so the
 * sidebar can link straight to it and highlight it.
 *
 * This redirect is what keeps every existing link working: the nav item, any
 * bookmark, and the announcement copy that pointed students at /tools all still
 * land somewhere real instead of a 404.
 */
export default function ToolsIndex() {
  redirect("/tools/humanize");
}
