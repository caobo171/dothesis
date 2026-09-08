"""translate: the stubbed model, the slug rule, resume, and the link pass.

Nothing here calls a model. The client is a stub replaying payloads, which is
also what makes the gate the thing under test: a payload that would fail QA has
to fail here for the same reason and with the same message.
"""
import csv
import json
import os

import pytest

from app.blog.content import llm, prompts, qa, translate


@pytest.fixture(autouse=True)
def _bind_db():
    """No database in the content engine. See test_blog_content_expand.py."""
    yield


TESTS_DIR = os.path.dirname(__file__)
FIXTURES = os.path.join(TESTS_DIR, "fixtures", "blog", "content")
VI_SEED = os.path.join(FIXTURES, "passing", "0001-cronbach-alpha-la-gi.json")
EN_SEED = os.path.join(FIXTURES, "passing-en", "0001-what-is-cronbachs-alpha.json")

# The three source posts every test directory holds. The first is the one being
# translated; the other two exist so the translated body has real siblings to
# link to, the way the Vietnamese bank does.
SRC_SLUGS = ("cronbach-alpha-la-gi", "phan-tich-efa-trong-spss", "do-tin-cay-thang-do")


def _load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _payload(**overrides):
    """What the model is contracted to return, with the source's own hrefs.

    The contract tells the model to copy every link target character for
    character, so a real translation still points at `/blog/vi/...` when it
    reaches the gate. The English exemplar is the English bank as it looks
    *after* the link pass, so the hrefs are put back here.
    """
    seed = _load(EN_SEED)
    body = (seed["body"]
            .replace("(/blog/en/exploratory-factor-analysis-in-spss)",
                     "(/blog/vi/phan-tich-efa-trong-spss)")
            .replace("(/blog/en/sample-size-for-a-thesis-survey)",
                     "(/blog/vi/do-tin-cay-thang-do)")
            .replace("(/blog/en/chu-de/spss)", "(/blog/vi/chu-de/spss)")
            .replace("(/blog/en)", "(/blog/vi)"))
    payload = {k: seed[k] for k in translate.PRODUCED_FIELDS}
    payload["body"] = body
    payload.update(overrides)
    return payload


def _src_dir(tmp_path, slugs=SRC_SLUGS):
    src = tmp_path / "vi"
    src.mkdir()
    base = _load(VI_SEED)
    for i, slug in enumerate(slugs, 1):
        seed = dict(base, slug=slug)
        (src / f"{i:04d}-{slug}.json").write_text(
            json.dumps(seed, ensure_ascii=False), encoding="utf-8")
    return str(src)


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


def _log_rows(path):
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def _run(tmp_path, payloads, **kwargs):
    out = tmp_path / "en"
    src = kwargs.pop("src_dir", None) or _src_dir(tmp_path)
    model = StubModel(payloads)
    summary = translate.run(src_dir=src, out_dir=str(out), client=model, workers=1,
                            **kwargs)
    return summary, model, out, src


# ------------------------------------------------------------------- prompts


def test_the_translate_prompt_carries_the_source_and_the_rules():
    seed = _load(VI_SEED)
    prompt = prompts.build_translate_prompt(seed)
    assert seed["body"][:120] in prompt, "the whole source article is the input"
    assert seed["title"] in prompt
    assert "Slop blacklist" in prompt                       # voice.md, verbatim
    assert "Fornell, C., & Larcker, D. F. (1981)" in prompt  # canonical-sources.md
    assert "et al." in prompt and "và cộng sự" in prompt     # the connector rule
    assert "/blog/vi/" in prompt, "hrefs are copied, the link pass moves them"


def test_the_prompt_quotes_the_three_strings_the_gate_matches():
    """The prompt and the gate read one definition, so they cannot drift."""
    rules = qa.rules_for("en")
    block = prompts.english_rules_block()
    assert f"## {rules.faq_heading}" in block
    assert f"`{rules.worked_label}`" in block
    assert rules.writing_lead.capitalize() in block
    for phrase in qa.BLACKLIST_EN:
        assert f"`{phrase}`" in prompts.english_voice_block()


def test_the_repair_prompt_names_the_failures_and_shows_the_draft():
    seed = _load(VI_SEED)
    draft = _payload(title="Half a translation")
    prompt = prompts.build_translate_repair_prompt(
        seed, draft, ["body is 900 words, floor is 1500"])
    assert "body is 900 words" in prompt
    assert "Half a translation" in prompt
    assert "you dropped something" in prompt


# ----------------------------------------------------------------- the seed


def test_a_stubbed_translation_produces_a_seed_that_passes_the_gate(tmp_path):
    summary, model, out, src = _run(tmp_path, [_payload()], limit=1)
    assert summary["written"] == 1 and summary["failed"] == 0
    assert len(model.prompts) == 1, "a clean draft costs exactly one call"

    written = sorted(out.glob("*.json"))
    assert [p.name for p in written] == ["0001-cronbachs-alpha.json"], "prefix kept"
    seed = _load(str(written[0]))

    assert seed["locale"] == "en"
    assert seed["slug"] == "cronbachs-alpha"
    assert seed["source_slug"] == "cronbach-alpha-la-gi"
    assert seed["title"] == _load(EN_SEED)["title"]
    assert seed["focus_keyword"] == "cronbach's alpha"
    assert seed["schema"] == qa.SCHEMA

    source = _load(VI_SEED)
    for field in translate.CARRIED_FIELDS:
        assert seed[field] == source.get(field), field
    assert "focus_keyword_volume" not in seed, (
        "a Vietnamese search volume does not describe an English query")

    fails, _warns, stats = qa.check_post(seed, qa.known_slugs(src))
    assert fails == []
    assert stats["locale"] == "en"


def test_a_string_where_a_list_belongs_does_not_become_a_list_of_letters(tmp_path):
    """`"tags": "spss, alpha"` is a shape the model reaches for now and then."""
    summary, _model, out, _src = _run(
        tmp_path, [_payload(tags="spss, alpha", secondary_keywords="alpha")], limit=1)
    assert summary["written"] == 1
    seed = _load(str(next(out.glob("*.json"))))
    assert seed["tags"] == [] and seed["secondary_keywords"] == []


def test_the_gate_rejects_a_translation_that_dropped_the_faq(tmp_path):
    """A half-translated post fails here for the reason it would fail QA."""
    broken = _payload(body=_payload()["body"].replace(
        "## Frequently asked questions", "## A few notes"))
    summary, model, out, _src = _run(tmp_path, [broken, broken], limit=1)
    assert summary["rejected"] == 1 and summary["written"] == 0
    assert len(model.prompts) == 2, "one draft, one repair, then it is rejected"
    assert "no `## Frequently asked questions` section" in model.prompts[1]
    assert (out / "rejected" / "0001-cronbachs-alpha.json").exists()
    row = _log_rows(tmp_path / "translate-log.tsv")[0]
    assert row["status"] == translate.STATUS_REJECTED
    assert "Frequently asked questions" in row["failures"]


def test_a_repaired_draft_is_written_and_logged_as_repaired(tmp_path):
    broken = _payload(meta_title="x" * 90)
    summary, model, _out, _src = _run(tmp_path, [broken, _payload()], limit=1)
    assert summary["repaired"] == 1 and summary["written"] == 0
    assert len(model.prompts) == 2
    assert _log_rows(tmp_path / "translate-log.tsv")[0]["status"] == translate.STATUS_REPAIRED


def test_a_model_error_is_logged_and_does_not_stop_the_batch(tmp_path):
    summary, _model, out, _src = _run(tmp_path, [RuntimeError("upstream is down"),
                                                 _payload(), _payload()])
    assert summary["errors"] == 1 and summary["written"] == 2
    assert len(list(out.glob("*.json"))) == 2
    assert "upstream is down" in _log_rows(tmp_path / "translate-log.tsv")[0]["failures"]


# ------------------------------------------------------------------- slugs


def test_the_english_slug_comes_from_the_english_focus_keyword():
    assert translate.english_slug("Cronbach's Alpha", "cronbach-alpha-la-gi", "0001", {}) \
        == "cronbachs-alpha"
    assert translate.english_slug("Exploratory Factor Analysis in SPSS",
                                  "phan-tich-efa-trong-spss", "0002", {}) \
        == "exploratory-factor-analysis-in-spss"


@pytest.mark.parametrize("keyword", ["Cronbach's Alpha", "Bartlett’s test"])
def test_a_generated_slug_is_what_the_gate_calls_normalised(keyword):
    slug = translate.english_slug(keyword, "x", "0001", {})
    assert slug == qa.slugify(slug) and 0 < len(slug) <= qa.SLUG_MAX


def test_a_long_keyword_is_cut_at_a_hyphen_under_the_limit():
    slug = translate.english_slug("confirmatory factor analysis " * 12, "x", "0001", {})
    assert len(slug) <= qa.SLUG_MAX
    assert slug == qa.slugify(slug)
    assert not slug.endswith("-") and "--" not in slug


def test_the_slug_is_stable_across_runs_and_unique_within_the_directory():
    """A slug never moves once it is written, and two sources never share one.

    Stability cannot come from a counter over the output directory, because the
    number a post gets would then depend on which sibling happened to be written
    first. It comes from two things: the slug is a pure function of the English
    focus keyword, and the collision tie-break is the source's own numeric
    prefix in the frozen Vietnamese bank. The directory is then the authority,
    and a resumed run reads it back before assigning anything.
    """
    a, b = "cronbach-alpha-la-gi", "he-so-cronbach-alpha"

    first_run: dict[str, str] = {}
    for source, prefix in [(a, "0001"), (b, "0042")]:
        first_run[translate.english_slug("Cronbach's alpha", source, prefix, first_run)] = source
    assert first_run == {"cronbachs-alpha": a, "cronbachs-alpha-0042": b}

    # A second run, resumed from that directory and reaching the two posts in
    # the other order. Neither URL moves.
    resumed = dict(first_run)
    assert translate.english_slug("Cronbach's alpha", b, "0042", resumed) \
        == "cronbachs-alpha-0042"
    assert translate.english_slug("Cronbach's alpha", a, "0001", resumed) == "cronbachs-alpha"


def test_resume_reads_the_assignment_back_off_the_directory(tmp_path):
    """`scan_output` is what makes a slug survive an interrupted batch."""
    out = _en_dir(tmp_path, [
        ("0001", "cronbachs-alpha", "cronbach-alpha-la-gi", "No links.\n"),
    ])
    done, taken = translate.scan_output(out)
    assert done == {"cronbach-alpha-la-gi": os.path.join(out, "0001-cronbachs-alpha.json")}
    assert taken == {"cronbachs-alpha": "cronbach-alpha-la-gi"}
    assert translate.english_slug("Cronbach's alpha", "cronbach-alpha-la-gi", "0001",
                                  taken) == "cronbachs-alpha"


def test_a_second_source_translating_to_the_same_keyword_gets_its_own_file(tmp_path):
    summary, _model, out, _src = _run(tmp_path, [_payload(), _payload(), _payload()])
    assert summary["written"] == 3
    names = sorted(p.name for p in out.glob("*.json"))
    assert names == ["0001-cronbachs-alpha.json", "0002-cronbachs-alpha-0002.json",
                     "0003-cronbachs-alpha-0003.json"]
    slugs = {_load(str(out / n))["slug"] for n in names}
    assert len(slugs) == 3


# --------------------------------------------------- resume, force, budget, dry run


def test_a_source_whose_translation_exists_is_skipped_and_costs_nothing(tmp_path):
    out = tmp_path / "en"
    out.mkdir()
    (out / "0001-cronbachs-alpha.json").write_text(
        json.dumps({"slug": "cronbachs-alpha", "source_slug": "cronbach-alpha-la-gi"}),
        encoding="utf-8")
    model = StubModel([_payload(), _payload()])
    summary = translate.run(src_dir=_src_dir(tmp_path), out_dir=str(out), client=model,
                            workers=1, limit=1)
    assert summary["skipped"] == 1
    assert len(model.prompts) == 1, "resume moved on to the next source, not this one"
    assert all(r["source_slug"] != "cronbach-alpha-la-gi"
               for r in _log_rows(tmp_path / "translate-log.tsv")), \
        "the post already on disk was never paid for again"


def test_resume_keys_on_the_source_because_the_english_slug_is_not_known_yet(tmp_path):
    """The English seed's `source_slug` is the only thing that can answer this."""
    out = tmp_path / "en"
    out.mkdir()
    # Same post, written under a slug an earlier run chose. Resume still knows.
    (out / "0001-what-cronbachs-alpha-measures.json").write_text(
        json.dumps({"slug": "what-cronbachs-alpha-measures",
                    "source_slug": "cronbach-alpha-la-gi"}), encoding="utf-8")
    model = StubModel([_payload()])
    summary = translate.run(src_dir=_src_dir(tmp_path, SRC_SLUGS[:1]), out_dir=str(out),
                            client=model, workers=1)
    assert summary["skipped"] == 1 and summary["planned"] == 0
    assert model.prompts == []


def test_force_retranslates_and_keeps_the_slug_it_already_owns(tmp_path):
    out = tmp_path / "en"
    out.mkdir()
    (out / "0001-cronbachs-alpha.json").write_text(
        json.dumps({"slug": "cronbachs-alpha", "source_slug": "cronbach-alpha-la-gi"}),
        encoding="utf-8")
    model = StubModel([_payload()])
    summary = translate.run(src_dir=_src_dir(tmp_path), out_dir=str(out),
                            client=model, workers=1, force=True, limit=1)
    assert summary["written"] == 1 and summary["skipped"] == 0
    assert _load(str(out / "0001-cronbachs-alpha.json"))["locale"] == "en"


def test_the_run_stops_when_the_budget_is_crossed(tmp_path):
    # One call costs 8000 in + 4000 out = $0.0064. A $0.01 budget buys two.
    summary, _model, out, _src = _run(tmp_path, [_payload() for _ in range(3)],
                                        budget_usd=0.01)
    assert summary["stopped_on_budget"] is True
    assert summary["written"] == 2
    assert len(list(out.glob("*.json"))) == 2


def test_limit_caps_the_number_of_posts(tmp_path):
    summary, _model, _out, _src = _run(tmp_path, [_payload(), _payload()], limit=2)
    assert summary["planned"] == 2 and summary["written"] == 2


def test_dry_run_builds_the_prompts_and_writes_nothing(tmp_path, capsys):
    out = tmp_path / "en"
    summary = translate.run(src_dir=_src_dir(tmp_path), out_dir=str(out), dry_run=True)
    assert summary["planned"] == 3 and summary["usd"] == 0.0
    assert summary["estimated_usd"] > 0
    assert not out.exists()
    assert "dry-run" in capsys.readouterr().out


def test_workers_greater_than_one_still_translates_every_post(tmp_path):
    out = tmp_path / "en"
    model = StubModel([_payload() for _ in range(3)])
    summary = translate.run(src_dir=_src_dir(tmp_path), out_dir=str(out), client=model,
                            workers=3, budget_usd=100)
    assert summary["written"] == 3
    assert len({_load(str(p))["slug"] for p in out.glob("*.json")}) == 3


# ------------------------------------------------------------- the link pass


def _en_dir(tmp_path, seeds):
    """`seeds` is a list of `(prefix, slug, source_slug, body)`."""
    out = tmp_path / "en"
    out.mkdir(exist_ok=True)
    base = _load(EN_SEED)
    for prefix, slug, source_slug, body in seeds:
        seed = dict(base, slug=slug, source_slug=source_slug, body=body,
                    sibling_slugs=["phan-tich-efa-trong-spss", "khong-bao-gio-duoc-dich"])
        (out / f"{prefix}-{slug}.json").write_text(
            json.dumps(seed, ensure_ascii=False), encoding="utf-8")
    return str(out)


_LINKED_BODY = ("Start here: [EFA in SPSS](/blog/vi/phan-tich-efa-trong-spss), "
                "[the hub](/blog/vi/chu-de/spss), [the bank](/blog/vi) and "
                "[a post nobody translated](/blog/vi/khong-bao-gio-duoc-dich). "
                "Then [open the workspace](/landing).\n")


def test_the_link_pass_maps_a_vietnamese_slug_to_its_english_one(tmp_path, capsys):
    out = _en_dir(tmp_path, [
        ("0001", "cronbachs-alpha", "cronbach-alpha-la-gi", _LINKED_BODY),
        ("0002", "exploratory-factor-analysis", "phan-tich-efa-trong-spss", "No links.\n"),
    ])
    stats = translate.rewrite_links(out, run_relink=False)
    body = _load(os.path.join(out, "0001-cronbachs-alpha.json"))["body"]

    assert "/blog/en/exploratory-factor-analysis" in body
    assert "/blog/vi/phan-tich-efa-trong-spss" not in body
    assert f"/blog/en/{qa.CATEGORY_SEGMENT}/spss" in body, "the category route moves too"
    assert "(/blog/en)" in body, "so does the index"
    assert "(/landing)" in body, "and the CTA is not a blog link"
    assert stats.rewritten == 3 and stats.changed == 2
    assert stats.unmapped == {"/blog/vi/khong-bao-gio-duoc-dich": 1}
    assert "1 link(s) to 1 untranslated post(s)" in capsys.readouterr().out


def test_the_link_pass_leaves_an_unmappable_target_for_relink(tmp_path):
    """Not a second unlinker: `relink.py` already unlinks a dead target."""
    out = _en_dir(tmp_path, [
        ("0001", "cronbachs-alpha", "cronbach-alpha-la-gi", _LINKED_BODY),
        ("0002", "exploratory-factor-analysis", "phan-tich-efa-trong-spss", "No links.\n"),
    ])
    stats = translate.rewrite_links(out)

    body = _load(os.path.join(out, "0001-cronbachs-alpha.json"))["body"]
    assert "/blog/vi/khong-bao-gio-duoc-dich" not in body, "relink took the dead link"
    assert "a post nobody translated" in body, "and kept its anchor text"
    assert stats.relink is not None and stats.relink.removed == 1


def test_the_link_pass_moves_the_siblings_onto_the_same_map(tmp_path):
    out = _en_dir(tmp_path, [
        ("0001", "cronbachs-alpha", "cronbach-alpha-la-gi", "No links.\n"),
        ("0002", "exploratory-factor-analysis", "phan-tich-efa-trong-spss", "No links.\n"),
    ])
    translate.rewrite_links(out, run_relink=False)
    seed = _load(os.path.join(out, "0001-cronbachs-alpha.json"))
    assert seed["sibling_slugs"] == ["exploratory-factor-analysis",
                                     "khong-bao-gio-duoc-dich"]


def test_the_link_pass_is_idempotent(tmp_path):
    """It runs after a batch, and a batch gets resumed. A second run is a no-op."""
    out = _en_dir(tmp_path, [
        ("0001", "cronbachs-alpha", "cronbach-alpha-la-gi", _LINKED_BODY),
        ("0002", "exploratory-factor-analysis", "phan-tich-efa-trong-spss", "No links.\n"),
    ])
    translate.rewrite_links(out, run_relink=False)
    first = _load(os.path.join(out, "0001-cronbachs-alpha.json"))

    again = translate.rewrite_links(out, run_relink=False)
    assert again.rewritten == 0 and again.changed == 0
    assert _load(os.path.join(out, "0001-cronbachs-alpha.json")) == first


def test_the_link_pass_writes_nothing_on_a_dry_run(tmp_path):
    out = _en_dir(tmp_path, [
        ("0001", "cronbachs-alpha", "cronbach-alpha-la-gi", _LINKED_BODY),
        ("0002", "exploratory-factor-analysis", "phan-tich-efa-trong-spss", "No links.\n"),
    ])
    before = _load(os.path.join(out, "0001-cronbachs-alpha.json"))
    stats = translate.rewrite_links(out, dry_run=True, run_relink=False)
    assert stats.rewritten == 3
    assert _load(os.path.join(out, "0001-cronbachs-alpha.json")) == before


def test_an_image_is_not_a_link(tmp_path):
    mapping = {"phan-tich-efa-trong-spss": "exploratory-factor-analysis"}
    body, rewritten, unmapped = translate.rewrite_body(
        "![hero](/blog/vi/phan-tich-efa-trong-spss)\n", mapping)
    assert rewritten == 0 and unmapped == [] and "/blog/vi/" in body


def test_the_map_is_built_from_the_source_slug_of_each_english_seed(tmp_path):
    out = _en_dir(tmp_path, [
        ("0001", "cronbachs-alpha", "cronbach-alpha-la-gi", "No links.\n"),
        ("0002", "exploratory-factor-analysis", "phan-tich-efa-trong-spss", "No links.\n"),
    ])
    assert translate.slug_map(out) == {
        "cronbach-alpha-la-gi": "cronbachs-alpha",
        "phan-tich-efa-trong-spss": "exploratory-factor-analysis",
    }
