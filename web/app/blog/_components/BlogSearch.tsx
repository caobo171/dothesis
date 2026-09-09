import { blogPath } from "../_lib/site";

const COPY: Record<string, { label: string; placeholder: string; submit: string }> = {
  vi: {
    label: "Tìm bài viết",
    placeholder: "Cronbach's Alpha, EFA, cỡ mẫu...",
    submit: "Tìm",
  },
  en: {
    label: "Search posts",
    placeholder: "Cronbach's Alpha, EFA, sample size...",
    submit: "Search",
  },
};

/**
 * The search box on the blog listing.
 *
 * A plain GET form, not a client component: it needs no state, it works with
 * JavaScript off, and its result is a real URL a reader can bookmark or share.
 * `action` is the listing itself, so submitting produces `/blog/vi?q=...` — the
 * shape `listingPath` builds and the listing page already reads.
 *
 * `page` is deliberately not carried: a new search starts at page 1, and
 * keeping the old page number would land the reader on an empty result set.
 */
export function BlogSearch({ locale, value }: { locale: string; value?: string }) {
  const copy = COPY[locale] ?? COPY.en;
  return (
    <form className="blog-search" action={blogPath(locale)} method="get" role="search">
      <label className="blog-search__label" htmlFor="blog-search-q">
        {copy.label}
      </label>
      <input
        id="blog-search-q"
        className="blog-search__input"
        type="search"
        name="q"
        defaultValue={value ?? ""}
        placeholder={copy.placeholder}
        autoComplete="off"
      />
      <button className="blog-search__submit" type="submit">
        {copy.submit}
      </button>
    </form>
  );
}
