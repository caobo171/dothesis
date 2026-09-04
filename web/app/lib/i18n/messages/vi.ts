/**
 * Vietnamese strings.
 *
 * Typed as Record<MessageKey, string> deliberately: adding a key to en.ts
 * without translating it here FAILS THE BUILD. That is the point — a silently
 * missing translation shows an English string to a Vietnamese student, which is
 * exactly the mixed-language state this system exists to fix.
 *
 * Register: second person "bạn", first person "mình" — the warm-but-not-childish
 * voice a copilot should use with a student. Not "quý khách" (too corporate) and
 * not "em/anh" (assumes an age relationship we don't know).
 *
 * Domain terms stay in English where that IS the Vietnamese academic usage —
 * "SmartPLS", "credits" — because translating them would make the UI harder to
 * follow, not easier.
 */
import type { MessageKey } from "./en";

export const vi: Record<MessageKey, string> = {
  // --- /new — trình phân tích luận văn ---
  // --- Auto Thesis mode ---
  "new.auto.title": "1 câu lệnh, trọn luận văn",
  "new.auto.tagline":
    "Tôi lo phần tổng quan tài liệu, thiết kế nghiên cứu và viết trọn sáu chương. " +
    "Đính kèm dữ liệu của bạn thì chương phân tích có số liệu thật.",
  "new.auto.placeholder": "Chủ đề nghiên cứu của bạn — một câu là đủ.",
  "auto.derived.reading": "Đang đọc tệp của bạn…",
  "auto.derived.title": "Mình đã đọc tệp của bạn",
  "auto.derived.topic": "Sẽ viết luận văn về:",
  "auto.derived.edit": "Chưa đúng? Bạn sửa lại nhé.",
  "auto.derived.start": "Viết luận văn cho tôi",
  "auto.derived.lowCredit": "Số dư không đủ để chạy hết lượt này.",
  "new.auto.analyze": "Viết luận văn cho tôi",
  "new.auto.analyzing": "Đang khởi động…",
  "new.mode.aria": "Bạn muốn làm theo cách nào",
  "new.mode.guided": "Có hướng dẫn",
  "new.mode.guided.hint": "Cùng nhau đi từng bước một",
  "new.mode.auto": "Auto Thesis",
  "new.mode.auto.hint": "Viết trọn luận văn từ đầu đến cuối",
  "new.back": "Về trang chủ",
  "new.title": "Phân tích luận văn của bạn",
  // Xưng "mình" như new.placeholder — giọng của chế độ có hướng dẫn là đồng
  // hành, khác với "tôi" dứt khoát bên Auto Thesis.
  "new.tagline":
    "Gửi bản nháp, tài liệu hay dữ liệu, mình sẽ nói rõ luận văn đang ở đâu " +
    "và cần sửa gì trước. Đi từng bước một, mỗi bước đều do bạn quyết.",
  "new.placeholder":
    "Cho mình biết bạn đang có gì — bản nháp, tài liệu, dữ liệu, hay chỉ mới có ý tưởng.",
  "new.attach": "Đính kèm tệp",
  "new.analyze": "Phân tích",
  "new.analyzing": "Đang phân tích…",
  "new.resumable": "Đã dừng. Phần đã xong được lưu lại — bấm phân tích lại để chạy tiếp từ chỗ đó.",
  "new.cancel": "Hủy",
  "new.dropHint": "Thả tệp vào đây để đính kèm",
  "new.fileTypes": "PDF, Word hoặc văn bản · có thể chọn nhiều tệp",
  "new.remove": "Xóa",

  "new.chip.draft": "Mình có bản nháp",
  "new.chip.draft.text":
    "Mình đã viết được một chương nháp, nhưng chưa có tổng quan tài liệu.",
  "new.chip.data": "Mình có dữ liệu",
  "new.chip.data.text":
    "Mình có dữ liệu khảo sát sẵn sàng cho SmartPLS, nhưng chưa chạy phân tích.",
  "new.chip.papers": "Mình có tài liệu",
  "new.chip.papers.text":
    "Mình đã thu thập tài liệu cho phần tổng quan nhưng chưa tổng hợp lại.",
  "new.chip.humanize": "Bài bị chê giống AI",
  "new.chip.humanize.text":
    "Mình viết xong rồi nhưng giáo viên nói đọc giống ChatGPT — " +
    "mình muốn viết lại tự nhiên hơn, giữ nguyên số liệu và trích dẫn.",
  "new.chip.fresh": "Mới bắt đầu",
  "new.chip.fresh.text":
    "Mình mới bắt đầu — có ý tưởng đề tài nhưng chưa viết gì cả.",

  // --- màn hình Auto Thesis đang chạy ---
  "run.eyebrow": "Auto Thesis",
  "run.live.title": "Đang viết luận văn của bạn",
  "run.live.body":
    "Quá trình này tự chạy — bạn có thể đóng tab rồi quay lại sau. " +
    "Ở đây không có gì cần bạn trả lời cả.",
  "run.done.title": "Luận văn của bạn đã xong",
  "run.done.body":
    "Các chương đã được viết và lưu lại. Mở trong trình soạn thảo để đọc và " +
    "chỉnh sửa, hoặc tải file Word về.",
  "run.failed.title": "Lượt chạy dừng giữa chừng",
  "run.canceled.title": "Bạn đã dừng lượt chạy này",
  "run.stopped.body":
    "Phần đã xong được lưu lại. Chạy tiếp sẽ bắt đầu từ module bị dừng, " +
    "không phải làm lại từ đầu.",
  "run.queued": "Đang khởi động…",
  "run.elapsed": "Đã chạy {n} phút",
  "run.tokens": "{n} token",
  "run.pause": "Tạm dừng",
  "run.resume": "Chạy tiếp",
  "run.stop": "Dừng hẳn",
  "run.retry": "Chạy tiếp",
  "run.openEditor": "Mở trình soạn thảo",
  "run.download": "Tải {kind}",
  "run.askInChat": "Hỏi thêm về luận văn \u2192",
  "run.askChanges": "Muốn sửa gì? Nhắn trong chat \u2192",
  "auto.back": "Quay lại Auto Thesis",
  "auto.back.live": "Đang viết — quay lại Auto Thesis",

  // --- tên các module — dùng chung ở dashboard, header chat và danh sách luận văn ---
  "module.M1": "Xác định đề tài",
  "module.M2": "Tổng quan tài liệu",
  "module.M3": "Thiết kế nghiên cứu",
  "module.M4": "Phân tích dữ liệu",
  // Một bước viết, không phải hai: phần thảo luận kết quả nằm TRONG chương
  // kết luận, không còn là một chương riêng.
  "module.M5": "Kết luận",

  // --- trang chủ ---
  // Trang chủ dạng "nhập thẳng" — thay cho hero dashboard cũ.
  "home.launcher.title": "Mình có thể giúp gì cho luận văn của bạn?",
  "home.launcher.tryTitle": "Thử một trong số này",
  "home.greeting.morning": "Chào buổi sáng",
  "home.greeting.afternoon": "Chào buổi chiều",
  "home.greeting.evening": "Chào buổi tối",
  "home.hello": "Chào {name} —",
  "home.resumePrompt": "tiếp tục từ chỗ đang dở nhé?",
  "home.startPrompt": "bắt đầu luận văn thôi?",
  "home.blurb":
    "Năm module từ đề tài đến bản thảo hoàn chỉnh — một cuộc trò chuyện, nguồn tài liệu của bạn, trích dẫn kèm số trang.",
  "home.inModule": "Bạn đang ở {module} · {label} của “{name}” — mở lại để tiếp tục.",
  "home.resume": "Tiếp tục luận văn",
  "home.startNew": "Bắt đầu luận văn mới",
  "home.credits": "Số dư credit",
  "home.creditsUnit": "credit",
  "home.topUp": "+ Nạp thêm",

  "home.stat.active": "Luận văn đang làm",
  "home.stat.activeSub": "trong tài khoản của bạn",
  "home.stat.done": "Module đã xong",
  "home.stat.doneSub": "trên tổng số 5 module",
  "home.stat.progress": "Đang thực hiện",
  "home.stat.progressSub": "module đang được xử lý",

  "home.theses": "Luận văn của bạn",
  // Tiếng Việt không biến đổi danh từ theo số — hai dòng giống nhau là CỐ Ý.
  "home.thesesCount_one": "{count} luận văn đang làm",
  "home.thesesCount_other": "{count} luận văn đang làm",
  "home.newThesis": "Luận văn mới",
  "home.empty": "Chưa có luận văn nào. Bấm “Luận văn mới” để bắt đầu.",
  "home.noField": "Chưa chọn lĩnh vực",
  "home.next": "Tiếp theo",
  "home.continue": "Tiếp tục {module}",
  "home.lastTouched": "sửa lần cuối {when}",
  "home.recent": "Hoạt động gần đây",
  "home.workingIn": "Đang làm ở",
  "home.proTip": "Mẹo nhỏ",
  "home.proTipBody":
    "Bạn có thể hỏi về bất kỳ module nào từ bất kỳ đâu — chỉ khi bạn sửa thì trọng tâm mới chuyển, còn hỏi thì không.",

  "time.justNow": "vừa xong",
  "time.minutes": "{n} phút trước",
  "time.hours": "{n} giờ trước",
  "time.days": "{n} ngày trước",
  "time.weeks": "{n} tuần trước",

  // --- lỗi khi mở workspace ---
  "ws.gone.title": "Luận văn này không còn tồn tại",
  "ws.gone.body": "Luận văn đã bị xóa, hoặc liên kết này trỏ tới một dự án ở tài khoản khác.",
  "ws.forbidden.title": "Bạn không có quyền xem luận văn này",
  "ws.forbidden.body":
    "Luận văn thuộc về một tài khoản khác. Kiểm tra lại xem bạn đang đăng nhập bằng tài khoản nào.",
  "ws.failed.title": "Không mở được luận văn này",
  "ws.failed.body": "Máy chủ không phản hồi như mong đợi. Thử lại sau một lát nhé.",
  "ws.back": "Về danh sách luận văn",
  "ws.retry": "Thử lại",
  "ws.threadsFailed": "Không tải được danh sách cuộc trò chuyện.",
  "ws.threadGone.title": "Cuộc trò chuyện này không còn tồn tại",
  "ws.threadGone.body":
    "Nó đã bị xóa, hoặc liên kết đã cũ. Chọn một cuộc trò chuyện khác ở thanh bên trái.",
  "ws.threadFailed.title": "Không mở được cuộc trò chuyện này",
  "ws.threadFailed.body": "Thử lại sau một lát nhé.",
  "ws.threadsEmpty": "Luận văn này chưa có cuộc trò chuyện nào — tạo một cái ở thanh bên trái.",
  "ws.loadingThread": "Đang mở cuộc trò chuyện…",
  "ws.projectThreadsFailed": "Không tải được các cuộc trò chuyện của luận văn này.",

  // --- thanh bên dự án ---
  "sidebar.projectCredits": "Tổng credits dự án",
  "sidebar.threads": "Cuộc trò chuyện",
  "sidebar.newThread": "Cuộc trò chuyện mới",
  "sidebar.project": "Dự án",
  "sidebar.loading": "Đang tải…",
  "sidebar.archived": "Đã lưu trữ",
  "sidebar.noThreads": "Chưa có cuộc trò chuyện nào — tạo một cái nhé.",

  // --- vỏ ứng dụng: menu chính + thanh trên ---
  "nav.workspace": "Không gian làm việc",
  "nav.dashboard": "Tổng quan",
  "nav.theses": "Luận văn",
  "nav.account": "Tài khoản",
  // "Credit" và "MCP" giữ nguyên tiếng Anh — đó chính là cách sinh viên và tài
  // liệu kỹ thuật gọi chúng; dịch ra sẽ khó hiểu hơn chứ không dễ hơn.
  "nav.credit": "Credit",
  "nav.transactions": "Giao dịch",
  "nav.mcp": "MCP",
  "nav.admin": "Quản trị",
  "nav.users": "Người dùng",
  "nav.papers": "Tài liệu",
  "nav.jobs": "Tác vụ",
  "nav.announcements": "Thông báo",
  "nav.orders": "Đơn hàng",
  "nav.connectors": "Kết nối",
  "nav.toolUsage": "Lượt dùng công cụ",
  "nav.toolUsageAll": "Toàn bộ lượt dùng",

  // Slogan. "Draft" trong bản tiếng Anh là ĐỘNG TỪ (viết), không phải "bản
  // nháp" — dịch thành danh từ khiến sản phẩm nghe như chỉ lo khâu nháp, trong
  // khi thứ nó làm là cả cuốn luận văn.
  "shell.tagline": "Tự tin viết luận văn",
  "shell.collapse": "Thu gọn",
  "shell.signOut": "Đăng xuất",
  "shell.openSidebar": "Mở thanh bên",
  "shell.closeSidebar": "Đóng thanh bên",
  "shell.notifications": "Xem thông báo",
  "shell.userMenu": "Mở menu tài khoản",

  // --- /tools — việc lẻ, không cần dự án luận văn ---
  "tools.title": "Công cụ",
  "tools.blurb":
    "Một việc, một câu trả lời — không cần tạo dự án luận văn. Việc nào cần hiểu " +
    "nghiên cứu của bạn thì làm trong cuộc trò chuyện của luận văn.",
  "tools.credits": "{count} credit",

  // "Humanize" giữ nguyên: đó là tên tính năng, và cũng là từ sinh viên đang dùng.
  "tools.humanize.name": "Humanize",
  "tools.humanize.tagline": "Viết lại bản thảo cho tự nhiên như người viết",
  "tools.humanize.blurb":
    "Viết lại giọng văn cho đoạn bạn đã viết để không còn đọc như văn AI. Chỉ đổi " +
    "cách diễn đạt, không đổi nội dung — mọi con số, số liệu và trích dẫn đều được " +
    "giữ nguyên và kiểm tra lại sau khi viết.",
  "tools.humanize.modePassage": "Một đoạn văn",
  "tools.humanize.modeDocument": "Cả tài liệu (.docx)",
  "tools.humanize.passageLabel": "Đoạn văn của bạn",
  "tools.humanize.placeholder":
    "Dán đoạn văn bạn muốn viết lại — hoặc đính kèm tệp ở trên.",
  "tools.humanize.anchorLabel": "Văn bạn tự viết (mẫu giọng văn)",
  "tools.humanize.anchorSaved_one": "đã lưu {count} từ",
  "tools.humanize.anchorSaved_other": "đã lưu {count} từ",
  "tools.humanize.anchorPlaceholderSaved":
    "Đang dùng mẫu bạn đã lưu. Chỉ dán bài mới vào đây nếu bạn muốn thay mẫu cũ.",
  "tools.humanize.anchorPlaceholder":
    "Khoảng 150 từ do chính bạn viết, trước khi dùng AI — một bài tiểu luận cũ, " +
    "một báo cáo, gì cũng được.",
  "tools.humanize.anchorTooShort": "Cần khoảng 150 từ thì mới nhận ra được giọng văn",
  "tools.humanize.anchorSaving": "Đang lưu…",
  "tools.humanize.anchorReplace": "Thay mẫu đã lưu",
  "tools.humanize.anchorSave": "Lưu mẫu giọng văn",
  "tools.humanize.anchorWillUse": "Sẽ dùng mẫu đã lưu.",
  "tools.humanize.anchorRequired":
    "Bắt buộc — bản viết lại phải dựa trên văn thật do người viết.",
  "tools.humanize.anchorCountShort": "{count} từ — nên có khoảng 150 từ.",
  "tools.humanize.anchorCountEnough": "{count} từ — vậy là đủ.",
  "tools.humanize.anchorSavedMsg":
    "Đã lưu — {count} từ. Những lần viết lại sau sẽ tự động dùng mẫu này.",
  "tools.humanize.anchorSaveFailed": "Không lưu được mẫu này.",
  "tools.humanize.running": "Đang viết lại…",
  "tools.humanize.errNoAnchor":
    "Thêm khoảng 150 từ văn bạn tự viết ở trên, rồi chạy lại.",
  "tools.humanize.errFrozen":
    "Bản viết lại đã làm sai lệch một con số hoặc trích dẫn, nên bản gốc của bạn " +
    "được giữ nguyên.",
  "tools.humanize.errFailed": "Việc viết lại không hoàn tất.",
  "tools.humanize.badgeRewritten": "Đã viết lại",
  "tools.humanize.badgeNoChange": "Không cần sửa gì",
  "tools.humanize.badgeVerified": "đã kiểm tra số liệu & trích dẫn",
  "tools.humanize.caveat":
    "Nếu bản viết lại làm thay đổi bất kỳ con số, số liệu hay trích dẫn nào thì nó " +
    "bị loại và bạn nhận lại bản gốc — công cụ này không bao giờ âm thầm sửa kết " +
    "quả nghiên cứu. Nó cũng không hứa hẹn gì về việc công cụ phát hiện AI sẽ nói gì.",

  "tools.rhythm.name": "Nhịp văn",
  "tools.rhythm.tagline": "Đo xem câu văn của bạn máy móc tới mức nào",
  "tools.rhythm.blurb":
    "Đo xem nhịp câu của bạn máy móc tới mức nào — độ dao động của độ dài câu, và " +
    "tần suất các đoạn mở đầu bằng cùng một từ nối. Đây là nhận xét về cách viết, " +
    "kiểu nhận xét giáo viên hướng dẫn hay đưa ra.",
  "tools.rhythm.passageLabel": "Đoạn văn (từ 3 câu trở lên)",
  "tools.rhythm.placeholder":
    "Dán một đoạn — cần ít nhất 3 câu để đo được nhịp văn.",
  "tools.rhythm.run": "Đo",
  "tools.rhythm.running": "Đang đo…",
  "tools.rhythm.errShort": "Chưa đủ văn bản để đo nhịp.",
  "tools.rhythm.band.veryEven": "Rất đều — các câu dài gần như bằng nhau",
  "tools.rhythm.band.fairlyEven": "Khá đều",
  "tools.rhythm.band.someVariation": "Có thay đổi ít nhiều",
  "tools.rhythm.band.bursty": "Linh hoạt — đọc như nhịp văn tự nhiên của người viết",
  "tools.rhythm.scaleLow": "0 · linh hoạt",
  "tools.rhythm.scaleHigh": "1 · đều như máy",
  "tools.rhythm.caveatLead": "Đây KHÔNG phải công cụ phát hiện AI.",
  "tools.rhythm.caveatBody":
    " Nó đo độ dao động độ dài câu và mật độ từ nối — nó không đo được perplexity, " +
    "thứ chiếm khoảng một nửa những gì các công cụ phát hiện thật sự dùng. Nó không " +
    "dự đoán được Turnitin, GPTZero hay bất kỳ công cụ thương mại nào, và điểm thấp " +
    "không có nghĩa là bạn đã qua. Hãy xem đây là nhận xét về cách viết: nếu các câu " +
    "của bạn dài như nhau cả thì nên thay đổi độ dài.",

  "tools.citation.name": "Tạo trích dẫn",
  "tools.similarity.name": "Trùng lặp & trích dẫn",
  "tools.sim.run": "Kiểm tra tài liệu",
  "tools.sim.running": "Đang kiểm tra…",
  "tools.sim.errFailed": "Không kiểm tra được tài liệu này.",
  "tools.sim.willCheck": "Sẽ kiểm tra {count} đoạn nội dung",
  "tools.sim.willDuplication": "Các đoạn bị lặp lại ở nơi khác trong chính tài liệu này",
  "tools.sim.willQuotes": "Trích dẫn nguyên văn không có nguồn kèm theo (tìm thấy {count} trích dẫn)",
  "tools.sim.willReferences": "Đối chiếu trích dẫn trong bài với danh mục tham khảo ({count} mục)",
  "tools.sim.willCorpus": "Có tra thêm nguồn đối chiếu bên ngoài",
  "tools.sim.willNotCorpus": "KHÔNG tra nguồn bên ngoài — công cụ này không cho biết đoạn văn có xuất hiện ở nơi khác hay không, và đây không phải điểm Turnitin",
  "tools.sim.willCost": "Chi phí {count} tín dụng",
  "tools.sim.doneFlagged": "{count} đoạn được tô sáng trong file",
  "tools.sim.doneDuplication": "{count} đoạn lặp lại bên trong tài liệu",
  "tools.sim.doneQuotes": "{count} trích dẫn không có nguồn",
  "tools.sim.doneGaps": "{count} trích dẫn thiếu trong danh mục tham khảo",
  "tools.sim.resultNoCorpus": "Không có nguồn bên ngoài nào được tra, nên kết quả này KHÔNG có nghĩa là bài không trùng với tài liệu khác. Muốn có điểm hội đồng chấp nhận, hãy dùng Turnitin của trường.",
  "tools.sim.caveat": "Bản tự kiểm tra trên chính file của bạn: chỗ nào lặp lại bên trong bài, và trích dẫn có khớp danh mục tham khảo không. Công cụ không tra web hay kho bài báo nên không đưa ra phần trăm trùng lặp — nhưng sửa những gì nó tìm được chính là cách kéo phần trăm thật xuống.",
  "tools.sim.caveatCorpus": "Kiểm tra file của bạn về lặp nội bộ và lỗi trích dẫn, đồng thời tra nguồn đối chiếu bên ngoài đã cấu hình. Dù vậy, chỉ bản chạy Turnitin của trường mới cho ra con số hội đồng chấp nhận.",
  "tools.citation.tagline": "Chèn nguồn còn thiếu, đối chiếu nguồn đã có",
  "tools.citation.blurb":
    "Đính kèm luận văn, nhận lại đúng file đó với danh mục tài liệu tham khảo được " +
    "dựng lại từ CrossRef và những câu chưa có nguồn được gắn nguồn — định dạng " +
    "giữ nguyên. Hoặc kiểm tra một trích dẫn lẻ, hoặc một danh mục bạn dán vào.",
  "tools.citation.refLabel": "Trích dẫn cần kiểm tra",
  "tools.citation.placeholder":
    "10.1016/j.chb.2021.106789  ·  hoặc  ·  Nguyen, T. (2021). Title of the paper. Journal Name.",
  "tools.citation.run": "Kiểm tra",
  "tools.citation.running": "Đang kiểm tra…",
  // Đặt tên theo THỨ NGƯỜI DÙNG ĐƯA VÀO, không theo cơ chế bên trong: "Một tài
  // liệu / Cả danh sách" không nói được là tài liệu gì, danh sách gì.
  "tools.citation.modeDocx": "Cả luận văn (.docx)",
  "tools.citation.modeList": "Danh mục dán vào",
  "tools.citation.modeOne": "Một trích dẫn",
  "tools.citation.listLabel": "Danh mục tài liệu tham khảo, hoặc cả luận văn",
  "tools.citation.listPlaceholder":
    "Dán danh sách tài liệu tham khảo — hoặc đính kèm cả luận văn ở trên, công cụ " +
    "tự tìm phần này trong đó.",
  "tools.citation.runAll": "Kiểm tra tất cả",
  "tools.citation.summary_one": "Đã kiểm tra {count} tài liệu",
  "tools.citation.summary_other": "Đã kiểm tra {count} tài liệu",
  "tools.citation.countConfirmed": "{count} xác nhận",
  "tools.citation.countProbable": "{count} khớp tương đối",
  "tools.citation.countMissing": "{count} không tìm thấy",
  "tools.citation.itemUnchecked": "Chưa kiểm tra được — không kết nối được CrossRef",
  "tools.citation.truncated":
    "Mới kiểm tra {checked} trong {detected} tài liệu. Tách danh sách ra rồi chạy " +
    "tiếp phần còn lại.",
  "tools.citation.errNoRefs":
    "Không tìm thấy tài liệu tham khảo nào. Công cụ tìm những dòng có năm hoặc có " +
    "DOI, thường nằm dưới mục “Tài liệu tham khảo” / “References” — bạn dán riêng " +
    "danh sách đó, hoặc dán cả tài liệu.",
  "tools.citation.errUnreachable":
    "Không kết nối được tới CrossRef, nên tài liệu này CHƯA được kiểm tra — điều đó " +
    "không có nghĩa là nó giả.",
  "tools.citation.none": "Không tìm thấy kết quả nào khớp",
  "tools.citation.exact": "Đã xác nhận — khớp chính xác theo DOI",
  "tools.citation.probable": "Có thể khớp (tìm tương đối, chưa phải bằng chứng)",
  "tools.citation.caveat":
    "Tra theo DOI là tra chính xác, kết quả là chắc chắn. Không có DOI thì công cụ " +
    "chuyển sang tìm theo thông tin thư mục, cách này chỉ tương đối — CrossRef luôn " +
    "trả về kết quả gần nhất cho mọi truy vấn, nên tìm thấy chỉ chứng tỏ có một tài " +
    "liệu na ná tồn tại, chứ không chứng minh tài liệu bạn trích là thật. Hãy đối " +
    "chiếu tên bài và tác giả với những gì bạn đã trích dẫn.",

  // --- chèn trích dẫn cho cả tài liệu (.docx vào, .docx ra) ---
  "tools.cite.found_one": "Luận văn đang trích {count} nguồn",
  "tools.cite.found_other": "Luận văn đang trích {count} nguồn",
  "tools.cite.willResolve": "từng nguồn được tra trên CrossRef và định dạng theo APA 7",
  "tools.cite.willCost": "{count} credit — tính theo số nguồn mình đi tra",
  "tools.cite.willLink":
    "mỗi trích dẫn thành một liên kết — bấm vào là nhảy xuống đúng mục trong danh mục",
  "tools.cite.willReplaceList":
    "danh mục tài liệu tham khảo hiện tại ({count} mục) sẽ được thay bằng bản dựng lại",
  "tools.cite.willCreateList": "chưa có danh mục tài liệu tham khảo — sẽ thêm vào cuối bài",
  "tools.cite.willKeepFormat":
    "{count} tiêu đề, cùng với bảng và đánh số, được giữ nguyên",
  "tools.cite.addMissing": "Chèn thêm nguồn cho những câu chưa có",
  "tools.cite.addMissingHint":
    "Quét {count} đoạn thân bài để tìm những câu mà người đọc sẽ đòi nguồn, tìm trên " +
    "CrossRef, và chỉ chèn trích dẫn khi xác nhận được có bài thật sự nói về nội dung " +
    "đó. Chỗ nào không xác nhận được thì đánh dấu [cần nguồn] chứ không đoán. Phần " +
    "này có chạy model nên tính thêm credit ngoài số ở trên — tính theo lượng thực " +
    "dùng, bước quét không đoán trước được.",
  "tools.cite.run": "Chèn trích dẫn",
  "tools.cite.running": "Đang xử lý…",
  "tools.cite.errFailed": "Không xử lý được tài liệu này.",
  "tools.cite.doneResolved": "đối chiếu được {count} trích dẫn trên CrossRef",
  "tools.cite.doneUnresolved":
    "{count} trích dẫn không tra ra — mục bạn tự viết được giữ nguyên kèm ghi chú",
  "tools.cite.doneWeak":
    "{count} mục chỉ khớp được theo tên và năm (bạn chưa liệt kê trong danh mục) — cần tự kiểm lại",
  "tools.cite.doneUncited": "{count} mục trong danh mục không thấy được trích ở bài",
  "tools.cite.doneAdded": "chèn thêm {count} trích dẫn mới",
  "tools.cite.doneMarked": "{count} câu được đánh dấu [cần nguồn]",
  "tools.cite.doneLinked": "{count} trích dẫn đã gắn liên kết tới danh mục",
  "tools.cite.caveat":
    "Không có trích dẫn nào được chèn nếu CrossRef không trả về nó và một bước kiểm " +
    "tra thứ hai không xác nhận bài đó đúng là nói về nội dung câu ấy — câu không xác " +
    "nhận được sẽ mang dấu [cần nguồn] chứ không nhận một nguồn nghe có vẻ hợp lý. " +
    "Không mục nào trong danh mục của bạn bị xoá: tra không ra thì giữ nguyên mục bạn " +
    "viết kèm ghi chú, chỉ khớp được theo tên và năm thì cũng ghi rõ để bạn kiểm lại. " +
    "Bảng, tiêu đề và đánh số không bị đụng tới; chữ in đậm hoặc in nghiêng nằm trong " +
    "câu bị sửa thì không giữ được.",

  // --- viết lại cả tài liệu ---
  "tools.doc.choose": "Chọn tệp .docx",
  "tools.doc.wordOnly": "Chỉ nhận Word — PDF không có đoạn văn sửa được",
  "tools.doc.readFailed": "Không đọc được tài liệu này.",
  "tools.doc.willRewrite_one": "Sẽ viết lại {count} đoạn",
  "tools.doc.willRewrite_other": "Sẽ viết lại {count} đoạn",
  "tools.doc.headings": "giữ nguyên {count} tiêu đề — đó là cấu trúc, không phải văn",
  "tools.doc.tables": "giữ nguyên {count} bảng — đó là dữ liệu",
  "tools.doc.captions": "bỏ qua {count} chú thích và dòng ngắn",
  "tools.doc.runsAs_one":
    "Sẽ chạy thành {count} lượt viết lại (các đoạn được gom theo mục). Bạn chỉ trả " +
    "cho số token thực dùng — số chính xác hiện trong mục Giao dịch.",
  "tools.doc.runsAs_other":
    "Sẽ chạy thành {count} lượt viết lại (các đoạn được gom theo mục). Bạn chỉ trả " +
    "cho số token thực dùng — số chính xác hiện trong mục Giao dịch.",
  // --- Claude Skill miễn phí ---
  "tools.skill.title": "Dùng phương pháp này trong Claude, miễn phí",
  "tools.skill.blurb":
    "Vẫn là cách viết lại dựa trên văn mẫu của chính bạn, đóng gói thành một "
    + "Claude Skill để bạn giữ luôn. Nó viết lại đoạn bạn dán vào và kiểm tra bằng "
    + "đúng script bên mình dùng — không được đổi số liệu, trích dẫn hay ngôn ngữ. "
    + "Còn xử lý cả tệp .docx mà vẫn giữ tiêu đề, bảng biểu thì làm ở đây.",
  "tools.skill.download": "Tải skill (.zip)",
  "tools.skill.how":
    "Trong Claude: Settings → Skills → Add → Upload a skill, rồi chọn tệp này.",
  "tools.doc.run": "Humanize cả tài liệu",
  "tools.doc.runningCount": "Đang viết lại… {done}/{total}",
  "tools.doc.runningBatches": "Đã viết lại {done}/{total} lô",
  "tools.doc.runningSteps": "Bước {done}/{total}",
  "tools.doc.errEmpty":
    "Không có gì để viết lại — tài liệu này chỉ gồm tiêu đề, bảng và chú thích.",
  "tools.doc.downloadAgain": "Tải file về",
  "tools.doc.downloaded": "Đã tải về {name}",
  "tools.doc.rewritten_one": "đã viết lại {count} đoạn",
  "tools.doc.rewritten_other": "đã viết lại {count} đoạn",
  "tools.doc.declined_one":
    "{count} đoạn đã đọc như người viết nên được giữ nguyên đúng như bạn viết.",
  "tools.doc.declined_other":
    "{count} đoạn đã đọc như người viết nên được giữ nguyên đúng như bạn viết.",
  "tools.doc.skipped_one":
    "{count} đoạn giữ nguyên văn bản gốc — viết lại không thành công hoặc sẽ " +
    "làm sai lệch số liệu, trích dẫn.",
  "tools.doc.skipped_other":
    "{count} đoạn giữ nguyên văn bản gốc — viết lại không thành công hoặc sẽ " +
    "làm sai lệch số liệu, trích dẫn.",
  "tools.doc.unchanged": "Tiêu đề, bảng và đánh số giữ nguyên.",
  "tools.doc.caveatBefore":
    "Bảng và tiêu đề không bao giờ bị viết lại, và lô nào mà bản viết lại làm sai " +
    "lệch số liệu hay trích dẫn thì giữ nguyên văn bản gốc. Có một thứ mất thật: " +
    "chữ in đậm hoặc in nghiêng ",
  "tools.doc.caveatEm": "bên trong",
  "tools.doc.caveatAfter":
    " một câu sẽ không giữ được — còn kiểu đoạn, cấp tiêu đề, bảng và đánh số thì có.",

  // --- điều khiển đính kèm tệp, dùng chung cho mọi công cụ ---
  "tools.file.attach": "Đính kèm tệp",
  "tools.file.reading": "Đang đọc…",
  "tools.file.types": "PDF, Word hoặc văn bản",
  "tools.file.orDrop": "{hint} · hoặc kéo thả vào đây",
  "tools.file.loaded": "{name} — nội dung đã đưa vào ô bên dưới, bạn sửa thoải mái",
  "tools.file.readFailed": "Không đọc được tệp này.",

  // --- lỗi khi gọi công cụ ---
  "tools.err.request": "Yêu cầu không thành công.",
  "tools.err.unsupported":
    "Không hỗ trợ định dạng này — hãy dùng PDF, Word hoặc tệp văn bản.",
  "tools.err.tooLarge": "Tệp này quá lớn.",
  "tools.err.readFile": "Không đọc được tệp ({status}).",
  "tools.err.noText": "Không đọc được nội dung nào từ tệp này.",
  "tools.err.needDocx":
    "Viết lại cả tài liệu cần tệp .docx — PDF không có đoạn văn sửa được.",
  "tools.err.readDoc": "Không đọc được tài liệu ({status}).",
  "tools.err.rewriteFailed": "Việc viết lại không hoàn tất ({status}).",
  "tools.err.docTimeout":
    "Quá lâu nên đã dừng chờ. Tài liệu của bạn không bị thay đổi — hãy thử lại, " +
    "hoặc tách thành nhiều tệp nhỏ hơn.",
  "tools.err.docConnection":
    "Mất kết nối tới máy chủ trước khi tài liệu trả về. Tài liệu của bạn không bị " +
    "thay đổi — hãy thử lại.",

  // --- /transactions — nơi sinh viên vào xem credit đã đi đâu ---
  "txn.title": "Giao dịch",
  "txn.balance": "{count} Credit",
  "txn.col.date": "Thời gian",
  "txn.col.activity": "Hoạt động",
  "txn.col.amount": "Số credit",
  "txn.col.tool": "Công cụ",
  "txn.col.result": "Kết quả",
  "txn.col.credits": "Credit",
  "txn.loading": "Đang tải…",
  "txn.empty": "Chưa có giao dịch nào.",
  "txn.prev": "Trước",
  "txn.next": "Sau",

  "txn.reason.chatTurn": "Lượt chat / viết",
  "txn.reason.autoRun": "Chạy tự động",
  "txn.reason.paperRun": "Chạy luận văn",
  "txn.reason.purchase": "Nạp credit",
  "txn.reason.refund": "Hoàn credit",

  // Tên công cụ theo cách sinh viên gọi, không phải slug của máy chủ — thứ mà
  // danh sách này vẫn hiện cho tới khi các công cụ bắt đầu tính tiền theo tên riêng.
  "txn.tool.humanize": "Humanize một đoạn",
  "txn.tool.humanizeDocx": "Humanize cả tài liệu",
  "txn.tool.citeDocx": "Chèn trích dẫn cho tài liệu",
  "txn.tool.verifyCitation": "Kiểm tra một trích dẫn",
  "txn.tool.verifyCitations": "Kiểm tra cả danh mục",
  "txn.tool.rhythm": "Nhịp văn",
  "txn.tool.plagiarism": "Kiểm tra trùng lặp",
  "txn.tool.similarityDocx": "Tự kiểm tra trùng lặp & trích dẫn",
  "txn.tool.similarityDocxCorpus": "Kiểm tra trùng lặp (có đối chiếu ngoài)",
  "txn.tool.scanSimilarityDocx": "Quét trùng lặp & trích dẫn",
  "txn.tool.extractText": "Đọc tệp",
  "txn.tool.scanDocx": "Quét tài liệu",
  "txn.tool.scanCiteDocx": "Quét trích dẫn",

  "txn.tools.seeRuns": "Tìm tệp của một lượt chạy công cụ?",
  "txn.tools.title": "Lượt dùng công cụ",
  "txn.tools.blurb":
    "Tất cả những gì bạn chạy ngoài dự án luận văn. Cả những lượt không mất credit " +
    "cũng được liệt kê, để bạn biết vì sao credit trừ — và vì sao không trừ.",
  "txn.tools.empty": "Bạn chưa dùng công cụ nào.",
  "txn.tools.ok": "Xong",
  "txn.tools.failed": "Chưa xong",
  "txn.tools.free": "Miễn phí",
  // --- tệp đã lưu + tiến độ ---
  "txn.tools.running": "Đang chạy — {done}/{total}",
  "txn.tools.runningPlain": "Đang chạy…",
  "txn.tools.partial":
    "{done} đoạn đã viết lại · {skipped} đoạn giữ nguyên văn bản gốc",
  "txn.tools.dlInput": "Tệp gốc",
  "txn.tools.dlOutput": "Kết quả",
  "txn.tools.rerun": "Chạy lại",
  "txn.tools.rerunning": "Đang chạy…",
  "txn.tools.rerunConfirm":
    "Chạy lại tài liệu này? Lượt chạy lại vẫn tốn credit như lần đầu.",
  "txn.tools.keptUntil": "giữ đến {date}",
  "txn.tools.viewDiff": "Xem đã đổi gì",
  "txn.tools.deleteFiles": "Xoá tệp",
  // --- chi tiết một lượt chạy ---
  "run.back": "Tất cả lượt dùng",
  "run.title": "Lượt chạy công cụ",
  "run.summary": "{changed} đoạn đã đổi · {unchanged} đoạn giữ nguyên · {total} đoạn trong tài liệu",
  "run.exportHtml": "Xuất HTML",
  "run.exportPdf": "Xuất PDF",
  "run.showUnchanged": "Hiện cả đoạn không đổi",
  "run.noChanges": "Lượt chạy này không đổi đoạn nào.",
  "run.truncated": "Chỉ hiện những đoạn đầu. Tải tệp về để xem phần còn lại.",
  "run.notAligned":
    "Hai tệp không còn khớp nhau theo từng đoạn, nên nếu ghép lại sẽ gán nhầm chữ "
    + "của đoạn này sang đoạn khác. Bạn hãy tải cả hai tệp về và so trực tiếp.",
  "txn.tools.deleteConfirm":
    "Xoá các tệp đã lưu của lượt chạy này? Không khôi phục được — lượt chạy vẫn nằm trong lịch sử.",
  "txn.tools.units": "· {count} nguồn",
  "txn.tools.shortfall": "{count} chưa trừ — số dư không đủ",

  // --- chuyển ngôn ngữ ---
  "lang.label": "Ngôn ngữ",
  "lang.en": "English",
  "lang.vi": "Tiếng Việt",
};
