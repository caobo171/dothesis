"""Whole-chapter translation must not cost the student a table or a number.

A preserved Chapter 4 is ~28,000 characters and 17 markdown tables. The editor's
inline translate_selection was never built for that: one call, a prompt that
calls the input "a short selection", and no check on what comes back. The two
ways that fails are both silent — a reflowed table (which is exactly what
preserving the chapter was meant to prevent) and a response cut off partway.

translate_markdown batches on block boundaries and verifies each batch before
accepting it. These tests pin the verification, because it is the part that
decides between a wrong number and a visible untranslated paragraph.
"""
import orchestrator.tools.m5_inline as inline


_TABLE = (
    "## 4.2 Kiểm định EFA\n\n"
    "Bảng 4.5: Chỉ số KMO\n\n"
    "| Chỉ số | Giá trị |\n"
    "|---|---|\n"
    "| Hệ số KMO | 0.843 |\n"
    "| Bartlett Sig. | 0.000 |\n\n"
    "Kết quả cho thấy thang đo đạt yêu cầu."
)


def _run(monkeypatch, fn, text=_TABLE):
    monkeypatch.setattr(inline, "_call_llm", fn)
    return inline.translate_markdown("results", "en", text)


def test_a_clean_translation_is_used(monkeypatch):
    def _ok(prompt):
        body = prompt.split("## Passage", 1)[1].split("## Output", 1)[0].strip()
        return (body.replace("Chỉ số", "Indicator").replace("Giá trị", "Value")
                    .replace("Hệ số KMO", "KMO coefficient").replace("Bảng", "Table"))

    out = _run(monkeypatch, _ok)
    assert "| KMO coefficient | 0.843 |" in out
    assert "Chỉ số" not in out


def test_a_dropped_table_row_is_rejected(monkeypatch):
    """The failure mode that looks like a smaller table instead of an error."""
    def _drops_a_row(prompt):
        body = prompt.split("## Passage", 1)[1].split("## Output", 1)[0].strip()
        return "\n".join(l for l in body.splitlines() if "Bartlett" not in l)

    out = _run(monkeypatch, _drops_a_row)
    assert out == _TABLE, "a table row went missing and the batch was accepted"


def test_an_altered_number_is_rejected(monkeypatch):
    """0.843 → 0.834 is a fabricated finding, not a translation."""
    def _fiddles(prompt):
        body = prompt.split("## Passage", 1)[1].split("## Output", 1)[0].strip()
        return body.replace("0.843", "0.834")

    assert _run(monkeypatch, _fiddles) == _TABLE


def test_a_truncated_response_is_rejected(monkeypatch):
    """The token-ceiling failure: plausible prose that simply stops."""
    def _cuts_off(prompt):
        body = prompt.split("## Passage", 1)[1].split("## Output", 1)[0].strip()
        return body[: len(body) // 2]

    assert _run(monkeypatch, _cuts_off) == _TABLE


def test_a_provider_error_keeps_the_original(monkeypatch):
    assert _run(monkeypatch, lambda p: (_ for _ in ()).throw(RuntimeError("503"))) == _TABLE


def test_an_empty_response_keeps_the_original(monkeypatch):
    assert _run(monkeypatch, lambda p: "   ") == _TABLE


def test_a_bad_batch_does_not_poison_the_good_ones(monkeypatch):
    """Per-batch fallback: one rejected batch stays in the source language, the
    rest of the chapter still gets translated."""
    monkeypatch.setattr(inline, "_TRANSLATE_BATCH_CHARS", 40)
    text = "\n\n".join(f"Đoạn văn số {i} của chương." for i in range(6))

    def _breaks_one(prompt):
        body = prompt.split("## Passage", 1)[1].split("## Output", 1)[0].strip()
        if "số 3" in body:
            return "Paragraph 99 of the chapter."      # number changed → reject
        return body.replace("Đoạn văn số", "Paragraph").replace("của chương", "of the chapter")

    monkeypatch.setattr(inline, "_call_llm", _breaks_one)
    out = inline.translate_markdown("results", "en", text)
    assert "Đoạn văn số 3" in out                      # rejected batch kept verbatim
    assert "Paragraph 0" in out and "Paragraph 5" in out
    assert "Paragraph 99" not in out


# --- batching -----------------------------------------------------------------

def test_a_table_is_never_split_across_batches():
    """Half a table in one request gives the model no header to align to, and it
    will invent one."""
    blocks = inline._batch_blocks(_TABLE, 20)      # budget far below the table
    table = [b for b in blocks if "|---|" in b]
    assert len(table) == 1
    assert table[0].count("\n") == 3               # header, rule, two body rows


def test_batches_reassemble_into_the_original():
    """Nothing is lost or duplicated at the seams — the join in translate_markdown
    is the inverse of the split, at every budget."""
    for budget in (1, 20, 30, 200, 100000):
        assert "\n\n".join(inline._batch_blocks(_TABLE, budget)) == _TABLE


def test_empty_prose_makes_no_call(monkeypatch):
    monkeypatch.setattr(inline, "_call_llm",
                        lambda p: (_ for _ in ()).throw(AssertionError("called")))
    assert inline.translate_markdown("results", "en", "   ") == "   "
