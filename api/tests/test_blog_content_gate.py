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


# ------------------------------------------- the unmeasured fill (spec §5)


def _fill_rows():
    """One family whose sample is strong, one whose sample is weak.

    `efa` has 5 measured keywords, 4 of them passing on their own, aggregate
    9,300. `tourism` has 3 measured, 1 passing, aggregate 120.
    """
    return [
        _row("efa 1", 5000, family="efa"), _row("efa 2", 3000, family="efa"),
        _row("efa 3", 1200, family="efa"), _row("efa 4", 100, family="efa"),
        _row("efa 5", 0, family="efa"),
        _row("efa unmeasured", None, family="efa"),
        _row("tourism 1", 110, family="tourism"), _row("tourism 2", 5, family="tourism"),
        _row("tourism 3", 5, family="tourism"),
        _row("tourism unmeasured", None, family="tourism"),
    ]


def _measured_keywords(rows):
    return {r.keyword for r in rows if not r.keyword.endswith("unmeasured")}


def test_unmeasured_rows_keep_their_drop_when_no_measured_set_is_given():
    """Without the flag nothing changes: an unmeasured row is a no-volume drop."""
    rows = _fill_rows()
    verdicts = {v.keyword: v for v in gate.apply_cuts(rows)}
    assert verdicts["efa unmeasured"].verdict == "drop"
    assert verdicts["efa unmeasured"].reason == "no volume returned"
    assert verdicts["efa unmeasured"].gate_status == ""


def test_unmeasured_row_passes_as_family_inferred_when_its_family_sample_carries_it():
    rows = _fill_rows()
    verdicts = {v.keyword: v for v in gate.apply_cuts(rows, _measured_keywords(rows))}
    v = verdicts["efa unmeasured"]
    assert v.verdict == "pass"
    assert v.gate_status == "family-inferred"
    assert v.reason == "unmeasured; family 'efa' sample 4/5 pass, aggregate 9,300"


def test_unmeasured_row_drops_when_its_family_sample_is_weak():
    rows = _fill_rows()
    verdicts = {v.keyword: v for v in gate.apply_cuts(rows, _measured_keywords(rows))}
    v = verdicts["tourism unmeasured"]
    assert v.verdict == "drop"
    assert v.gate_status == ""
    assert v.reason == "unmeasured; family 'tourism' sample 1/3 pass, aggregate 120"


def test_unmeasured_row_drops_when_fewer_than_three_family_keywords_were_measured():
    rows = [_row("a", 9000, family="thin"), _row("b", 9000, family="thin"),
            _row("c", None, family="thin")]
    verdicts = {v.keyword: v for v in gate.apply_cuts(rows, {"a", "b"})}
    assert verdicts["c"].verdict == "drop"
    assert "sample 2/2 pass" in verdicts["c"].reason


def test_unmeasured_row_drops_when_the_family_aggregate_is_under_the_floor():
    """Half the sample passes, but 3 x 100 does not clear FAMILY_AGGREGATE_FLOOR."""
    rows = [_row(k, 100, family="small") for k in ("a", "b", "c")]
    rows.append(_row("d", None, family="small"))
    verdicts = {v.keyword: v for v in gate.apply_cuts(rows, {"a", "b", "c"})}
    assert verdicts["d"].verdict == "drop"
    assert verdicts["d"].reason == "unmeasured; family 'small' sample 3/3 pass, aggregate 300"


def test_a_measured_zero_still_counts_toward_the_family_sample():
    """(a) is "present in the TSV", not "has volume": a measured 0 is evidence."""
    rows = [_row("a", 400, family="efa"), _row("b", 400, family="efa"),
            _row("c", 0, family="efa"), _row("d", None, family="efa")]
    verdicts = {v.keyword: v for v in gate.apply_cuts(rows, {"a", "b", "c"})}
    assert verdicts["d"].verdict == "pass"
    assert verdicts["d"].reason == "unmeasured; family 'efa' sample 2/3 pass, aggregate 800"


def test_the_fill_leaves_measured_rows_on_the_normal_cut_rules():
    rows = _fill_rows()
    verdicts = {v.keyword: v for v in gate.apply_cuts(rows, _measured_keywords(rows))}
    assert verdicts["efa 1"].verdict == "pass"
    assert verdicts["efa 1"].gate_status == "measured"
    assert verdicts["efa 5"].verdict == "drop"          # measured 0 is still a drop
    assert verdicts["efa 4"].verdict == "pass"          # 100 >= MIN_VOLUME
    assert verdicts["tourism 3"].verdict == "drop"      # thin, weak family aggregate


def _fill_fixture(tmp_path):
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


def test_gate_without_the_flag_still_drops_the_unmeasured_candidate(tmp_path):
    candidates, measured = _fill_fixture(tmp_path)
    summary = gate.run(source="tsv", candidates_path=candidates, measured_path=measured,
                       out_dir=str(tmp_path))
    rows = {r["keyword"]: r for r in csv.DictReader(
        open(tmp_path / "gate-demo-axis.tsv", encoding="utf-8"), delimiter="\t")}
    assert rows["efa unmeasured"]["verdict"] == "drop"
    assert rows["efa unmeasured"]["reason"] == "no volume returned"
    assert summary["unmeasured_filled"] == 0


def test_gate_fill_unmeasured_writes_the_inferred_row_and_counts_the_three_kinds(
        tmp_path, capsys):
    candidates, measured = _fill_fixture(tmp_path)
    summary = gate.run(source="tsv", candidates_path=candidates, measured_path=measured,
                       out_dir=str(tmp_path), fill_unmeasured=True)

    rows = {r["keyword"]: r for r in csv.DictReader(
        open(tmp_path / "gate-demo-axis.tsv", encoding="utf-8"), delimiter="\t")}
    assert rows["efa unmeasured"]["verdict"] == "pass"
    assert rows["efa unmeasured"]["search_volume"] == ""
    assert rows["efa unmeasured"]["reason"].startswith("unmeasured; family 'efa' sample 3/4")

    assert summary["pass_measured"] == 3       # efa 1..3
    assert summary["family_inferred"] == 1     # efa thin, on the aggregate rule
    assert summary["unmeasured_filled"] == 1   # efa unmeasured
    assert summary["pass"] == 5

    out = capsys.readouterr().out
    assert "3 measured" in out
    assert "1 family-inferred" in out
    assert "1 unmeasured-filled" in out


def test_read_gate_files_derives_family_inferred_from_aggregate_or_from_unmeasured(tmp_path):
    """Both fallbacks write `pass` rows that `plan` must insert as drafts."""
    path = tmp_path / "gate-demo-axis.tsv"
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter="\t", lineterminator="\n")
        w.writerow(gate.GATE_COLUMNS)
        w.writerow(["measured one", "1300", "pass", "volume 1300"])
        w.writerow(["thin one", "5", "pass", "volume 5 under 10, family 'efa' aggregate 9300"])
        w.writerow(["unmeasured one", "", "pass",
                    "unmeasured; family 'efa' sample 4/5 pass, aggregate 9,300"])
        w.writerow(["unmeasured no digits", "", "pass", "unmeasured; family 'efa' carried it"])

    verdicts = gate.read_gate_files(str(tmp_path))
    assert verdicts["measured one"].gate_status == "measured"
    assert verdicts["thin one"].gate_status == "family-inferred"
    assert verdicts["unmeasured one"].gate_status == "family-inferred"
    assert verdicts["unmeasured no digits"].gate_status == "family-inferred"
    assert verdicts["unmeasured one"].search_volume is None
