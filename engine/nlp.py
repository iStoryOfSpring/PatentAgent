"""NLP 文本分析 — 词频、关键词、突发词检测"""

from collections import Counter, defaultdict

import pandas as pd

from engine.preprocessing import (
    tokenize_text, filter_stopwords, filter_english_nouns,
    STOP_WORDS, detect_language,  # noqa: F401
)
from models.analysis_results import WordFreqResult, YearlyKeywordsResult, BurstTermResult


def compute_word_frequency(texts: list[str],
                           stopwords: set[str] | None = None,
                           top_n: int = 100) -> WordFreqResult:
    """词频统计 — 使用完整流水线（分词 + 停用词 + 词性过滤）"""
    if not texts:
        return WordFreqResult(result_type="word_freq", data=[])
    from engine.preprocessing import extract_keywords
    keyword_counts = extract_keywords(texts, stopwords, top_n, pos_filter=True)
    data = [{"word": w, "count": c} for w, c in keyword_counts]
    return WordFreqResult(result_type="word_freq", data=data)


def compute_yearly_keywords(df: pd.DataFrame,
                            text_col: str = 'title',
                            top_n: int = 10) -> YearlyKeywordsResult:
    """逐年 Top 关键词"""
    sw = STOP_WORDS.copy()
    yearly_words = defaultdict(list)

    for _, row in df.iterrows():
        year = row.get('year')
        text = row.get(text_col, '')
        if pd.isna(year) or not text:
            continue
        words = tokenize_text(str(text).lower())
        words = filter_stopwords(words)
        words = filter_english_nouns(words)
        yearly_words[int(year)].extend(words)

    result = {}
    for year in sorted(yearly_words.keys()):
        top_words = Counter(yearly_words[year]).most_common(top_n)
        result[year] = [[w, c] for w, c in top_words]

    return YearlyKeywordsResult(result_type="yearly_keywords", data=result)


def compute_burst_terms(yearly_texts: dict[int, str],
                        stopwords: set[str] | None = None,
                        top_n: int = 20,
                        min_support: int | None = None) -> BurstTermResult:
    """近期增长分数（非 Kleinberg Burst）。

    输入值可为年度文档列表或兼容旧调用的合并字符串。分数使用文档频率、
    最小支持度和加性平滑，降低只出现一两次的伪热点。
    """
    years = sorted(yearly_texts.keys())
    if len(years) < 3:
        print("[跳过] 年份不足，无法检测突发词（至少需要3年数据）")
        return BurstTermResult(result_type="burst_terms", data=[])

    recent_size = max(1, len(years) // 3)
    early_years = years[:-recent_size]
    late_years = years[-recent_size:]

    def documents(selected_years):
        docs = []
        for year in selected_years:
            value = yearly_texts.get(year, [])
            docs.extend(value if isinstance(value, list) else [str(value)])
        return [d for d in docs if d]

    def document_frequency(docs: list[str]) -> Counter:
        counts = Counter()
        for text in docs:
            words = tokenize_text(text.lower(), min_len=3)
            words = filter_stopwords(words, stopwords)
            words = filter_english_nouns(words)
            counts.update(set(words))
        return counts

    early_docs, late_docs = documents(early_years), documents(late_years)
    early_counts = document_frequency(early_docs)
    late_counts = document_frequency(late_docs)
    total_docs = len(early_docs) + len(late_docs)
    threshold = min_support or max(3, int(total_docs * 0.002))
    alpha = 1.0

    scores = []
    for word in set(list(early_counts.keys()) + list(late_counts.keys())):
        support = early_counts.get(word, 0) + late_counts.get(word, 0)
        if support < threshold:
            continue
        ef = early_counts.get(word, 0) / max(len(early_docs), 1) * 1000
        lf = late_counts.get(word, 0) / max(len(late_docs), 1) * 1000
        baseline = (early_counts.get(word, 0) + alpha) / (len(early_docs) + 2 * alpha)
        recent = (late_counts.get(word, 0) + alpha) / (len(late_docs) + 2 * alpha)
        burst = round(recent / baseline, 2)
        scores.append({
            "term": word,
            "burst": burst,
            "support": support,
            "early_freq": round(ef, 2),
            "late_freq": round(lf, 2),
        })

    scores.sort(key=lambda item: (-item["burst"], -item["support"], item["term"]))
    return BurstTermResult(
        result_type="burst_terms", data=scores[:top_n],
        methodology="近期/历史文档频率比（加性平滑、最小支持度）；不是 Kleinberg Burst。",
        result_metadata={
            "history_years": early_years, "recent_years": late_years,
            "minimum_document_support": threshold,
        },
    )
