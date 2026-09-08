"""gate: what the measurement source knows, recorded, plus the printed API cost.

The cut rules these tests used to assert were removed on 2026-09-08: measured
volume no longer vetoes a page, it only orders one. What is left to test is
that every candidate survives and that the verdict says which of them we
actually have a number for.
"""
import csv
import json
import os

import pytest

from app.blog.content import dataforseo, gate


@pytest.fixture(autouse=True)
def _bind_db():
    """No database in the content engine. See test_blog_content_expand.py."""
    yield


FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures", "blog", "content")


class StubHttp:
    """Stands in for httpx: records the request, replays a canned response."""

    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code
        self.calls = []

    def post(self, url, json=None, auth=None, headers=None, timeout=None):
        self.calls.append({"url": url, "json": json, "auth": auth})
        return StubResponse(self.status_code, self.payload)


class StubResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = "stub"

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def _payload():
    with open(os.path.join(FIXTURES, "dataforseo_search_volume.json"), encoding="utf-8") as fh:
        return json.load(fh)


# --------------------------------------------------------------- the client


def test_client_posts_vietnam_and_returns_volumes_with_cost():
    http = StubHttp(_payload())
    client = dataforseo.DataForSEOClient(login="u", password="p", http=http)
    volumes, cost = client.search_volume(
        ["spss", "cronbach alpha", "thang đo likert", "hồi quy tuyến tính", "mô hình nghiên cứu"])

    assert volumes["spss"] == 14800
    assert volumes["cronbach alpha"] == 1300
    assert cost == pytest.approx(0.0075)

    body = http.calls[0]["json"][0]
    assert body["location_code"] == 2704
    assert body["language_code"] == "vi"
    assert http.calls[0]["url"].endswith("/keywords_data/google_ads/search_volume/live")
    assert http.calls[0]["auth"] == ("u", "p")


def test_client_batches_at_a_thousand_keywords():
    http = StubHttp(_payload())
    client = dataforseo.DataForSEOClient(login="u", password="p", http=http)
    client.search_volume([f"kw {i}" for i in range(2100)])
    assert len(http.calls) == 3
    assert [len(c["json"][0]["keywords"]) for c in http.calls] == [1000, 1000, 100]


def test_client_raises_on_a_non_20000_status():
    payload = _payload()
    payload["status_code"] = 40501
    payload["status_message"] = "Invalid Field"
    client = dataforseo.DataForSEOClient(login="u", password="p", http=StubHttp(payload))
    with pytest.raises(dataforseo.DataForSEOError) as err:
        client.search_volume(["spss"])
    assert "40501" in str(err.value)


def test_client_explains_an_http_error_from_the_body():
    """A 402 means the account balance ran out, and the message must say so.

    Measured on 2026-09-08: the endpoint answers `402` with status_code 40200,
    "Payment Required" in the body, and httpx's bare `402 Unknown` sends the
    reader looking for a bug in the request instead.
    """
    payload = {"status_code": 40200, "status_message": "Payment Required.", "cost": 0}
    client = dataforseo.DataForSEOClient(login="u", password="p",
                                         http=StubHttp(payload, status_code=402))
    with pytest.raises(dataforseo.DataForSEOError) as err:
        client.search_volume(["spss"])
    assert "402" in str(err.value)
    assert "Payment Required" in str(err.value)


def test_client_reports_a_keyword_with_no_data_as_none():
    payload = _payload()
    payload["tasks"][0]["result"].append({"keyword": "khong ai tim", "search_volume": None})
    client = dataforseo.DataForSEOClient(login="u", password="p", http=StubHttp(payload))
    volumes, _ = client.search_volume(["khong ai tim"])
    assert volumes["khong ai tim"] is None


# ------------------------------------------------- what the gate records now
#
# The rule changed on 2026-09-08. Before that date these tests asserted the
# opposite of most of what follows: no volume was a drop, volume under 10 was a
# drop unless the family aggregate cleared 500, and difficulty over 40 deferred.
# Measured volume now sets priority order and nothing else, so the assertions
# are that every candidate survives and is labelled honestly.


def _row(keyword, volume, family="reliability", kd=None):
    return gate.Measured(keyword=keyword, search_volume=volume, family=family, kd=kd,
                         axis="demo-axis")


def test_volume_at_or_above_ten_passes_as_measured():
    verdicts = gate.classify([_row("cronbach alpha", 1300)])
    assert verdicts[0].verdict == "pass"
    assert verdicts[0].gate_status == "measured"
    assert verdicts[0].reason == "volume 1300"


def test_a_thin_keyword_passes_and_says_it_is_thin():
    """It has its own number; it just is not worth much. Ordering handles that."""
    verdicts = gate.classify([_row("bien hiem", 5)])
    assert verdicts[0].verdict == "pass"
    assert verdicts[0].gate_status == "measured"
    assert verdicts[0].reason == "volume 5, thin"


def test_no_volume_returned_passes_as_unmeasured():
    """Rule changed 2026-09-08: this was a drop, and the drop was the veto."""
    verdicts = gate.classify([_row("khong ai tim", None)])
    assert verdicts[0].verdict == "pass"
    assert verdicts[0].gate_status == "unmeasured"
    assert verdicts[0].reason == "no volume returned; quality gates decide"
    assert verdicts[0].search_volume is None


def test_a_measured_zero_is_measured_not_unmeasured():
    """We asked and the answer was a number. `None` is the absence of one."""
    verdicts = gate.classify([_row("cung khong ai tim", 0)])
    assert verdicts[0].gate_status == "measured"
    assert verdicts[0].reason == "volume 0, thin"


def test_difficulty_above_forty_still_passes_and_notes_the_deprioritisation():
    """Rule changed 2026-09-08: this used to be a `defer` verdict."""
    verdicts = gate.classify([_row("kho", 900, kd=55)])
    assert verdicts[0].verdict == "pass"
    assert verdicts[0].gate_status == "measured"
    assert verdicts[0].reason == "volume 900; difficulty 55 above 40, deprioritised"


def test_missing_difficulty_never_deprioritises():
    """Google Ads volume carries no difficulty, so the rule must not fire on None."""
    verdicts = gate.classify([_row("cronbach alpha", 1300, kd=None)])
    assert "deprioritised" not in verdicts[0].reason


def test_nothing_is_dropped_or_deferred_whatever_the_batch_looks_like():
    rows = [_row("a", 5000), _row("b", 5), _row("c", 0), _row("d", None),
            _row("e", 900, kd=90)]
    verdicts = gate.classify(rows)
    assert {v.verdict for v in verdicts} == {"pass"}
    assert len(verdicts) == len(rows)


# --------------------------------------------------------------- the command


def test_gate_writes_one_file_per_axis_and_prints_the_cost(tmp_path, capsys):
    candidates = tmp_path / "candidates.tsv"
    with open(candidates, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter="\t", lineterminator="\n")
        w.writerow(["keyword", "axis", "unit", "family", "category", "archetype"])
        w.writerow(["spss", "demo-axis", "spss", "reliability", "spss", "term-la-gi"])
        w.writerow(["cronbach alpha", "demo-axis", "cronbach-alpha", "reliability",
                    "spss", "term-la-gi"])
        w.writerow(["khong ai tim", "other-axis", "x", "misc", "spss", "term-la-gi"])

    client = dataforseo.DataForSEOClient(login="u", password="p", http=StubHttp(_payload()))
    summary = gate.run(source="dataforseo", candidates_path=str(candidates),
                       out_dir=str(tmp_path), client=client)

    out = capsys.readouterr().out
    assert "cost" in out.lower()
    assert "0.0075" in out or "0.008" in out
    assert summary["cost_usd"] == pytest.approx(0.0075)

    rows = list(csv.DictReader(open(tmp_path / "gate-demo-axis.tsv", encoding="utf-8"),
                               delimiter="\t"))
    assert [r["keyword"] for r in rows] == ["spss", "cronbach alpha"]
    assert list(rows[0]) == ["keyword", "search_volume", "verdict", "reason"]
    assert rows[0]["verdict"] == "pass"
    # The keyword the API returned nothing for is a page too now, with an empty
    # volume column so the gate file still records which pages those were.
    other = list(csv.DictReader(open(tmp_path / "gate-other-axis.tsv", encoding="utf-8"),
                                delimiter="\t"))
    assert other[0]["verdict"] == "pass"
    assert other[0]["search_volume"] == ""


def test_gate_summary_counts_measured_against_unmeasured(tmp_path, capsys):
    candidates, measured = _fixture(tmp_path)
    summary = gate.run(source="tsv", candidates_path=candidates, measured_path=measured,
                       out_dir=str(tmp_path))

    assert summary["candidates"] == 5
    assert summary["pass"] == 5
    assert summary["measured"] == 4          # efa 1..3 plus the thin one
    assert summary["unmeasured"] == 1
    assert summary["thin"] == 1
    assert summary["volume_total"] == 9204

    out = capsys.readouterr().out
    assert "4 measured" in out
    assert "1 unmeasured" in out
    assert "9,204/month" in out


def _fixture(tmp_path):
    candidates = tmp_path / "candidates.tsv"
    with open(candidates, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter="\t", lineterminator="\n")
        w.writerow(["keyword", "axis", "unit", "family", "category", "archetype"])
        for keyword in ("efa 1", "efa 2", "efa 3", "efa thin", "efa unmeasured"):
            w.writerow([keyword, "demo-axis", "u", "efa", "spss", "term-la-gi"])
    measured = tmp_path / "measured.tsv"
    with open(measured, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter="\t", lineterminator="\n")
        w.writerow(["keyword", "search_volume", "kd"])
        w.writerow(["efa 1", "5000", "3"])
        w.writerow(["efa 2", "3000", ""])
        w.writerow(["efa 3", "1200", ""])
        w.writerow(["efa thin", "4", ""])
    return str(candidates), str(measured)


def test_gate_from_a_tsv_of_measured_rows_makes_no_network_call(tmp_path):
    candidates, measured = _fixture(tmp_path)
    summary = gate.run(source="tsv", candidates_path=candidates, measured_path=measured,
                       out_dir=str(tmp_path))
    assert summary["cost_usd"] == 0.0
    assert summary["pass"] == 5


def test_the_unmeasured_candidate_reaches_the_gate_file_as_a_pass(tmp_path):
    candidates, measured = _fixture(tmp_path)
    gate.run(source="tsv", candidates_path=candidates, measured_path=measured,
             out_dir=str(tmp_path))
    rows = {r["keyword"]: r for r in csv.DictReader(
        open(tmp_path / "gate-demo-axis.tsv", encoding="utf-8"), delimiter="\t")}
    assert rows["efa unmeasured"]["verdict"] == "pass"
    assert rows["efa unmeasured"]["search_volume"] == ""
    assert rows["efa unmeasured"]["reason"] == "no volume returned; quality gates decide"


def test_fill_unmeasured_is_accepted_as_a_deprecated_no_op(tmp_path, capsys):
    """A committed script or doc that still passes the flag must not break."""
    candidates, measured = _fixture(tmp_path)
    with_flag = gate.run(source="tsv", candidates_path=candidates, measured_path=measured,
                         out_dir=str(tmp_path), fill_unmeasured=True)
    out = capsys.readouterr().out
    assert "deprecated" in out
    without_flag = gate.run(source="tsv", candidates_path=candidates,
                            measured_path=measured, out_dir=str(tmp_path))
    assert with_flag == without_flag


def test_probe_measures_the_five_known_head_terms():
    client = dataforseo.DataForSEOClient(login="u", password="p", http=StubHttp(_payload()))
    result = gate.probe(client=client)
    assert result["volumes"]["spss"] == 14800
    assert set(result["volumes"]) == set(gate.PROBE_KEYWORDS)
    assert result["cost_usd"] == pytest.approx(0.0075)


# --------------------------------------------------------- reading back files


def test_read_gate_files_calls_a_pass_measured_only_when_it_carries_a_number(tmp_path):
    """Including the files written before 2026-09-08, whose reasons read differently."""
    path = tmp_path / "gate-demo-axis.tsv"
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter="\t", lineterminator="\n")
        w.writerow(gate.GATE_COLUMNS)
        w.writerow(["measured one", "1300", "pass", "volume 1300"])
        w.writerow(["thin one", "5", "pass", "volume 5, thin"])
        w.writerow(["unmeasured one", "", "pass", "no volume returned; quality gates decide"])
        # Old vocabulary, still on disk in the committed gate files.
        w.writerow(["old family carried", "5", "pass",
                    "volume 5 under 10, family 'efa' aggregate 9300"])
        w.writerow(["old fill", "", "pass",
                    "unmeasured; family 'efa' sample 4/5 pass, aggregate 9,300"])
        w.writerow(["old drop", "", "drop", "no volume returned"])

    verdicts = gate.read_gate_files(str(tmp_path))
    assert verdicts["measured one"].gate_status == "measured"
    assert verdicts["thin one"].gate_status == "measured"
    assert verdicts["unmeasured one"].gate_status == "unmeasured"
    assert verdicts["old family carried"].gate_status == "measured"
    assert verdicts["old fill"].gate_status == "unmeasured"
    assert verdicts["unmeasured one"].search_volume is None
    # A verdict an earlier run wrote as a drop stays a drop: `plan` must not
    # silently promote it, the operator re-runs `gate` to change its mind.
    assert verdicts["old drop"].verdict == "drop"
    assert verdicts["old drop"].gate_status == ""
