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


def test_defense_skill_exists_and_wired():
    # F6: the mock-committee drill skill exists, drives the committee-questions
    # tool, and is routed from the root skill.
    ds = ROOT / "skills/dothesis-defense/SKILL.md"
    assert ds.exists() and "generate_committee_questions" in ds.read_text()
    assert "defense" in (ROOT / "skills/dothesis/SKILL.md").read_text().lower()


def test_support_playbook_exists_and_referenced():
    # The FillForm support synthesis (docs/research/2026-09-10-fillform-support-synthesis.md)
    # is only useful to the agent if the root skill still points at the playbook it produced.
    ref = ROOT / "skills/dothesis/references/support-playbook.md"
    assert ref.exists()
    body = ref.read_text()
    # The six behaviors the playbook exists to carry.
    for marker in (
        "Triage before you advise",
        "picks the software",
        "questionnaire before it is fielded",
        "supervisor outranks you",
        "argument, not a verdict",
        "make the numbers pass",
    ):
        assert marker in body, marker
    skill = (ROOT / "skills/dothesis/SKILL.md").read_text()
    assert "support-playbook" in skill


def test_supervisor_precedence_rule_present():
    # An advisor-approved model outranking the agent's own recommendation is a hard rule,
    # not a tone preference — it must stay in the root skill, next to the feedback loop.
    skill = (ROOT / "skills/dothesis/SKILL.md").read_text()
    assert "Supervisor precedence" in skill


def test_bootstrap_triage_present():
    # Entry focus must be routed by where the student is stuck, not only by which
    # artifacts they uploaded.
    boot = (ROOT / "skills/dothesis-bootstrap/SKILL.md").read_text()
    assert "Step 1b — Triage" in boot
    assert "needs_inferential" in boot and "research_stage" in boot


def test_questionnaire_structural_defects_present():
    ref = (
        ROOT / "skills/dothesis-m3-design/references/questionnaire-quality.md"
    ).read_text()
    assert "Structural defects" in ref
    for marker in (
        "Screening question not isolated",
        "Mixed response formats inside one construct",
        "Fewer than three observed items per construct",
        "A model construct missing from the questionnaire",
        "second-order construct given its own observed items",
        "Naming drift between model and questionnaire",
    ):
        assert marker in ref, marker


def test_keep_it_argument_present():
    # M4 already carries the thresholds; the marginal-number argument is the part a
    # student needs to survive the viva, and the defense drill links to it by name.
    ref = (
        ROOT / "skills/dothesis-m4-analysis/references/output-interpretation.md"
    ).read_text()
    assert "Building the keep-it argument" in ref
    defense = (ROOT / "skills/dothesis-defense/SKILL.md").read_text()
    assert "output-interpretation.md" in defense
