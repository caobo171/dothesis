"""Parse the REAL uploaded questionnaire into the rows of Bảng 3.1.

27 KB of extracted text, 13 constructs, 65 Likert items, plus a screening
section and a demographics section that use the same heading shape. Everything
here is asserted against that file, because the shapes that broke the parser
are the ones a synthetic fixture would never have.
"""
from pathlib import Path

import pytest

from orchestrator.instrument_parse import assign_codes, parse_instrument_items

FIXTURE = Path(__file__).parent / "fixtures" / "questionnaire_raw.txt"
# The codes the student's own SmartPLS model used, read off the outer-loadings
# table (ATT_1, DEC_1, …) — ground truth, not inference.
CODES = ["ATT", "DEC", "ECONN", "EXP", "INSP", "INT", "SIMI", "TRUST"]


@pytest.fixture
def raw() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def test_every_likert_item_is_parsed(raw):
    items = parse_instrument_items(raw, codes=CODES)
    assert len(items) == 65


def test_all_thirteen_constructs_survive(raw):
    items = parse_instrument_items(raw, codes=CODES)
    constructs = list(dict.fromkeys(i["construct"] for i in items))
    assert len(constructs) == 13
    assert all(sum(1 for i in items if i["construct"] == c) == 5 for c in constructs)


def test_demographics_headings_do_not_overwrite_constructs(raw):
    """PHẦN C restarts its numbering at 1 and collides with constructs 2–6.

    Keying headings by their number was the first implementation, and it
    silently relabelled four scales: "2. Nhóm tuổi / Age group" replaced
    "2. Mối quan tâm đến môi trường / Environmental Concern", so five
    environmental-concern items came out as an age question.
    """
    constructs = {i["construct"] for i in parse_instrument_items(raw, codes=CODES)}
    assert "Mối quan tâm đến môi trường" in constructs
    assert "Thái độ đối với du lịch nội địa" in constructs
    assert "Nhóm tuổi" not in constructs, "a demographics heading became a scale"
    assert "Trình độ học vấn" not in constructs


def test_screening_and_demographic_questions_are_not_items(raw):
    # They are questionnaire content but not observed variables, so they do not
    # belong in the measurement table. Anchoring items on "Câu" excludes them.
    texts = " ".join(i["text"] for i in parse_instrument_items(raw, codes=CODES))
    assert "Giới tính" not in texts
    assert "Bạn có sử dụng mạng xã hội không?" not in texts


def test_item_text_is_verbatim(raw):
    """These are the student's own survey questions. Byte-for-byte or they are
    not the instrument that was fielded."""
    items = parse_instrument_items(raw, codes=CODES)
    att = [i for i in items if i["construct"] == "Độ thu hút"]
    assert att[0]["text"] == "Influencer có phong cách sống và hình ảnh cá nhân rất cuốn hút."
    assert att[0]["text_en"] == "The influencer has an attractive lifestyle and personal image."


def test_unambiguous_codes_are_assigned(raw):
    items = parse_instrument_items(raw, codes=CODES)
    by_construct = {i["construct"]: i["code"] for i in items}
    assert by_construct["Kết nối cảm xúc"] == "ECONN"
    assert by_construct["Ý định du lịch"] == "INT"
    assert by_construct["Quyết định du lịch"] == "DEC"
    assert by_construct["Sự tin cậy"] == "TRUST"
    assert by_construct["Sự tương đồng"] == "SIMI"
    assert by_construct["Khả năng truyền cảm hứng"] == "INSP"


def test_ids_are_the_codes_the_results_tables_use(raw):
    items = parse_instrument_items(raw, codes=CODES)
    intent = [i["id"] for i in items if i["construct"] == "Ý định du lịch"]
    assert intent == ["INT1", "INT2", "INT3", "INT4", "INT5"]


def test_an_ambiguous_code_is_left_blank_rather_than_guessed(raw):
    """ATT prefixes both "Attractiveness" and "Attitude Toward Domestic
    Tourism"; EXP prefixes both "Expertise" and "Service Sector Expansion".

    Labelling five attitude items as the attractiveness scale would put the
    wrong rows in a table the examiner reads against the structural model. A
    blank cell is a gap the student closes in one sentence; a mislabelled one
    is a defect they have to spot first.
    """
    items = parse_instrument_items(raw, codes=CODES)
    by_construct = {i["construct"]: i["code"] for i in items}
    assert by_construct["Độ thu hút"] == ""
    assert by_construct["Thái độ đối với du lịch nội địa"] == ""
    assert by_construct["Chuyên môn"] == ""
    # The construct still identifies itself, and numbering still works.
    ids = [i["id"] for i in items if i["construct"] == "Độ thu hút"]
    assert ids == ["1b.1", "1b.2", "1b.3", "1b.4", "1b.5"]


def test_the_injection_envelope_never_reaches_a_row(raw):
    items = parse_instrument_items(raw, codes=CODES)
    blob = " ".join(f"{i['construct']} {i['text']}" for i in items)
    assert "UNTRUSTED DOCUMENT" not in blob
    assert "BEGIN DOCUMENT" not in blob


def test_nothing_parseable_yields_nothing():
    # A half-parsed instrument reads as a complete measurement table while
    # silently missing scales — worse than returning nothing.
    assert parse_instrument_items("") == []
    assert parse_instrument_items("Chương 3. Phương pháp nghiên cứu\n\nKhông có bảng hỏi.") == []


def test_assign_codes_requires_mutual_uniqueness():
    # One code, two candidate constructs -> neither is labelled.
    assert assign_codes(["Attractiveness", "Attitude Toward X"], ["ATT"]) == {}
    # One code, one construct -> labelled.
    assert assign_codes(["Attractiveness"], ["ATT"]) == {"Attractiveness": "ATT"}


def test_initial_plus_prefix_codes_match():
    # ECONN is E(motional) + CONN(ection) — the shape a plain prefix misses.
    assert assign_codes(["Emotional Connection"], ["ECONN"]) == {
        "Emotional Connection": "ECONN"}


def test_the_doctor_surfaces_an_unparsed_questionnaire(raw):
    """The raw blob must survive the repair — it is the student's document."""
    from orchestrator.doctor import DoctorInput, diagnose

    inp = DoctorInput(
        context_store={"m3_design": {"instrument": {"raw": raw}},
                       "m4_analysis": {"results": {"outer_loadings": [
                           {"label": "INT_1", "values": [0.8]},
                           {"label": "DEC_1", "values": [0.8]}]}}},
        uploads=[], chapter_prose={},
    )
    found = [f for f in diagnose(inp) if f.code == "INSTRUMENT_NOT_PARSED"]
    assert found
    assert len(found[0].payload["items"]) == 65
    assert found[0].payload["instrument"]["raw"] == raw, "raw must ride along"
    # Codes came from the outer-loadings labels, not from guessing.
    ids = {i["id"] for i in found[0].payload["items"]}
    assert "INT1" in ids and "DEC1" in ids


def test_an_already_parsed_instrument_is_left_alone(raw):
    from orchestrator.doctor import DoctorInput, diagnose

    inp = DoctorInput(
        context_store={"m3_design": {"instrument": {
            "raw": raw, "items": [{"text": "already parsed"}]}}},
        uploads=[], chapter_prose={},
    )
    assert not [f for f in diagnose(inp) if f.code == "INSTRUMENT_NOT_PARSED"]
