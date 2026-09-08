"""report + the CLI wiring."""
import csv
import json
import os

import pytest

from app.blog.content import cli, report


@pytest.fixture(autouse=True)
def _bind_db():
    """No database in the content engine. See test_blog_content_expand.py."""
    yield


def _tsv(path, header, rows):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter="\t", lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)
    return str(path)


def _fixture_run(tmp_path):
    backlog = _tsv(tmp_path / "backlog.tsv",
                   ["priority", "slug", "focus_keyword", "search_volume",
                    "secondary_keywords", "category", "archetype", "family",
                    "sibling_slugs", "competitor_urls", "gate_status"],
                   [[1, "cronbach-alpha", "cronbach alpha", 1300, "", "spss",
                     "term-la-gi", "reliability", "", "", "measured"],
                    [2, "bootstrapping-smartpls", "bootstrapping smartpls", 90, "",
                     "smartpls", "smartpls-howto", "estimation", "", "",
                     "family-inferred"]])  # pre-2026-09-08 spelling of `unmeasured`
    seed_dir = tmp_path / "posts"
    (seed_dir / "rejected").mkdir(parents=True)
    (seed_dir / "0001-cronbach-alpha.json").write_text(
        json.dumps({"slug": "cronbach-alpha"}), encoding="utf-8")
    (seed_dir / "rejected" / "0002-bootstrapping-smartpls.json").write_text(
        "{}", encoding="utf-8")
    log = _tsv(tmp_path / "write-log.tsv",
               ["slug", "status", "attempts", "prompt_tokens", "output_tokens",
                "usd", "seconds", "failures"],
               [["cronbach-alpha", "ok", 1, 8000, 4000, "0.00640", "12.1", ""],
                ["bootstrapping-smartpls", "rejected", 2, 16000, 8000, "0.01280",
                 "22.4", "no table"]])
    return backlog, str(seed_dir), log


def test_report_counts_rows_seeds_spend_and_the_shortfall(tmp_path, capsys):
    backlog, seed_dir, log = _fixture_run(tmp_path)
    summary = report.run(backlog_path=backlog, seed_dir=seed_dir, log_path=log)

    assert summary["backlog_rows"] == 2
    assert summary["volume_total"] == 1390
    # Read back through the alias: the backlog row above says `family-inferred`.
    assert summary["unmeasured"] == 1
    assert summary["per_category"] == {"spss": 1, "smartpls": 1}
    assert summary["per_archetype"] == {"term-la-gi": 1, "smartpls-howto": 1}
    assert summary["seeds_written"] == 1
    assert summary["seeds_rejected"] == 1
    assert summary["usd"] == pytest.approx(0.0192)
    assert summary["statuses"] == {"ok": 1, "rejected": 1}
    assert summary["ceiling_shortfall"] == 998

    out = capsys.readouterr().out
    assert "backlog:" in out and "spend:" in out and "target:" in out
    assert "the gate stopped cutting" in out


def test_report_survives_an_empty_run(tmp_path, capsys):
    summary = report.run(backlog_path=str(tmp_path / "nope.tsv"),
                         seed_dir=str(tmp_path / "nope"),
                         log_path=str(tmp_path / "nope.log"))
    assert summary["backlog_rows"] == 0 and summary["seeds_written"] == 0
    assert "target:" in capsys.readouterr().out


# --------------------------------------------------------------------- cli


def test_cli_expand_writes_candidates(tmp_path, capsys):
    axes = os.path.join(os.path.dirname(__file__), "fixtures", "blog", "content", "axes")
    out = tmp_path / "candidates.tsv"
    assert cli.main(["expand", "--axes", axes, "--out", str(out)]) == 0
    assert out.is_file()
    assert "4 candidates" in capsys.readouterr().out


def test_cli_qa_returns_the_gate_exit_code(tmp_path):
    base = os.path.join(os.path.dirname(__file__), "fixtures", "blog", "content")
    assert cli.main(["qa", os.path.join(base, "passing")]) == 0
    assert cli.main(["qa", os.path.join(base, "failing")]) == 1


def test_cli_report_runs(tmp_path, capsys):
    backlog, seed_dir, log = _fixture_run(tmp_path)
    assert cli.main(["report", "--backlog", backlog, "--seed-dir", seed_dir,
                     "--log", log]) == 0
    assert "backlog:" in capsys.readouterr().out


def test_cli_exposes_every_command():
    parser = cli.build_parser()
    actions = [a for a in parser._actions if a.dest == "command"]
    assert set(actions[0].choices) == {"expand", "gate", "plan", "write", "qa",
                                       "images", "report"}
