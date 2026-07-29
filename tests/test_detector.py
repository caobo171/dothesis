"""Tests for the pluggable humanize detectors (v4).

Scope: the training-free StylometricScorer's discrimination + edge cases, and
the get_scorer() routing / graceful-degradation contract that lets the loop
fall back to single-pass whenever a backend's model/key/dep is missing.
"""
from __future__ import annotations

import pytest

from orchestrator.tools import detector as D


# --- StylometricScorer ---------------------------------------------------

# Uniform sentence length + formulaic sentence-openers: the LLM metronome.
_AI_EVEN = ("Kết quả cho thấy nhân tố này tác động tích cực đến biến phụ thuộc. "
            "Hơn nữa, mức độ ảnh hưởng của nhân tố này là đáng kể và rõ ràng. "
            "Bên cạnh đó, kết quả kiểm định cũng khẳng định giả thuyết nghiên cứu. "
            "Đồng thời, mô hình đề xuất phù hợp với dữ liệu thu thập được.")

# Deliberately varied rhythm: a very short sentence next to long ones.
_HUMAN_BURSTY = ("Mô hình đạt yêu cầu. Tuy nhiên, khi xem xét kỹ hơn từng chỉ số "
                 "đo lường độ tin cậy và giá trị hội tụ của thang đo, nhóm nghiên "
                 "cứu nhận thấy một vài biến quan sát có hệ số tải thấp hơn ngưỡng "
                 "khuyến nghị và cần cân nhắc loại bỏ. Điều này đáng lưu tâm.")


def test_stylometric_flags_uniform_text_higher_than_bursty():
    s = D.StylometricScorer()
    ai = s.score(_AI_EVEN)
    human = s.score(_HUMAN_BURSTY)
    assert ai is not None and human is not None
    assert ai > human                       # the metronome scores more AI-like
    assert 0.0 <= human <= 1.0 and 0.0 <= ai <= 1.0


def test_stylometric_returns_none_on_too_short_text():
    # Fewer than 3 sentences: no rhythm to measure.
    assert D.StylometricScorer().score("Một câu duy nhất.") is None
    assert D.StylometricScorer().score("") is None
    assert D.StylometricScorer().score("   ") is None


# --- graceful degradation (no deps / no key) -----------------------------

def test_perplexity_scorer_degrades_to_none_on_unloadable_model():
    # Whether or not torch is installed, an unloadable model must degrade to
    # None (single-pass fallback) rather than raise — a bogus path exercises the
    # load-failure branch deterministically, independent of the environment.
    assert D.PerplexityScorer(model_path="__no_such_model_xyz__").score(
        _AI_EVEN) is None


def test_videtect_scorer_degrades_to_none_without_model(monkeypatch):
    monkeypatch.delenv("HUMANIZE_VIDETECT_MODEL", raising=False)
    assert D.ViDetectScorer().score(_AI_EVEN) is None


def test_originality_scorer_degrades_to_none_without_key(monkeypatch):
    monkeypatch.delenv("ORIGINALITY_API_KEY", raising=False)
    assert D.OriginalityScorer().score(_AI_EVEN) is None


# --- get_scorer routing --------------------------------------------------

@pytest.mark.parametrize("env,expected", [
    (None, None),
    ("none", None),
    ("off", None),
    ("bogus", None),
    ("stylometric", D.StylometricScorer),
    ("perplexity", D.PerplexityScorer),
    ("videtect", D.ViDetectScorer),
    ("originality", D.OriginalityScorer),
])
def test_get_scorer_routing(monkeypatch, env, expected):
    if env is None:
        monkeypatch.delenv("HUMANIZE_SCORER", raising=False)
    else:
        monkeypatch.setenv("HUMANIZE_SCORER", env)
    scorer = D.get_scorer()
    if expected is None:
        assert scorer is None
    else:
        assert isinstance(scorer, expected)


def test_thresholds_read_from_env(monkeypatch):
    monkeypatch.setenv("HUMANIZE_AI_THRESHOLD", "0.3")
    monkeypatch.setenv("HUMANIZE_MAX_ROUNDS", "6")
    assert D.ai_threshold() == 0.3
    assert D.max_rounds() == 6
    # A bad value falls back to the default rather than crashing the pass.
    monkeypatch.setenv("HUMANIZE_MAX_ROUNDS", "not-a-number")
    assert D.max_rounds() == 4
