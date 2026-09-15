import type { Metadata } from "next";
import Image from "next/image";

import { Footer } from "../landing/_components/Footer";
import { Nav } from "../landing/_components/Nav";
import { COMPETITORS, comparisonImage } from "./_lib/competitors";
import "../landing/landing.css";
import "./compare.css";

export const metadata: Metadata = {
  title: "So sánh DoThesis với các công cụ AI viết luận văn",
  description: "So sánh DoThesis với ThesisAI, Jenni AI, Paperguide, Thesify, SciSpace và các công cụ nghiên cứu AI phổ biến.",
  alternates: { canonical: "/compare" },
  openGraph: { images: ["/img/compare/overview.webp"] },
};

export default function CompareIndexPage() {
  return (
    <div className="lp-root">
      <Nav />
      <main className="compare-page">
        <header className="compare-hero">
          <div className="lp-wrap">
            <div className="compare-kicker">So sánh công cụ AI luận văn</div>
            <h1 className="compare-title">Không phải AI học thuật nào cũng làm cùng một việc.</h1>
            <p className="compare-lede">Một số công cụ sinh bài, một số giúp đọc paper, một số sửa câu chữ. DoThesis nối đề tài, nguồn, phương pháp, dữ liệu và chương viết thành một dự án có thể kiểm tra.</p>
            <div className="compare-meta"><span className="compare-chip">11 đối thủ</span><span className="compare-chip">Dữ liệu cập nhật 14.09.2026</span><span className="compare-chip">So sánh theo use case</span></div>
            <figure className="compare-visual compare-visual--overview">
              <Image src="/img/compare/overview.webp" width={1664} height={936} priority alt="Hành trình nghiên cứu từ ý tưởng và nguồn đến một luận văn hoàn chỉnh" />
            </figure>
          </div>
        </header>
        <section className="compare-section">
          <div className="lp-wrap">
            <div className="compare-grid">
              <h2>Chọn theo việc bạn cần hoàn thành</h2>
              <p className="compare-prose">Đừng chọn bằng số bài báo trong cơ sở dữ liệu hay số trang AI có thể sinh. Hãy chọn theo điểm nghẽn thật: tìm bằng chứng, cải thiện một bản đã viết, tạo essay thật nhanh, hay đưa một luận văn qua nhiều vòng từ ý tưởng đến bản nộp.</p>
            </div>
            <div className="compare-directory">
              {COMPETITORS.map((item) => <a href={`/compare/${item.slug}`} key={item.slug}><Image className="compare-card-image" src={comparisonImage(item.category)} width={1664} height={936} alt="" /><div className="compare-card-body"><span className="compare-chip">{item.category}</span><h2>DoThesis vs {item.name}</h2><p>{item.verdict}</p><div className="compare-arrow">Đọc so sánh →</div></div></a>)}
            </div>
          </div>
        </section>
      </main>
      <Footer />
    </div>
  );
}
