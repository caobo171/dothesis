import type { Metadata } from "next";
import Image from "next/image";
import { notFound } from "next/navigation";

import { Footer } from "../../landing/_components/Footer";
import { Nav } from "../../landing/_components/Nav";
import { CTA_HREF } from "../../landing/_components/shared";
import { COMPETITORS, comparisonImage, competitorBySlug } from "../_lib/competitors";
import "../../landing/landing.css";
import "../compare.css";

type Props = { params: Promise<{ slug: string }> };

export function generateStaticParams() { return COMPETITORS.map(({ slug }) => ({ slug })); }

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const item = competitorBySlug((await params).slug);
  if (!item) return {};
  return {
    title: `DoThesis vs ${item.name}: công cụ nào hợp với luận văn của bạn?`,
    description: `${item.verdict} So sánh quy trình, điểm mạnh, giới hạn và mức giá công bố.`,
    alternates: { canonical: `/compare/${item.slug}` },
    openGraph: { images: [comparisonImage(item.category)] },
  };
}

export default async function CompetitorPage({ params }: Props) {
  const item = competitorBySlug((await params).slug);
  if (!item) notFound();
  return (
    <div className="lp-root">
      <Nav />
      <main className="compare-page">
        <header className="compare-hero"><div className="lp-wrap"><div className="compare-kicker">DoThesis hay {item.name}?</div><h1 className="compare-title">DoThesis vs {item.name}</h1><p className="compare-lede">{item.verdict}</p><div className="compare-meta"><span className="compare-chip">{item.category}</span><span className="compare-chip">{item.price}</span><span className="compare-chip">Cập nhật 14.09.2026</span></div><figure className="compare-visual"><Image src={comparisonImage(item.category)} width={1664} height={936} priority alt={`Minh họa khác biệt giữa DoThesis và nhóm ${item.category.toLocaleLowerCase("vi")}`} /></figure></div></header>
        <section className="compare-section"><div className="lp-wrap compare-grid"><h2>Khác nhau ở đâu?</h2><div><p className="compare-prose">{item.longForm}</p><p className="compare-verdict">{item.verdict}</p></div></div></section>
        <section className="compare-section"><div className="lp-wrap"><h2>So sánh nhanh</h2><div className="compare-tablewrap"><table className="compare-table"><thead><tr><th>Tiêu chí</th><th>DoThesis</th><th>{item.name}</th></tr></thead><tbody>
          <tr><td>Lời hứa chính</td><td className="compare-winner">Đi cùng một dự án từ đề tài đến bản nộp</td><td>{item.promise}</td></tr>
          <tr><td>Đơn vị công việc</td><td>Một luận văn có trạng thái xuyên suốt 5 mô-đun</td><td>Một phiên viết, thư viện nguồn hoặc bản thảo</td></tr>
          <tr><td>Điểm mạnh</td><td>Nối nguồn, mô hình, phương pháp, dữ liệu và chương; cảnh báo khi thay đổi gây lệch phần sau</td><td>{item.strength}</td></tr>
          <tr><td>Kiểm tra cứng</td><td className="compare-winner">Nguồn được xác minh; số liệu bất khả thi và prose lệch kết quả bị chặn</td><td>Phụ thuộc workflow và thao tác rà soát của người dùng</td></tr>
          <tr><td>Phù hợp nhất</td><td>Sinh viên làm luận văn nhiều tháng, có dữ liệu và góp ý giảng viên</td><td>{item.bestFor}</td></tr>
          <tr><td>Giá công bố</td><td>Trả theo credit sử dụng</td><td>{item.price}</td></tr>
        </tbody></table></div></div></section>
        <section className="compare-section"><div className="lp-wrap"><div className="compare-cards"><div className="compare-card"><h3>Khi nên chọn {item.name}</h3><p>{item.bestFor} {item.strength}</p></div><div className="compare-card"><h3>Khi nên chọn DoThesis</h3><p>Khi bạn cần biết bước tiếp theo, giữ mọi quyết định nhất quán và có một bản DOCX/PDF đi ra từ cùng dữ liệu dự án.</p></div></div></div></section>
        <section className="compare-section"><div className="lp-wrap compare-grid"><h2>Nguồn và cách đọc</h2><div><p className="compare-prose">So sánh dùng giá trả phí thấp nhất được công bố trong nghiên cứu ngày 14.09.2026; mức “trả năm” là giá quy đổi theo tháng. Tính năng và giá có thể thay đổi. DoThesis không khẳng định công cụ nào tốt nhất cho mọi người — trang này chỉ làm rõ chúng tối ưu cho công việc khác nhau.</p><p className="compare-sources" style={{marginTop:18}}>Nguồn chính: {item.sources.map(([label,url], index) => <span key={url}>{index > 0 ? ", " : ""}<a href={url} target="_blank" rel="noopener noreferrer">{label}</a></span>)}</p></div></div></section>
        <section className="compare-cta"><div className="lp-wrap"><h2>Đừng chỉ tạo thêm chữ. Hãy hoàn thành một luận văn nhất quán.</h2><p>Đưa đề tài hoặc tài liệu bạn đang có vào DoThesis. Agent sẽ đọc trạng thái hiện tại, chỉ ra bước tiếp theo và làm cùng bạn.</p><a href={CTA_HREF}>Bắt đầu với DoThesis</a></div></section>
      </main>
      <Footer />
    </div>
  );
}
