/* ===== DoThesis scenario data ===== */
/* Two language packs, one project state, one conversation transcript per scenario. */

window.DT_DATA = (function () {

  const MODULES = [
    { id: 'M1', en: 'Topic Discovery',     vi: 'Tìm chủ đề',           shape: 'wizard' },
    { id: 'M2', en: 'Literature Review',   vi: 'Tổng quan tài liệu',   shape: 'chat' },
    { id: 'M3', en: 'Research Design',     vi: 'Thiết kế nghiên cứu',  shape: 'wizard' },
    { id: 'M4', en: 'Data Analysis',       vi: 'Phân tích dữ liệu',    shape: 'pipeline' },
    { id: 'M5', en: 'Writing',             vi: 'Viết luận văn',        shape: 'wizard' },
  ];

  /* The project state — a snapshot of context_store + status + focus */
  const PROJECT = {
    name: {
      en: 'TikTok livestream buying behavior of Gen Z in Hà Nội',
      vi: 'Hành vi mua hàng qua livestream TikTok của Gen Z tại Hà Nội',
    },
    field: { en: 'Marketing — Consumer behavior', vi: 'Marketing — Hành vi người tiêu dùng' },
    status: { M1: 'done', M2: 'in_progress', M3: 'needs_review', M4: 'locked', M5: 'locked' },
    focus: 'M2',
    tokens: { balance: 184_500, used: 65_500, plan: 'Pro Student' },
    contextStore: {
      research_title: {
        en: 'Antecedents of impulsive purchasing on TikTok Live among Gen Z consumers in Hà Nội',
        vi: 'Các yếu tố tác động đến hành vi mua sắm bốc đồng trên TikTok Live của Gen Z tại Hà Nội',
      },
      research_questions: {
        en: [
          'Which streamer attributes drive impulsive purchasing on TikTok Live?',
          'Does perceived scarcity moderate the impact of social presence on purchase intention?',
          'How does parasocial interaction mediate trust → purchase intention?',
        ],
        vi: [
          'Những đặc điểm nào của streamer thúc đẩy hành vi mua bốc đồng trên TikTok Live?',
          'Cảm nhận khan hiếm có điều tiết tác động của sự hiện diện xã hội lên ý định mua không?',
          'Tương tác bán xã hội trung gian như thế nào giữa niềm tin và ý định mua?',
        ],
      },
      research_gaps: [
        {
          id: 'G1',
          en: 'Live-streaming research has focused on Chinese platforms (Taobao Live); TikTok Live behavior in Southeast Asia is under-studied.',
          vi: 'Nghiên cứu live-streaming tập trung vào nền tảng Trung Quốc (Taobao Live); hành vi trên TikTok Live tại Đông Nam Á còn ít được khảo sát.',
          relevance: 'High',
          confirmed: true,
          papers: [
            { author: 'Sun et al.',   year: 2019, page: 41,  verified: true },
            { author: 'Wongkitrungrueng & Assarut', year: 2020, page: 545, verified: true },
            { author: 'Chen & Lin',   year: 2018, page: 28,  verified: true },
          ],
        },
        {
          id: 'G2',
          en: 'Parasocial interaction is theorised but rarely tested as a mediator between streamer trust and impulsive purchase intention.',
          vi: 'Tương tác bán xã hội đã được nêu ra trên lý thuyết nhưng hiếm khi được kiểm định như biến trung gian giữa niềm tin streamer và ý định mua bốc đồng.',
          relevance: 'High',
          confirmed: true,
          papers: [
            { author: 'Hu, Zhang & Wang', year: 2017, page: 1132, verified: true },
            { author: 'Xu et al.',        year: 2020, page: null, verified: false },
          ],
        },
        {
          id: 'G3',
          en: 'Most studies treat scarcity cues as a direct driver; moderating effects on social presence remain unexplored for Gen Z.',
          vi: 'Phần lớn nghiên cứu xem tín hiệu khan hiếm như biến tác động trực tiếp; vai trò điều tiết với hiện diện xã hội ở Gen Z chưa được khai thác.',
          relevance: 'Medium',
          confirmed: false,
          papers: [
            { author: 'Aggarwal et al.', year: 2011, page: 19, verified: true },
          ],
        },
      ],
      hypotheses: [
        { id: 'H1', en: 'Streamer trust → Impulsive purchase intention (+)',                vi: 'Niềm tin streamer → Ý định mua bốc đồng (+)' },
        { id: 'H2', en: 'Parasocial interaction mediates H1',                                vi: 'Tương tác bán xã hội trung gian cho H1' },
        { id: 'H3', en: 'Perceived scarcity moderates Social presence → Purchase intention', vi: 'Cảm nhận khan hiếm điều tiết Hiện diện xã hội → Ý định mua' },
      ],
      methodology: {
        paradigm: 'quantitative',
        design: 'PLS-SEM',
        tool: 'SmartPLS 4',
        sampling: { strategy: 'Convenience', minSize: 250, targetSize: 320 },
      },
      literature_sources: 41,
      module_summaries: {
        M1: { en: 'Topic narrowed to Gen Z livestream impulse buying after 3 candidate directions.', vi: 'Chủ đề thu hẹp về Gen Z mua bốc đồng trên livestream sau 3 phương án.' },
      },
    },
  };

  /* M2 transcript — currently focused conversation */
  const TRANSCRIPT_M2 = [
    {
      role: 'assistant', module: 'M2', phase: 'familiarization',
      blocks: [
        { type: 'md', en: "I've indexed **41 papers** from your uploads + Semantic Scholar. Let me sketch the state of the literature, then propose gaps.", vi: "Mình đã chỉ mục **41 bài báo** từ tệp bạn tải lên + Semantic Scholar. Mình sẽ phác hoạ tình hình nghiên cứu, sau đó đề xuất khoảng trống." },
        { type: 'state-of-lit' },
        { type: 'md', en: "Here are the **foundational papers** I'll lean on. Each quote is page-cited — click ⤴ on any line to jump into the PDF, or ✗ to flag and re-fetch.", vi: "Đây là **các bài báo nền** mình sẽ dựa vào. Mỗi trích dẫn đều có số trang — bấm ⤴ để mở PDF, hoặc ✗ để gắn cờ và tra lại." },
        { type: 'sources' },
      ],
    },
    {
      role: 'user',
      blocks: [{ type: 'md', en: 'Looks good. What are the most defensible gaps?', vi: 'Ổn. Đâu là những khoảng trống dễ bảo vệ nhất?' }],
    },
    {
      role: 'assistant', module: 'M2', phase: 'gap_analysis',
      blocks: [
        { type: 'md', en: "Three candidates, each grounded in ≥1 paper with page-level citations. Tap a gap to inspect supporting quotes.", vi: "Ba ứng viên, mỗi cái được neo bởi ≥1 bài báo với trích dẫn ở cấp trang. Bấm vào khoảng trống để xem trích dẫn nguồn." },
        { type: 'gaps' },
        { type: 'md', en: "G3's third citation didn't return a page — want me to re-fetch via DOI or mark it `[page?]`?", vi: "Trích dẫn thứ 3 của G3 chưa lấy được số trang — bạn muốn mình tra lại theo DOI hay đánh dấu `[page?]`?" },
      ],
      quickReplies: [
        { en: 'Re-fetch via DOI',          vi: 'Tra lại theo DOI' },
        { en: 'Mark [page?] and move on', vi: 'Đánh dấu [page?] và tiếp tục' },
        { en: 'Show me G3 in detail',     vi: 'Xem G3 chi tiết' },
      ],
    },
    {
      role: 'user',
      blocks: [{ type: 'md', en: "Confirm G1 and G2. Hold G3 — what was gap 1 in M1's terms again?", vi: "Xác nhận G1 và G2. Hoãn G3 — nhắc lại G1 đối chiếu với khung M1?" }],
    },
    {
      role: 'assistant', module: 'M2', router: { intent: 'read', target: 'M1' },
      blocks: [
        { type: 'md', en: "**Reading M1** to answer — focus stays on M2.\n\nIn M1 you scoped the topic to *Gen Z impulse buying on TikTok Live in Hà Nội*. **G1** maps to that scope directly: the Southeast Asia / TikTok corner is under-studied, while existing work concentrated on Chinese platforms.", vi: "**Đọc M1** để trả lời — tiêu điểm vẫn ở M2.\n\nỞ M1 bạn đã thu hẹp phạm vi về *Gen Z mua bốc đồng trên TikTok Live ở Hà Nội*. **G1** ánh xạ trực tiếp với phạm vi đó: góc Đông Nam Á / TikTok còn ít nghiên cứu, trong khi các công trình hiện có tập trung vào nền tảng Trung Quốc." },
      ],
    },
    {
      role: 'user',
      blocks: [{ type: 'md', en: "Good. Confirm G1 + G2 as the working gaps and draft the chapter 2 outline.", vi: "Tốt. Xác nhận G1 + G2 là khoảng trống làm việc và phác Chương 2." }],
    },
    {
      role: 'assistant', module: 'M2', phase: 'output_gen',
      blocks: [
        { type: 'md', en: "Locked **G1** and **G2** into `context_store.research_gaps`. Drafting Chapter 2 — preview below. Edit any section inline; I'll keep your edits.", vi: "Đã lưu **G1** và **G2** vào `context_store.research_gaps`. Đang dựng Chương 2 — xem trước bên dưới. Sửa trực tiếp; mình sẽ giữ lại các thay đổi của bạn." },
        { type: 'doc-preview' },
        { type: 'md', en: "When you confirm, I'll mark **M2 as `done`** and ungate **M3**. Heads up: this will also clear M3's current `needs_review` flag.", vi: "Khi bạn xác nhận, mình sẽ đặt **M2 = `done`** và mở khoá **M3**. Lưu ý: thao tác này cũng xoá cờ `needs_review` hiện tại của M3." },
      ],
      quickReplies: [
        { en: 'Confirm & move to M3',  vi: 'Xác nhận & sang M3' },
        { en: 'Edit Section 2.3',      vi: 'Sửa mục 2.3' },
        { en: 'Add a Vietnam context paragraph', vi: 'Thêm đoạn bối cảnh Việt Nam' },
      ],
    },
  ];

  /* M4 transcript — pipeline shape, shown when scenario=M4-analysis */
  const TRANSCRIPT_M4 = [
    {
      role: 'assistant', module: 'M4',
      blocks: [
        { type: 'md', en: "Detected **`thesis-pilot.sav`** — SPSS dataset, **n = 287**, 24 variables. Proposed outline below; remove / reorder steps before I run anything.", vi: "Đã nhận diện **`thesis-pilot.sav`** — dữ liệu SPSS, **n = 287**, 24 biến. Phác outline bên dưới; xoá / sắp xếp lại các bước trước khi mình chạy." },
        { type: 'outline' },
      ],
    },
    {
      role: 'user',
      blocks: [{ type: 'md', en: 'Run steps 1–4 and stop before bootstrapping.', vi: 'Chạy bước 1–4 rồi dừng trước khi bootstrap.' }],
    },
    {
      role: 'assistant', module: 'M4',
      blocks: [
        { type: 'md', en: "Ran **Descriptives, Reliability, EFA, CFA loadings**. Two thresholds tripped — review the table.", vi: "Đã chạy **Mô tả, Độ tin cậy, EFA, CFA loadings**. Hai ngưỡng vượt — xem bảng." },
        { type: 'results-table' },
        { type: 'md', en: "I'd recommend dropping **TR3** (loading .41) before re-running CFA. Want me to?", vi: "Mình khuyến nghị bỏ **TR3** (loading .41) trước khi chạy lại CFA. Bạn đồng ý?" },
      ],
      quickReplies: [
        { en: 'Drop TR3 and re-run CFA',  vi: 'Bỏ TR3 và chạy lại CFA' },
        { en: 'Keep TR3, explain why',    vi: 'Giữ TR3, giải thích' },
        { en: 'Run a t-test on Gender × TI', vi: 'Chạy t-test Giới tính × TI' },
      ],
    },
    {
      role: 'user',
      blocks: [{ type: 'md', en: "Actually — add a gap about remote work to M2.", vi: "Khoan — thêm một khoảng trống về remote work vào M2." }],
    },
    {
      role: 'assistant', module: 'M2', router: { intent: 'mutate', target: 'M2' },
      blocks: [
        { type: 'md', en: "**Editing M2** — focus shifts. I'll draft a new gap candidate; **M3, M4, M5 are flagged `needs_review`** because hypothesis grounding and instrument coverage may shift.", vi: "**Sửa M2** — tiêu điểm chuyển. Mình sẽ phác khoảng trống mới; **M3, M4, M5 bị đánh dấu `needs_review`** vì việc neo giả thuyết và phạm vi đo lường có thể thay đổi." },
        { type: 'gap-draft' },
      ],
      quickReplies: [
        { en: 'Confirm gap G4',          vi: 'Xác nhận khoảng trống G4' },
        { en: 'Tighten scope to Hà Nội', vi: 'Thu hẹp phạm vi Hà Nội' },
        { en: 'Discard',                  vi: 'Bỏ' },
      ],
    },
  ];

  /* Outline + results data */
  const M4_OUTLINE = [
    { step: 1, op: 'descriptive',    name: { en: 'Descriptive statistics',  vi: 'Thống kê mô tả' },           status: 'done' },
    { step: 2, op: 'reliability',    name: { en: "Cronbach's α (8 scales)", vi: 'Cronbach\'s α (8 thang đo)' }, status: 'done' },
    { step: 3, op: 'efa',            name: { en: 'Exploratory factor analysis (PCA, varimax)', vi: 'EFA (PCA, varimax)' }, status: 'done' },
    { step: 4, op: 'cfa',            name: { en: 'CFA loadings (PLS measurement model)',        vi: 'CFA loadings (mô hình đo lường PLS)' }, status: 'done' },
    { step: 5, op: 'bootstrap',      name: { en: 'Bootstrap path coefficients (5000 resamples)', vi: 'Bootstrap hệ số đường dẫn (5000 mẫu)' }, status: 'queued' },
    { step: 6, op: 'sobel',          name: { en: 'Sobel mediation test',     vi: 'Kiểm định trung gian Sobel' },  status: 'queued' },
  ];

  const M4_RESULTS = [
    { name: 'Streamer Trust (TR)',     items: 5, alpha: 0.71, AVE: 0.49, CR: 0.83, flag: 'AVE < .50' },
    { name: 'Parasocial Interaction',  items: 4, alpha: 0.86, AVE: 0.62, CR: 0.88, flag: null },
    { name: 'Social Presence',          items: 4, alpha: 0.81, AVE: 0.58, CR: 0.85, flag: null },
    { name: 'Perceived Scarcity',       items: 3, alpha: 0.78, AVE: 0.61, CR: 0.83, flag: null },
    { name: 'Impulsive Purchase Int.',  items: 5, alpha: 0.89, AVE: 0.66, CR: 0.91, flag: null },
    { name: 'TR3 item loading',         items: '—', alpha: '—', AVE: 0.41, CR: '—', flag: 'loading < .50' },
  ];

  /* Foundational sources for M2 (seminal papers DoThesis is grounded in) */
  const FOUNDING_SOURCES = [
    {
      camp: { en: 'Stimulus–Organism–Response', vi: 'Kích thích–Tổ chức–Phản hồi' },
      papers: [
        { author: 'Sun, Y., Shao, X., Li, X., Guo, Y. & Nie, K.', year: 2019,
          title: 'How live streaming influences purchase intentions in social commerce: An IT affordance perspective',
          venue: 'Electronic Commerce Research and Applications', vol: '37', cites: 612, doi: '10.1016/j.elerap.2019.100886',
          quote: { en: '“The live streaming context affords four IT affordances — visibility, metavoicing, guidance shopping, and trading — that map onto SOR stimulus.” (p. 41)',
                   vi: '“Bối cảnh livestream cung cấp bốn affordance công nghệ — visibility, metavoicing, guidance shopping, trading — ánh xạ vào kích thích SOR.” (tr. 41)' },
          page: 41, verified: true, seminal: true,
        },
        { author: 'Chen, C.-C. & Lin, Y.-C.', year: 2018,
          title: 'What drives live-stream usage intention? The perspectives of flow, entertainment, social interaction, and endorsement',
          venue: 'Telematics and Informatics', vol: '35(1)', cites: 487, doi: '10.1016/j.tele.2017.12.003',
          quote: { en: '“Flow, perceived entertainment, and parasocial endorsement explain 64% of usage intention variance.” (p. 28)',
                   vi: '“Flow, giải trí cảm nhận và endorsement bán xã hội giải thích 64% phương sai ý định.” (tr. 28)' },
          page: 28, verified: true, seminal: false,
        },
      ],
    },
    {
      camp: { en: 'Parasocial Interaction Theory', vi: 'Lý thuyết tương tác bán xã hội' },
      papers: [
        { author: 'Hu, M., Zhang, M. & Wang, Y.', year: 2017,
          title: 'Why do audiences choose to keep watching on live video streaming platforms? An explanation of dual identification framework',
          venue: 'Computers in Human Behavior', vol: '75', cites: 1043, doi: '10.1016/j.chb.2017.05.006',
          quote: { en: '“Parasocial interaction with the streamer fully mediates the effect of social identification on continuance.” (p. 1132)',
                   vi: '“Tương tác bán xã hội với streamer trung gian hoàn toàn cho tác động của nhận dạng xã hội lên tiếp tục xem.” (tr. 1132)' },
          page: 1132, verified: true, seminal: true,
        },
        { author: 'Wongkitrungrueng, A. & Assarut, N.', year: 2020,
          title: 'The role of live streaming in building consumer trust and engagement with social commerce sellers',
          venue: 'Journal of Business Research', vol: '117', cites: 824, doi: '10.1016/j.jbusres.2018.08.032',
          quote: { en: '“Trust in product and trust in seller jointly mediate live-streaming attributes → engagement.” (p. 545)',
                   vi: '“Niềm tin sản phẩm và niềm tin người bán cùng trung gian thuộc tính livestream → gắn kết.” (tr. 545)' },
          page: 545, verified: true, seminal: true,
        },
      ],
    },
    {
      camp: { en: 'Scarcity & Urgency cues', vi: 'Tín hiệu khan hiếm & khẩn cấp' },
      papers: [
        { author: 'Aggarwal, P., Jun, S. Y. & Huh, J. H.', year: 2011,
          title: 'Scarcity messages',
          venue: 'Journal of Advertising', vol: '40(3)', cites: 358, doi: '10.2753/JOA0091-3367400302',
          quote: { en: '“Limited-quantity scarcity outperforms limited-time scarcity when perceived urgency is high.” (p. 19)',
                   vi: '“Khan hiếm theo số lượng vượt khan hiếm theo thời gian khi tính cấp bách cao.” (tr. 19)' },
          page: 19, verified: true, seminal: true,
        },
      ],
    },
  ];

  /* Theoretical-camp totals — drives the bar block in the chat */
  const STATE_OF_LIT = [
    { camp: 'Stimulus–Organism–Response',      papers: 14, sample: 'Chen & Lin (2018); Sun et al. (2019)' },
    { camp: 'Parasocial Interaction Theory',   papers: 11, sample: 'Hu, Zhang & Wang (2017); Lim et al. (2022)' },
    { camp: 'Scarcity & Urgency cues',         papers:  9, sample: 'Aggarwal et al. (2011); Cialdini (2009)' },
    { camp: 'Trust & social commerce',         papers:  7, sample: 'Hajli (2014); Wongkitrungrueng & Assarut (2020)' },
  ];

  /* Expert agents — specialist personas the student can consult mid-thread */
  const EXPERTS = [
    {
      id: 'methodologist',
      avatar: 'M',
      name:    { en: 'Methodologist',         vi: 'Chuyên gia phương pháp' },
      tagline: { en: 'Research design, paradigms, sampling logic',
                 vi: 'Thiết kế NC, hệ hình, logic chọn mẫu' },
      modules: ['M1', 'M3'],
      sample:  { en: 'Why PLS-SEM over CB-SEM here?',
                 vi: 'Tại sao chọn PLS-SEM thay vì CB-SEM?' },
    },
    {
      id: 'statistician',
      avatar: 'Σ',
      name:    { en: 'Statistician',          vi: 'Chuyên gia thống kê' },
      tagline: { en: 'Tests, assumptions, effect sizes, interpretation',
                 vi: 'Kiểm định, giả định, effect size, diễn giải' },
      modules: ['M4'],
      sample:  { en: 'Interpret these CFA loadings for me',
                 vi: 'Đọc giúp mình các loading CFA này' },
    },
    {
      id: 'lit-reviewer',
      avatar: '¶',
      name:    { en: 'Literature reviewer',   vi: 'Chuyên gia tổng quan' },
      tagline: { en: 'Camps, gaps, theoretical mapping',
                 vi: 'Trường phái, khoảng trống, ánh xạ lý thuyết' },
      modules: ['M2'],
      sample:  { en: 'Map my 41 papers into camps',
                 vi: 'Phân nhóm 41 bài thành các trường phái' },
    },
    {
      id: 'writing-coach',
      avatar: '§',
      name:    { en: 'Writing coach',         vi: 'Chuyên gia học thuật' },
      tagline: { en: 'Voice, structure, signposting, APA style',
                 vi: 'Giọng văn, cấu trúc, signposting, APA' },
      modules: ['M5'],
      sample:  { en: 'Tighten my §2.3 paragraph',
                 vi: 'Siết lại đoạn §2.3' },
    },
    {
      id: 'citations',
      avatar: '"',
      name:    { en: 'Citation manager',      vi: 'Quản lý trích dẫn' },
      tagline: { en: 'DOI lookup, page verify, APA/IEEE formatting',
                 vi: 'Tra DOI, xác minh trang, định dạng APA/IEEE' },
      modules: ['M2', 'M5'],
      sample:  { en: 'Verify all unverified page numbers',
                 vi: 'Xác minh hết các số trang còn cờ' },
    },
    {
      id: 'peer-reviewer',
      avatar: '⚖',
      name:    { en: 'Peer-review simulator', vi: 'Mô phỏng phản biện' },
      tagline: { en: 'Read like a reviewer — what would they ask?',
                 vi: 'Đọc như reviewer — họ sẽ hỏi gì?' },
      modules: ['M2', 'M3', 'M5'],
      sample:  { en: 'Stress-test my hypotheses',
                 vi: 'Soi giả thuyết của mình' },
    },
  ];

  /* Bootstrap wizard — declaration step */
  const HAVE_ITEMS = [
    { id: 'topic',       en: 'Topic / title',             vi: 'Chủ đề / tiêu đề',          mod: 'M1', icon: '✦' },
    { id: 'references',  en: 'Reference PDFs',            vi: 'PDF tài liệu tham khảo',   mod: 'M2', icon: '📄' },
    { id: 'gaps',        en: 'Pre-written gaps',          vi: 'Khoảng trống đã viết sẵn',  mod: 'M2', icon: '◐' },
    { id: 'model',       en: 'Conceptual model',          vi: 'Mô hình khái niệm',         mod: 'M3', icon: '◇' },
    { id: 'instrument',  en: 'Questionnaire / guide',     vi: 'Bảng hỏi / dàn ý phỏng vấn', mod: 'M3', icon: '✎' },
    { id: 'data',        en: 'Raw data (.sav / .csv)',    vi: 'Dữ liệu thô (.sav / .csv)', mod: 'M4', icon: '∑' },
    { id: 'draft',       en: 'Existing draft (Word)',     vi: 'Bản thảo (Word)',           mod: 'M5', icon: '§' },
  ];

  /* Module summaries for sidebar tooltips & context panel */
  const THREADS = [
    {
      id: 'th-current',
      title:   { en: 'Gap analysis → Chapter 2 draft',   vi: 'Phân tích khoảng trống → Chương 2' },
      module: 'M2', pinned: true, unread: 0, status: 'active',
      turns: 26, tokens: '12.4k',
      lastAuthor: 'assistant',
      preview: { en: "I'll mark M2 as done and ungate M3 once you confirm…",
                 vi: "Mình sẽ đánh dấu M2 hoàn tất và mở M3 khi bạn xác nhận…" },
      lastAt: { en: 'now',     vi: 'vừa xong' },
      transcript: 'M2-full',
    },
    {
      id: 'th-method',
      title:   { en: 'Methodology check — PLS-SEM vs CB-SEM', vi: 'Kiểm tra phương pháp — PLS-SEM với CB-SEM' },
      module: 'M3', pinned: true, unread: 2, status: 'active',
      turns: 14, tokens: '8.2k',
      lastAuthor: 'assistant',
      preview: { en: 'PLS-SEM is defensible given n=287 and reflective…',
                 vi: 'PLS-SEM hợp lí với n=287 và thang đo phản ánh…' },
      lastAt: { en: '2h',      vi: '2 giờ' },
      transcript: 'M3-method',
    },
    {
      id: 'th-m4',
      title:   { en: 'M4 — Measurement model & CFA',     vi: 'M4 — Mô hình đo lường & CFA' },
      module: 'M4', pinned: false, unread: 0, status: 'active',
      turns: 9, tokens: '5.7k',
      lastAuthor: 'user',
      preview: { en: 'Run a t-test on Gender × TI',           vi: 'Chạy t-test Giới tính × TI' },
      lastAt: { en: 'yesterday', vi: 'hôm qua' },
      transcript: 'M4-full',
    },
    {
      id: 'th-readclub',
      title:   { en: 'Reading: Wongkitrungrueng (2020)',  vi: 'Đọc: Wongkitrungrueng (2020)' },
      module: 'M2', pinned: false, unread: 0, status: 'active',
      turns: 7, tokens: '3.1k',
      lastAuthor: 'assistant',
      preview: { en: 'Trust in seller mediates engagement — p. 547',
                 vi: 'Niềm tin người bán trung gian gắn kết — tr. 547' },
      lastAt: { en: '3d', vi: '3 ngày' },
      transcript: 'M2-reading',
    },
    {
      id: 'th-topic',
      title:   { en: 'Topic scoping — 3 directions',     vi: 'Thu hẹp chủ đề — 3 hướng' },
      module: 'M1', pinned: false, unread: 0, status: 'archived',
      turns: 18, tokens: '9.0k',
      lastAuthor: 'user',
      preview: { en: "Let's go with the TikTok livestream direction.",
                 vi: 'Chốt hướng TikTok livestream.' },
      lastAt: { en: 'last week', vi: 'tuần trước' },
      transcript: 'M1-archived',
    },
  ];

  /* Short transcripts for additional threads */
  const TRANSCRIPT_M3_METHOD = [
    {
      role: 'user',
      blocks: [{ type: 'md', en: 'Reviewer suggested CB-SEM. Is PLS-SEM still defensible for my model?',
                                vi: 'Phản biện đề xuất CB-SEM. PLS-SEM vẫn hợp lí cho mô hình của mình chứ?' }],
    },
    {
      role: 'assistant', module: 'M3', router: { intent: 'read', target: 'M3' },
      blocks: [
        { type: 'md', en: "**Reading M3** — your model has 5 reflective constructs, 3 paths, and one moderation. Verdict: **PLS-SEM is defensible**, here's why:",
                       vi: '**Đọc M3** — mô hình gồm 5 thang đo phản ánh, 3 đường dẫn, một điều tiết. Kết luận: **PLS-SEM hợp lí**, lý do:' },
      ],
    },
    {
      role: 'assistant', module: 'M3',
      blocks: [
        { type: 'md', en: '· **Sample n = 287** — acceptable for both; PLS-SEM doesn\'t require multivariate normality.\n· **Predictive focus** — you care about *Impulsive purchase intention* as outcome, not parameter recovery.\n· **Moderation (scarcity)** — PLS-SEM handles interaction terms via product-indicator approach.',
                       vi: '· **Mẫu n = 287** — cả hai đều đủ; PLS-SEM không đòi phân phối chuẩn.\n· **Mục đích dự báo** — bạn quan tâm ý định mua như biến kết quả.\n· **Điều tiết (khan hiếm)** — PLS xử bằng product-indicator.' },
      ],
      quickReplies: [
        { en: 'Show comparison table',     vi: 'Hiển thị bảng so sánh' },
        { en: 'Draft reviewer reply',       vi: 'Trả lời phản biện' },
        { en: 'Switch to CB-SEM',           vi: 'Chuyển sang CB-SEM' },
      ],
    },
  ];

  const TRANSCRIPT_M2_READING = [
    {
      role: 'user',
      blocks: [{ type: 'md', en: 'Pull the trust-engagement claim from Wongkitrungrueng & Assarut (2020).',
                                vi: 'Lấy lập luận trust–engagement từ Wongkitrungrueng & Assarut (2020).' }],
    },
    {
      role: 'assistant', module: 'M2',
      blocks: [
        { type: 'md', en: 'Found three citation-worthy passages. Quote 2 is the cleanest for your H2.',
                       vi: 'Tìm được ba đoạn đáng trích. Trích 2 phù hợp nhất cho H2.' },
        { type: 'sources' },
      ],
      quickReplies: [
        { en: 'Insert quote 2 into Chapter 2', vi: 'Chèn trích 2 vào Chương 2' },
        { en: 'Add to H2 grounding',           vi: 'Thêm vào nền H2' },
      ],
    },
  ];

  const TRANSCRIPT_M1_ARCHIVED = [
    {
      role: 'assistant', module: 'M1',
      blocks: [
        { type: 'md', en: 'You weighed three directions:\n\n· Gen Z TikTok livestream impulse buying — strong gap, accessible sample.\n· Influencer parasocial trust on Instagram Reels — crowded literature.\n· Cross-border e-commerce on Shopee — data harder to source.',
                       vi: 'Bạn cân nhắc ba hướng:\n\n· Gen Z mua bốc đồng TikTok livestream — khoảng trống rõ, mẫu dễ tiếp cận.\n· Niềm tin bán xã hội với KOL trên Instagram Reels — văn liệu đông.\n· TMDT xuyên biên giới trên Shopee — dữ liệu khó tìm.' },
      ],
    },
    {
      role: 'user',
      blocks: [{ type: 'md', en: "Let's go with the TikTok livestream direction.",
                                vi: 'Chốt hướng TikTok livestream.' }],
    },
    {
      role: 'assistant', module: 'M1',
      blocks: [
        { type: 'md', en: 'Locked into `context_store.research_title`. M2 unlocked. This thread archived.',
                       vi: 'Đã lưu vào `context_store.research_title`. M2 được mở. Thread này lưu trữ.' },
      ],
    },
  ];
  const MODULE_BLURB = {
    M1: { en: 'Topic, scope, RQs, objectives.',            vi: 'Chủ đề, phạm vi, câu hỏi, mục tiêu.' },
    M2: { en: 'Sources, gaps, hypotheses, Ch. 2 draft.',    vi: 'Tài liệu, khoảng trống, giả thuyết, Ch. 2.' },
    M3: { en: 'Paradigm, model, instrument, sampling.',     vi: 'Hệ hình, mô hình, công cụ đo, mẫu.' },
    M4: { en: 'Detect → outline → execute (sandboxed).',     vi: 'Nhận diện → outline → chạy (sandbox).' },
    M5: { en: 'Auto-fill chapters · citation manager · export.', vi: 'Tự điền chương · quản lý trích dẫn · xuất.' },
  };

  return {
    MODULES, PROJECT,
    TRANSCRIPT_M2, TRANSCRIPT_M4,
    M4_OUTLINE, M4_RESULTS, STATE_OF_LIT,
    HAVE_ITEMS, MODULE_BLURB,
    FOUNDING_SOURCES, EXPERTS,
    THREADS,
    TRANSCRIPT_M3_METHOD, TRANSCRIPT_M2_READING, TRANSCRIPT_M1_ARCHIVED,
  };
})();
