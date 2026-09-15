import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { absoluteUrl } from "../../blog/_lib/site";
import { alternateLanguages } from "../../blog/_lib/hreflang";
import { LegalShell } from "../../legal/_components/LegalShell";
import { type Section, inline, renderSections } from "../../legal/_lib/inline";
import {
  EMAIL,
  ENTITY,
  PRODUCT,
  SITE_HOST,
  formattedDate,
  legalPath,
  mailto,
} from "../../legal/_lib/site";
import { LOCALES, type Locale, isLocale } from "../../lib/i18n/locale";

/**
 * The privacy policy, in both editions.
 *
 * Written against what the service ACTUALLY does, verified in the code rather
 * than adapted from a template: the model routes in `api/app/pricing.py` and
 * `quality/model_prices.py`, the three payment rails in `api/app/routers/
 * credit.py`, S3 and SES in `api/app/settings.py`, the CrossRef lookups in
 * `api/app/routers/tools.py`, and the backend-only PostHog in
 * `api/app/analytics.py`. A policy listing a subprocessor we do not use is as
 * wrong as one omitting a subprocessor we do.
 */
export const dynamic = "force-static";

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

const COPY: Record<Locale, { title: string; meta: (d: string) => string; lede: string; sections: Section[] }> = {
  en: {
    title: "Privacy Policy",
    meta: (d) => `Last updated ${d}`,
    lede: `This policy explains what ${PRODUCT} ([${SITE_HOST}](https://${SITE_HOST})) collects, why, and the choices you have. It describes what the service actually does, so you can decide what you are comfortable putting into it.`,
    sections: [
      {
        h2: "Who we are",
        blocks: [
          {
            p: `${PRODUCT} is operated by ${ENTITY}, in Vietnam. For anything in this policy, write to [${EMAIL}](${mailto()}).`,
          },
        ],
      },
      {
        h2: "What we collect",
        blocks: [
          {
            ul: [
              "**Account information.** Your email address, your name or username, and a hashed form of your password. We never store your password as plain text. If you sign in with Google, we receive your email address and basic profile from Google instead of a password.",
              "**Your thesis work.** The topic and research model you set up, the analysis output you upload (SmartPLS or SPSS exports), documents you pass to the tools, your reference list, the drafts the agent produces, and the conversation threads you have with it.",
              "**Payment information.** Payments are handled by our payment providers. We receive confirmation that a payment succeeded, which credit pack it was for, and — for a bank transfer — the transfer reference and memo we need to match it to your order. We never see or store your full card number.",
              "**Credit activity.** A ledger of credits added and spent, and which run or tool spent them, so a charge on your account can always be explained.",
              "**Technical information.** A token that keeps you signed in, and the ordinary data your browser sends, such as your IP address and browser type, which we use to run and secure the service.",
            ],
          },
        ],
      },
      {
        h2: "How we use your information",
        blocks: [
          {
            ul: [
              "To run the service: to draft, revise and export your thesis chapters, and to keep your project in sync across the app and the tools.",
              "To meter and bill credits, and to show you what each run cost.",
              "To send account email you need — address verification, payment receipts, and notices about your account or the service.",
              "To respond when you contact us.",
              "To keep the service secure, detect abuse, and diagnose failures.",
            ],
          },
        ],
      },
      {
        h2: "The AI agent and your work",
        blocks: [
          {
            p: "To draft a chapter, the agent sends the relevant parts of your project — your topic, your research model, your uploaded analysis output, your reference list and your instructions — to a large-language-model provider. This is the core of what the service does, and it cannot be switched off while still using it.",
          },
          {
            p: "We send that provider what it needs to write; we do not send it your password, your payment details, or your credit balance. We do not use your thesis content to train models.",
          },
        ],
      },
      {
        h2: "Who we share data with",
        blocks: [
          { p: "We do not sell your personal information. We share what is necessary with the providers that make the service work:" },
          {
            ul: [
              "**Large-language-model providers** (currently OpenAI and Google) to generate and revise your drafts.",
              "**Payment providers** — Polar and PayPal for card payments, and SePay for Vietnamese bank transfers — to take payment and confirm it.",
              "**Amazon Web Services** to store your uploads and exports, and to deliver account email.",
              "**CrossRef**, when you use the citation tools: we send the citation strings found in your document so they can be checked against the public record.",
              "**A similarity-checking provider**, when one is configured for your deployment and you run that check. If none is configured, the check reports itself unavailable and nothing leaves the service.",
              "**PostHog**, for our own product and quality analytics, when it is enabled.",
              "**Our hosting provider**, which runs the servers and the database.",
            ],
          },
          {
            p: "We may also disclose information where the law requires it, or to protect our rights or someone's safety.",
          },
        ],
      },
      {
        h2: "Cookies and analytics",
        blocks: [
          {
            p: "We use a token to keep you signed in, and a cookie to remember your language. We do not run advertising on this site and we do not sell data to advertisers.",
          },
        ],
      },
      {
        h2: "Keeping and deleting your data",
        blocks: [
          {
            p: `You can read, edit and export your work inside the app at any time — the whole point of the export is that the document is yours to take away. To delete your account and the data attached to it, write to [${EMAIL}](${mailto("DoThesis — delete my account")}) and we will remove it. We keep the records we are required to keep for accounting and tax, such as the fact that a payment was made.`,
          },
        ],
      },
      {
        h2: "Security",
        blocks: [
          {
            p: "Passwords are stored hashed, and traffic to the service travels over HTTPS. No method of storage or transmission over the internet is ever completely secure, so we cannot promise absolute security.",
          },
        ],
      },
      {
        h2: "Children",
        blocks: [
          {
            p: `${PRODUCT} is built for university and graduate students and is not directed at children under 13. We do not knowingly collect their information; if you believe a child has given us data, contact us and we will delete it.`,
          },
        ],
      },
      {
        h2: "Changes to this policy",
        blocks: [
          {
            p: "We may update this policy from time to time. When we do, we will post the new version on this page and change the date above.",
          },
        ],
      },
      {
        h2: "Contact",
        blocks: [{ p: `Questions about this policy? Email [${EMAIL}](${mailto("DoThesis — privacy")}).` }],
      },
    ],
  },

  vi: {
    title: "Chính sách bảo mật",
    meta: (d) => `Cập nhật lần cuối ${d}`,
    lede: `Chính sách này giải thích ${PRODUCT} ([${SITE_HOST}](https://${SITE_HOST})) thu thập những gì, để làm gì, và bạn có những lựa chọn nào. Nội dung mô tả đúng những gì dịch vụ thực sự làm, để bạn tự quyết định mình muốn đưa vào đây đến đâu.`,
    sections: [
      {
        h2: "Chúng tôi là ai",
        blocks: [
          {
            p: `${PRODUCT} do ${ENTITY} vận hành, tại Việt Nam. Mọi vấn đề liên quan đến chính sách này, bạn viết thư tới [${EMAIL}](${mailto()}).`,
          },
        ],
      },
      {
        h2: "Chúng tôi thu thập gì",
        blocks: [
          {
            ul: [
              "**Thông tin tài khoản.** Địa chỉ email, tên hoặc tên đăng nhập của bạn, và mật khẩu đã được băm (hash). Chúng tôi không bao giờ lưu mật khẩu dạng văn bản thường. Nếu bạn đăng nhập bằng Google, chúng tôi nhận email và thông tin hồ sơ cơ bản từ Google thay cho mật khẩu.",
              "**Nội dung luận văn của bạn.** Đề tài và mô hình nghiên cứu bạn thiết lập, kết quả phân tích bạn tải lên (file xuất từ SmartPLS hoặc SPSS), tài liệu bạn đưa vào các công cụ, danh mục tài liệu tham khảo, các bản thảo agent tạo ra, và các đoạn hội thoại của bạn với agent.",
              "**Thông tin thanh toán.** Việc thanh toán do các nhà cung cấp dịch vụ thanh toán xử lý. Chúng tôi nhận xác nhận rằng giao dịch thành công, đó là gói credit nào, và — với chuyển khoản ngân hàng — mã tham chiếu cùng nội dung chuyển khoản để đối soát với đơn hàng của bạn. Chúng tôi không nhìn thấy và không lưu số thẻ đầy đủ của bạn.",
              "**Lịch sử credit.** Sổ ghi credit được cộng và bị trừ, kèm theo lần chạy hoặc công cụ nào đã trừ, để mọi khoản trừ trên tài khoản luôn giải thích được.",
              "**Thông tin kỹ thuật.** Token giữ cho bạn đang đăng nhập, và những dữ liệu thông thường trình duyệt gửi lên như địa chỉ IP và loại trình duyệt, dùng để vận hành và bảo vệ dịch vụ.",
            ],
          },
        ],
      },
      {
        h2: "Chúng tôi dùng thông tin để làm gì",
        blocks: [
          {
            ul: [
              "Để vận hành dịch vụ: viết, chỉnh sửa và xuất các chương luận văn của bạn, và giữ dự án đồng bộ giữa ứng dụng và các công cụ.",
              "Để tính và trừ credit, và để cho bạn thấy mỗi lần chạy tốn bao nhiêu.",
              "Để gửi các email tài khoản bạn cần — xác thực địa chỉ, biên nhận thanh toán, và thông báo về tài khoản hoặc dịch vụ.",
              "Để phản hồi khi bạn liên hệ.",
              "Để giữ dịch vụ an toàn, phát hiện lạm dụng, và tìm nguyên nhân khi có lỗi.",
            ],
          },
        ],
      },
      {
        h2: "AI agent và nội dung của bạn",
        blocks: [
          {
            p: "Để viết một chương, agent gửi những phần liên quan trong dự án của bạn — đề tài, mô hình nghiên cứu, kết quả phân tích bạn tải lên, danh mục tài liệu tham khảo và yêu cầu của bạn — tới nhà cung cấp mô hình ngôn ngữ lớn. Đây chính là phần lõi của dịch vụ, nên không thể tắt đi mà vẫn dùng được.",
          },
          {
            p: "Chúng tôi gửi cho nhà cung cấp đó những gì cần để viết; chúng tôi không gửi mật khẩu, thông tin thanh toán hay số dư credit của bạn. Chúng tôi không dùng nội dung luận văn của bạn để huấn luyện mô hình.",
          },
        ],
      },
      {
        h2: "Chúng tôi chia sẻ dữ liệu với ai",
        blocks: [
          { p: "Chúng tôi không bán thông tin cá nhân của bạn. Chúng tôi chỉ chia sẻ những gì cần thiết với các nhà cung cấp giúp dịch vụ hoạt động:" },
          {
            ul: [
              "**Các nhà cung cấp mô hình ngôn ngữ lớn** (hiện tại là OpenAI và Google) để tạo và chỉnh sửa bản thảo của bạn.",
              "**Các nhà cung cấp thanh toán** — Polar và PayPal cho thanh toán thẻ, và SePay cho chuyển khoản ngân hàng tại Việt Nam — để nhận và xác nhận thanh toán.",
              "**Amazon Web Services** để lưu trữ file bạn tải lên và file xuất ra, và để gửi email tài khoản.",
              "**CrossRef**, khi bạn dùng các công cụ trích dẫn: chúng tôi gửi các chuỗi trích dẫn tìm thấy trong tài liệu của bạn để đối chiếu với dữ liệu công khai.",
              "**Nhà cung cấp dịch vụ kiểm tra trùng lặp**, khi hệ thống có cấu hình sẵn và bạn chạy kiểm tra đó. Nếu không có nhà cung cấp nào được cấu hình, chức năng sẽ báo là không khả dụng và không có dữ liệu nào rời khỏi dịch vụ.",
              "**PostHog**, phục vụ phân tích sản phẩm và chất lượng của chính chúng tôi, khi được bật.",
              "**Nhà cung cấp hạ tầng**, nơi vận hành máy chủ và cơ sở dữ liệu.",
            ],
          },
          {
            p: "Chúng tôi cũng có thể cung cấp thông tin khi pháp luật yêu cầu, hoặc để bảo vệ quyền của chúng tôi hay sự an toàn của người khác.",
          },
        ],
      },
      {
        h2: "Cookie và phân tích",
        blocks: [
          {
            p: "Chúng tôi dùng một token để giữ bạn đang đăng nhập, và một cookie để ghi nhớ ngôn ngữ bạn chọn. Chúng tôi không chạy quảng cáo trên trang này và không bán dữ liệu cho bên quảng cáo.",
          },
        ],
      },
      {
        h2: "Lưu trữ và xóa dữ liệu",
        blocks: [
          {
            p: `Bạn có thể đọc, sửa và xuất nội dung của mình trong ứng dụng bất cứ lúc nào — ý nghĩa của việc xuất file chính là tài liệu đó thuộc về bạn và bạn mang đi được. Để xóa tài khoản cùng dữ liệu gắn với nó, hãy viết thư tới [${EMAIL}](${mailto("DoThesis — yêu cầu xóa tài khoản")}) và chúng tôi sẽ xóa. Chúng tôi giữ lại những chứng từ bắt buộc phải lưu cho mục đích kế toán và thuế, chẳng hạn việc một giao dịch đã được thanh toán.`,
          },
        ],
      },
      {
        h2: "Bảo mật",
        blocks: [
          {
            p: "Mật khẩu được lưu ở dạng băm, và mọi lưu lượng tới dịch vụ đi qua HTTPS. Không có phương thức lưu trữ hay truyền tải nào trên internet là an toàn tuyệt đối, nên chúng tôi không thể cam kết an toàn tuyệt đối.",
          },
        ],
      },
      {
        h2: "Trẻ em",
        blocks: [
          {
            p: `${PRODUCT} được xây dựng cho sinh viên đại học và học viên sau đại học, không hướng tới trẻ em dưới 13 tuổi. Chúng tôi không cố ý thu thập thông tin của trẻ em; nếu bạn cho rằng một trẻ em đã cung cấp dữ liệu cho chúng tôi, hãy liên hệ và chúng tôi sẽ xóa.`,
          },
        ],
      },
      {
        h2: "Thay đổi chính sách",
        blocks: [
          {
            p: "Chúng tôi có thể cập nhật chính sách này theo thời gian. Khi cập nhật, chúng tôi sẽ đăng phiên bản mới trên trang này và đổi ngày ở phía trên.",
          },
        ],
      },
      {
        h2: "Liên hệ",
        blocks: [{ p: `Có câu hỏi về chính sách này? Gửi email tới [${EMAIL}](${mailto("DoThesis — bảo mật")}).` }],
      },
    ],
  },
};

const META: Record<Locale, { title: string; description: string }> = {
  en: {
    title: `Privacy Policy — ${PRODUCT}`,
    description: `What ${PRODUCT} collects, who it is shared with, and the choices you have over your data.`,
  },
  vi: {
    title: `Chính sách bảo mật — ${PRODUCT}`,
    description: `${PRODUCT} thu thập những gì, chia sẻ với ai, và bạn có những lựa chọn nào với dữ liệu của mình.`,
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
      canonical: legalPath("privacy", locale),
      // Both editions ship in this file, so the pair is verified by
      // construction — the condition `alternateLanguages` guards against
      // (a counterpart that 404s) cannot arise here.
      languages: alternateLanguages({
        vi: absoluteUrl(legalPath("privacy", "vi")),
        en: absoluteUrl(legalPath("privacy", "en")),
      }),
    },
  };
}

export default async function PrivacyPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  if (!isLocale(locale)) notFound();
  const copy = COPY[locale];
  return (
    <LegalShell doc="privacy" locale={locale} title={copy.title} meta={copy.meta(formattedDate(locale))}>
      {/* The lede sits one step above body size, matching the blog's lead
          treatment. Inline rather than via `.blog-lead`, whose rule targets a
          `.blog-prose` DESCENDANT — here the prose wrapper is the parent. */}
      <p style={{ fontSize: 19, lineHeight: 1.6 }}>{inline(copy.lede)}</p>
      {renderSections(copy.sections)}
    </LegalShell>
  );
}
