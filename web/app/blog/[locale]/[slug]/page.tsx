import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { isLocale } from "../../../lib/i18n/locale";
import { BlogShell } from "../../_components/BlogShell";
import { ContentsBox } from "../../_components/ContentsBox";
import { CtaBlock } from "../../_components/CtaBlock";
import { JsonLd } from "../../_components/JsonLd";
import { Markdown } from "../../_components/Markdown";
import { fetchPost } from "../../_lib/api";
import { formatDate, formatReadingTime } from "../../_lib/format";
import { blogPostingJsonLd, faqJsonLd, postUrl } from "../../_lib/jsonld";
import { extractFaq, tableOfContents } from "../../_lib/markdown";
import { absoluteUrl, blogPath, categoryPath, ogImagePath, postPath } from "../../_lib/site";

export const dynamic = "force-dynamic";

type Params = { locale: string; slug: string };

const COPY: Record<string, { back: string; related: string }> = {
  vi: { back: "Quay lại blog", related: "Bài liên quan" },
  en: { back: "Back to the blog", related: "Related posts" },
};

export async function generateMetadata({
  params,
}: {
  params: Promise<Params>;
}): Promise<Metadata> {
  const { locale, slug } = await params;
  if (!isLocale(locale)) return {};
  const data = await fetchPost(locale, slug);
  if (!data) return { title: "Not found", robots: { index: false, follow: false } };

  const { post } = data;
  const url = postUrl(post);
  const title = post.meta_title || post.title;
  const description = post.meta_description || post.excerpt;
  // Always emit an og:image. A link preview with no image is a grey box in
  // every chat app a student would share this in, and the generated card costs
  // nothing to point at.
  const image = post.image_url || absoluteUrl(ogImagePath(locale, post.slug));

  return {
    metadataBase: new URL(absoluteUrl("/")),
    title,
    description,
    alternates: { canonical: url },
    openGraph: {
      type: "article",
      title,
      description,
      url,
      siteName: "DoThesis",
      locale: locale === "vi" ? "vi_VN" : "en_US",
      images: [{ url: image, width: 1200, height: 630, alt: post.title }],
      publishedTime: post.published_at ?? undefined,
      modifiedTime: post.updated_at ?? post.published_at ?? undefined,
      tags: post.tags,
    },
    twitter: { card: "summary_large_image", title, description, images: [image] },
    robots: { index: true, follow: true },
  };
}

export default async function BlogPostPage({ params }: { params: Promise<Params> }) {
  const { locale, slug } = await params;
  if (!isLocale(locale)) notFound();
  const data = await fetchPost(locale, slug);
  if (!data) notFound();

  const { post, related, category } = data;
  const copy = COPY[locale] ?? COPY.en;
  const headings = tableOfContents(post.body);
  const faq = extractFaq(post.body);
  const date = formatDate(post.published_at, locale);
  const read = formatReadingTime(post.reading_time, locale);
  const categorySlug = category?.slug ?? post.category?.slug ?? null;
  const categoryName = category?.display_name ?? post.category?.display_name ?? null;

  return (
    <BlogShell>
      <JsonLd data={blogPostingJsonLd(post)} />
      <JsonLd data={faqJsonLd(faq, post)} />

      <div className="lp-wrap">
        <article className="blog-measure">
          <div className="blog-meta" style={{ marginBottom: 20 }}>
            <Link href={blogPath(locale)}>{copy.back}</Link>
          </div>

          <h1 className="blog-article__title">{post.title}</h1>

          <div className="blog-meta" style={{ marginTop: 16 }}>
            {categorySlug && categoryName && (
              <>
                <Link href={categoryPath(locale, categorySlug)}>{categoryName}</Link>
                <span className="blog-meta__sep">·</span>
              </>
            )}
            {date && <time dateTime={post.published_at ?? undefined}>{date}</time>}
            {date && read && <span className="blog-meta__sep">·</span>}
            {read && <span>{read}</span>}
          </div>

          <ContentsBox headings={headings} locale={locale} />

          <Markdown>{post.body}</Markdown>

          <CtaBlock locale={locale} />

          {related.length > 0 && (
            <section className="blog-related">
              <h2 className="blog-section-title">{copy.related}</h2>
              <ul className="blog-linklist">
                {related.map((r) => (
                  <li key={r.slug}>
                    <Link href={postPath(r.locale, r.slug)}>{r.title}</Link>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </article>
      </div>
    </BlogShell>
  );
}
