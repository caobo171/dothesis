/**
 * `/blog/en/topic/<slug>` — the English category hub.
 *
 * Same page as `../../chu-de/[category]`, reached through the English segment.
 * A Vietnamese request that lands here (and an English one that lands on
 * `chu-de`) is 308'd to the segment its locale actually uses, so each hub has
 * exactly one working URL per language.
 */
import { CategoryRoute, categoryRouteMetadata } from "../../../_components/CategoryRoute";

export const dynamic = "force-dynamic";

type Params = { locale: string; category: string };
type Search = { page?: string | string[] };

export async function generateMetadata(args: { params: Promise<Params> }) {
  return categoryRouteMetadata("topic", args);
}

export default async function Page(args: {
  params: Promise<Params>;
  searchParams: Promise<Search>;
}) {
  return CategoryRoute("topic", args);
}
