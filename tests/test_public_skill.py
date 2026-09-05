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
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills-public" / "dothesis-humanizer"
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


# --- rhythm: the half the first version shipped without --------------------
#
# The skill originally carried the frozen gate and none of the burstiness work,
# so a user could follow it, get PASS, and hand back prose MORE machine-even
# than they wrote — the exact failure the engine had until it was measured.

def test_burstiness_separates_a_metronome_from_real_rhythm(fc):
    flat = ("Nghiên cứu khảo sát nhân viên khách sạn ở Hà Nội. "
            "Dữ liệu được thu thập trong khoảng ba tháng. "
            "Phân tích thực hiện bằng phần mềm SmartPLS. "
            "Kết quả cho thấy giả thuyết được chấp nhận.")
    bursty = ("Nghiên cứu khảo sát nhân viên khách sạn ở Hà Nội, dữ liệu thu "
              "thập trong khoảng ba tháng và phân tích bằng SmartPLS. "
              "Giả thuyết được chấp nhận. Không có ngoại lệ.")
    assert fc.burstiness(flat) < 0.35 < fc.burstiness(bursty)


def test_a_flatter_rewrite_fails_even_when_nothing_was_broken(fc, tmp_path):
    """PASS on content and FAIL overall — the trap the first version had."""
    bursty = ("Mô hình được kiểm định bằng SmartPLS với 5000 lần lặp, và kết "
              "quả cho thấy các giả thuyết đều được ủng hộ. Không có ngoại lệ. "
              "Dữ liệu sạch.")
    flat = ("Mô hình được kiểm định bằng SmartPLS với 5000 lần lặp. "
            "Kết quả cho thấy các giả thuyết đều được ủng hộ. "
            "Dữ liệu thu được là hoàn toàn sạch sẽ.")
    r = fc.check(bursty, flat)
    assert r["missing"] == [] and r["added"] == []   # content is intact
    assert r["flatter_than_original"] is True
    assert r["ok"] is False                          # and it still fails
    assert r["rhythm"]["after"] < r["rhythm"]["before"]

    a = tmp_path / "a.txt"; b = tmp_path / "b.txt"
    a.write_text(bursty, encoding="utf-8"); b.write_text(flat, encoding="utf-8")
    res = subprocess.run([sys.executable, str(SCRIPT), str(a), str(b)],
                         capture_output=True, text=True)
    assert res.returncode == 1
    assert "machine-even" in res.stdout


def test_the_rhythm_verdict_is_relative_not_an_absolute_bar(fc):
    """A writer whose prose already varies must not have it replaced by a
    flatter rewrite that still clears a fixed threshold."""
    already_good = ("Kết quả rất rõ ràng. Mô hình được kiểm định bằng SmartPLS "
                    "với 5000 lần lặp và toàn bộ giả thuyết đều được ủng hộ ở "
                    "mức ý nghĩa thông thường. Không có ngoại lệ nào.")
    assert fc.burstiness(already_good) > fc.CV_TARGET
    slightly_worse = ("Kết quả rất rõ ràng và đầy đủ. Mô hình được kiểm định "
                      "bằng SmartPLS với 5000 lần lặp lại. Toàn bộ giả thuyết "
                      "đều được ủng hộ ở mức ý nghĩa.")
    assert fc.check(already_good, slightly_worse)["flatter_than_original"] is True


def test_scan_names_the_paragraphs_worth_rewriting(fc):
    flat = ("Một hai ba bốn năm sáu bảy tám. Một hai ba bốn năm sáu bảy chín. "
            "Một hai ba bốn năm sáu bảy mười.")
    varied = ("Ngắn thôi. Câu này dài hơn hẳn so với câu trước đó và tiếp tục "
              "kéo dài thêm một đoạn nữa để tạo nhịp. Rồi lại ngắn.")
    r = fc.scan(flat + "\n\n" + varied)
    assert r["measured"] == 2 and r["flat"] == 1
    assert [p["index"] for p in r["paragraphs"] if p["flat"]] == [1]


def test_scan_runs_from_the_command_line(tmp_path):
    f = tmp_path / "draft.txt"
    f.write_text("Một hai ba bốn năm sáu bảy tám. Một hai ba bốn năm sáu bảy "
                 "chín. Một hai ba bốn năm sáu bảy mười.", encoding="utf-8")
    r = subprocess.run([sys.executable, str(SCRIPT), "--scan", str(f)],
                       capture_output=True, text=True)
    assert r.returncode == 0
    assert "machine-even" in r.stdout


def test_the_skill_documents_the_measurement_and_the_ladder():
    """The numbers are the argument; without them "vary your sentences" is the
    same advice everyone else gives."""
    md = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    assert "0.247" in md and "0.473" in md
    assert "RESTRUCTURE" in md
    assert "--scan" in md


# --- the pattern library --------------------------------------------------
#
# The skill tells the agent HOW to rewrite and WHEN TO STOP. The pattern library
# is the third question — what is actually wrong with this passage — and it is
# the half that has to be named, numbered and guarded, because an unguarded
# pattern list turns into a search-and-destroy pass over prose that was fine.

PATTERNS = SKILL / "references" / "ai-patterns.md"
INTERNAL = ROOT / "skills" / "dothesis-humanize" / "references" / "ai-patterns.md"


def _pattern_sections(text: str) -> list[tuple[int, str]]:
    """(number, body) for each `### N. Name` block."""
    parts = re.split(r"(?m)^### (\d+)\. ", text)[1:]
    return [(int(parts[i]), parts[i + 1]) for i in range(0, len(parts), 2)]


def test_the_pattern_library_ships_and_the_skill_points_at_it():
    assert PATTERNS.exists(), "the reference the skill sends the agent to must ship"
    assert "references/ai-patterns.md" in (SKILL / "SKILL.md").read_text(encoding="utf-8")


def test_the_patterns_are_numbered_contiguously_from_one():
    """A gap or a repeat breaks every citation of the form "this trips 7 and 23"."""
    numbers = [n for n, _ in _pattern_sections(PATTERNS.read_text(encoding="utf-8"))]
    assert numbers, "no numbered patterns found"
    assert numbers == list(range(1, len(numbers) + 1)), numbers


def test_the_pattern_count_matches_what_the_copy_promises():
    """The count is quoted in both SKILL.md files and on the web download card
    (`tools.skill.includes`, vi and en). Adding a pattern means editing four
    other places, and this is the tripwire that says so."""
    text = PATTERNS.read_text(encoding="utf-8")
    assert len(_pattern_sections(text)) == 32
    assert "thirty-two" in (SKILL / "SKILL.md").read_text(encoding="utf-8")
    assert "thirty-two" in (
        ROOT / "skills" / "dothesis-humanize" / "SKILL.md").read_text(encoding="utf-8")


def test_every_pattern_says_when_to_leave_it_alone():
    """The guard is the point. Without it this is a list of things to delete,
    and the measured failure mode of this whole feature is a rewrite that
    "fixed" prose which was already the student's own."""
    missing = [
        n for n, body in _pattern_sections(PATTERNS.read_text(encoding="utf-8"))
        if "**Leave it when:**" not in body
    ]
    assert not missing, f"patterns with no guard: {missing}"


def test_the_library_keeps_the_thesis_specific_inversions():
    """Two rules a general-purpose humanizer gets backwards for a thesis: a
    construct keeps ONE name, and "đáng kể"/significant may be a technical term."""
    text = PATTERNS.read_text(encoding="utf-8")
    assert "What not to flag" in text
    assert "đáng kể" in text


def test_every_example_in_the_library_passes_the_gate_it_teaches(fc):
    """The examples are the instruction. A before/after pair that quietly drops
    a p-value or invents a citation teaches exactly the failure frozen_check.py
    exists to catch, and it teaches it more strongly than the prose above it."""
    field = re.compile(
        r"(?ms)^\*\*(Before|After):\*\*\s+(.*?)(?=\n\*\*|\n### |\n## |\Z)")
    for number, body in _pattern_sections(PATTERNS.read_text(encoding="utf-8")):
        found = field.findall(body)
        pairs = [(found[i][1], found[i + 1][1]) for i in range(0, len(found) - 1, 2)]
        assert pairs, f"pattern {number} has no before/after pair"
        for before, after in pairs:
            r = fc.check(before.strip(), after.strip())
            assert not r["missing"], f"pattern {number} drops {r['missing']}"
            assert not r["added"], f"pattern {number} invents {r['added']}"
            assert not r["language_changed"], f"pattern {number} translates"


def test_the_internal_skill_carries_the_same_library():
    """Two copies exist because a symlink does not survive the zip. Nothing but
    a test stops them drifting."""
    assert INTERNAL.exists()
    assert INTERNAL.read_bytes() == PATTERNS.read_bytes()


# --- the shipped package --------------------------------------------------

ZIP = ROOT / "web" / "public" / "skills" / "dothesis-humanizer.zip"


@pytest.fixture(scope="module")
def build():
    path = ROOT / "scripts" / "build_public_skill.py"
    spec = importlib.util.spec_from_file_location("build_public_skill", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_shipped_zip_matches_its_sources(build):
    """The zip is a build artifact committed to git, so it can go stale in a
    commit that edits the skill and forgets to rebuild. Nothing would say so."""
    expected = {str(arc): path.read_bytes() for arc, path in build.source_files()}
    with zipfile.ZipFile(ZIP) as z:
        actual = {name: z.read(name) for name in z.namelist()}
    assert actual == expected, "run: python scripts/build_public_skill.py"


def test_the_zip_carries_no_build_junk(build):
    """A stray __pycache__ ships someone's local bytecode to a stranger."""
    with zipfile.ZipFile(ZIP) as z:
        names = z.namelist()
    assert not [n for n in names if "__pycache__" in n or n.endswith(".pyc")]


def test_the_build_syncs_the_library_into_the_internal_skill(tmp_path):
    public = tmp_path / "skills-public" / "dothesis-humanizer" / "references"
    public.mkdir(parents=True)
    (public / "ai-patterns.md").write_text("# patterns\n", encoding="utf-8")

    build_mod_synced = tmp_path / "skills" / "dothesis-humanize" / "references"
    assert not build_mod_synced.exists()

    import importlib.util as _u
    spec = _u.spec_from_file_location(
        "bps_tmp", ROOT / "scripts" / "build_public_skill.py")
    mod = _u.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.sync_internal(tmp_path)

    assert (build_mod_synced / "ai-patterns.md").read_text(
        encoding="utf-8") == "# patterns\n"


def test_the_package_manifests_agree_with_the_skill():
    """Version parity across three files, blader's rule: a plugin that reports a
    version the skill does not have is worse than no version at all."""
    plugin = json.loads((SKILL / ".claude-plugin" / "plugin.json").read_text())
    market = json.loads((SKILL / ".claude-plugin" / "marketplace.json").read_text())
    md = (SKILL / "SKILL.md").read_text(encoding="utf-8")

    assert plugin["name"] == "dothesis-humanizer"
    assert [p["name"] for p in market["plugins"]] == ["dothesis-humanizer"]
    version = re.search(r'(?m)^\s+version:\s*"([^"]+)"', md)
    assert version and version.group(1) == plugin["version"]


def test_the_install_paths_are_documented_for_a_stranger():
    install = (SKILL / "INSTALL.md").read_text(encoding="utf-8")
    for path in ("claude.ai", "~/.claude/skills", "plugin"):
        assert path in install
