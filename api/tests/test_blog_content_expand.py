"""expand: axis TSV -> candidates.tsv, and the committed axis files themselves."""
import csv
import os

import pytest

from app.blog import content
from app.blog.content import expand

# The content engine talks to no database. Override the session-wide autouse
# fixture from conftest.py so these tests do not pay for (or depend on) a
# Postgres testcontainer.
@pytest.fixture(autouse=True)
def _bind_db():
    yield


FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures", "blog", "content")
AXIS_FIXTURES = os.path.join(FIXTURES, "axes")


def test_load_axis_file_reads_every_column():
    rows = expand.load_axis_file(os.path.join(AXIS_FIXTURES, "demo-axis.tsv"))
    assert [r.unit for r in rows] == ["cronbach-alpha", "efa"]
    first = rows[0]
    assert first.axis == "demo-axis"
    assert first.display == "cronbach alpha"
    assert first.templates == ["{display} là gì", "{display} trong spss"]
    assert (first.category, first.archetype, first.family) == ("spss", "term-la-gi", "reliability")


def test_expand_crosses_units_with_templates_and_substitutes_both_placeholders():
    rows = expand.load_axes(AXIS_FIXTURES)
    candidates = expand.expand_rows(rows)
    keywords = [c.keyword for c in candidates]
    assert keywords == [
        "cronbach alpha là gì",
        "cronbach alpha trong spss",
        "efa là gì",
        "cách chạy efa trong spss",  # {unit} substitution
    ]
    assert candidates[0].axis == "demo-axis"
    assert candidates[0].family == "reliability"
    assert candidates[3].archetype == "spss-howto"


def test_expand_dedupes_keywords_across_units():
    rows = expand.load_axes(AXIS_FIXTURES)
    # Two units whose templates collide produce one candidate, not two.
    rows.append(expand.AxisRow(axis="demo-axis", unit="cronbach-alpha-2",
                               display="cronbach alpha", templates=["{display} là gì"],
                               category="spss", archetype="term-la-gi", family="reliability"))
    candidates = expand.expand_rows(rows)
    assert [c.keyword for c in candidates].count("cronbach alpha là gì") == 1


def test_run_writes_candidates_tsv_and_returns_axis_counts(tmp_path):
    out = tmp_path / "candidates.tsv"
    counts = expand.run(axes_dir=AXIS_FIXTURES, out_path=str(out))
    assert counts == {"demo-axis": 4}
    with open(out, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh, delimiter="\t"))
    assert len(rows) == 4
    assert set(rows[0]) == {"keyword", "axis", "unit", "family", "category", "archetype"}
    assert rows[0]["keyword"] == "cronbach alpha là gì"


def test_committed_axis_files_are_well_formed():
    """Every shipped axis row must name a real category and a real archetype.

    The axis files are hand-edited from here on, so this is the guard against a
    typo becoming 600 pages in the wrong category.
    """
    rows = expand.load_axes(content.axes_dir())
    assert len(rows) >= 600, "the nine axes should carry about 640 units"
    for row in rows:
        assert row.category in expand.CATEGORY_SLUGS, f"{row.unit}: bad category {row.category}"
        assert row.archetype in expand.ARCHETYPES, f"{row.unit}: bad archetype {row.archetype}"
        assert row.templates, f"{row.unit}: no templates"
        assert row.family, f"{row.unit}: no family"
        for tpl in row.templates:
            assert "{display}" in tpl or "{unit}" in tpl, f"{row.unit}: template {tpl!r}"
    axes = {r.axis for r in rows}
    assert len(axes) == 9, f"expected nine axis files, found {sorted(axes)}"
