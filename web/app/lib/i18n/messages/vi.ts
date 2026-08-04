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
  "new.back": "Về trang chủ",
  "new.title": "Phân tích luận văn của bạn",
  "new.placeholder":
    "Cho mình biết bạn đang có gì — bản nháp, tài liệu, dữ liệu, hay chỉ mới có ý tưởng.",
  "new.attach": "Đính kèm tệp",
  "new.analyze": "Phân tích",
  "new.analyzing": "Đang phân tích…",
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

  // --- tên các module — dùng chung ở dashboard, header chat và danh sách luận văn ---
  "module.M1": "Xác định đề tài",
  "module.M2": "Tổng quan tài liệu",
  "module.M3": "Thiết kế nghiên cứu",
  "module.M4": "Phân tích dữ liệu",
  "module.M5": "Viết luận văn",

  // --- trang chủ ---
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
  "home.stat.review": "Cần xem lại",
  "home.stat.reviewOpen": "mục ⚠ đang mở",
  "home.stat.reviewClear": "không có gì cần xem lại",

  "home.theses": "Luận văn của bạn",
  // Tiếng Việt không biến đổi danh từ theo số — hai dòng giống nhau là CỐ Ý.
  "home.thesesCount_one": "{count} luận văn đang làm",
  "home.thesesCount_other": "{count} luận văn đang làm",
  "home.reviewCount_one": "{count} mục cần xem lại",
  "home.reviewCount_other": "{count} mục cần xem lại",
  "home.newThesis": "Luận văn mới",
  "home.empty": "Chưa có luận văn nào. Bấm “Luận văn mới” để bắt đầu.",
  "home.noField": "Chưa chọn lĩnh vực",
  "home.next": "Tiếp theo",
  "home.continue": "Tiếp tục {module}",
  "home.lastTouched": "sửa lần cuối {when}",
  "home.recent": "Hoạt động gần đây",
  "home.flaggedIn": "Được đánh dấu cần xem lại ở",
  "home.workingIn": "Đang làm ở",
  "home.needsReview": "Cần xem lại",
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

  // --- chuyển ngôn ngữ ---
  "lang.label": "Ngôn ngữ",
  "lang.en": "English",
  "lang.vi": "Tiếng Việt",
};
