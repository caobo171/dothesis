import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { alternateLanguages } from "../../blog/_lib/hreflang";
import { absoluteUrl } from "../../blog/_lib/site";
import { LegalShell } from "../../legal/_components/LegalShell";
import { type Section, inline, renderSections } from "../../legal/_lib/inline";
import { EMAIL, ENTITY, PRODUCT, SITE_HOST, formattedDate, legalPath, mailto } from "../../legal/_lib/site";
import { LOCALES, type Locale, isLocale } from "../../lib/i18n/locale";

/**
 * Terms of use, in both editions.
 *
 * Two clauses here are specific to this product rather than boilerplate, and
 * both are load-bearing:
 *
 *   Academic integrity — a tool that drafts a thesis has to say plainly that the
 *   submission is the student's and their institution's rules govern it. Leaving
 *   it out would not make the obligation go away; it would only mean the student
 *   first meets it from their supervisor.
 *
 *   Credits and refunds — these restate the promise the credit page already
 *   makes (`credit.note.refund`, `credit.note.deduct` in the i18n catalogue).
 *   Terms that contradicted that page would be the version that loses.
 */
export const dynamic = "force-static";

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

const COPY: Record<Locale, { title: string; meta: (d: string) => string; lede: string; sections: Section[] }> = {
  en: {
    title: "Terms of Use",
    meta: (d) => `Last updated ${d}`,
    lede: `These terms govern your use of ${PRODUCT} ([${SITE_HOST}](https://${SITE_HOST})). By creating an account or using the service, you agree to them. If you do not agree, please do not use the service.`,
    sections: [
      {
        h2: "The service",
        blocks: [
          {
            p: `${PRODUCT} is operated by ${ENTITY}, in Vietnam. It is an AI writing assistant for quantitative theses: you bring a topic, a research model and your own analysis output from SmartPLS or SPSS, and it drafts, revises and exports chapters with you. We may add, change or remove features as the product develops.`,
          },
          {
            p: `${PRODUCT} does **not** run your statistics for you. You run your own analysis in your own software, and the service writes about the output you provide.`,
          },
        ],
      },
      {
        h2: "Your academic responsibility",
        blocks: [
          {
            p: "The thesis you submit is yours, and so is the responsibility for it. Universities differ — some permit AI assistance with disclosure, some restrict it, some prohibit it — and it is your obligation to know and follow the rules of your own institution and supervisor.",
          },
          {
            p: "You are responsible for checking every fact, number, citation and claim in a draft before you submit it. The tools flag problems; they do not certify that a document is correct, original or acceptable to your examiner. We provide no warranty that output will be accepted, graded a particular way, or pass any similarity check.",
          },
          {
            p: "Do not use the service to misrepresent someone else's work as your own, or to fabricate data or results.",
          },
        ],
      },
      {
        h2: "Your account",
        blocks: [
          {
            p: "You need an account to use the service, and you must verify your email address. Keep your password and any API tokens private — anything done through your account is treated as done by you. Tell us promptly if you think someone else has access. One account is for one person; do not share or resell access.",
          },
        ],
      },
      {
        h2: "Acceptable use",
        blocks: [
          {
            p: "Use the service lawfully. Do not attempt to break, overload, scrape or reverse engineer it, do not use it to store or distribute unlawful content, and do not use it in a way that infringes someone else's rights.",
          },
        ],
      },
      {
        h2: "Your content",
        blocks: [
          {
            p: "The topic, data, documents and drafts you put into the service are yours. To run the service you grant us the permission needed to store and process that content on your behalf, including sending the relevant parts to a large-language-model provider so a chapter can be drafted — see the [Privacy Policy](/privacy/en) for exactly who that is. We do not claim ownership of your work, and we do not use it to train models.",
          },
          {
            p: "You can export your work at any time, and delete it or your whole account.",
          },
        ],
      },
      {
        h2: "Credits, payment and refunds",
        blocks: [
          {
            p: "The service runs on credits. You buy a credit pack at the price shown at checkout, and runs and tools debit credits from your balance. Credit packs are one-off purchases, not a subscription — nothing renews automatically.",
          },
          {
            ul: [
              "**When you are charged.** Credits are debited when a run starts, and the cost of each run is recorded in your credit history.",
              "**When we refund.** If a run fails because of an error on our side, or a tool cannot complete, the credits for it are returned to your balance. A run that completes and produces a draft you simply did not like is not an error and is not refunded.",
              "**Money refunds.** Except where the law requires otherwise, payments for credit packs are non-refundable once credits have been used. If something went wrong with a charge, write to us and we will look into it.",
              "**Prices.** Prices and pack sizes may change. A change never alters credits already in your balance or a purchase already made.",
            ],
          },
        ],
      },
      {
        h2: "Our intellectual property",
        blocks: [
          {
            p: `The ${PRODUCT} software, name and branding belong to ${ENTITY}. These terms give you the right to use the service, not any right to our code, trademarks or design.`,
          },
        ],
      },
      {
        h2: "Availability and disclaimer",
        blocks: [
          {
            p: 'The service is provided "as is", without warranties of any kind. We work to keep it running and accurate, but we do not guarantee that it will be uninterrupted or error-free, or that generated text, citations or analysis commentary will always be correct. AI systems make mistakes, including confident ones.',
          },
        ],
      },
      {
        h2: "Limitation of liability",
        blocks: [
          {
            p: `To the extent the law allows, ${ENTITY} is not liable for indirect or consequential losses, or for lost data, lost marks, missed deadlines or academic penalties, arising from your use of or inability to use the service. Where liability cannot be excluded, it is limited to the amount you paid us in the twelve months before the claim.`,
          },
        ],
      },
      {
        h2: "Termination",
        blocks: [
          {
            p: "You can stop using the service and delete your account at any time. We may suspend or close an account that breaks these terms or puts the service or its users at risk. If we close your account without cause, we will refund unused credits.",
          },
        ],
      },
      {
        h2: "Changes to these terms",
        blocks: [
          {
            p: "We may update these terms from time to time. When we do, we will post the new version here and change the date above. Continuing to use the service after a change means you accept the updated terms.",
          },
        ],
      },
      {
        h2: "Governing law",
        blocks: [
          { p: "These terms are governed by the laws of Vietnam, without regard to its conflict-of-law rules." },
        ],
      },
      {
        h2: "Contact",
        blocks: [{ p: `Questions about these terms? Email [${EMAIL}](${mailto("DoThesis — terms")}).` }],
      },
    ],
  },

  vi: {
    title: "Điều khoản sử dụng",
    meta: (d) => `Cập nhật lần cuối ${d}`,
    lede: `Các điều khoản này điều chỉnh việc bạn sử dụng ${PRODUCT} ([${SITE_HOST}](https://${SITE_HOST})). Khi tạo tài khoản hoặc sử dụng dịch vụ, bạn đồng ý với các điều khoản này. Nếu bạn không đồng ý, vui lòng không sử dụng dịch vụ.`,
    sections: [
      {
        h2: "Về dịch vụ",
        blocks: [
          {
            p: `${PRODUCT} do ${ENTITY} vận hành, tại Việt Nam. Đây là công cụ AI hỗ trợ viết luận văn định lượng: bạn đưa vào đề tài, mô hình nghiên cứu và kết quả phân tích của chính bạn từ SmartPLS hoặc SPSS, còn dịch vụ cùng bạn viết, chỉnh sửa và xuất các chương.  Chúng tôi có thể bổ sung, thay đổi hoặc gỡ bỏ tính năng trong quá trình phát triển sản phẩm.`,
          },
          {
            p: `${PRODUCT} **không** chạy thống kê thay bạn. Bạn tự chạy phân tích trên phần mềm của mình, và dịch vụ viết dựa trên kết quả bạn cung cấp.`,
          },
        ],
      },
      {
        h2: "Trách nhiệm học thuật của bạn",
        blocks: [
          {
            p: "Luận văn bạn nộp là của bạn, và trách nhiệm với nó cũng vậy. Mỗi trường có quy định khác nhau — có nơi cho phép dùng AI kèm khai báo, có nơi hạn chế, có nơi cấm — và bạn có nghĩa vụ nắm rõ và tuân thủ quy định của trường cùng giảng viên hướng dẫn của mình.",
          },
          {
            p: "Bạn chịu trách nhiệm kiểm tra mọi dữ kiện, con số, trích dẫn và luận điểm trong bản thảo trước khi nộp. Các công cụ chỉ ra vấn đề; chúng không chứng nhận rằng một tài liệu là chính xác, nguyên bản hay được hội đồng chấp nhận. Chúng tôi không cam kết rằng kết quả sẽ được chấp nhận, được chấm theo một mức nào đó, hay vượt qua bất kỳ lần kiểm tra trùng lặp nào.",
          },
          {
            p: "Không sử dụng dịch vụ để trình bày công trình của người khác như của mình, hoặc để bịa dữ liệu, bịa kết quả.",
          },
        ],
      },
      {
        h2: "Tài khoản của bạn",
        blocks: [
          {
            p: "Bạn cần một tài khoản để sử dụng dịch vụ, và cần xác thực địa chỉ email. Hãy giữ kín mật khẩu và các token API — mọi thao tác thực hiện qua tài khoản của bạn được xem là do bạn thực hiện. Hãy báo cho chúng tôi ngay nếu bạn nghĩ có người khác truy cập được. Một tài khoản dành cho một người; không chia sẻ hoặc bán lại quyền truy cập.",
          },
        ],
      },
      {
        h2: "Sử dụng hợp lệ",
        blocks: [
          {
            p: "Hãy sử dụng dịch vụ đúng pháp luật. Không tìm cách phá hoại, gây quá tải, thu thập dữ liệu tự động hay dịch ngược dịch vụ; không dùng dịch vụ để lưu trữ hoặc phát tán nội dung trái pháp luật; không dùng theo cách xâm phạm quyền của người khác.",
          },
        ],
      },
      {
        h2: "Nội dung của bạn",
        blocks: [
          {
            p: "Đề tài, dữ liệu, tài liệu và bản thảo bạn đưa vào dịch vụ là của bạn. Để vận hành dịch vụ, bạn cho phép chúng tôi lưu trữ và xử lý nội dung đó thay mặt bạn, bao gồm việc gửi các phần liên quan tới nhà cung cấp mô hình ngôn ngữ lớn để viết một chương — xem [Chính sách bảo mật](/privacy/vi) để biết chính xác đó là những bên nào. Chúng tôi không tuyên bố quyền sở hữu với công trình của bạn, và không dùng nó để huấn luyện mô hình.",
          },
          { p: "Bạn có thể xuất nội dung của mình bất cứ lúc nào, và xóa nội dung đó hoặc toàn bộ tài khoản." },
        ],
      },
      {
        h2: "Credit, thanh toán và hoàn tiền",
        blocks: [
          {
            p: "Dịch vụ vận hành bằng credit. Bạn mua gói credit theo giá hiển thị khi thanh toán, và mỗi lần chạy hoặc dùng công cụ sẽ trừ credit từ số dư. Gói credit là khoản mua một lần, không phải thuê bao — không có gì tự động gia hạn.",
          },
          {
            ul: [
              "**Khi nào bị trừ.** Credit bị trừ khi một lần chạy bắt đầu, và chi phí của từng lần chạy được ghi lại trong lịch sử credit của bạn.",
              "**Khi nào được hoàn.** Nếu một lần chạy thất bại do lỗi từ phía chúng tôi, hoặc một công cụ không hoàn thành được, credit cho lần đó sẽ được trả lại vào số dư. Một lần chạy hoàn tất và cho ra bản thảo mà bạn chỉ đơn giản là không thích thì không phải lỗi và không được hoàn.",
              "**Hoàn tiền mặt.** Trừ khi pháp luật quy định khác, các khoản thanh toán cho gói credit không được hoàn lại sau khi credit đã được sử dụng. Nếu có sự cố với một giao dịch, hãy viết thư cho chúng tôi và chúng tôi sẽ kiểm tra.",
              "**Giá.** Giá và dung lượng gói có thể thay đổi. Thay đổi không bao giờ ảnh hưởng tới credit đã có trong số dư hay giao dịch đã thực hiện.",
            ],
          },
        ],
      },
      {
        h2: "Quyền sở hữu trí tuệ của chúng tôi",
        blocks: [
          {
            p: `Phần mềm, tên gọi và bộ nhận diện ${PRODUCT} thuộc về ${ENTITY}. Các điều khoản này trao cho bạn quyền sử dụng dịch vụ, không trao bất kỳ quyền nào đối với mã nguồn, nhãn hiệu hay thiết kế của chúng tôi.`,
          },
        ],
      },
      {
        h2: "Tính khả dụng và miễn trừ",
        blocks: [
          {
            p: 'Dịch vụ được cung cấp "nguyên trạng", không kèm bảo đảm dưới bất kỳ hình thức nào. Chúng tôi nỗ lực để dịch vụ hoạt động ổn định và chính xác, nhưng không cam kết rằng dịch vụ sẽ không gián đoạn hay không có lỗi, cũng không cam kết rằng văn bản, trích dẫn hay phần bình luận kết quả do AI tạo ra luôn đúng. Các hệ thống AI có thể sai, kể cả khi trình bày rất chắc chắn.',
          },
        ],
      },
      {
        h2: "Giới hạn trách nhiệm",
        blocks: [
          {
            p: `Trong phạm vi pháp luật cho phép, ${ENTITY} không chịu trách nhiệm với các thiệt hại gián tiếp hoặc phái sinh, hoặc với việc mất dữ liệu, mất điểm, trễ hạn nộp hay bị xử lý kỷ luật học thuật, phát sinh từ việc bạn sử dụng hoặc không thể sử dụng dịch vụ. Với phần trách nhiệm không thể loại trừ, mức trách nhiệm được giới hạn ở số tiền bạn đã thanh toán cho chúng tôi trong mười hai tháng trước thời điểm phát sinh khiếu nại.`,
          },
        ],
      },
      {
        h2: "Chấm dứt",
        blocks: [
          {
            p: "Bạn có thể ngừng sử dụng dịch vụ và xóa tài khoản bất cứ lúc nào. Chúng tôi có thể tạm khóa hoặc đóng tài khoản vi phạm các điều khoản này hoặc gây rủi ro cho dịch vụ và người dùng khác. Nếu chúng tôi đóng tài khoản của bạn mà không có lý do từ phía bạn, chúng tôi sẽ hoàn lại phần credit chưa dùng.",
          },
        ],
      },
      {
        h2: "Thay đổi điều khoản",
        blocks: [
          {
            p: "Chúng tôi có thể cập nhật các điều khoản này theo thời gian. Khi cập nhật, chúng tôi sẽ đăng phiên bản mới tại đây và đổi ngày ở phía trên. Việc bạn tiếp tục sử dụng dịch vụ sau khi có thay đổi đồng nghĩa với việc bạn chấp nhận điều khoản đã cập nhật.",
          },
        ],
      },
      {
        h2: "Luật áp dụng",
        blocks: [
          { p: "Các điều khoản này được điều chỉnh bởi pháp luật Việt Nam, không áp dụng các quy phạm xung đột pháp luật." },
        ],
      },
      {
        h2: "Liên hệ",
        blocks: [{ p: `Có câu hỏi về các điều khoản này? Gửi email tới [${EMAIL}](${mailto("DoThesis — điều khoản")}).` }],
      },
    ],
  },
};

const META: Record<Locale, { title: string; description: string }> = {
  en: {
    title: `Terms of Use — ${PRODUCT}`,
    description: `The terms you agree to when you use ${PRODUCT}, including credits, refunds and your academic responsibility.`,
  },
  vi: {
    title: `Điều khoản sử dụng — ${PRODUCT}`,
    description: `Các điều khoản bạn đồng ý khi dùng ${PRODUCT}: credit, hoàn tiền và trách nhiệm học thuật của bạn.`,
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
      canonical: legalPath("terms", locale),
      languages: alternateLanguages({
        vi: absoluteUrl(legalPath("terms", "vi")),
        en: absoluteUrl(legalPath("terms", "en")),
      }),
    },
  };
}

export default async function TermsPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  if (!isLocale(locale)) notFound();
  const copy = COPY[locale];
  return (
    <LegalShell doc="terms" locale={locale} title={copy.title} meta={copy.meta(formattedDate(locale))}>
      <p style={{ fontSize: 19, lineHeight: 1.6 }}>{inline(copy.lede)}</p>
      {renderSections(copy.sections)}
    </LegalShell>
  );
}
