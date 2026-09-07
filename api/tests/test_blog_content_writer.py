"""writer + prompts: the stubbed model, the repair path, the budget, resume."""
import csv
import json
import os

import pytest

from app.blog.content import llm, prompts, writer
from app.blog.content.plan import BacklogRow

@pytest.fixture(autouse=True)
def _bind_db():
    """No database in the content engine. See test_blog_content_expand.py."""
    yield


TESTS_DIR = os.path.dirname(__file__)
FIXTURES = os.path.join(TESTS_DIR, "fixtures", "blog", "content")
PASSING = os.path.join(FIXTURES, "passing", "0001-cronbach-alpha-la-gi.json")


def good_seed():
    with open(PASSING, encoding="utf-8") as fh:
        return json.load(fh)


def model_payload(**overrides):
    """What the model is contracted to return: the six authored fields."""
    seed = good_seed()
    payload = {k: seed[k] for k in
               ("title", "meta_title", "meta_description", "excerpt", "tags", "body")}
    payload.update(overrides)
    return payload


ROW = BacklogRow(
    priority=7, slug="cronbach-alpha-la-gi", focus_keyword="cronbach alpha",
    search_volume=1300, secondary_keywords=["cronbach alpha là gì"],
    category="spss", archetype="term-la-gi", family="reliability",
    sibling_slugs=["do-tin-cay-thang-do", "phan-tich-efa-trong-spss"],
    competitor_urls=["phantichspss.com:/he-so-cronbach-alpha-la-gi.html"],
    gate_status="measured",
)


class StubModel:
    """Replays a queue of payloads. Records every prompt it was given."""

    def __init__(self, payloads, seconds=1.5):
        self.payloads = list(payloads)
        self.prompts = []
        self.seconds = seconds

    def complete_json(self, prompt):
        self.prompts.append(prompt)
        payload = self.payloads.pop(0) if self.payloads else self.payloads[-1]
        if isinstance(payload, Exception):
            raise payload
        return llm.Completion(text=json.dumps(payload, ensure_ascii=False),
                              prompt_tokens=8000, output_tokens=4000,
                              reasoning_tokens=500, seconds=self.seconds)


def _backlog(tmp_path, rows=(ROW,)):
    path = tmp_path / "backlog.tsv"
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter="\t", lineterminator="\n")
        w.writerow(["priority", "slug", "focus_keyword", "search_volume",
                    "secondary_keywords", "category", "archetype", "family",
                    "sibling_slugs", "competitor_urls", "gate_status"])
        for r in rows:
            w.writerow([r.priority, r.slug, r.focus_keyword, r.search_volume,
                        "; ".join(r.secondary_keywords), r.category, r.archetype,
                        r.family, "; ".join(r.sibling_slugs),
                        "; ".join(r.competitor_urls), r.gate_status])
    return str(path)


def _log_rows(path):
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


# ------------------------------------------------------------------- prompts


def test_preamble_is_built_from_the_skill_files_on_disk():
    preamble = prompts.build_preamble()
    # a distinctive line from each of the three reference files
    assert "The proprietary element" in preamble           # structure.md
    assert "Slop blacklist" in preamble                    # voice.md
    assert "Fornell, C., & Larcker, D. F. (1981)" in preamble  # canonical-sources.md
    assert "M4" in preamble and "/landing" in preamble     # the product block
    assert "fillform.info" in preamble


def test_preamble_fails_loudly_when_the_skill_is_missing(tmp_path):
    with pytest.raises(FileNotFoundError) as err:
        prompts.build_preamble(skills_dir=str(tmp_path))
    assert "the writer's rules come from the skill" in str(err.value)


def test_brief_carries_the_row_and_the_right_skeleton():
    text = prompts.load_skill_files()["structure"]
    brief = prompts.build_brief(ROW, {"do-tin-cay-thang-do": "Độ tin cậy thang đo"}, text)
    assert "cronbach alpha" in brief
    assert "1,300 searches a month" in brief
    assert "cronbach alpha là gì" in brief          # secondary keyword
    assert "/blog/vi/chu-de/spss" in brief          # category route
    assert "/blog/vi/do-tin-cay-thang-do" in brief
    assert "Độ tin cậy thang đo" in brief           # the sibling's title, so links read well
    assert "he so cronbach alpha la gi" in brief    # competitor slug as a question hint
    assert "1800 to 2400" in brief.replace(",", "")
    assert "`term-la-gi`" in brief
    assert "`spss-howto`" not in brief, "only this row's skeleton belongs in the brief"


def test_prompt_says_json_because_json_mode_requires_it():
    prompt = prompts.build_prompt(ROW)
    assert "json" in prompt.lower()
    assert '"body"' in prompt


def test_repair_prompt_names_every_failure_and_carries_the_draft():
    previous = model_payload(meta_description="quá ngắn")
    prompt = prompts.build_repair_prompt(
        ROW, previous, ["meta_description is 8 chars, must be 110 to 170"])
    assert "meta_description is 8 chars" in prompt
    assert "repair it" in prompt
    assert "quá ngắn" in prompt


# ------------------------------------------------------------- the happy path


def test_a_clean_draft_is_written_with_the_pipeline_fields_from_the_row(tmp_path):
    model = StubModel([model_payload()])
    out = tmp_path / "posts"
    summary = writer.run(backlog_path=_backlog(tmp_path), out_dir=str(out), client=model,
                         workers=1)

    assert summary["written"] == 1 and summary["failed"] == 0
    path = out / "0007-cronbach-alpha-la-gi.json"
    assert path.is_file(), "the filename carries the backlog priority"
    seed = json.load(open(path, encoding="utf-8"))
    assert seed["schema"] == "dothesis-blog-seed/1"
    assert seed["slug"] == ROW.slug and seed["category"] == ROW.category
    assert seed["focus_keyword_volume"] == 1300
    assert seed["sibling_slugs"] == ROW.sibling_slugs
    assert seed["gate_status"] == "measured"
    assert seed["images"] == []


def test_the_model_cannot_overwrite_the_pipeline_fields(tmp_path):
    """A drifting model must not be able to change the slug or the category."""
    model = StubModel([model_payload(slug="khac-hoan-toan", category="tin-tuc",
                                     focus_keyword="cai gi do")])
    out = tmp_path / "posts"
    writer.run(backlog_path=_backlog(tmp_path), out_dir=str(out), client=model, workers=1)
    seed = json.load(open(out / "0007-cronbach-alpha-la-gi.json", encoding="utf-8"))
    assert seed["slug"] == "cronbach-alpha-la-gi"
    assert seed["category"] == "spss"
    assert seed["focus_keyword"] == "cronbach alpha"


def test_write_log_carries_every_agreed_column(tmp_path):
    model = StubModel([model_payload()])
    out = tmp_path / "posts"
    writer.run(backlog_path=_backlog(tmp_path), out_dir=str(out), client=model, workers=1)
    rows = _log_rows(tmp_path / "write-log.tsv")
    assert list(rows[0]) == list(writer.LOG_COLUMNS)
    assert rows[0]["slug"] == "cronbach-alpha-la-gi"
    assert rows[0]["status"] == "ok"
    assert rows[0]["attempts"] == "1"
    assert rows[0]["prompt_tokens"] == "8000"
    assert rows[0]["output_tokens"] == "4000"
    assert float(rows[0]["usd"]) == pytest.approx(llm.usd_for(8000, 4000))
    assert float(rows[0]["seconds"]) > 0
    assert rows[0]["failures"] == ""


# ------------------------------------------------------------------- repair


def test_a_failing_draft_gets_exactly_one_repair_call(tmp_path):
    bad = model_payload(meta_description="ngắn quá")
    model = StubModel([bad, model_payload()])
    out = tmp_path / "posts"
    summary = writer.run(backlog_path=_backlog(tmp_path), out_dir=str(out), client=model,
                         workers=1)

    assert summary["repaired"] == 1 and summary["written"] == 0
    assert len(model.prompts) == 2
    assert "previous draft failed the checker" in model.prompts[1]
    assert "meta_description is" in model.prompts[1]
    assert (out / "0007-cronbach-alpha-la-gi.json").is_file()
    assert _log_rows(tmp_path / "write-log.tsv")[0]["status"] == "repaired"


def test_a_second_failure_lands_in_rejected_and_the_run_continues(tmp_path):
    bad = model_payload(body="Quá ngắn để làm một bài viết.")
    model = StubModel([bad, bad])
    out = tmp_path / "posts"
    summary = writer.run(backlog_path=_backlog(tmp_path), out_dir=str(out), client=model,
                         workers=1)

    assert summary["rejected"] == 1
    assert not (out / "0007-cronbach-alpha-la-gi.json").exists()
    assert (out / "rejected" / "0007-cronbach-alpha-la-gi.json").is_file()
    row = _log_rows(tmp_path / "write-log.tsv")[0]
    assert row["status"] == "rejected"
    assert row["attempts"] == "2"
    assert "floor is 1500" in row["failures"]


def test_a_raising_model_is_logged_as_an_error_not_a_crash(tmp_path):
    model = StubModel([RuntimeError("upstream is down")])
    out = tmp_path / "posts"
    summary = writer.run(backlog_path=_backlog(tmp_path), out_dir=str(out), client=model,
                         workers=1)
    assert summary["errors"] == 1 and summary["failed"] == 1
    assert "upstream is down" in _log_rows(tmp_path / "write-log.tsv")[0]["failures"]


# ------------------------------------------------- resume, force, budget, dry run


def test_a_row_whose_seed_exists_is_skipped_and_costs_nothing(tmp_path):
    out = tmp_path / "posts"
    out.mkdir()
    (out / "0007-cronbach-alpha-la-gi.json").write_text("{}", encoding="utf-8")
    model = StubModel([model_payload()])
    summary = writer.run(backlog_path=_backlog(tmp_path), out_dir=str(out), client=model,
                         workers=1)
    assert summary["skipped"] == 1 and summary["planned"] == 0
    assert model.prompts == [], "resume must not pay for a row that is already on disk"


def test_force_rewrites_an_existing_seed(tmp_path):
    out = tmp_path / "posts"
    out.mkdir()
    (out / "0007-cronbach-alpha-la-gi.json").write_text("{}", encoding="utf-8")
    model = StubModel([model_payload()])
    summary = writer.run(backlog_path=_backlog(tmp_path), out_dir=str(out), client=model,
                         workers=1, force=True)
    assert summary["written"] == 1 and summary["skipped"] == 0
    assert json.load(open(out / "0007-cronbach-alpha-la-gi.json", encoding="utf-8"))["slug"]


def test_the_run_stops_when_the_budget_is_crossed(tmp_path):
    rows = [BacklogRow(**{**ROW.__dict__, "priority": i, "slug": f"bai-viet-{i}"})
            for i in range(1, 6)]
    model = StubModel([model_payload() for _ in rows])
    out = tmp_path / "posts"
    # One call costs 8000 in + 4000 out = $0.0064. A $0.01 budget buys two.
    summary = writer.run(backlog_path=_backlog(tmp_path, rows), out_dir=str(out),
                         client=model, workers=1, budget_usd=0.01)
    assert summary["stopped_on_budget"] is True
    assert summary["written"] == 2
    assert len(list(out.glob("*.json"))) == 2


def test_limit_caps_the_number_of_rows(tmp_path):
    rows = [BacklogRow(**{**ROW.__dict__, "priority": i, "slug": f"bai-viet-{i}"})
            for i in range(1, 6)]
    model = StubModel([model_payload() for _ in rows])
    out = tmp_path / "posts"
    summary = writer.run(backlog_path=_backlog(tmp_path, rows), out_dir=str(out),
                         client=model, workers=1, limit=2)
    assert summary["planned"] == 2 and summary["written"] == 2


def test_dry_run_builds_the_prompts_and_writes_nothing(tmp_path, capsys):
    out = tmp_path / "posts"
    summary = writer.run(backlog_path=_backlog(tmp_path), out_dir=str(out), dry_run=True)
    assert summary["planned"] == 1 and summary["usd"] == 0.0
    assert summary["estimated_usd"] > 0
    assert not out.exists()
    assert "dry-run" in capsys.readouterr().out


def test_workers_greater_than_one_still_writes_every_row(tmp_path):
    rows = [BacklogRow(**{**ROW.__dict__, "priority": i, "slug": f"bai-viet-{i}"})
            for i in range(1, 8)]
    model = StubModel([model_payload() for _ in rows])
    out = tmp_path / "posts"
    summary = writer.run(backlog_path=_backlog(tmp_path, rows), out_dir=str(out),
                         client=model, workers=3, budget_usd=100)
    assert summary["written"] == 7
    assert len(list(out.glob("*.json"))) == 7


# ----------------------------------------------------------------- the client


def test_cost_is_the_documented_luna_price():
    assert llm.usd_for(1_000_000, 0) == pytest.approx(0.20)
    assert llm.usd_for(0, 1_000_000) == pytest.approx(1.20)


def test_a_429_is_retried_after_the_header_says_so():
    waits = []

    class Boom(Exception):
        status_code = 429

        class response:  # noqa: N801 - mimics the openai error shape
            headers = {"Retry-After": "7"}

    class FlakyOpenAI:
        def __init__(self):
            self.calls = 0
            self.chat = self

        @property
        def completions(self):
            return self

        def create(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise Boom("rate limited")
            return _fake_completion()

    client = llm.LunaClient(client=FlakyOpenAI(), sleep=waits.append)
    result = client.complete_json("json please")
    assert waits == [7.0], "Retry-After is honoured, not replaced by our own backoff"
    assert result.output_tokens == 4000


def test_a_400_is_not_retried():
    class Bad(Exception):
        status_code = 400

    class AlwaysBad:
        def __init__(self):
            self.calls = 0
            self.chat = self

        @property
        def completions(self):
            return self

        def create(self, **kwargs):
            self.calls += 1
            raise Bad("bad request")

    inner = AlwaysBad()
    with pytest.raises(Bad):
        llm.LunaClient(client=inner, sleep=lambda _: None).complete_json("json")
    assert inner.calls == 1


def test_request_shape_matches_what_gpt_5_6_accepts():
    seen = {}

    class Recorder:
        def __init__(self):
            self.chat = self

        @property
        def completions(self):
            return self

        def create(self, **kwargs):
            seen.update(kwargs)
            return _fake_completion()

    llm.LunaClient(client=Recorder(), model="gpt-5.6-luna").complete_json("say json")
    assert seen["model"] == "gpt-5.6-luna"
    assert seen["response_format"] == {"type": "json_object"}
    assert seen["max_completion_tokens"] == llm.MAX_OUTPUT_TOKENS
    assert "temperature" not in seen, "gpt-5.6-* rejects a non-default temperature"
    assert "max_tokens" not in seen, "gpt-5.6-* rejects max_tokens"


class _Details:
    reasoning_tokens = 500


class _Usage:
    prompt_tokens = 8000
    completion_tokens = 4000
    completion_tokens_details = _Details()


class _Message:
    content = '{"ok": true}'


class _Choice:
    message = _Message()
    finish_reason = "stop"


class _Completion:
    choices = [_Choice()]
    usage = _Usage()


def _fake_completion():
    return _Completion()
