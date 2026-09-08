/**
 * `/blog/vi/chu-de/<slug>` — the Vietnamese category hub.
 *
 * 420 published posts link here and the sitemap lists every one of these URLs,
 * so this folder keeps its name forever. The page lives in `_components/
 * CategoryRoute` and is shared with the English `topic` folder; all this file
 * adds is which segment the request came through, which is the one thing the
 * router knows and `params` does not.
 */
import { CategoryRoute, categoryRouteMetadata } from "../../../_components/CategoryRoute";

export const dynamic = "force-dynamic";

type Params = { locale: string; category: string };
type Search = { page?: string | string[] };

export async function generateMetadata(args: { params: Promise<Params> }) {
  return categoryRouteMetadata("chu-de", args);
}

export default async function Page(args: {
  params: Promise<Params>;
  searchParams: Promise<Search>;
}) {
  return CategoryRoute("chu-de", args);
}
