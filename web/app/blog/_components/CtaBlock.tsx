import Link from "next/link";

/**
 * The one CTA a post is allowed (spec §13: more than one is a QA warning).
 *
 * It points at /landing rather than /signup: a reader who arrived from a
 * search for "cronbach alpha bao nhiêu là đạt" has no idea what DoThesis is,
 * and a signup form is a worse answer to that than the page that explains it.
 */
const COPY: Record<
  string,
  { title: string; body: string; action: string }
> = {
  vi: {
    title: "Làm bước này trong DoThesis",
    body:
      "DoThesis dựng thang đo và bảng hỏi, chạy phân tích và viết chương cho luận văn định lượng, kèm nguồn đã kiểm chứng.",
    action: "Xem DoThesis làm gì",
  },
  en: {
    title: "Do this step in DoThesis",
    body:
      "DoThesis builds the scale and the questionnaire, runs the analysis and drafts the chapter, with every citation checked.",
    action: "See what DoThesis does",
  },
};

export function CtaBlock({ locale, note }: { locale: string; note?: string }) {
  const copy = COPY[locale] ?? COPY.en;
  return (
    <aside className="blog-cta">
      <div className="blog-cta__title">{copy.title}</div>
      <p className="blog-cta__body">{note || copy.body}</p>
      <div className="blog-cta__action">
        <Link href="/landing" className="ds-btn ds-btn--default ds-btn--pill ds-btn--sm">
          {copy.action}
        </Link>
      </div>
    </aside>
  );
}
