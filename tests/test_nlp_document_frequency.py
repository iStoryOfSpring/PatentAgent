"""Keyword tools must count patent documents rather than repeated tokens."""

import pandas as pd

from engine.nlp import compute_word_frequency, compute_yearly_keywords
from engine.preprocessing import filter_english_nouns


def test_word_frequency_counts_each_document_once():
    result = compute_word_frequency([
        "battery battery battery battery",
        "battery motor",
    ], top_n=20)
    battery = next(item for item in result.data if item["word"] == "battery")
    assert battery["count"] == 2
    assert battery["document_frequency"] == 2
    assert battery["term_frequency"] == 5
    assert battery["document_ratio"] == 1.0
    assert result.result_metadata["metric"] == "document_frequency"


def test_yearly_keywords_use_document_frequency():
    frame = pd.DataFrame({
        "year": [2024, 2024],
        "title": ["battery battery battery", "battery motor"],
    })
    result = compute_yearly_keywords(frame, top_n=10)
    values = dict(result.data[2024])
    assert values["battery"] == 2
    assert result.result_metadata["documents_by_year"][2024] == 2


def test_mixed_chinese_english_terms_are_retained():
    result = compute_word_frequency([
        "固态电池 solid battery electrolyte",
        "固态电池 battery material",
    ], top_n=30)
    terms = {item["word"] for item in result.data}
    assert any("电池" in term for term in terms)
    assert "battery" in terms


def test_missing_nltk_model_does_not_download(monkeypatch):
    import nltk

    def missing(*_args, **_kwargs):
        raise LookupError("missing")

    monkeypatch.setattr(nltk.data, "find", missing)
    monkeypatch.setattr(
        nltk, "download",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("network download")),
    )
    assert filter_english_nouns(["battery", "configured"]) == ["battery"]
