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
  "new.chip.fresh": "Mới bắt đầu",
  "new.chip.fresh.text":
    "Mình mới bắt đầu — có ý tưởng đề tài nhưng chưa viết gì cả.",

  // --- thanh bên dự án ---
  "sidebar.projectCredits": "Tổng credits dự án",
  "sidebar.threads": "Cuộc trò chuyện",
  "sidebar.newThread": "Cuộc trò chuyện mới",
  "sidebar.project": "Dự án",

  // --- chuyển ngôn ngữ ---
  "lang.label": "Ngôn ngữ",
  "lang.en": "English",
  "lang.vi": "Tiếng Việt",
};
