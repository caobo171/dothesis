# Cài đặt / Install

Skill này là Markdown thuần, chạy được với bất kỳ agent nào đọc được skill. Chọn
một trong ba cách dưới đây.

This skill is plain Markdown and works with any agent that reads skills. Pick one
of the three paths below.

## 1. claude.ai hoặc Claude Desktop

Settings → Skills → Upload a skill, rồi chọn file `dothesis-humanizer.zip` vừa
tải về. Không cần giải nén.

On claude.ai or Claude Desktop: Settings → Skills → Upload a skill, then pick the
`dothesis-humanizer.zip` you downloaded. Do not unzip it first.

## 2. Claude Code

Giải nén rồi chép cả thư mục vào `~/.claude/skills/`:

```bash
unzip dothesis-humanizer.zip -d ~/.claude/skills/
```

Kết quả phải là `~/.claude/skills/dothesis-humanizer/SKILL.md`. Bỏ `~` và dùng
`.claude/skills/` trong thư mục dự án nếu chỉ muốn cài cho một dự án.

The result must be `~/.claude/skills/dothesis-humanizer/SKILL.md`. Use
`.claude/skills/` inside a project instead if you only want it there.

## 3. Claude Code, dạng plugin

Giải nén ra một thư mục bất kỳ, rồi trong Claude Code:

```text
/plugin marketplace add /đường/dẫn/tới/dothesis-humanizer
/plugin install dothesis-humanizer@dothesis
```

## Agent khác / Other agents

Chép `SKILL.md` vào thư mục skill của agent đó. Nhớ chép kèm `references/` và
`scripts/` — phần kiểm tra `frozen_check.py` là thứ giữ cho số liệu không bị đổi,
và nó chỉ dùng thư viện chuẩn của Python, không cần cài gì thêm.

Copy `SKILL.md` into that agent's skills folder. Bring `references/` and
`scripts/` with it: `frozen_check.py` is what stops a rewrite moving a number,
and it is standard-library Python with nothing to install.

## Dùng nó / Using it

```text
Viết lại đoạn này cho tự nhiên hơn, giữ nguyên số liệu:
[dán đoạn văn]
```

Skill sẽ hỏi bạn khoảng 150 chữ do chính bạn viết, trước khi dùng AI. Đó là thứ
quyết định kết quả, không phải câu lệnh. Không có nó thì bản viết lại yếu hơn
nhiều, và skill sẽ nói thẳng điều đó.

It will ask you for about 150 words you wrote yourself, before you used AI. That
sample is what decides the result, not the prompt. Without one the rewrite is
much weaker, and the skill says so rather than pretending otherwise.

Bản đầy đủ, chạy trên cả luận văn `.docx` giữ nguyên bảng biểu và định dạng:
https://dothesis.info
