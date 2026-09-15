import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { alternateLanguages } from "../../blog/_lib/hreflang";
import { absoluteUrl } from "../../blog/_lib/site";
import { LegalShell } from "../../legal/_components/LegalShell";
import { inline } from "../../legal/_lib/inline";
import { EMAIL, ENTITY, PRODUCT, legalPath, mailto } from "../../legal/_lib/site";
import { LOCALES, type Locale, isLocale } from "../../lib/i18n/locale";

/**
 * Support, as one inbox.
 *
 * No form and no ticketing backend, the same call agentmemo made: a form needs
 * an endpoint, spam handling and a delivery guarantee, and all three exist to
 * reproduce what `mailto:` already does. The subject line is the only routing
 * this gets, so each reason below pre-fills its own.
 *
 * Deliberately reachable signed out — the people most likely to need support
 * are the ones who cannot get in — which is why this route sits outside the
 * (inapp) and (chat) groups.
 */
export const dynamic = "force-static";

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

type Reason = { title: string; body: string; subject: string };

const COPY: Record<
  Locale,
  {
    title: string;
    lede: string;
    cardEyebrow: string;
    cardNote: string;
    reasonsHeading: string;
    reasons: Reason[];
    footer: string;
  }
> = {
  en: {
    title: "Contact",
    lede: `There is one way to reach us and it is the direct one: email. Every message goes to the people who build ${PRODUCT}.`,
    cardEyebrow: "Email",
    cardNote: "We read every message. It is a small team, so a reply can take a day or two.",
    reasonsHeading: "What are you writing about?",
    reasons: [
      {
        title: "General questions",
        body: `Anything about ${PRODUCT} — how it works, what it can and cannot do, feedback, or an idea.`,
        subject: "DoThesis — question",
      },
      {
        title: "Something is broken",
        body: "A run that failed, an export that will not open, a page that will not load. Tell us what you were doing and we will look at the run.",
        subject: "DoThesis — bug report",
      },
      {
        title: "Credits & payment",
        body: "A payment that did not land, a bank transfer that has not been matched, a charge you do not recognise, or a refund.",
        subject: "DoThesis — billing",
      },
      {
        title: "Privacy & your data",
        body: "Deleting your account, exporting your data, or any question about the privacy policy.",
        subject: "DoThesis — privacy",
      },
    ],
    footer: `${ENTITY}, Vietnam. See also the [Privacy Policy](/privacy/en) and the [Terms of Use](/terms/en).`,
  },

  vi: {
    title: "Liên hệ",
    lede: `Chỉ có một cách liên hệ với chúng tôi, và đó là cách trực tiếp: email. Mọi tin nhắn đều đến thẳng những người xây dựng ${PRODUCT}.`,
    cardEyebrow: "Email",
    cardNote: "Chúng tôi đọc mọi tin nhắn. Đội ngũ nhỏ nên có thể mất một hai ngày để phản hồi.",
    reasonsHeading: "Bạn muốn hỏi về việc gì?",
    reasons: [
      {
        title: "Câu hỏi chung",
        body: `Bất cứ điều gì về ${PRODUCT} — cách hoạt động, làm được và không làm được những gì, góp ý, hoặc một ý tưởng.`,
        subject: "DoThesis — câu hỏi",
      },
      {
        title: "Có lỗi xảy ra",
        body: "Một lần chạy bị lỗi, file xuất ra không mở được, một trang không tải được. Hãy cho biết bạn đang làm gì lúc đó, chúng tôi sẽ kiểm tra lần chạy đó.",
        subject: "DoThesis — báo lỗi",
      },
      {
        title: "Credit & thanh toán",
        body: "Thanh toán chưa vào, chuyển khoản chưa được đối soát, một khoản trừ bạn không nhận ra, hoặc yêu cầu hoàn tiền.",
        subject: "DoThesis — thanh toán",
      },
      {
        title: "Bảo mật & dữ liệu của bạn",
        body: "Xóa tài khoản, xuất dữ liệu, hoặc bất kỳ câu hỏi nào về chính sách bảo mật.",
        subject: "DoThesis — bảo mật",
      },
    ],
    footer: `${ENTITY}, Việt Nam. Xem thêm [Chính sách bảo mật](/privacy/vi) và [Điều khoản sử dụng](/terms/vi).`,
  },
};

const META: Record<Locale, { title: string; description: string }> = {
  en: {
    title: `Contact — ${PRODUCT}`,
    description: `Reach ${PRODUCT} by email — questions, bug reports, billing and privacy all go to the same inbox.`,
  },
  vi: {
    title: `Liên hệ — ${PRODUCT}`,
    description: `Liên hệ ${PRODUCT} qua email — câu hỏi, báo lỗi, thanh toán và bảo mật đều về cùng một hộp thư.`,
  },
};

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  if (!isLocale(locale)) return {};
  return {
    ...META[locale],
    alternates: {
      canonical: legalPath("contact", locale),
      languages: alternateLanguages({
        vi: absoluteUrl(legalPath("contact", "vi")),
        en: absoluteUrl(legalPath("contact", "en")),
      }),
    },
  };
}

export default async function ContactPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  if (!isLocale(locale)) notFound();
  const copy = COPY[locale];

  return (
    <LegalShell doc="contact" locale={locale} title={copy.title}>
      <p style={{ fontSize: 19, lineHeight: 1.6 }}>{copy.lede}</p>

      {/* The whole card is the link. A visitor who has decided to write should
          not have to find the 200px of it that happens to be clickable. */}
      <a
        href={mailto()}
        style={{
          display: "block",
          marginTop: 30,
          padding: "26px 28px",
          border: "1px solid var(--ink-200)",
          borderRadius: "var(--radius-lg)",
          background: "var(--ink-50)",
          textDecoration: "none",
        }}
      >
        <div className="lp-eyebrow">{copy.cardEyebrow}</div>
        <div
          style={{
            marginTop: 10,
            fontSize: 24,
            fontWeight: 600,
            letterSpacing: "-0.015em",
            color: "var(--primary-600)",
            overflowWrap: "anywhere",
          }}
        >
          {EMAIL}
        </div>
        <div style={{ marginTop: 10, fontSize: 15, color: "var(--ink-600)" }}>{copy.cardNote}</div>
      </a>

      <h2>{copy.reasonsHeading}</h2>
      <div style={{ display: "flex", flexDirection: "column", gap: 12, marginTop: 22 }}>
        {copy.reasons.map((r) => (
          <a
            key={r.subject}
            href={mailto(r.subject)}
            style={{
              display: "block",
              padding: "18px 20px",
              border: "1px solid var(--ink-200)",
              borderRadius: "var(--radius-lg)",
              textDecoration: "none",
            }}
          >
            <div style={{ fontSize: 16.5, fontWeight: 600, color: "var(--ink-900)" }}>{r.title}</div>
            <div style={{ marginTop: 6, fontSize: 15, lineHeight: 1.55, color: "var(--ink-600)" }}>
              {r.body}
            </div>
          </a>
        ))}
      </div>

      <p style={{ marginTop: 34, fontSize: 15, color: "var(--ink-600)" }}>{inline(copy.footer)}</p>
    </LegalShell>
  );
}
