"""Grep-style guards that the F8 quant-correctness content assets exist and are
wired into the skills that must consult them. These are content invariants, not
behavior — they fail loudly if an asset is renamed/moved and the reference goes
stale (the plan's "keep skill content <-> code in sync" constraint)."""
from pathlib import Path

# repo root: api/tests/ -> api -> repo
ROOT = Path(__file__).resolve().parents[2]


def test_design_test_matrix_exists_and_referenced():
    ref = ROOT / "skills/dothesis-m3-design/references/design-test-matrix.md"
    assert ref.exists()
    body = ref.read_text()
    assert "PLS-SEM" in body and "CB-SEM" in body
    skill = (ROOT / "skills/dothesis-m3-design/SKILL.md").read_text()
    assert "design-test-matrix" in skill


def test_two_register_rule_present():
    skill = (ROOT / "skills/dothesis/SKILL.md").read_text().lower()
    assert "two-register" in skill or "two register" in skill
