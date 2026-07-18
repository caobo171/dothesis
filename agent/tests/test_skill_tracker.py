"""Gap 3: mechanical skill-read nudge tracker."""
import agent.skill_tracker as st


def setup_function():
    st.reset()


def test_note_read_maps_skill_path_to_module():
    st.arm('p1')
    st.note_read("p1", "/skills/dothesis-m4-analysis/SKILL.md")
    assert not st.should_nudge("p1", "M4")     # read → no nudge
    assert st.should_nudge("p1", "M2")         # unread → nudge once


def test_non_module_skill_ignored():
    st.arm('p1')
    st.note_read("p1", "/skills/dothesis-defense/SKILL.md")
    st.note_read("p1", "/skills/dothesis/SKILL.md")
    assert st.should_nudge("p1", "M4")         # nothing module-relevant was read


def test_nudge_is_once_then_proceeds():
    st.arm('p1')
    assert st.should_nudge("p1", "M4") is True   # first: nudge
    assert st.should_nudge("p1", "M4") is False  # second: proceeds (no deadlock)


def test_read_after_nudge_still_no_nudge():
    st.arm('p1')
    st.should_nudge("p1", "M4")
    st.note_read("p1", "/skills/dothesis-m4-analysis/SKILL.md")
    assert st.should_nudge("p1", "M4") is False


def test_unknown_module_never_nudged():
    st.arm('p1')
    assert st.should_nudge("p1", "MX") is False
    assert st.should_nudge("p1", "defense") is False


def test_isolated_per_project():
    st.arm('pA'); st.arm('pB')
    st.note_read("pA", "/skills/dothesis-m4-analysis/SKILL.md")
    assert st.should_nudge("pB", "M4") is True   # pB has its own state


def test_recording_backend_preserves_semantics():
    class _Inner:
        def read(self, path, offset=0, limit=2000):
            return f"bytes:{path}"
        def other(self):
            return "ok"
    rb = st.RecordingBackend(_Inner(), "p1")
    assert rb.read("/skills/dothesis-m3-design/SKILL.md") == "bytes:/skills/dothesis-m3-design/SKILL.md"
    assert not st.should_nudge("p1", "M3")   # the read was observed
    assert rb.other() == "ok"                # delegation works


def test_not_armed_never_nudges():
    st.reset()
    assert st.should_nudge("unarmed", "M4") is False   # no skill channel → inert
