"""gate: the demand cut rules, the family aggregate, and the printed API cost."""
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


def test_client_reports_a_keyword_with_no_data_as_none():
    payload = _payload()
    payload["tasks"][0]["result"].append({"keyword": "khong ai tim", "search_volume": None})
    client = dataforseo.DataForSEOClient(login="u", password="p", http=StubHttp(payload))
    volumes, _ = client.search_volume(["khong ai tim"])
    assert volumes["khong ai tim"] is None


# ---------------------------------------------------------------- cut rules


def _row(keyword, volume, family="reliability", kd=None):
    return gate.Measured(keyword=keyword, search_volume=volume, family=family, kd=kd,
                         axis="demo-axis")


def test_no_volume_is_dropped():
    verdicts = gate.apply_cuts([_row("khong ai tim", None)])
    assert verdicts[0].verdict == "drop"
    assert "no volume" in verdicts[0].reason


def test_zero_volume_is_dropped():
    verdicts = gate.apply_cuts([_row("cung khong ai tim", 0)])
    assert verdicts[0].verdict == "drop"


def test_volume_at_or_above_ten_passes_as_measured():
    verdicts = gate.apply_cuts([_row("cronbach alpha", 1300)])
    assert verdicts[0].verdict == "pass"
    assert verdicts[0].gate_status == "measured"


def test_thin_row_survives_only_when_the_family_aggregate_clears_500():
    strong_family = [_row("a", 480), _row("b", 30), _row("c", 5)]
    verdicts = {v.keyword: v for v in gate.apply_cuts(strong_family)}
    assert verdicts["c"].verdict == "pass"
    assert verdicts["c"].gate_status == "family-inferred"
    assert "family" in verdicts["c"].reason

    weak_family = [_row("d", 100), _row("e", 5)]
    verdicts = {v.keyword: v for v in gate.apply_cuts(weak_family)}
    assert verdicts["e"].verdict == "drop"
    assert "under 10" in verdicts["e"].reason


def test_family_aggregate_is_computed_per_family_not_across_the_batch():
    rows = [_row("a", 600, family="efa"), _row("b", 5, family="reliability")]
    verdicts = {v.keyword: v for v in gate.apply_cuts(rows)}
    assert verdicts["b"].verdict == "drop"


def test_difficulty_above_forty_defers():
    verdicts = gate.apply_cuts([_row("kho", 900, kd=55)])
    assert verdicts[0].verdict == "defer"
    assert "difficulty" in verdicts[0].reason


def test_missing_difficulty_never_defers():
    """Google Ads volume carries no difficulty, so the rule must not fire on None."""
    verdicts = gate.apply_cuts([_row("cronbach alpha", 1300, kd=None)])
    assert verdicts[0].verdict == "pass"


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
    # a keyword the API returned nothing for still gets a row, so the drop is evidenced
    other = list(csv.DictReader(open(tmp_path / "gate-other-axis.tsv", encoding="utf-8"),
                                delimiter="\t"))
    assert other[0]["verdict"] == "drop"


def test_gate_from_a_tsv_of_measured_rows_makes_no_network_call(tmp_path):
    candidates = tmp_path / "candidates.tsv"
    with open(candidates, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter="\t", lineterminator="\n")
        w.writerow(["keyword", "axis", "unit", "family", "category", "archetype"])
        w.writerow(["cronbach alpha", "demo-axis", "cronbach-alpha", "reliability",
                    "spss", "term-la-gi"])
    measured = tmp_path / "measured.tsv"
    with open(measured, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter="\t", lineterminator="\n")
        w.writerow(["keyword", "search_volume", "kd"])
        w.writerow(["cronbach alpha", "1300", "0"])

    summary = gate.run(source="tsv", candidates_path=str(candidates),
                       measured_path=str(measured), out_dir=str(tmp_path))
    assert summary["cost_usd"] == 0.0
    assert summary["pass"] == 1


def test_probe_measures_the_five_known_head_terms():
    client = dataforseo.DataForSEOClient(login="u", password="p", http=StubHttp(_payload()))
    result = gate.probe(client=client)
    assert result["volumes"]["spss"] == 14800
    assert set(result["volumes"]) == set(gate.PROBE_KEYWORDS)
    assert result["cost_usd"] == pytest.approx(0.0075)
