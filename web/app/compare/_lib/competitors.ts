export type Competitor = {
  slug: string;
  name: string;
  category: "Máy sinh bài" | "Trợ lý viết" | "Tổng hợp bằng chứng";
  price: string;
  promise: string;
  strength: string;
  limitation: string;
  verdict: string;
  bestFor: string;
  longForm: string;
  sources: Array<[string, string]>;
};

/**
 * Decision: comparison claims live in one typed catalogue so the hub, detail
 * pages, footer and sitemap cannot quietly disagree as competitors change.
 * Facts below are from the supplied competitive review dated 14 September 2026.
 */
export const COMPETITORS: Competitor[] = [
  {
    slug: "thesisai",
    name: "ThesisAI",
    category: "Máy sinh bài",
    price: "$12–16/tháng",
    promise: "Một prompt tạo tài liệu 8–80 trang, có tìm nguồn và xuất nhiều định dạng.",
    strength: "Sinh bản dài rất nhanh; xuất PDF, Word, LaTeX và BibTeX.",
    limitation: "Quy trình chủ yếu là một lượt và giới hạn bốn tài liệu mỗi tháng.",
    verdict: "Chọn ThesisAI khi bạn cần một bản nháp dài ngay. Chọn DoThesis khi luận văn còn thay đổi qua góp ý, dữ liệu và nhiều vòng viết lại.",
    bestFor: "Người đã có brief rõ và cần bản nháp dài trong một lần chạy.",
    longForm: "Khác biệt không nằm ở số trang. DoThesis giữ đề tài, nguồn, mô hình, dữ liệu phân tích và từng chương trong cùng một hồ sơ dự án; khi một giả thuyết thay đổi, các phần phía sau được đánh dấu để rà soát. Đó là lợi thế quan trọng hơn tốc độ sinh bản đầu tiên khi luận văn phải đi qua nhiều vòng với giảng viên.",
    sources: [["ThesisAI", "https://thesisai.io"]],
  },
  {
    slug: "paperguide",
    name: "Paperguide",
    category: "Tổng hợp bằng chứng",
    price: "từ $12/tháng (trả năm)",
    promise: "Tìm, đọc, quản lý tài liệu và viết với kho hơn 200 triệu bài.",
    strength: "Một workspace nghiên cứu rộng, có xuất RIS, CSV, BIB, PDF và DOCX.",
    limitation: "Rộng về nghiên cứu tài liệu nhưng không dẫn dắt toàn bộ cấu trúc luận văn theo từng mốc.",
    verdict: "Paperguide mạnh khi công việc bắt đầu từ thư viện bài báo. DoThesis mạnh khi công việc bắt đầu từ một luận văn phải hoàn thành và bảo vệ.",
    bestFor: "Người làm literature review nặng và cần quản lý thư viện nghiên cứu.",
    longForm: "DoThesis coi literature review là một trong năm mô-đun có quan hệ với câu hỏi nghiên cứu, mô hình, phương pháp, phân tích và chương viết. Vì vậy nguồn không đứng riêng trong thư viện: nó phải giải thích được khoảng trống, nâng đỡ giả thuyết và xuất hiện nhất quán trong bản thảo.",
    sources: [["Paperguide", "https://paperguide.ai"]],
  },
  {
    slug: "thesify",
    name: "Thesify",
    category: "Trợ lý viết",
    price: "từ €7,50/tháng (trả năm)",
    promise: "Phản biện bản nháp và hỗ trợ học thuật mà không viết thay toàn bộ.",
    strength: "Định vị có trách nhiệm, tập trung vào phản hồi và tính liêm chính học thuật.",
    limitation: "Không chủ động tạo và vận hành trọn quy trình từ đề tài đến phân tích dữ liệu.",
    verdict: "Thesify phù hợp để nhận phản hồi trên bản đã có. DoThesis phù hợp khi bạn cần vừa xây nghiên cứu, vừa được kiểm tra ở mỗi bước.",
    bestFor: "Người đã có bản thảo và muốn một lớp phản biện bổ sung.",
    longForm: "DoThesis cũng giữ người học trong vòng lặp, nhưng can thiệp sớm hơn: từ câu hỏi nghiên cứu, nguồn đã xác minh, thiết kế phương pháp đến số liệu thật. Các cổng kiểm tra chặn số liệu bất khả thi và chặn chương viết nếu hệ số trong prose mâu thuẫn với kết quả phân tích đã lưu.",
    sources: [["Thesify", "https://thesify.ai"]],
  },
  {
    slug: "jenni-ai",
    name: "Jenni AI",
    category: "Trợ lý viết",
    price: "$12–29/tháng",
    promise: "Autocomplete, trích dẫn và viết cùng người dùng trên một trình soạn thảo gọn.",
    strength: "Trải nghiệm viết trực tiếp tốt và kho tìm kiếm học thuật rất lớn.",
    limitation: "Tối ưu cho từng phiên viết hơn là quản lý trạng thái của cả dự án luận văn.",
    verdict: "Jenni là trình viết AI tốt. DoThesis là một quy trình luận văn có trình viết ở bên trong.",
    bestFor: "Người biết mình cần viết gì và muốn tăng tốc ngay trong editor.",
    longForm: "Nếu nút thắt là câu chữ, Jenni rất hợp lý. Nếu nút thắt là không biết bước tiếp theo, mô hình có còn khớp câu hỏi hay Chương 5 có đang dẫn sai số liệu ở Chương 4, DoThesis giải bài toán ở cấp dự án thay vì cấp đoạn văn.",
    sources: [["Jenni AI", "https://jenni.ai"]],
  },
  {
    slug: "samwell",
    name: "Samwell",
    category: "Máy sinh bài",
    price: "từ $8/tháng (trả năm)",
    promise: "Sinh essay dài nhanh với tìm nguồn và công cụ làm văn bản giống người viết.",
    strength: "Giá thấp, vào việc nhanh, phù hợp bài tập có deadline ngắn.",
    limitation: "Thiên về essay và đầu ra một lượt hơn một nghiên cứu kéo dài nhiều tháng.",
    verdict: "Samwell hợp với essay. DoThesis được xây riêng cho luận văn có mô hình, dữ liệu, chương và vòng phản hồi.",
    bestFor: "Sinh viên cần một essay hoặc bản nháp ngắn với chi phí thấp.",
    longForm: "Luận văn không chỉ là một bài viết dài hơn. Nó là chuỗi quyết định phụ thuộc nhau. DoThesis lưu các quyết định đó theo dự án, cảnh báo phần hạ nguồn khi nền tảng thay đổi và yêu cầu dữ liệu thật trước khi ghi nhận kết quả phân tích.",
    sources: [["Samwell", "https://samwell.ai"]],
  },
  {
    slug: "textero",
    name: "Textero",
    category: "Máy sinh bài",
    price: "từ $8,25/tháng (trả năm)",
    promise: "Sinh bài đến 20.000 từ, paraphrase và giảm khả năng bị phát hiện là AI.",
    strength: "Nhanh, dễ bắt đầu và nhắm thẳng nhu cầu bài viết có deadline.",
    limitation: "Lớp nguồn và kiểm chứng cần người dùng tự rà soát kỹ trước khi nộp.",
    verdict: "Textero tối ưu cho tốc độ tạo chữ. DoThesis tối ưu cho một luận văn có thể truy ngược từ kết luận về dữ liệu và nguồn.",
    bestFor: "Người ưu tiên tốc độ tạo bản nháp ngắn hơn quy trình nghiên cứu.",
    longForm: "DoThesis không xem việc qua AI detector là thước đo chất lượng luận văn. Sản phẩm tập trung vào nguồn được tra cứu, phân tích chạy bằng công cụ thống kê giới hạn thao tác và tính nhất quán giữa kết quả đã lưu với chương cuối.",
    sources: [["Textero", "https://textero.ai"]],
  },
  {
    slug: "paperpal",
    name: "Paperpal",
    category: "Trợ lý viết",
    price: "từ $12/tháng (trả năm)",
    promise: "Biên tập học thuật, kiểm tra ngôn ngữ và nguồn cho bản thảo nghiên cứu.",
    strength: "Mạnh về chuẩn tiếng Anh học thuật và workflow Word, Google Docs, Overleaf.",
    limitation: "Không phải hệ thống lập kế hoạch và hoàn tất một luận văn từ đầu.",
    verdict: "Paperpal là lớp polish rất tốt trước khi nộp. DoThesis là nơi dự án được hình thành, phân tích và viết ra trước bước polish.",
    bestFor: "Tác giả đã có manuscript và cần nâng chuẩn tiếng Anh học thuật.",
    longForm: "Hai sản phẩm có thể bổ sung nhau. DoThesis giữ logic nghiên cứu và bằng chứng xuyên năm mô-đun; Paperpal đi sâu vào chất lượng diễn đạt và chuẩn nộp tạp chí của một bản thảo đã tồn tại.",
    sources: [["Paperpal", "https://paperpal.com"]],
  },
  {
    slug: "yomu",
    name: "Yomu AI",
    category: "Trợ lý viết",
    price: "từ $10/tháng",
    promise: "Soạn thảo theo từng phần, tìm trích dẫn và cải thiện văn phong trong editor.",
    strength: "Trải nghiệm viết tập trung, nhẹ và dễ dùng cho bài học thuật.",
    limitation: "Người dùng vẫn phải tự kết nối các quyết định nghiên cứu và kiểm tra nguồn cuối cùng.",
    verdict: "Yomu giúp viết từng phần. DoThesis nhớ vì sao phần đó tồn tại và nó phải khớp với phần nào khác.",
    bestFor: "Người đã có outline và muốn một editor hỗ trợ viết theo đoạn.",
    longForm: "Điểm khác biệt của DoThesis là state dùng chung cho toàn dự án. Câu hỏi, khoảng trống, giả thuyết, phương pháp, kết quả và chương không phải các tài liệu rời; chúng là các lát cắt có quan hệ và được kiểm tra khi thay đổi.",
    sources: [["Yomu AI", "https://www.yomu.ai"]],
  },
  {
    slug: "elicit",
    name: "Elicit",
    category: "Tổng hợp bằng chứng",
    price: "từ $49/tháng (trả năm)",
    promise: "Systematic review, sàng lọc và trích xuất dữ liệu từ khối lượng nghiên cứu lớn.",
    strength: "Quy trình evidence synthesis sâu, có thể kiểm toán và phù hợp nhóm nghiên cứu.",
    limitation: "Giá và workflow vượt nhu cầu của nhiều sinh viên đang hoàn thành một luận văn đơn lẻ.",
    verdict: "Elicit thắng ở systematic review quy mô lớn. DoThesis thắng ở việc nối evidence với toàn bộ luận văn của một sinh viên.",
    bestFor: "Nhóm nghiên cứu, y tế hoặc chính sách làm tổng quan hệ thống.",
    longForm: "Đây không hoàn toàn là hai sản phẩm thay thế nhau. Elicit đào sâu bước tổng hợp bằng chứng; DoThesis bao phủ cả hành trình và đưa bằng chứng vào đúng câu hỏi, mô hình, phương pháp và chương viết của một dự án cụ thể.",
    sources: [["Elicit", "https://elicit.com"]],
  },
  {
    slug: "scispace",
    name: "SciSpace",
    category: "Tổng hợp bằng chứng",
    price: "từ $12/tháng (trả năm)",
    promise: "Tìm, đọc, giải thích paper và hỗ trợ viết từ một kho nghiên cứu lớn.",
    strength: "Bộ công cụ khám phá và trò chuyện với tài liệu rất rộng.",
    limitation: "Nhiều công cụ mạnh nhưng không biến thành một lộ trình luận văn có trạng thái rõ ràng.",
    verdict: "SciSpace là bàn làm việc cho paper. DoThesis là người dẫn đường cho thesis.",
    bestFor: "Người đọc nhiều paper và cần hỏi đáp nhanh trên tài liệu.",
    longForm: "DoThesis không cố thay thế chiều sâu khám phá paper của SciSpace. Nó tập trung vào đoạn khó hơn sau đó: biến những gì đã đọc thành khoảng trống có thể bảo vệ, thiết kế khả thi, phân tích hợp lệ và bản thảo nhất quán.",
    sources: [["SciSpace", "https://scispace.com"]],
  },
  {
    slug: "sourcely",
    name: "Sourcely",
    category: "Tổng hợp bằng chứng",
    price: "từ $19/tháng (trả năm)",
    promise: "Tìm nguồn học thuật liên quan và định dạng trích dẫn theo hàng trăm kiểu.",
    strength: "Tập trung rõ vào việc tìm nguồn cho một đoạn văn hoặc lập luận.",
    limitation: "Không làm phần thiết kế nghiên cứu, phân tích dữ liệu và quản lý chương.",
    verdict: "Sourcely giải bài toán tìm nguồn. DoThesis giải bài toán làm luận văn, trong đó tìm nguồn là một bước bắt buộc.",
    bestFor: "Người có bản nháp và đang thiếu nguồn nâng đỡ một số lập luận.",
    longForm: "Nguồn trong DoThesis không chỉ được chèn vào câu. Chúng được dùng để xác lập khoảng trống, nối với mô hình khái niệm và được đối chiếu với danh mục tham khảo trước khi xuất bản thảo.",
    sources: [["Sourcely", "https://www.sourcely.net"]],
  },
];

export const competitorBySlug = (slug: string) =>
  COMPETITORS.find((competitor) => competitor.slug === slug);

export function comparisonImage(category: Competitor["category"]): string {
  if (category === "Máy sinh bài") return "/img/compare/generator.webp";
  if (category === "Trợ lý viết") return "/img/compare/writing-assistant.webp";
  return "/img/compare/evidence-synthesis.webp";
}
