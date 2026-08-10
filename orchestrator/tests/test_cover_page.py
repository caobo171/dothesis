"""The cover page says what the thesis is, or says nothing.

Every export shipped a cover page reading:

    None
    2026

`_title_block_frontmatter_lines` guards with `if not t: return []` and computes
`t = esc(title)` where esc does `str(s)` — and `str(None)` is "None", five
truthy characters. The guard could never fire. And `title` is an optional
parameter that not one of run_export's seven callers ever passed, so it was
None every single time, on a project whose m1_topic.research_title had been
correctly backfilled all along.

The rest of the cover machinery was already built and never fed: the engine
constructs PDFGenerationOptions from the markdown's YAML metadata, and
docx_post_processor turns that into the institution block above the title and
the degree/supervisor block below the date.
"""
from orchestrator.tools.m5_writing import (
    _COVER_FIELDS, _title_block_frontmatter_lines, cover_fields,
)


_TITLE = "The Impact of KOL Credibility on Purchase Behaviour"


def _fm(title, language="en", cover=None):
    return _title_block_frontmatter_lines(title, language, cover)


# --- the None regression ------------------------------------------------------

def test_no_title_emits_no_title_block():
    """"None" is not a thesis title."""
    for empty in (None, "", "   "):
        assert _fm(empty) == [], f"{empty!r} produced a title block"


def test_a_real_title_is_emitted_with_a_date():
    """docx_post_processor._find_title_block needs both to build a cover."""
    lines = _fm(_TITLE)
    assert lines[0] == f'title: "{_TITLE}"'
    assert lines[1].startswith("date:")


def test_a_vietnamese_cover_dates_in_vietnamese():
    assert 'date: "Năm ' in _fm(_TITLE, "vi")[1]


def test_quotes_in_a_title_do_not_break_the_yaml():
    lines = _fm('A study of "influence" \\ trust')
    assert lines[0] == 'title: "A study of \\"influence\\" \\\\ trust"'


# --- cover fields -------------------------------------------------------------

def test_every_declared_field_reaches_the_frontmatter():
    cover = {k: f"v-{k}" for k in _COVER_FIELDS}
    lines = _fm(_TITLE, "en", cover)
    for k in _COVER_FIELDS:
        assert f'{k}: "v-{k}"' in lines, f"{k} never reached the cover"


def test_unknown_keys_are_not_smuggled_into_the_yaml():
    out = cover_fields({"m1_topic": {"cover": {"author": "A", "evil": "x"}}})
    assert out == {"author": "A"}


def test_blank_values_are_dropped_rather_than_rendered_empty():
    cover = {"author": "  ", "institution": None, "advisor": "TS. A"}
    out = cover_fields({"m1_topic": {"cover": cover}})
    assert out == {"advisor": "TS. A"}


def test_department_falls_back_to_the_m1_field():
    out = cover_fields({"m1_topic": {"field": "Marketing"}})
    assert out["department"] == "Marketing"


def test_an_explicit_department_wins_over_the_derived_one():
    out = cover_fields({"m1_topic": {"field": "Marketing",
                                     "cover": {"department": "School of Business"}}})
    assert out["department"] == "School of Business"


def test_the_project_type_line_follows_the_language():
    en = cover_fields({"m1_topic": {"research_type": "quantitative"}}, "en")
    vi = cover_fields({"m1_topic": {"research_type": "quantitative"}}, "vi")
    assert en["project_type"] == "A Master's Thesis"
    assert vi["project_type"] == "Luận văn Thạc sĩ"


def test_nothing_about_the_student_is_ever_guessed():
    """A plausible wrong university on a cover page is worse than a blank one."""
    out = cover_fields({"m1_topic": {"field": "Marketing", "research_type": "quantitative"}})
    for never in ("author", "institution", "advisor", "student_id", "degree"):
        assert never not in out


def test_an_empty_store_is_safe():
    assert cover_fields(None) == {} and cover_fields({}) == {}
    assert cover_fields({"m1_topic": {"cover": "not a dict"}}) == {}
