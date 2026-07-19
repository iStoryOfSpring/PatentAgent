"""测试: engine/nlp.py"""

import pandas as pd
import pytest

from engine.nlp import (
    compute_word_frequency, compute_yearly_keywords, compute_burst_terms,
    detect_language,
)


@pytest.fixture
def sample_df():
    return pd.DataFrame({
        'year': [2020, 2020, 2021, 2021, 2022],
        'title': [
            '锂电池正极材料制备方法',
            '一种高效的电解液添加剂',
            '固态电池电解质组合物',
            'Solid state battery electrolyte',
            '锂金属负极保护涂层',
        ],
        'abstract': [
            '本发明涉及锂电池领域',
            '电解液添加剂技术方案',
            '固态电解质用于全固态电池',
            'solid electrolyte for batteries',
            '锂金属负极保护技术',
        ],
    })


@pytest.fixture
def sample_yearly_texts():
    return {
        2020: '锂电池 正极 材料 电解液 添加剂',
        2021: '固态电池 电解质 全固态 电池',
        2022: '锂金属 负极 保护 涂层 技术',
    }


class TestDetectLanguage:
    def test_chinese(self):
        assert detect_language('锂电池正极材料及其制备方法') == 'zh'

    def test_english(self):
        assert detect_language('Solid state battery electrolyte') == 'en'

    def test_empty(self):
        assert detect_language('') == 'en'


class TestWordFrequency:
    def test_normal(self, sample_df):
        titles = sample_df['title'].dropna().tolist()
        result = compute_word_frequency(titles)
        assert result.result_type == "word_freq"
        assert len(result.data) > 0
        for d in result.data:
            assert 'word' in d
            assert 'count' in d

    def test_empty(self):
        result = compute_word_frequency([])
        assert len(result.data) == 0

    def test_with_stopwords(self):
        texts = ['一种高效的电池制备方法', '一种电池管理系统']
        result = compute_word_frequency(texts, stopwords={'一种', '的'})
        words = {d['word'] for d in result.data}
        assert '一种' not in words
        assert '的' not in words


class TestYearlyKeywords:
    def test_normal(self, sample_df):
        result = compute_yearly_keywords(sample_df, text_col='title')
        assert result.result_type == "yearly_keywords"
        for year in [2020, 2021, 2022]:
            assert year in result.data

    def test_empty(self):
        df = pd.DataFrame({'year': [], 'title': []})
        result = compute_yearly_keywords(df)
        assert len(result.data) == 0


class TestBurstTerms:
    def test_normal(self, sample_yearly_texts):
        result = compute_burst_terms(sample_yearly_texts, top_n=20)
        assert result.result_type == "burst_terms"

    def test_insufficient_years(self):
        """少于 3 年数据 → 返回空"""
        result = compute_burst_terms({2020: '电池', 2021: '固态 电池'})
        assert len(result.data) == 0

    def test_empty(self):
        result = compute_burst_terms({})
        assert len(result.data) == 0
