# 📘 Product Requirements Document (PRD)

## ResearchFlow — AI-Powered Academic Research Assistant

**Version:** 1.1.0 | **Ngày:** 2026-05 | **Loại tài liệu:** PRD \+ UX Spec \+ Feature Spec **Changelog v1.1:** Redesign Module 2 (Chat-first flow \+ cited gaps), Module 3 (Multi-method \+ qualitative), Module 4 (Adaptive analysis outline by data type)

---

## MỤC LỤC

1. [Tổng quan sản phẩm](#1-tổng-quan-sản-phẩm)  
2. [Người dùng mục tiêu & Pain Points](#2-người-dùng-mục-tiêu--pain-points)  
3. [Triết lý thiết kế UX](#3-triết-lý-thiết-kế-ux)  
4. [Kiến trúc thông tin & Navigation](#4-kiến-trúc-thông-tin--navigation)  
5. [Hệ thống Project & Workspace](#5-hệ-thống-project--workspace)  
6. [Các Module chính (Research Flow)](#6-các-module-chính-research-flow)  
   - [Module 1 — Topic Discovery](#module-1--topic-discovery)  
   - [Module 2 — Literature Review *(Chat-first, cited gaps)*](#module-2--literature-review)  
   - [Module 3 — Research Design *(Multi-method)*](#module-3--research-design)  
   - [Module 4 — Data Analysis *(Adaptive outline)*](#module-4--data-analysis)  
   - [Module 5 — Writing & Finalization](#module-5--writing--finalization)  
7. [Cross-Module Features](#7-cross-module-features)  
8. [Entry Points & Flexible Onboarding](#8-entry-points--flexible-onboarding)  
9. [Interaction Model: Click-first, Chat-fallback](#9-interaction-model-click-first-chat-fallback)  
10. [Token-based Pricing Model](#10-token-based-pricing-model)  
11. [Technical Architecture Notes](#11-technical-architecture-notes)  
12. [Use Cases chi tiết](#12-use-cases-chi-tiết)  
13. [Non-functional Requirements](#13-non-functional-requirements)  
14. [Roadmap gợi ý](#14-roadmap-gợi-ý)

---

## 1\. TỔNG QUAN SẢN PHẨM

### 1.1 Định nghĩa sản phẩm

**ResearchFlow** là nền tảng SaaS hỗ trợ toàn bộ vòng đời nghiên cứu học thuật (academic research lifecycle) — từ lúc hình thành ý tưởng đến khi hoàn thiện bài luận — bằng cách kết hợp AI generative, giao diện click-driven và quản lý dữ liệu theo project.

Sản phẩm không thay thế tư duy nghiên cứu của người dùng, mà **đóng vai trò một Research Copilot**: tự động hóa các tác vụ lặp lại (tổng hợp tài liệu, format citation, diễn giải kết quả thống kê), đồng thời hướng dẫn người dùng đi đúng quy trình học thuật chuẩn.

### 1.2 Tagline đề xuất

*"Từ ý tưởng đến luận văn — không bỏ lỡ bước nào."*

### 1.3 Giá trị cốt lõi

| Giá trị | Mô tả |
| :---- | :---- |
| **Guided, not dictated** | AI gợi ý, người dùng quyết định — không tạo cảm giác bị "chạy thay" |
| **Context-persistent** | Output của bước trước tự động trở thành input của bước sau |
| **Academically sound** | Quy trình, ngôn ngữ, citation chuẩn mực học thuật |
| **Flexible entry** | Vào từ bất kỳ điểm nào trong quy trình, không bắt buộc tuần tự |
| **Transparent cost** | Token usage hiển thị minh bạch trước khi thực hiện hành động |

---

## 2\. NGƯỜI DÙNG MỤC TIÊU & PAIN POINTS

### 2.1 Persona chính

#### Persona A — Sinh viên Đại học / Cao học (Primary)

- **Ngữ cảnh:** Viết khóa luận tốt nghiệp, tiểu luận học phần, luận văn thạc sĩ  
- **Chuyên ngành:** Kinh tế, Quản trị kinh doanh, Marketing, Tâm lý học, Xã hội học, Giáo dục  
- **Pain points:**  
  - Không biết bắt đầu từ đâu, đặc biệt ở bước tìm đề tài  
  - Đọc nhiều tài liệu nhưng không biết tổng hợp research gap  
  - Lúng túng với mô hình nghiên cứu, không biết chọn biến  
  - Sợ chạy SPSS/SmartPLS, không hiểu kết quả ra  
  - Citation sai format, paraphrase bị coi là đạo văn  
  - Mất dữ liệu khi chuyển qua lại giữa nhiều file/tool

#### Persona B — Giảng viên / Nhà nghiên cứu (Secondary)

- **Ngữ cảnh:** Viết bài báo khoa học, đề tài NCKH cấp trường/bộ  
- **Pain points:**  
  - Quản lý nhiều đề tài nghiên cứu đồng thời  
  - Cần literature review nhanh cho lĩnh vực mới  
  - Format bài theo yêu cầu từng tạp chí khác nhau

#### Persona C — Học viên nghiên cứu độc lập (Tertiary)

- **Ngữ cảnh:** Tự học NCKH, làm dự án nghiên cứu ngoài trường

### 2.2 Jobs-to-be-Done (JTBD)

Khi tôi \[cần viết luận văn nhưng không biết bắt đầu\],

Tôi muốn \[được hướng dẫn từng bước rõ ràng với gợi ý cụ thể\],

Để \[hoàn thành đúng hạn mà không bị sai về mặt học thuật\].

Khi tôi \[đã có đề tài nhưng không biết tổng hợp tài liệu\],

Tôi muốn \[chat với AI và nhận phân tích thực trạng \+ gap có trích dẫn ngay\],

Để \[tiết kiệm thời gian và không bỏ sót research gap quan trọng\].

Khi tôi \[nhận được kết quả từ SPSS/SmartPLS nhưng không hiểu\],

Tôi muốn \[upload file và nhận outline phân tích \+ diễn giải tự động\],

Để \[viết phần phân tích chính xác mà không sợ hiểu sai số liệu\].

---

## 3\. TRIẾT LÝ THIẾT KẾ UX

### 3.1 Nguyên tắc core

**Principle 1: Progressive Disclosure** Không hiển thị tất cả tùy chọn ngay từ đầu. Chỉ hiện bước tiếp theo khi bước hiện tại đã hoàn thành.

**Principle 2: Smart Defaults with Override** Mọi quyết định AI đưa ra đều có thể được người dùng chỉnh sửa. Giao diện ưu tiên click-to-confirm thay vì text input, nhưng luôn có ô chat/import để override.

**Principle 3: Context Continuity** Thông tin được truyền ngầm giữa các bước. Người dùng không phải giải thích lại ngữ cảnh khi chuyển module.

**Principle 4: Academic Vocabulary Alignment** Ngôn ngữ trong UI sử dụng đúng thuật ngữ học thuật để người dùng làm quen với chuẩn mực nghiên cứu.

**Principle 5: Undo-safe Environment** Mọi thao tác đều có thể hoàn tác. Output của mỗi bước được lưu version history.

**Principle 6: Chat as Primary Interface (Module 2\)** Module 2 hoạt động thuần chat — không có form hay wizard. AI dẫn dắt bằng ngôn ngữ tự nhiên, người dùng phản hồi tự nhiên, toàn bộ nội dung được trích dẫn nguồn rõ ràng.

### 3.2 Interaction Model tổng thể

\[AI đề xuất\] → \[Người dùng xem xét\] → \[Click chọn / Chỉnh sửa / Từ chối\]

                                              ↓

                                    \[Lưu vào Project Context\]

                                              ↓

                                    \[Truyền sang bước tiếp theo\]

---

## 4\. KIẾN TRÚC THÔNG TIN & NAVIGATION

### 4.1 Cấu trúc màn hình chính

ResearchFlow App

├── Dashboard (Home)

│   ├── Recent Projects

│   ├── Continue where you left off

│   └── Start New Project

│

├── Project Workspace

│   ├── Project Overview (Progress Tracker)

│   ├── Module 1: Topic Discovery

│   ├── Module 2: Literature Review (Chat Interface)

│   ├── Module 3: Research Design (Multi-method)

│   ├── Module 4: Data Analysis (Adaptive)

│   ├── Module 5: Writing & Finalization

│   └── Project Settings

│

├── Library

│   ├── Uploaded Papers

│   ├── Citation Database

│   └── Reference Collections

│

├── Settings

│   ├── Account & Billing

│   ├── Token Usage Dashboard

│   └── Preferences

│

└── Help & Templates

    ├── Sample Projects

    ├── Glossary học thuật

    └── Tutorial Videos

### 4.2 Project Progress Tracker

\[●\] Module 1: Topic Discovery       ← Completed

\[●\] Module 2: Literature Review     ← Completed

\[◐\] Module 3: Research Design       ← In Progress

\[○\] Module 4: Data Analysis         ← Locked

\[○\] Module 5: Writing               ← Locked

● \= Done  ◐ \= In Progress  ○ \= Not started  ⚠ \= Needs attention

---

## 5\. HỆ THỐNG PROJECT & WORKSPACE

### 5.1 Project Object Model

Project {

  id: UUID

  name: string

  field: enum (Economics | Management | Marketing | Psychology | Sociology | Education | Other)

  language: enum (Vietnamese | English | Bilingual)

  citation\_style: enum (APA7 | APA6 | Vancouver | Chicago | Harvard | Custom)

  research\_approach: enum (Quantitative | Qualitative | Mixed)  // ← NEW

  created\_at: timestamp

  last\_modified: timestamp

  status: enum (Draft | In Progress | Review | Completed | Archived)

  modules: {

    topic\_discovery: ModuleState

    literature\_review: ModuleState

    research\_design: ModuleState

    data\_analysis: ModuleState

    writing: ModuleState

  }

  context\_store: {

    research\_title: string

    research\_objectives: string\[\]

    research\_questions: string\[\]

    hypotheses: Hypothesis\[\]                     // định lượng

    propositions: Proposition\[\]                  // định tính  ← NEW

    constructs: Construct\[\]

    literature\_sources: Paper\[\]

    research\_gaps: CitedGap\[\]                    // ← NEW: gap có citation

    methodology: MethodologyConfig

    analysis\_type: AnalysisTypeConfig            // ← NEW: SPSS/SEM/Qualitative

    questionnaire: Questionnaire

    interview\_guide: InterviewGuide              // ← NEW

    analysis\_results: AnalysisResult\[\]

    analysis\_outline: AnalysisOutline            // ← NEW: outline tự động

    final\_sections: DocumentSection\[\]

  }

  token\_usage: TokenLedger

  version\_history: VersionSnapshot\[\]

}

### 5.2 Kiểu dữ liệu mới

CitedGap {

  id: UUID

  description: string

  supporting\_papers: PaperReference\[\]   // \[{author, year, page, quote}\]

  relevance: enum (High | Medium | Low)

  confirmed: boolean

}

AnalysisTypeConfig {

  tool: enum (SPSS | SmartPLS | R\_lavaan | Stata | AMOS | NVivo | Atlas\_ti | Manual\_Qualitative)

  paradigm: enum (Quantitative | Qualitative | Mixed)

  spss\_tests: string\[\]          // \["Descriptive", "Reliability", "EFA", "Regression", "ANOVA"\]

  sem\_type: enum (PLS\_SEM | CB\_SEM | null)

  qualitative\_approach: enum (Thematic | Grounded | Phenomenological | Content | null)

  outline\_confirmed: boolean

}

AnalysisOutline {

  sections: OutlineSection\[\]

  confirmed\_by\_user: boolean

  generated\_from: string   // "SPSS" | "SmartPLS" | "qualitative\_interview" | ...

}

### 5.3 Project Creation Flow

**Path A — Start from Scratch:**

New Project

  → Đặt tên project

  → Chọn lĩnh vực nghiên cứu

  → Chọn ngôn ngữ bài viết

  → Chọn định dạng citation

  → \[Bắt đầu Module 1\]

**Path B — Quick Start:**

New Project

  → "Bạn đã có gì rồi?" (Multi-select checklist)

    ☑ Đã có tên/chủ đề đề tài

    ☑ Đã có tài liệu tham khảo

    ☑ Đã có bảng hỏi / interview guide

    ☑ Đã có kết quả phân tích

  → Import tương ứng

  → Hệ thống tự skip các bước không cần thiết

---

## 6\. CÁC MODULE CHÍNH (RESEARCH FLOW)

---

### MODULE 1 — TOPIC DISCOVERY

*"Tìm & Xác định Đề tài Nghiên cứu"*

*(Không thay đổi so với v1.0 — giữ nguyên toàn bộ)*

#### 6.1.1 Mục tiêu học thuật

- Xác định lĩnh vực và vấn đề nghiên cứu cụ thể  
- Xác định tính mới, tính cần thiết (justification)  
- Phát biểu mục tiêu nghiên cứu (research objectives)  
- Đặt câu hỏi nghiên cứu (research questions)  
- Output: Research proposal mini (đặt vấn đề hoàn chỉnh)

#### 6.1.2 Sub-steps & UX Flow

**Step 1.1 — Chọn lĩnh vực**

UI: Card grid với các lĩnh vực phổ biến

\[Quản trị kinh doanh\] \[Marketing\] \[Kế toán-Tài chính\]

\[Tâm lý học\]  \[Xã hội học\]  \[Giáo dục học\]

\[Kinh tế phát triển\]  \[Thương mại điện tử\]  \[Khác...\]

→ AI tự động load danh sách chủ đề nghiên cứu phổ biến trong lĩnh vực đó

**Step 1.2 — Khám phá chủ đề**

3-column layout:

Left:   Topic Clusters

Center: Suggested Topics (Trending / Understudied)

Right:  Topic Detail Panel (mô tả, relevance, số bài báo)

\[Gợi ý thêm\] \[Tìm kiếm\] \[Nhập chủ đề của tôi\]

**Step 1.3 — Cụ thể hóa đề tài**

AI gợi ý 3 hướng:

Option A: "Tác động của \[X\] đến \[Y\] trong bối cảnh \[Z\]" → Định lượng

Option B: "Các nhân tố ảnh hưởng đến \[Y\] tại \[Z\]"      → Định lượng

Option C: "Nghiên cứu trải nghiệm \[Y\] của \[nhóm Z\]"    → Định tính

\[Tùy chỉnh đề tài\]  \[Nhập đề tài hoàn chỉnh\]

**Step 1.4 — Xác định đối tượng & phạm vi**

**Step 1.5 — Sinh Mục tiêu & Câu hỏi nghiên cứu**

#### 6.1.3 Output của Module 1

{

  "research\_title": "...",

  "field": "Quản trị kinh doanh",

  "research\_type": "Quantitative | Qualitative | Mixed",

  "target\_population": "...",

  "scope": "...",

  "objectives": \["..."\],

  "research\_questions": \["..."\]

}

---

### MODULE 2 — LITERATURE REVIEW

*"Tổng quan tài liệu & Xác định Khoảng trống Nghiên cứu — Chat-first"*

**\[THAY ĐỔI TOÀN BỘ v1.1\]** Module 2 được thiết kế lại hoàn toàn theo mô hình **thuần chat**. Không có wizard, không có form. AI chủ động dẫn dắt cuộc trò chuyện, trình bày thực trạng nghiên cứu và gaps **có trích dẫn trang cụ thể**. Người dùng phản hồi tự nhiên. Nếu không đồng ý, AI làm lại. Sau khi đồng ý, AI xác nhận lại và viết output document Literature Review.

#### 6.2.1 Mục tiêu học thuật

- Tổng hợp thực trạng nghiên cứu trong lĩnh vực (với citation đầy đủ)  
- Xác định research gap có căn cứ từ literature (trích dẫn trang cụ thể)  
- Xây dựng cơ sở lý thuyết (theoretical framework)  
- Viết output document chương Tổng quan lý thuyết chuẩn học thuật

#### 6.2.2 Interaction Model: Chat-first

**Giao diện tổng thể:**

┌─────────────────────────────────────────────────────────────────┐

│  MODULE 2 — LITERATURE REVIEW                                    │

│  \[Upload tài liệu (tùy chọn)\] ←─ nằm ở top, không bắt buộc     │

├─────────────────────────────────────────────────────────────────┤

│                                                                   │

│  \[CHAT WINDOW — chiếm toàn bộ không gian\]                        │

│                                                                   │

│  AI: "Chào bạn\! Tôi đã đọc đề tài của bạn:                       │

│       'Tác động của lãnh đạo chuyển đổi đến sự gắn kết của       │

│        nhân viên tại SMEs Việt Nam'                               │

│                                                                   │

│       Cho tôi hỏi thêm một chút để tổng hợp tốt hơn..."          │

│                                                                   │

│  \[💬 Nhập tin nhắn của bạn...\]              \[Gửi\]                │

└─────────────────────────────────────────────────────────────────┘

#### 6.2.3 Sub-steps (Chat Flow)

---

**PHASE 1 — Khởi động & Thu thập tài liệu (Tùy chọn)**

AI mở đầu:

────────────────────────────────────────────────────────────────

🤖 AI: "Tôi đã nắm được đề tài của bạn. Trước khi bắt đầu tổng 

quan tài liệu, bạn có tài liệu tham khảo sẵn không? 

Nếu có, bạn có thể upload lên để tôi sử dụng làm nguồn chính.

Nếu không, tôi sẽ tổng hợp từ knowledge base của mình."

👤 User: "Tôi có 5 bài báo PDF"

   → Upload panel mở ra (hỗ trợ PDF, DOI paste, plain text)

   → AI tự đọc và index các papers

HOẶC

👤 User: "Tôi không có, bạn tự tổng hợp nhé"

   → AI tiến hành dựa trên knowledge base \+ Semantic Scholar API

────────────────────────────────────────────────────────────────

---

**PHASE 2 — Trình bày Thực trạng Nghiên cứu (có Citation)**

AI tự động phân tích và trình bày trong chat:

────────────────────────────────────────────────────────────────

🤖 AI: "Dưới đây là tổng hợp thực trạng nghiên cứu về 

\*\*Lãnh đạo chuyển đổi và Sự gắn kết nhân viên:\*\*

\---

\*\*📚 1\. THỰC TRẠNG NGHIÊN CỨU\*\*

Lãnh đạo chuyển đổi (Transformational Leadership) lần đầu được 

conceptualize bởi Burns (1978, tr.20) và sau đó được Bass (1985, 

tr.31-34) phát triển thành mô hình 4 thành phần...

Về sự gắn kết nhân viên, Kahn (1990, tr.694) định nghĩa đây là 

"the harnessing of organization members' selves to their work 

roles"...

Mối quan hệ giữa hai biến này đã được kiểm định nhiều lần:

\- Wang et al. (2011, tr.112-115): β \= 0.45, nghiên cứu tại Trung Quốc

\- Tims et al. (2011, tr.207): xác nhận tác động gián tiếp qua 

  self-efficacy

\- Nguyen & Tran (2020, tr.88-90): bối cảnh Việt Nam, n=312, 

  β \= 0.38 nhưng hạn chế ở SMEs

\*\*📊 2\. XU HƯỚNG NGHIÊN CỨU GẦN ĐÂY (2019-2025)\*\*

\- Vai trò của biến trung gian (mediating variables): Trust, 

  Psychological Safety

\- Ảnh hưởng của bối cảnh văn hóa (cultural context)

\- Nghiên cứu trong môi trường làm việc từ xa (remote work)

\---

Bạn thấy phần tổng hợp này có phù hợp không?"

────────────────────────────────────────────────────────────────

Nút quick-reply gợi ý:

\[✅ Phù hợp, tiếp tục\]  \[➕ Bổ sung thêm lĩnh vực này\]  

\[🔄 Làm lại theo hướng khác\]  \[✏️ Tôi muốn điều chỉnh...\]

**Nhánh — User không đồng ý:**

────────────────────────────────────────────────────────────────

👤 User: "Bạn chưa đề cập đến góc độ động lực nội tại, 

          làm lại tập trung hơn vào Self-Determination Theory"

🤖 AI: "Hiểu rồi\! Tôi sẽ làm lại tập trung vào góc độ 

Self-Determination Theory (SDT)..."

\[AI generate lại toàn bộ phần thực trạng với góc nhìn mới\]

\[Vẫn giữ đầy đủ citation có trang\]

────────────────────────────────────────────────────────────────

→ Vòng lặp này có thể lặp lại vô hạn cho đến khi user đồng ý

→ Mỗi lần làm lại, AI ghi nhớ yêu cầu điều chỉnh và áp dụng

---

**PHASE 3 — Trình bày Research Gaps (có Citation)**

Sau khi user đồng ý phần thực trạng:

────────────────────────────────────────────────────────────────

🤖 AI: "Rất tốt\! Dựa trên thực trạng nghiên cứu trên, tôi xác 

định được các khoảng trống nghiên cứu (research gaps) sau:

\---

\*\*⚠️ KHOẢNG TRỐNG NGHIÊN CỨU\*\*

\*\*Gap 1 — Thiếu nghiên cứu tại bối cảnh SMEs Việt Nam\*\*

Các nghiên cứu hiện tại chủ yếu thực hiện tại doanh nghiệp lớn 

(Wang et al., 2011, tr.118; Bass & Riggio, 2006, tr.9) hoặc bối 

cảnh phương Tây. Nguyen & Tran (2020, tr.92) cũng thừa nhận mẫu 

nghiên cứu của họ chưa đại diện cho khu vực SMEs. 

→ \*\*Mức độ liên quan: Rất cao\*\* (trực tiếp với đề tài của bạn)

\*\*Gap 2 — Vai trò trung gian của Niềm tin (Trust) chưa được kiểm định\*\*

Tims et al. (2011, tr.210) đề xuất Trust as mediator nhưng không 

kiểm định thực nghiệm. Li et al. (2019, tr.445) gọi đây là 

"a notable gap in the literature."

→ \*\*Mức độ liên quan: Cao\*\*

\*\*Gap 3 — Chưa xem xét biến điều tiết văn hóa tập thể (collectivism)\*\*

Hofstede (2001, tr.211) chỉ ra đặc điểm văn hóa tập thể của 

Việt Nam nhưng chưa có nghiên cứu nào tích hợp vào mô hình TL–EE.

→ \*\*Mức độ liên quan: Trung bình\*\*

\---

Bạn muốn sử dụng những gaps nào?"

────────────────────────────────────────────────────────────────

Quick-reply:

\[✅ Dùng cả 3 gaps\]  

\[✅ Gap 1 \+ 2 là đủ\]  

\[🔄 Làm lại — tôi muốn gap về phương pháp\]

\[✏️ Tôi muốn thêm gap này: \_\_\_\]

**Nhánh — User không đồng ý gaps:**

────────────────────────────────────────────────────────────────

👤 User: "Làm lại đi, tôi muốn gap tập trung vào phương pháp 

          nghiên cứu định tính chưa được áp dụng"

🤖 AI: "Được\! Tôi sẽ tìm lại các gaps về phương pháp..."

\[AI generate lại với góc nhìn methodological gap\]

\[Vẫn giữ citation đầy đủ có trang\]

────────────────────────────────────────────────────────────────

---

**PHASE 4 — Xác nhận & Bổ sung Page References**

Khi user đồng ý với gaps:

────────────────────────────────────────────────────────────────

🤖 AI: "Tuyệt\! Bạn đã chọn Gap 1 và Gap 2\. Tôi muốn xác nhận 

lại các page references với bạn để đảm bảo độ chính xác:

📋 XÁC NHẬN REFERENCES:

Gap 1 — Dựa trên:

  • Wang et al. (2011) — tôi đang trích trang 118\.

    Bạn có thể kiểm tra lại không? \[Đúng ✅\] \[Sai, trang \_\_\]

  • Nguyen & Tran (2020) — tôi đang trích trang 92\.

    \[Đúng ✅\] \[Sai, trang \_\_\]

Gap 2 — Dựa trên:

  • Tims et al. (2011) — tôi đang trích trang 210\.

    \[Đúng ✅\] \[Sai, trang \_\_\]

  • Li et al. (2019) — tôi đang trích trang 445\.

    \[Đúng ✅\] \[Sai, trang \_\_\]

Nếu bạn không có bản gốc để kiểm tra, bạn có thể bỏ qua bước 

này — tôi sẽ gắn \[page?\] để nhắc nhở khi viết."

────────────────────────────────────────────────────────────────

Note: User có thể:

\- Xác nhận từng trang

\- Sửa số trang

\- Bỏ qua (AI sẽ đánh dấu \[page?\] trong output)

\- Upload bài báo để AI tự đọc và verify trang

---

**PHASE 5 — Viết Output Document**

Sau khi xác nhận references:

────────────────────────────────────────────────────────────────

🤖 AI: "Cảm ơn\! Tôi sẽ viết chương Tổng quan lý thuyết 

cho bạn. Bạn muốn output theo cấu trúc nào?"

Quick-reply:

\[📄 Cấu trúc chuẩn luận văn (5 chương)\]

\[📄 Cấu trúc bài báo khoa học\]

\[📄 Tự nhập cấu trúc mong muốn\]

────────────────────────────────────────────────────────────────

AI generate document dạng preview ngay trong chat:

────────────────────────────────────────────────────────────────

🤖 AI: "Đây là bản draft Chương 2 của bạn:

─────────────────────────────────────────

CHƯƠNG 2: TỔNG QUAN LÝ THUYẾT

2.1 Cơ sở lý thuyết về Lãnh đạo chuyển đổi

Lãnh đạo chuyển đổi (Transformational Leadership – TL) được 

Burns (1978, tr.20) lần đầu đề xuất như một phong cách lãnh đạo 

trong đó lãnh đạo truyền cảm hứng và thúc đẩy người theo thông 

qua tầm nhìn...

2.2 Sự gắn kết của nhân viên

Kahn (1990, tr.694) định nghĩa sự gắn kết như là mức độ mà 

người lao động đầu tư về mặt nhận thức, cảm xúc và thể chất 

vào vai trò công việc...

2.3 Mối quan hệ giữa Lãnh đạo chuyển đổi và Sự gắn kết

Nhiều nghiên cứu đã xác nhận tác động tích cực và có ý nghĩa 

thống kê của TL đến EE (Wang et al., 2011, tr.112-115; Tims 

et al., 2011, tr.207; Nguyen & Tran, 2020, tr.88-90)...

2.4 Khoảng trống nghiên cứu và Giả thuyết

Mặc dù đã có nhiều nghiên cứu về mối quan hệ TL–EE, các 

nghiên cứu trong bối cảnh SMEs Việt Nam còn hạn chế (Nguyen 

& Tran, 2020, tr.92). Đặc biệt, vai trò trung gian của niềm 

tin chưa được kiểm định thực nghiệm (Li et al., 2019, tr.445)...

Từ đó, nghiên cứu đề xuất:

H1: Lãnh đạo chuyển đổi có tác động tích cực đến sự gắn kết (+)

H2: Niềm tin đóng vai trò trung gian trong mối quan hệ TL–EE

─────────────────────────────────────────

Bạn thấy bản draft này thế nào?"

\[✅ Tốt, lưu vào project\]  

\[✏️ Chỉnh sửa section này: \_\_\_\]  

\[🔄 Viết lại theo phong cách khác\]

\[📥 Export ngay ra Word/PDF\]

────────────────────────────────────────────────────────────────

#### 6.2.4 Output của Module 2 (saved to context\_store)

{

  "chat\_history": \[...\],

  "research\_gaps": \[

    {

      "id": "gap\_001",

      "description": "Thiếu nghiên cứu tại bối cảnh SMEs Việt Nam",

      "supporting\_papers": \[

        {"author": "Wang et al.", "year": 2011, "page": 118, "verified": true},

        {"author": "Nguyen & Tran", "year": 2020, "page": 92, "verified": true}

      \],

      "relevance": "High",

      "confirmed": true

    }

  \],

  "theoretical\_framework": "Transformational Leadership Theory \+ Social Exchange Theory",

  "hypotheses": \["H1: TL → EE (+)", "H2: Trust mediates TL → EE"\],

  "literature\_review\_doc": "...\[full text of Chapter 2\]...",

  "citation\_list": \[...\]

}

---

### MODULE 3 — RESEARCH DESIGN

*"Thiết kế Nghiên cứu — Đa phương pháp"*

**\[THAY ĐỔI v1.1\]** Module 3 bổ sung đầy đủ các phương pháp nghiên cứu ngoài định lượng: nghiên cứu định tính (qualitative), hỗn hợp (mixed methods). AI giải thích rõ từng phương pháp, đề xuất phù hợp với đề tài, và hỗ trợ thiết kế công cụ thu thập phù hợp (bảng hỏi cho định lượng, interview guide cho định tính). Nếu nghiên cứu định tính, AI đề xuất conceptual model thay vì structural model.

#### 6.3.1 Mục tiêu học thuật

- Giúp người dùng hiểu và lựa chọn đúng phương pháp nghiên cứu phù hợp với câu hỏi nghiên cứu  
- Thiết kế công cụ thu thập dữ liệu phù hợp theo phương pháp  
- Xác định cỡ mẫu và chiến lược lấy mẫu  
- Xây dựng conceptual model (định lượng) hoặc thematic framework (định tính)

#### 6.3.2 Step 3.1 — Hướng dẫn & Lựa chọn Phương pháp

AI mở đầu với hướng dẫn giáo dục:

────────────────────────────────────────────────────────────────

🤖 AI: "Dựa trên câu hỏi nghiên cứu của bạn, có 3 hướng 

tiếp cận phương pháp. Hãy để tôi giải thích để bạn chọn 

phù hợp nhất:

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 PHƯƠNG PHÁP ĐỊNH LƯỢNG (Quantitative)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Mục đích: Kiểm định mối quan hệ nhân quả / tương quan giữa các biến

Phù hợp khi: Bạn muốn trả lời "X có ảnh hưởng đến Y không?" 

              "Mức độ ảnh hưởng là bao nhiêu?"

Công cụ: Bảng hỏi Likert → SPSS, SmartPLS, AMOS

Ưu điểm: Kết quả có thể khái quát hóa, kiểm định thống kê rõ ràng

Hạn chế: Không giải thích được "tại sao" hay "như thế nào"

Ví dụ mẫu: "Tác động của lãnh đạo chuyển đổi đến sự gắn kết nhân viên"

  📌 Các thiết kế định lượng phổ biến:

  ┌─────────────────────────────────────────────────────────┐

  │ • Regression Analysis       → Phù hợp khi: biến độc lập│

  │   (Hồi quy tuyến tính)        ít, không có latent var  │

  │                                                         │

  │ • PLS-SEM (SmartPLS)        → Phù hợp khi: nhiều biến  │

  │   (Mô hình cấu trúc PLS)      tiềm ẩn, mẫu nhỏ \~200   │

  │                                                         │

  │ • CB-SEM (AMOS)             → Phù hợp khi: mẫu lớn    │

  │   (Mô hình cấu trúc CFA)      \>300, kiểm định CFA      │

  │                                                         │

  │ • ANOVA/t-test              → Phù hợp khi: so sánh     │

  │                                nhóm (giới tính, tuổi)  │

  └─────────────────────────────────────────────────────────┘

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔍 PHƯƠNG PHÁP ĐỊNH TÍNH (Qualitative)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Mục đích: Khám phá, hiểu sâu nhận thức, trải nghiệm, ý nghĩa

Phù hợp khi: Bạn muốn trả lời "Tại sao?", "Như thế nào?", 

              "Trải nghiệm của họ là gì?"

Công cụ: Phỏng vấn sâu, focus group → NVivo, Atlas.ti, thủ công

Ưu điểm: Hiểu sâu bản chất hiện tượng, khám phá yếu tố mới

Hạn chế: Không thể khái quát hóa rộng, phụ thuộc vào diễn giải

  📌 Các thiết kế định tính phổ biến:

  ┌─────────────────────────────────────────────────────────┐

  │ • Thematic Analysis         → Phù hợp nhất cho luận văn│

  │   (Phân tích chủ đề)         thạc sĩ, linh hoạt       │

  │                                                         │

  │ • Grounded Theory           → Phù hợp khi: lĩnh vực   │

  │   (Lý thuyết nền tảng)       chưa có lý thuyết sẵn    │

  │                                                         │

  │ • Phenomenological Study    → Phù hợp khi: khám phá   │

  │   (Nghiên cứu hiện tượng)    trải nghiệm cá nhân      │

  │                                                         │

  │ • Case Study                → Phù hợp khi: nghiên cứu │

  │   (Nghiên cứu tình huống)    1 tổ chức/nhóm cụ thể    │

  └─────────────────────────────────────────────────────────┘

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔀 PHƯƠNG PHÁP HỖN HỢP (Mixed Methods)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Mục đích: Kết hợp lợi ích của cả hai, bù đắp hạn chế của nhau

Phù hợp khi: Vừa muốn đo lường (định lượng) vừa muốn 

              hiểu sâu nguyên nhân (định tính)

Thiết kế phổ biến:

  • Sequential Explanatory: Định lượng trước → Định tính sau 

    (dùng định tính để giải thích kết quả định lượng)

  • Sequential Exploratory: Định tính trước → Định lượng sau 

    (dùng định tính để xây dựng thang đo mới)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💡 GỢI Ý CHO ĐỀ TÀI CỦA BẠN:

Dựa trên câu hỏi nghiên cứu '\[RQ từ M1\]', tôi đề xuất:

→ \[Phương pháp được AI recommend \+ lý do cụ thể\]

Bạn muốn chọn phương pháp nào?"

**Quick-reply:**

\[📊 Định lượng\]  \[🔍 Định tính\]  \[🔀 Hỗn hợp\]  \[❓ Tư vấn thêm\]

---

#### 6.3.3 Step 3.2A — Nhánh ĐỊNH LƯỢNG

Sau khi chọn Định lượng:

────────────────────────────────────────────────────────────────

AI hỏi thêm để chọn công cụ phân tích:

Q1: "Mô hình nghiên cứu có biến tiềm ẩn (latent variables) 

     đo lường bằng nhiều items không?"

    \[Có — nhiều biến tiềm ẩn\]  \[Không — biến đo trực tiếp\]

Q2: (Nếu có latent var) "Mẫu bạn dự kiến bao nhiêu người?"

    \[\< 200\]  \[200-300\]  \[\> 300\]

→ AI đề xuất: PLS-SEM / CB-SEM / Regression / ANOVA

  Kèm giải thích tại sao phù hợp với tình huống cụ thể

────────────────────────────────────────────────────────────────

**Step 3.2A-i — Conceptual Model (Định lượng)**

AI đề xuất conceptual model từ gaps đã xác định ở M2:

────────────────────────────────────────────────────────────────

\[Visual drag-and-drop model builder\]

Biến đề xuất từ literature (M2):

  IV:  \[Lãnh đạo chuyển đổi — TL\]

  DV:  \[Sự gắn kết nhân viên — EE\]

  MED: \[Niềm tin — Trust\]

Canvas: Kéo thả → Vẽ mũi tên → AI gắn nhãn Hypothesis

  TL ──(+)──→ EE   (H1)

  TL ──(+)──→ Trust (H2)

  Trust ──(+)──→ EE  (H3)

  Trust mediates TL→EE (H4)

\[Thêm biến điều tiết\]  \[Thêm biến kiểm soát\]

\[Chat để thêm/xóa biến\]

────────────────────────────────────────────────────────────────

**Step 3.2A-ii — Scale Builder**

*(Giữ nguyên từ v1.0 — Scale Builder với nguồn thang đo \+ Likert items)*

**Step 3.2A-iii — Sample Size Calculator**

*(Giữ nguyên từ v1.0 — Cohen / Hair et al. formula)*

---

#### 6.3.4 Step 3.2B — Nhánh ĐỊNH TÍNH

Sau khi chọn Định tính:

────────────────────────────────────────────────────────────────

AI hỏi thêm:

Q1: "Thiết kế nghiên cứu bạn muốn sử dụng là gì?"

    \[Thematic Analysis\]  \[Grounded Theory\]  

    \[Phenomenological\]   \[Case Study\]

    \[Tư vấn cho tôi\]

→ Nếu chọn "Tư vấn": AI giải thích lại từng loại và 

  đề xuất dựa trên câu hỏi nghiên cứu cụ thể

────────────────────────────────────────────────────────────────

**Step 3.2B-i — Thematic Framework (Định tính)**

Thay vì conceptual model (nhân quả), AI đề xuất:

Thematic Framework — khung chủ đề sơ bộ

────────────────────────────────────────────────────────────────

THEMATIC FRAMEWORK SƠ BỘ

Dựa trên literature review, tôi đề xuất các themes chính 

cần khám phá:

Theme 1: Cách thức lãnh đạo truyền cảm hứng trong SMEs

  Sub-themes: Tầm nhìn, Giao tiếp, Hành vi gương mẫu

Theme 2: Biểu hiện gắn kết của nhân viên

  Sub-themes: Gắn kết nhận thức, Cảm xúc, Hành vi

Theme 3: Các yếu tố trung gian

  Sub-themes: Niềm tin, Tâm lý an toàn

\[Thêm theme\]  \[Xóa theme\]  \[Chat để điều chỉnh\]

────────────────────────────────────────────────────────────────

Note: Framework này sẽ được kiểm chứng/điều chỉnh sau khi 

phân tích dữ liệu thực tế ở Module 4

**Step 3.2B-ii — Interview Guide Builder**

AI tự động tạo Interview Guide dựa trên themes:

────────────────────────────────────────────────────────────────

INTERVIEW GUIDE — Phỏng vấn sâu bán cấu trúc

(Semi-structured In-depth Interview)

PHẦN MỞ ĐẦU (5 phút)

Giới thiệu, mục đích nghiên cứu, xác nhận ghi âm...

CÂU HỎI CHÍNH (40-50 phút)

Theme 1: Lãnh đạo

  Q1: "Anh/chị mô tả phong cách lãnh đạo của cấp trên 

       trực tiếp như thế nào?"

  Q2: "Những hành động nào của lãnh đạo khiến anh/chị 

       cảm thấy được truyền cảm hứng?"

  Probe: "Anh/chị có thể cho ví dụ cụ thể không?"

Theme 2: Gắn kết

  Q3: "Anh/chị cảm thấy thế nào về công việc hàng ngày?"

  ...

\[✏ Chỉnh sửa câu hỏi\]  \[+ Thêm câu hỏi\]  \[Xóa câu hỏi\]

\[📄 Export Word\]  \[📋 Copy nội dung\]

────────────────────────────────────────────────────────────────

**Step 3.2B-iii — Sampling Strategy (Định tính)**

AI đề xuất chiến lược lấy mẫu có chủ đích:

────────────────────────────────────────────────────────────────

CHIẾN LƯỢC LẤY MẪU — Purposive Sampling

────────────────────────────────────────────────────────────────

Phương pháp: Purposive / Theoretical Sampling

Cỡ mẫu: 10-15 người (đến khi đạt data saturation)

Tiêu chí lựa chọn:

  ✅ Nhân viên tại SMEs (\< 300 nhân viên)

  ✅ Có ít nhất 6 tháng làm việc tại công ty hiện tại

  ✅ Có cấp trên trực tiếp quản lý

Chiến lược bổ sung:

  ○ Snowball sampling (nhờ người phỏng vấn giới thiệu)

  ○ Maximum variation sampling (đa dạng giới tính, tuổi, ngành)

Thời lượng phỏng vấn: 45-60 phút/người

────────────────────────────────────────────────────────────────

---

#### 6.3.5 Step 3.2C — Nhánh HỖN HỢP (Mixed Methods)

AI xác định thiết kế hỗn hợp:

────────────────────────────────────────────────────────────────

"Bạn muốn triển khai theo thiết kế nào?"

○ Sequential Explanatory (Giải thích tuần tự)

  → Định lượng trước (khảo sát) → Định tính sau (phỏng vấn)

  → Dùng định tính để giải thích kết quả định lượng bất ngờ

  → Phù hợp nhất cho luận văn thạc sĩ

○ Sequential Exploratory (Khám phá tuần tự)  

  → Định tính trước (phỏng vấn) → Định lượng sau (khảo sát)

  → Dùng định tính để xây dựng thang đo mới

  → Phù hợp khi lĩnh vực chưa có thang đo chuẩn

→ AI triển khai công cụ cho cả 2 pha theo lựa chọn

────────────────────────────────────────────────────────────────

#### 6.3.6 Output của Module 3

{

  "methodology": {

    "paradigm": "Quantitative | Qualitative | Mixed",

    "design": "PLS-SEM | Thematic Analysis | Sequential Explanatory | ...",

    "tool": "SmartPLS | NVivo | SPSS | ..."

  },

  "sampling": {

    "strategy": "Convenience | Purposive | Snowball",

    "min\_size": 200,

    "target\_size": 350

  },

  "conceptual\_model": { ... },     // định lượng

  "thematic\_framework": { ... },   // định tính

  "constructs": \[ ... \],           // định lượng

  "questionnaire\_text": "...",     // định lượng

  "interview\_guide": "..."         // định tính

}

---

### MODULE 4 — DATA ANALYSIS

*"Phân tích Dữ liệu — Adaptive Outline theo Loại Dữ liệu"*

**\[THAY ĐỔI TOÀN BỘ v1.1\]** Module 4 tự động nhận dạng loại dữ liệu được upload và tự lên outline phân tích chuẩn tương ứng. Người dùng có thể can thiệp vào outline hoặc yêu cầu phân tích tùy chọn qua chat. AI phân tích từng phần theo outline và diễn giải chuẩn học thuật.

#### 6.4.1 Mục tiêu học thuật

- Tự động nhận dạng loại dữ liệu và phần mềm phân tích  
- Tự động đề xuất outline phân tích chuẩn cho từng loại  
- Thực thi phân tích từng bước theo outline đã xác nhận  
- Hỗ trợ can thiệp linh hoạt: thêm/xóa bước, yêu cầu phân tích tùy chọn qua chat  
- Diễn giải kết quả bằng ngôn ngữ học thuật (VI/EN)

#### 6.4.2 Step 4.1 — Upload & Nhận dạng Loại Dữ liệu

Upload Panel:

────────────────────────────────────────────────────────────────

\[📊 Upload file kết quả phân tích\]

Hỗ trợ: SPSS (.spv, .sav), SmartPLS HTML, R output (.txt/.html),

         Stata log, NVivo export, Excel/CSV, Paste text

Sau khi upload, AI nhận dạng tự động:

  "Tôi nhận ra đây là kết quả từ \[SPSS / SmartPLS / R / ...\]"

  "Dữ liệu thuộc loại: \[Định lượng — SEM / Định lượng — SPSS 

                         / Định tính / Hỗn hợp\]"

  "Tôi sẽ đề xuất outline phân tích phù hợp..."

────────────────────────────────────────────────────────────────

---

#### 6.4.3 Step 4.2 — Auto-generate Analysis Outline (theo loại dữ liệu)

AI tự động đề xuất outline chuẩn dựa trên loại dữ liệu nhận dạng.  
Người dùng xem xét, có thể chỉnh sửa, rồi confirm trước khi AI chạy phân tích.

---

**OUTLINE A — SPSS (Định lượng — Không có SEM)**

OUTLINE PHÂN TÍCH — SPSS

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Bước 1: Thống kê mô tả (Descriptive Statistics)

  → Tần suất, phần trăm biến nhân khẩu học

  → Mean, Std Dev của các thang đo chính

Bước 2: Đánh giá độ tin cậy thang đo (Reliability)

  → Cronbach's Alpha cho từng construct

  → Tiêu chí: α ≥ 0.7 (Nunnally, 1978\)

  → Corrected Item-Total Correlation ≥ 0.3

Bước 3: Phân tích nhân tố khám phá (EFA)

  → KMO và kiểm định Bartlett (KMO ≥ 0.5, Sig. \< 0.05)

  → Eigenvalue ≥ 1 để xác định số nhân tố

  → Factor loading ≥ 0.5

Bước 4: Phân tích tương quan (Correlation)

  → Ma trận tương quan Pearson giữa các biến chính

  → Kiểm tra multicollinearity (r \< 0.85)

Bước 5: Phân tích hồi quy (Regression)

  → Kiểm định các giả định: chuẩn hóa phần dư, VIF \< 10

  → Bảng hệ số hồi quy (β, t, Sig.)

  → R², F-test

Bước 6: Phân tích ANOVA / Independent t-test (nếu có)

  → So sánh trung bình theo nhóm nhân khẩu học

  → Post-hoc tests nếu cần

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

\[✅ Xác nhận outline này\]  

\[✏️ Thêm/bớt bước\]  

\[💬 Chat để yêu cầu thay đổi\]

---

**OUTLINE B — SmartPLS / PLS-SEM**

OUTLINE PHÂN TÍCH — PLS-SEM (SmartPLS)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PHẦN I — ĐÁNH GIÁ MÔ HÌNH ĐO LƯỜNG (Measurement Model)

Bước 1: Kiểm tra độ tin cậy hội tụ (Convergent Validity)

  → Outer Loadings ≥ 0.7

  → AVE ≥ 0.5 (Fornell & Larcker, 1981\)

  → Composite Reliability (CR) ≥ 0.7

  → Cronbach's Alpha ≥ 0.7

Bước 2: Kiểm tra giá trị phân biệt (Discriminant Validity)

  → HTMT \< 0.85 (Henseler et al., 2015\) — Tiêu chí mới

  → Fornell-Larcker Criterion: √AVE \> max correlation

  → Cross-loadings

PHẦN II — ĐÁNH GIÁ MÔ HÌNH CẤU TRÚC (Structural Model)

Bước 3: Kiểm tra đa cộng tuyến (Collinearity)

  → VIF \< 5 (Hair et al., 2019\)

Bước 4: Kiểm định hệ số đường dẫn (Path Coefficients)

  → β (Path Coefficient)

  → t-value và p-value (Bootstrap ≥ 5000 samples)

  → Kết luận chấp nhận / bác bỏ giả thuyết

Bước 5: Hệ số xác định (R² và Adjusted R²)

  → Giải thích % phương sai của biến phụ thuộc

Bước 6: Effect size (f²)

  → f² ≥ 0.02 (nhỏ), ≥ 0.15 (trung bình), ≥ 0.35 (lớn)

Bước 7: Predictive Relevance (Q² — Blindfolding)

  → Q² \> 0: mô hình có giá trị dự báo

Bước 8: Kiểm định hiệu ứng trung gian (Nếu có mediator)

  → Indirect effect, Bootstrapped CI

  → Phân loại: full / partial mediation

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

\[✅ Xác nhận outline này\]  

\[✏️ Thêm kiểm định điều tiết (Moderating)\]  

\[💬 Chat để yêu cầu thay đổi\]

---

**OUTLINE C — CB-SEM / AMOS / R lavaan**

OUTLINE PHÂN TÍCH — CB-SEM (CFA \+ SEM)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Bước 1: Phân tích nhân tố khẳng định (CFA)

  → Model fit: CFI/TLI ≥ 0.90, RMSEA ≤ 0.08, SRMR ≤ 0.08

  → Factor loadings ≥ 0.5

  → AVE ≥ 0.5, CR ≥ 0.7

Bước 2: Kiểm tra Discriminant Validity

  → HTMT, Fornell-Larcker

Bước 3: Kiểm định mô hình cấu trúc (SEM)

  → Model fit indices

  → Standardized path coefficients

  → p-values

Bước 4: Mediation / Moderation Analysis

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

---

**OUTLINE D — Phân tích Định tính (Thematic Analysis)**

OUTLINE PHÂN TÍCH — THEMATIC ANALYSIS (Braun & Clarke, 2006\)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Bước 1: Làm quen với dữ liệu (Familiarization)

  → Đọc transcript phỏng vấn, ghi chú ban đầu

  → Tạo verbatim quotes đáng chú ý

Bước 2: Tạo mã hóa ban đầu (Initial Coding)

  → Line-by-line coding

  → AI suggest initial codes từ transcript

  → Người dùng xem, điều chỉnh codes

Bước 3: Tìm kiếm Themes (Theme Generation)

  → Nhóm codes vào potential themes

  → Vẽ thematic map

  → AI đề xuất themes từ patterns trong codes

Bước 4: Review và tinh chỉnh Themes

  → So sánh themes với data gốc

  → Tách / gộp themes

  → Kiểm tra internal homogeneity, external heterogeneity

Bước 5: Đặt tên và định nghĩa Themes

  → Essence of each theme

  → Relationship giữa các themes

Bước 6: Viết kết quả

  → Mỗi theme: mô tả \+ verbatim quotes \+ giải thích

  → Liên kết với literature

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Upload transcript:

  \[📁 Upload file Word/PDF transcript\]

  \[📋 Paste nội dung phỏng vấn\]

  

AI xử lý: 

  → Trích xuất verbatim quotes

  → Suggest initial codes

  → Nhóm thành potential themes

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

\[✅ Xác nhận outline này\]  

\[✏️ Thêm/bớt bước\]  

\[💬 Chat để yêu cầu thay đổi\]

---

**OUTLINE E — Hỗn hợp (Mixed Methods)**

OUTLINE PHÂN TÍCH — MIXED METHODS

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Pha 1: \[Kết quả Định lượng theo Outline A hoặc B\]

Pha 2: \[Kết quả Định tính theo Outline D\]

Pha 3: Integration — So sánh & Tích hợp kết quả 2 pha

  → Convergence: điểm tương đồng

  → Divergence: điểm mâu thuẫn → giải thích

  → Expansion: định tính mở rộng kết quả định lượng

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

---

#### 6.4.4 Step 4.3 — User Review Outline

Trước khi chạy phân tích, AI hiển thị outline để user xác nhận:

────────────────────────────────────────────────────────────────

🤖 AI: "Đây là outline phân tích tôi đề xuất cho dữ liệu 

SPSS của bạn. Bạn có muốn điều chỉnh không?

\[Outline hiển thị dạng checklist có thể tích/bỏ tích từng bước\]

  ☑ Bước 1: Thống kê mô tả

  ☑ Bước 2: Độ tin cậy (Cronbach's Alpha)

  ☑ Bước 3: EFA

  ☑ Bước 4: Tương quan

  ☑ Bước 5: Hồi quy

  ☐ Bước 6: ANOVA (bỏ tích nếu không cần)

\[+ Thêm bước phân tích\]  \[💬 Chat để yêu cầu\]"

────────────────────────────────────────────────────────────────

Người dùng có thể:

  \- Tích/bỏ tích từng bước

  \- Chat: "Thêm phân tích Independent Samples t-test theo giới tính"

  \- Chat: "Tôi muốn kiểm định Common Method Bias trước"

  \- Chat: "Bỏ bước EFA vì tôi đã thực hiện CFA"

Sau khi confirm → AI tiến hành phân tích từng bước

---

#### 6.4.5 Step 4.4 — Thực thi Phân tích & Diễn giải

AI phân tích từng bước theo outline đã confirm:

────────────────────────────────────────────────────────────────

📊 BƯỚC 1: THỐNG KÊ MÔ TẢ

━━━━━━━━━━━━━━━━━━━━━━━━━━━

\[Bảng kết quả được trích xuất và hiển thị\]

AI diễn giải tự động:

"Mẫu nghiên cứu gồm 325 người, trong đó nữ chiếm 58.5% (n=190). 

Độ tuổi phổ biến nhất là 25-35 tuổi (42.2%). Giá trị trung bình 

của thang đo Lãnh đạo chuyển đổi đạt 3.87/5.0 (SD=0.72), cho 

thấy mức đánh giá khá cao..."

\[✅ Xác nhận diễn giải\]  \[✏ Chỉnh sửa\]  \[Copy\]

────────────────────────────────────────────────────────────────

📊 BƯỚC 2: ĐỘ TIN CẬY THANG ĐO

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

\[Bảng Cronbach's Alpha\]

Phát hiện cảnh báo:

  ⚠ TL3: Corrected Item-Total \= 0.24 \< 0.3

  Gợi ý: Xem xét loại item TL3

  \[Xem tác động nếu loại TL3\]  \[Giữ nguyên \+ giải thích\]

AI diễn giải tự động:

"Hầu hết các thang đo đạt độ tin cậy tốt với Cronbach's Alpha 

từ 0.81 đến 0.89. Tuy nhiên, construct Transformational 

Leadership có item TL3 với Corrected Item-Total Correlation 

\= 0.24, thấp hơn ngưỡng 0.3 đề xuất bởi Nunnally (1978)..."

\[✅ Xác nhận\]  \[✏ Chỉnh sửa\]  \[Copy\]  \[⚡ Tiếp tục bước 3\]

────────────────────────────────────────────────────────────────

\[Tiếp tục tương tự cho tất cả các bước trong outline\]

────────────────────────────────────────────────────────────────

---

#### 6.4.6 Step 4.5 — Phân tích Tùy chọn qua Chat

Người dùng có thể yêu cầu phân tích bổ sung bất kỳ lúc nào:

────────────────────────────────────────────────────────────────

💬 Chat box luôn hiển thị bên cạnh kết quả:

Ví dụ yêu cầu:

  "Chạy thêm Independent Samples t-test so sánh TL score 

   theo giới tính"

  → AI extract dữ liệu, hiển thị kết quả, diễn giải

  "Tôi muốn kiểm định mediation theo phương pháp Sobel test"

  → AI thực hiện và trình bày kết quả

  "Hiển thị scatter plot giữa TL và EE"

  → AI generate visualization

  "Giải thích tại sao R² \= 0.38 lại thấp hơn kỳ vọng"

  → AI đưa ra giải thích học thuật và gợi ý

────────────────────────────────────────────────────────────────

---

#### 6.4.7 Output của Module 4

{

  "data\_type\_detected": "SPSS | SmartPLS | Qualitative | ...",

  "analysis\_outline": {

    "generated\_from": "SPSS",

    "sections": \["Descriptive", "Reliability", "EFA", "Correlation", "Regression"\],

    "confirmed\_by\_user": true,

    "user\_modifications": \["Removed ANOVA", "Added CMB test"\]

  },

  "results": {

    "descriptive": { ... },

    "reliability": { "TL": {"alpha": 0.84, "items\_removed": \["TL3"\]}, ... },

    "efa": { ... },

    "correlation": { ... },

    "regression": { "R2": 0.42, "hypotheses": {"H1": "supported", ...} }

  },

  "interpretations": { "section\_by\_section": \[ ... \] },

  "custom\_analyses": \[ ... \]

}

---

### MODULE 5 — WRITING & FINALIZATION

*"Hoàn thiện Bài viết"*

*(Không thay đổi cấu trúc từ v1.0, nhưng auto-fill logic được mở rộng để hỗ trợ output từ cả định tính và hỗn hợp)*

#### 6.5.1 Mục tiêu

- Tự động điền nội dung từ các module trước vào cấu trúc bài  
- Hỗ trợ paraphrase và kiểm tra ngôn ngữ học thuật  
- Quản lý citation và reference list  
- Xuất file theo định dạng yêu cầu

#### 6.5.2 Step 5.1 — Document Structure Overview

Outline auto-fill thích ứng theo loại nghiên cứu:

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ĐỊNH LƯỢNG:                    ĐỊNH TÍNH:

Chương 4: Kết quả              Chương 4: Kết quả & Thảo luận

  4.1 Mô tả mẫu                  4.1 Mô tả mẫu & bối cảnh

  4.2 Kiểm định thang đo          4.2 Theme 1: \[Tên theme\]

  4.3 Kiểm định giả thuyết        4.3 Theme 2: \[Tên theme\]

  4.4 Thảo luận                   4.4 Theme 3: \[Tên theme\]

                                   4.5 Tích hợp kết quả

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

#### 6.5.3 Step 5.2 — Section Editor

*(Giữ nguyên từ v1.0 — Paraphrase, Citation insert, Academic style, Translate)*

#### 6.5.4 Step 5.3 — Citation Manager

*(Giữ nguyên từ v1.0 — tất cả citations từ M2 được import tự động)*

#### 6.5.5 Step 5.4 — Export

*(Giữ nguyên từ v1.0 — Word, PDF, LaTeX, Google Docs)*

---

## 7\. CROSS-MODULE FEATURES

### 7.1 Context Propagation Engine

Khi Module N hoàn thành → context\_store cập nhật →

Module N+1 tự động nhận context mới nhất

Ví dụ cụ thể (v1.1):

\- M2 xác nhận research\_gaps với citation đầy đủ

  → M3 tự động đề xuất conceptual model dựa trên gaps

  → M5 auto-fill phần "Khoảng trống nghiên cứu" trong Ch.2

\- M3 xác nhận methodology \= "Qualitative / Thematic"

  → M4 tự động đề xuất Outline D (Thematic Analysis)

  → M5 auto-fill cấu trúc Ch.4 theo themes

\- M4 xác nhận analysis\_outline (đã được user chỉnh sửa)

  → M5 auto-fill Ch.4 theo đúng các bước trong outline

### 7.2 Version History

*(Giữ nguyên từ v1.0)*

### 7.3 Comment & Annotation

*(Giữ nguyên từ v1.0)*

### 7.4 AI Chat (Global)

Luôn hiển thị ở góc dưới phải, context-aware:

  "Thêm kiểm định moderating effect vào M4"

  → AI hiểu đang ở module nào, cập nhật analysis outline

Commands mẫu:

  /addstep \[tên bước phân tích\]

  /removestep \[tên bước\]

  /rerun \[section\_id\]

  /cite \[doi\]

  /translate \[vi→en\]

  /explain \[thuật ngữ thống kê\]

---

## 8\. ENTRY POINTS & FLEXIBLE ONBOARDING

### 8.1 Onboarding Wizard

"Bạn đang ở giai đoạn nào?"

○ Bắt đầu từ đầu — Tôi chưa có gì

○ Đã có đề tài — Tôi muốn bắt đầu từ Literature Review

○ Đã có tài liệu & mô hình — Tôi muốn thiết kế nghiên cứu

○ Đã có dữ liệu — Tôi muốn phân tích và viết bài

○ Đã có bản thảo — Tôi cần hỗ trợ hoàn thiện & citation

### 8.2 Import per Module

| Module bị skip | Cần import |
| :---- | :---- |
| M1 (Topic) | Tên đề tài, mục tiêu, câu hỏi nghiên cứu (text/file) |
| M2 (Literature) | Upload PDF tài liệu, hoặc nhập danh sách references \+ gaps |
| M3 (Design) | Upload bảng hỏi/interview guide (Word/PDF) hoặc mô tả phương pháp |
| M4 (Analysis) | Upload kết quả SPSS/.spv, SmartPLS HTML, transcript phỏng vấn |
| M5 (Writing) | Upload bản thảo đã có (Word) |

---

## 9\. INTERACTION MODEL: CLICK-FIRST, CHAT-FALLBACK

### 9.1 Hierarchy of Interaction

Level 1 (Primary):   Click lựa chọn từ gợi ý AI

Level 2 (Secondary): Chỉnh sửa inline trên card/field

Level 3 (Tertiary):  Chat với AI để override hoàn toàn

Level 4 (Advanced):  Import file để thay thế toàn bộ

**Ngoại lệ:** Module 2 hoạt động hoàn toàn ở Level 3 (Chat-first). Tất cả interaction trong M2 đều qua chat; click-choice chỉ xuất hiện như quick-reply buttons để tiện lợi, không phải flow bắt buộc.

### 9.2 Gợi ý thông minh theo ngữ cảnh

Tại mỗi decision point, AI phải:

1. Hiển thị **tối đa 4 lựa chọn** (cognitive load thấp)  
2. Mỗi lựa chọn kèm **lý do ngắn** (1 dòng)  
3. Luôn có option **"Tùy chỉnh"** và **"Nhập thủ công"**  
4. Highlight option **recommended**

---

## 10\. TOKEN-BASED PRICING MODEL

### 10.1 Token Cost Table (Cập nhật v1.1)

| Hành động | Token ước tính |
| :---- | :---- |
| Phân tích 1 paper PDF (≤20 trang) | 2,000 |
| Generate thực trạng \+ gaps (có citation) | 4,500 |
| Xác nhận page references | 500 |
| Viết output chương Literature Review (\~1500 từ) | 5,000 |
| Generate Interview Guide (10 câu hỏi) | 2,000 |
| Giải thích phương pháp nghiên cứu | 1,000 |
| Tạo bảng hỏi hoàn chỉnh (10 constructs) | 4,000 |
| Auto-generate Analysis Outline | 1,000 |
| Phân tích \+ diễn giải 1 bước (SPSS/SEM) | 2,000 |
| Coding transcript định tính (\~5000 chữ) | 3,500 |
| Generate 1 theme \+ verbatim quotes | 2,000 |
| Generate 1 section bài viết (500 từ) | 2,500 |
| Paraphrase 1 đoạn (100 từ) | 500 |
| Translate 1 đoạn (\~200 từ) | 800 |

### 10.2 Gói Token

| Gói | Token | Giá (VND) | Phù hợp với |
| :---- | :---- | :---- | :---- |
| **Starter** | 50,000 | 99,000 | 1 đề cương nhỏ |
| **Student** | 200,000 | 299,000 | 1 khóa luận đầy đủ |
| **Researcher** | 600,000 | 699,000 | 3-4 bài nghiên cứu |
| **Unlimited** | Không giới hạn/tháng | 499,000/tháng | Subscription cho giảng viên |

### 10.3 Token UX

Top bar: \[⚡ 45,230 tokens còn lại\]

Trước hành động tốn token:

┌──────────────────────────────────────┐

│ ⚡ Hành động này tốn \~4,500 tokens   │

│ Số dư hiện tại: 45,230 tokens        │

│ \[Tiến hành\]  \[Hủy\]                   │

└──────────────────────────────────────┘

Cảnh báo khi còn ít: \[⚠ Còn 5,000 tokens — Nạp thêm\]

---

## 11\. TECHNICAL ARCHITECTURE NOTES

### 11.1 Data Flow

User Input / File Upload

        ↓

Input Processing Layer

  (OCR, PDF parse, transcript segmentation, table extract)

        ↓

AI Processing Layer

  (LLM calls với structured prompts)

  (Chat mode: streaming responses, turn management)

        ↓

Context Store (per Project)

  (JSON, versioned, persistent)

        ↓

Output Rendering

  (Chat bubbles, WYSIWYG editor, Analysis tables)

        ↓

Export Engine

  (docx, pdf, latex generation)

### 11.2 Module 2 — Chat Engine Architecture

Chat Session Manager:

  \- Maintains conversation history per project

  \- Injects project context vào system prompt

  \- Tracks phases: \[Familiarization → Research\_State → 

                     Gap\_Analysis → Reference\_Confirm → Output\_Gen\]

  \- Phase-aware AI prompts (khác nhau cho từng phase)

  \- Re-generation on user rejection (history preserved)

Citation Verification Layer:

  \- Nếu paper đã upload: extract text → verify page numbers

  \- Nếu không có paper: generate với \[page?\] placeholder

  \- Cross-reference checker: kiểm tra tính nhất quán citation

### 11.3 Module 4 — Adaptive Analysis Engine

Data Type Detector:

  Input: file extension, content patterns, header signatures

  Output: {tool: "SPSS|SmartPLS|R|Qualitative|...", 

           paradigm: "Quantitative|Qualitative|Mixed"}

Outline Generator:

  Input: detected data type \+ methodology from M3

  Output: Structured outline phù hợp

  Override: User chỉnh sửa trước khi confirm

Analysis Executor:

  \- Step-by-step execution theo confirmed outline

  \- Per-step diễn giải tự động

  \- Warning flags cho giá trị ngoài ngưỡng chuẩn

  \- Chat-triggered ad-hoc analysis bất kỳ lúc

Qualitative Analysis Pipeline:

  \- Transcript ingestion → cleaning

  \- AI-suggested initial codes

  \- Theme clustering

  \- Visual thematic map

  \- Verbatim quote extraction per theme

### 11.4 Export Pipeline

context\_store \+ user edits

  → Document Assembler (section order, chapter numbering)

  → Citation Formatter (CSL — Citation Style Language)

  → Template Renderer (docx-js / LaTeX template)

  → File Download

---

## 12\. USE CASES CHI TIẾT

### UC-01: Sinh viên bắt đầu từ scratch (Định lượng — SPSS)

**Luồng chính:**

1. Tạo project → Chọn "Bắt đầu từ đầu"  
2. M1: Chọn đề tài "Tác động của TL đến EE tại SMEs"  
3. M2 (Chat): AI trình bày thực trạng → User OK → AI trình bày gaps với citation → User chọn Gap 1+2 → Xác nhận page refs → AI viết Ch.2  
4. M3: AI giải thích 3 phương pháp → User chọn Định lượng → PLS-SEM → Build conceptual model → Scale builder → Export bảng hỏi  
5. M4: Upload SPSS .spv → AI nhận dạng → Đề xuất Outline A → User confirm → AI chạy từng bước → Diễn giải  
6. M5: Auto-fill tất cả chương → Chỉnh sửa → Export Word

### UC-02: Sinh viên nghiên cứu định tính (Thematic Analysis)

**Luồng chính:**

1. M1: Chọn đề tài "Trải nghiệm lãnh đạo của nhân viên Gen Z"  
2. M2 (Chat): AI tổng hợp literature về Gen Z \+ Leadership → Xác định gaps phương pháp (thiếu nghiên cứu định tính sâu)  
3. M3: AI giải thích phương pháp → User chọn Định tính → Thematic Analysis → AI tạo Interview Guide → Purposive sampling strategy  
4. M4: Upload 10 transcript → AI nhận dạng → Đề xuất Outline D → Initial coding → Theme clustering → Verbatim quotes → Diễn giải  
5. M5: Auto-fill Ch.4 theo themes → Export

### UC-03: Nghiên cứu hỗn hợp (Mixed Methods)

**Luồng chính:**

1. M3: Chọn Mixed Methods → Sequential Explanatory  
2. M4 Pha 1: Upload SPSS → Outline A → Kết quả định lượng  
3. M4 Pha 2: Upload transcript phỏng vấn → Outline D → Thematic analysis  
4. M4 Pha 3: AI Integration — so sánh & tích hợp 2 pha  
5. M5: Ch.4 gồm cả kết quả định lượng \+ định tính \+ tích hợp

### UC-04: User can thiệp vào Analysis Outline

**Luồng chính:**

1. Upload SPSS data → AI đề xuất Outline A (6 bước)  
2. User chat: "Thêm kiểm định Common Method Bias trước bước EFA"  
3. AI cập nhật outline → Bước 2.5: Harman's Single Factor Test  
4. User bỏ tích bước ANOVA → AI loại khỏi outline  
5. User confirm → AI chạy phân tích theo outline đã chỉnh

### UC-05: Giảng viên review luận văn sinh viên

*(Giữ nguyên từ v1.0)*

---

## 13\. NON-FUNCTIONAL REQUIREMENTS

### 13.1 Performance

- File upload PDF ≤ 50MB: xử lý \< 30 giây  
- AI response chat (streaming): first token \< 2 giây  
- Generate 1 section (500 từ): \< 15 giây  
- Transcript coding (5000 chữ): \< 60 giây

### 13.2 Data Privacy

- Toàn bộ project data encrypted at rest (AES-256)  
- Papers upload và transcripts không được dùng để train AI  
- GDPR-compliant, có tùy chọn xóa toàn bộ data

### 13.3 Availability

- Uptime SLA: 99.5%  
- Auto-save mỗi 30 giây  
- Chat history persistent (không mất khi reload)

### 13.4 Compatibility

- Web app: Chrome, Firefox, Safari, Edge (3 phiên bản gần nhất)  
- Mobile: Responsive cho tablet (chat mode full-support)  
- Export: Tương thích Word 2016+, Google Docs

---

## 14\. ROADMAP GỢI Ý

### Phase 1 — MVP (Tháng 1-3)

- [ ] Project creation & management  
- [ ] Module 1: Topic Discovery (full flow)  
- [ ] Module 2: Literature Review (Chat-first, basic citation)  
- [ ] Module 5: Writing với auto-fill từ M1, M2  
- [ ] Token billing cơ bản  
- [ ] Export Word/PDF

### Phase 2 — Core Complete (Tháng 4-6)

- [ ] Module 2: Page reference verification layer  
- [ ] Module 3: Multi-method support (Quantitative \+ Qualitative)  
- [ ] Module 4: SPSS \+ SmartPLS adaptive outline \+ auto-diễn giải  
- [ ] Module 4: Chat-triggered ad-hoc analysis  
- [ ] Context propagation hoàn chỉnh M1→M5  
- [ ] Citation Manager (APA7, APA6)  
- [ ] Version history

### Phase 3 — Qualitative & Collaboration (Tháng 7-9)

- [ ] Module 4: Qualitative analysis (Thematic, Grounded Theory)  
- [ ] Module 4: NVivo/Atlas.ti output import  
- [ ] Module 3: Interview Guide Builder hoàn chỉnh  
- [ ] Comment & annotation (supervisor flow)  
- [ ] Project sharing & permissions  
- [ ] Google Form export từ Module 3  
- [ ] Zotero/Mendeley integration

### Phase 4 — Advanced Features (Tháng 10-12)

- [ ] Module 4: Mixed Methods integration report  
- [ ] Module 2: Semantic Scholar API integration (live paper search)  
- [ ] Multi-language bilingual paper (VI/EN)  
- [ ] Journal-specific templates  
- [ ] Similarity detection (anti-plagiarism semantic check)  
- [ ] Team collaboration (nhiều sinh viên, 1 advisor)  
- [ ] Mobile app (iOS/Android)

---

## PHỤ LỤC

### A. Thuật ngữ học thuật trong sản phẩm

| Thuật ngữ | Viết tắt | Giải thích ngắn |
| :---- | :---- | :---- |
| Research Gap | — | Khoảng trống trong kiến thức hiện tại |
| Construct | — | Biến tiềm ẩn, đo lường gián tiếp qua items |
| Cronbach's Alpha | α | Độ tin cậy thang đo |
| Average Variance Extracted | AVE | Giá trị hội tụ (≥0.5) |
| Composite Reliability | CR | Độ tin cậy tổng hợp (≥0.7) |
| PLS-SEM | — | Partial Least Squares SEM |
| CB-SEM | — | Covariance-Based SEM |
| Path Coefficient | β | Hệ số tác động trong mô hình cấu trúc |
| Bootstrap | — | Phương pháp kiểm định phi tham số |
| HTMT | — | Heterotrait-Monotrait Ratio |
| Thematic Analysis | — | Phân tích dữ liệu định tính theo chủ đề |
| Data Saturation | — | Điểm dữ liệu định tính không còn thêm thông tin mới |
| Verbatim Quote | — | Trích dẫn nguyên văn từ phỏng vấn |
| Initial Coding | — | Giai đoạn đầu gán nhãn dữ liệu định tính |
| Thematic Map | — | Sơ đồ mối quan hệ giữa các themes |
| Proposition | — | Mệnh đề lý thuyết (thay cho hypothesis trong định tính) |

### B. Supported Citation Formats

- APA 7th Edition (default)  
- APA 6th Edition  
- Chicago 17th Edition (Author-Date)  
- Harvard (UK style)  
- Vancouver (y tế)  
- IEEE (kỹ thuật)  
- Custom format

### C. Supported Analysis Tools & Paradigms

| Tool | Import format | Paradigm | Tính năng nhận dạng |
| :---- | :---- | :---- | :---- |
| SmartPLS 4 | HTML Report, Copy-paste | Quantitative | Outer loadings, AVE, CR, HTMT, Path coeff, Bootstrap |
| SPSS 27+ | .spv, .sav, Copy-paste | Quantitative | Alpha, EFA, CFA, Regression, ANOVA, Descriptives |
| R (lavaan) | Console output | Quantitative | CFA, SEM fit indices |
| Stata | Log file | Quantitative | Regression, panel data |
| AMOS | Output text | Quantitative | SEM, fit indices |
| NVivo | Export .xlsx/.docx | Qualitative | Coded themes, node summaries |
| Atlas.ti | Export report | Qualitative | Codes, quotations, networks |
| Manual transcript | Word/PDF/text | Qualitative | AI-driven coding \+ theme generation |

### D. Qualitative Research Designs — Supported

| Design | Phù hợp khi | Tool phân tích |
| :---- | :---- | :---- |
| Thematic Analysis | Linh hoạt, phổ biến nhất | Manual / AI-assisted |
| Grounded Theory | Xây dựng lý thuyết mới | Constant comparative method |
| Phenomenological | Khám phá trải nghiệm chủ quan | IPA (Interpretative Phenomenological Analysis) |
| Case Study | Nghiên cứu sâu 1 tổ chức/nhóm | Cross-case / within-case analysis |
| Content Analysis | Phân tích văn bản/tài liệu | Frequency \+ thematic |

---

*Document maintained by: Product Team* *Version: 1.1.0 | Last updated: 2026-05* *Changelog: Redesign M2 (Chat-first \+ cited gaps), M3 (Multi-method \+ qualitative tools), M4 (Adaptive analysis outline)* *Status: Living Document — cập nhật theo feedback*  
