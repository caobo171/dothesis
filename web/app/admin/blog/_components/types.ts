/** Shapes the /admin/blog/* routes return. One file so the list, the editor
 *  and the categories screen cannot drift from each other. */

/** blog_posts.status — app/blog/__init__.py. */
export const STATUS = { DRAFT: 0, PUBLISHED: 1, SCHEDULED: 2 } as const;

export const STATUS_LABEL: Record<number, string> = {
  [STATUS.DRAFT]: "Draft",
  [STATUS.PUBLISHED]: "Published",
  [STATUS.SCHEDULED]: "Scheduled",
};

export type CategoryRef = {
  slug: string;
  name: string;
  display_name: string;
  intro_md: string | null;
  sort_order: number;
};

/** A listing card (`compact` + the admin extras). NO `body` — /admin/blog/get
 *  is the read that carries one. */
export type PostRow = {
  id: string;
  locale: string;
  slug: string;
  title: string;
  excerpt: string | null;
  image_url: string | null;
  tags: string[];
  category: CategoryRef | null;
  published_at: string | null;
  updated_at: string | null;
  reading_time: number | null;
  views: number | null;
  status: number;
  scheduled_at: string | null;
  focus_keyword: string | null;
  focus_keyword_volume: number | null;
  archetype: string | null;
  source_batch: string | null;
  duplicate_override_reason: string | null;
};

/** What the editor loads: the full detail payload plus the admin extras. */
export type AdminPost = PostRow & {
  body: string;
  meta_title: string | null;
  meta_description: string | null;
  secondary_keywords: string[];
  canonical_url: string | null;
};

export type ListResp = {
  posts: PostRow[];
  total: number;
  page: number;
  page_size: number;
};

export type CategoryRow = {
  id: string;
  locale: string;
  slug: string;
  name: string;
  display_name: string;
  intro_md: string | null;
  sort_order: number;
  post_count: number;
};

export type Options = {
  /** The closed list of §6. A post may not name anything else. */
  category_slugs: string[];
  /** Free text in the seed schema, so these are suggestions, not a set. */
  archetypes: string[];
};
