"""What an unattended run is told about the student's uploaded files.

The interactive surface prefixes a turn with `[ATTACHED] uploads/…` and the
system prompt (agent/runtime.py) tells the agent what to do with that line.
A headless run had no equivalent: its kickoff said "reconstruct missing modules
from what already exists" and never mentioned that a file existed at all.

On a measured run that cost the student the whole analysis chapter. Their
uploaded results chapter — eleven SmartPLS tables, already transcribed into
uploads/…docx.txt — sat unread while M4 reported it had no data and flagged the
same blocker seven times.
"""
from __future__ import annotations

from app.headless_entry import kickoff_prompt


def test_a_run_with_no_uploads_says_nothing_extra(tmp_path):
    assert "[ATTACHED]" not in kickoff_prompt(tmp_path)


def test_the_uploaded_files_are_named_in_the_wire_format_the_agent_knows(tmp_path):
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    (uploads / "Results.docx").write_bytes(b"x")
    (uploads / "Results.docx.txt").write_text("| AVE | 0.743 |", encoding="utf-8")

    prompt = kickoff_prompt(tmp_path)

    assert "[ATTACHED] uploads/Results.docx" in prompt
    # The extracted sidecar is not a second attachment. The system prompt
    # already tells the agent to read `<file>.txt` for the text.
    assert "uploads/Results.docx.txt" not in prompt


def test_several_uploads_are_listed_in_one_line(tmp_path):
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    (uploads / "data.csv").write_text("a,b", encoding="utf-8")
    (uploads / "Results.docx").write_bytes(b"x")

    line = next(ln for ln in kickoff_prompt(tmp_path).splitlines()
                if ln.startswith("[ATTACHED]"))

    assert line == "[ATTACHED] uploads/Results.docx | uploads/data.csv"


def test_the_run_is_told_to_use_them_before_asking_for_anything(tmp_path):
    """A blocker the student cannot see is worse than no blocker: the run stops
    on 'no data' while their data is on disk. Naming the files is not enough if
    nothing says to read them first."""
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    (uploads / "Results.docx").write_bytes(b"x")

    prompt = kickoff_prompt(tmp_path)

    assert "before" in prompt.lower()
    assert "already-computed" in prompt or "already computed" in prompt


def test_build_artifacts_are_not_offered_as_attachments(tmp_path):
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    (uploads / ".DS_Store").write_bytes(b"x")
    (uploads / "Results.docx").write_bytes(b"x")

    prompt = kickoff_prompt(tmp_path)

    assert ".DS_Store" not in prompt
    assert "uploads/Results.docx" in prompt
