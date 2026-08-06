"""The downloadable humanizer skill must work outside this repo.

It ships to strangers who upload it to claude.ai, so the two failure modes that
matter are: the script does not run at all (a bad import, a syntax error), and
the gate is wrong (it passes a rewrite that lost a p-value). Both are cheap to
test and expensive to ship.

The script is a PORT, not an import — it must stay standard-library-only, so
these tests load it by path rather than through the package.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parents[1] / "skills-public" / "dothesis-humanizer"
SCRIPT = SKILL / "scripts" / "frozen_check.py"


@pytest.fixture(scope="module")
def fc():
    spec = importlib.util.spec_from_file_location("frozen_check", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --- the package itself ---------------------------------------------------

def test_the_skill_has_the_files_claude_expects():
    md = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    assert md.startswith("---"), "SKILL.md needs YAML frontmatter"
    assert "name: dothesis-humanizer" in md
    assert "description:" in md
    assert SCRIPT.exists()
    assert (SKILL / "references" / "anchors.md").exists()


def test_the_script_imports_nothing_outside_the_standard_library():
    """It runs on someone else's machine with no install step."""
    src = SCRIPT.read_text(encoding="utf-8")
    imports = [ln.strip() for ln in src.splitlines()
               if ln.startswith(("import ", "from ")) and "__future__" not in ln]
    allowed = {"json", "re", "sys", "unicodedata", "collections"}
    for line in imports:
        mod = line.split()[1].split(".")[0]
        assert mod in allowed, f"non-stdlib import in a shipped script: {line}"


def test_the_script_runs_end_to_end(tmp_path):
    a = tmp_path / "a.txt"; b = tmp_path / "b.txt"
    a.write_text("Kết quả tại Bảng 4.3 cho thấy β = 0,412 với p = 0,003 "
                 "(Nguyễn, 2019).", encoding="utf-8")
    b.write_text("Bảng 4.3 cho thấy β = 0,412, p = 0,003, đúng như Nguyễn "
                 "(2019) đã nêu.", encoding="utf-8")
    r = subprocess.run([sys.executable, str(SCRIPT), str(a), str(b)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "PASS" in r.stdout


def test_a_bad_rewrite_exits_nonzero(tmp_path):
    """The exit code is the whole point — it is what a caller can branch on."""
    a = tmp_path / "a.txt"; b = tmp_path / "b.txt"
    a.write_text("Hệ số đạt 0,871 trên mẫu 245 quan sát.", encoding="utf-8")
    b.write_text("Hệ số đạt mức cao trên mẫu 245 quan sát.", encoding="utf-8")
    r = subprocess.run([sys.executable, str(SCRIPT), str(a), str(b)],
                       capture_output=True, text=True)
    assert r.returncode == 1
    assert "0,871" in r.stdout


# --- the gate -------------------------------------------------------------

def test_a_pure_prose_rewrite_passes(fc):
    src = ("Kết quả phân tích tại Bảng 4.3 cho thấy Chất lượng dịch vụ có tác "
           "động tích cực đến Sự hài lòng (β = 0,412; p = 0,003).")
    good = ("Bảng 4.3 cho thấy Chất lượng dịch vụ tác động tích cực tới Sự hài "
            "lòng (β = 0,412; p = 0,003).")
    assert fc.check(src, good)["ok"]


def test_a_rounded_p_value_is_caught(fc):
    assert not fc.check("với p = 0,032", "với p = 0,03")["ok"]


def test_an_invented_number_is_caught(fc):
    r = fc.check("Nhân tố này giải thích phần lớn phương sai.",
                 "Nhân tố này giải thích 67,4% phương sai.")
    assert not r["ok"] and r["added"]


def test_a_citation_may_move_between_forms(fc):
    """Parenthetical ↔ narrative is an ordinary writing choice, not a violation."""
    assert fc.check("Kết quả phù hợp (Nguyễn, 2019).",
                    "Nguyễn (2019) đã cho thấy kết quả tương tự.")["ok"]


def test_a_dropped_citation_is_caught(fc):
    r = fc.check("Kết quả phù hợp với lý thuyết (Nguyễn, 2019).",
                 "Kết quả phù hợp với lý thuyết.")
    assert not r["ok"] and r["missing"]


def test_a_translation_is_caught(fc):
    """The failure that shipped to a real student: every number and citation
    preserved, and the whole dissertation in the wrong language."""
    en = ("Prior research has confirmed that leadership matters in hospitality, "
          "but three limitations restrict what it can tell a hotel manager "
          "(Bass, 1985).")
    vi = ("Các nghiên cứu trước đây đã khẳng định vai trò của lãnh đạo trong "
          "lĩnh vực khách sạn, nhưng ba hạn chế khiến kết quả chưa đủ để hướng "
          "dẫn nhà quản lý khách sạn (Bass, 1985).")
    r = fc.check(en, vi)
    assert not r["ok"] and r["language_changed"]


def test_an_english_paragraph_citing_a_vietnamese_author_is_still_english(fc):
    assert fc.detect_language(
        "The sample was drawn from hotels in Hanoi and analysed by "
        "Nguyễn (2019), whose instrument this study adapts.") == "en"


def test_a_foreign_script_is_caught(fc):
    r = fc.check("Kết quả đánh giá và mua sắm đều tăng.",
                 "Kết quả đánh giá तथा mua sắm đều tăng.")
    assert not r["ok"] and r["foreign_scripts"]


def test_greek_notation_is_not_a_foreign_script(fc):
    """β and α are ordinary notation in a statistics chapter."""
    assert fc.check("Hệ số hồi quy đạt 0,412 trong mô hình đề xuất.",
                    "Hệ số β đạt 0,412 trong mô hình đề xuất.")["foreign_scripts"] == []
