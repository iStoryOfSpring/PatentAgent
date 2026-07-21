"""技术功效矩阵分析（对应书第8-9章）

Engine 层 — 纯计算:
  - 关键词共现矩阵
  - TF-IDF 矩阵
  - 密度热点/空白点识别

Tool 层负责 LLM 增强（聚类标签、创新方向建议）
"""

from collections import Counter
import re
import numpy as np

from models.analysis_results import TechEffectMatrix


def _tokenize_patent_texts(patents) -> list[list[str]]:
    """从专利标题+摘要提取关键词列表（含停用词+词性过滤）"""
    from engine.preprocessing import (
        tokenize_text, filter_stopwords, filter_english_nouns,
    )
    all_keywords = []
    for p in patents:
        title = getattr(p, 'title', '') or ''
        abstract = getattr(p, 'abstract', '') or ''
        text = f"{title} {abstract}"
        words = tokenize_text(text, min_len=2)
        words = filter_stopwords(words)
        words = filter_english_nouns(words)
        all_keywords.append(words)
    return all_keywords


_SECTION_RE = re.compile(
    r'(?P<label>NOVELTY|DETAILED DESCRIPTION|USE|ADVANTAGE)\s*[:\-]?\s*'
    r'(?P<body>.*?)(?=(?:NOVELTY|DETAILED DESCRIPTION|USE|ADVANTAGE|'
    r'DESCRIPTION OF DRAWING\(S\)|TECHNOLOGY FOCUS|EXAMPLE|ACTIVITY)\s*[:\-]|$)',
    re.I | re.S,
)


def _extract_proxy_sections(abstract: str) -> tuple[str, str]:
    """提取 Derwent 摘要中的技术手段段与用途/效果段。"""
    technology, effects = [], []
    for match in _SECTION_RE.finditer(abstract or ""):
        label = match.group("label").upper()
        body = match.group("body").strip()
        if label in {"NOVELTY", "DETAILED DESCRIPTION"}:
            technology.append(body)
        elif label in {"USE", "ADVANTAGE"}:
            effects.append(body)
    return " ".join(technology), " ".join(effects)


def _section_terms(text: str) -> set[str]:
    from engine.preprocessing import tokenize_text, filter_stopwords, filter_english_nouns
    words = filter_stopwords(tokenize_text(text, min_len=3))
    return set(filter_english_nouns(words))


def _proxy_documents(patents: list) -> list[tuple[set[str], set[str]]]:
    docs = []
    for patent in patents:
        technology, effect = _extract_proxy_sections(
            getattr(patent, "abstract", "") or "",
        )
        tech_terms, effect_terms = _section_terms(technology), _section_terms(effect)
        if tech_terms and effect_terms:
            docs.append((tech_terms, effect_terms))
    return docs


def build_co_occurrence_keyword_matrix(
    patents: list,
    top_n: int = 50,
) -> 'np.ndarray':
    """基于关键词共现构建技术-功效初始矩阵（纯统计方法）。

    Args:
        patents: FullPatent 列表
        top_n: 保留的 Top N 高频关键词

    Returns:
        (n_keywords, n_keywords) 的共现矩阵
    """
    all_kw = _tokenize_patent_texts(patents)
    if not all_kw:
        return np.zeros((0, 0))

    # 统计关键词频率
    kw_counter = Counter()
    for kws in all_kw:
        kw_counter.update(set(kws))  # 每篇专利每个词只计一次

    top_keywords = [w for w, _ in kw_counter.most_common(top_n)]
    kw_to_idx = {w: i for i, w in enumerate(top_keywords)}

    matrix = np.zeros((len(top_keywords), len(top_keywords)))
    for kws in all_kw:
        unique = set(kws)
        for w1 in unique:
            for w2 in unique:
                if w1 in kw_to_idx and w2 in kw_to_idx:
                    matrix[kw_to_idx[w1]][kw_to_idx[w2]] += 1

    return matrix


def compute_tfidf_matrix(texts: list[str]) -> 'np.ndarray':
    """TF-IDF 矩阵计算。

    Returns:
        (n_docs, n_features) TF-IDF 矩阵
    """
    if not texts:
        return np.zeros((0, 0))
    from sklearn.feature_extraction.text import TfidfVectorizer
    vectorizer = TfidfVectorizer(max_features=200, stop_words='english')
    return vectorizer.fit_transform(texts).toarray()


def find_density_hotspots(matrix: np.ndarray,
                          threshold: float = None) -> list[tuple[int, int]]:
    """找高密度区域（技术热点）。

    Args:
        matrix: 共现矩阵 (n, n)
        threshold: 密度阈值，默认为均值 + 1 标准差

    Returns:
        [(row_idx, col_idx), ...] 热点坐标列表
    """
    if matrix.size == 0:
        return []
    if threshold is None:
        threshold = float(np.mean(matrix) + np.std(matrix))

    hotspots = []
    n = matrix.shape[0]
    for i in range(n):
        for j in range(i + 1, n):  # 上三角，排除自共现
            if matrix[i, j] > threshold:
                hotspots.append((i, j))
    return sorted(hotspots, key=lambda x: matrix[x[0], x[1]], reverse=True)


def find_density_gaps(matrix: np.ndarray,
                      threshold: float = None) -> list[tuple[int, int]]:
    """找低密度区域（空白点 → 潜在创新方向）。

    Args:
        matrix: 共现矩阵
        threshold: 低密度阈值，默认为最大值的 10%

    Returns:
        [(row_idx, col_idx), ...] 空白点坐标
    """
    if matrix.size == 0:
        return []
    if threshold is None:
        threshold = float(np.max(matrix) * 0.1)

    gaps = []
    n = matrix.shape[0]
    max_val = np.max(matrix)
    for i in range(n):
        for j in range(i + 1, n):
            if matrix[i, j] <= threshold and max_val > 0:
                # 排除真正的零（完全无关联）
                gaps.append((i, j))
    return sorted(gaps, key=lambda x: matrix[x[0], x[1]])  # 从最稀疏开始


def find_gap_recommendations(
    patents: list, top_n: int = 120, top_gaps: int = 10,
) -> list[dict]:
    """从全量关键词空间找出专利数最低的技术组合（真正的空白点）。

    与热力图不同：热力图只展示 Top N 高频词的交叉，空白点扫描则覆盖
    更大的词汇空间，筛出低共现组合供人工复核；零共现不是蓝海证据。

    Returns:
        [{"function": "microalgae", "effect": "valve", "patent_count": 0}, ...]
        按专利数升序排列（最空白的排最前）
    """
    docs = _proxy_documents(patents)
    if not docs:
        return []
    tech_counter, effect_counter = Counter(), Counter()
    for tech_terms, effect_terms in docs:
        tech_counter.update(tech_terms)
        effect_counter.update(effect_terms)
    min_support = max(2, int(len(docs) * 0.002))
    functions = [w for w, c in sorted(
        tech_counter.items(), key=lambda item: (-item[1], item[0]),
    )[:top_n]
                 if c >= min_support]
    effects = [w for w, c in sorted(
        effect_counter.items(), key=lambda item: (-item[1], item[0]),
    )[:top_n]
               if c >= min_support]

    # 构建共现矩阵
    matrix = np.zeros((len(functions), len(effects)), dtype=int)
    for tech_terms, effect_terms in docs:
        for fi, fw in enumerate(functions):
            if fw not in tech_terms:
                continue
            for ej, ew in enumerate(effects):
                if ew in effect_terms:
                    matrix[fi][ej] += 1

    # 收集所有组合（不只是空白点），按专利数升序排列
    gaps = []
    for fi in range(len(functions)):
        for ej in range(len(effects)):
            gaps.append({
                "function": functions[fi],
                "effect": effects[ej],
                "patent_count": int(matrix[fi][ej]),
                "requires_patent_review": True,
                "interpretation": "低共现复核候选，不等同于蓝海",
            })

    gaps.sort(key=lambda item: (
        item["patent_count"], item["function"], item["effect"],
    ))
    return gaps[:top_gaps]


def build_tech_effect_matrix_results(patents: list,
                                     top_n: int = 30) -> TechEffectMatrix:
    """构建完整技术功效矩阵结果。

    Returns:
        TechEffectMatrix(functions, effects, matrix)
    """
    docs = _proxy_documents(patents)
    if not docs:
        return TechEffectMatrix(
            result_type="tech_effect_matrix",
            functions=[], effects=[], matrix=[],
            warnings=["摘要中没有同时可识别的 NOVELTY/描述段和 USE/ADVANTAGE 段，无法构建代理功效矩阵。"],
        )

    tech_counter, effect_counter = Counter(), Counter()
    for tech_terms, effect_terms in docs:
        tech_counter.update(tech_terms)
        effect_counter.update(effect_terms)
    min_support = max(2, int(len(docs) * 0.002))
    per_axis = max(2, top_n // 2)
    functions = [w for w, c in sorted(
        tech_counter.items(), key=lambda item: (-item[1], item[0]),
    )[:per_axis * 2]
                 if c >= min_support][:per_axis]
    effects = [w for w, c in sorted(
        effect_counter.items(), key=lambda item: (-item[1], item[0]),
    )[:per_axis * 2]
               if c >= min_support][:per_axis]
    matrix = np.zeros((len(functions), len(effects)), dtype=int)
    for tech_terms, effect_terms in docs:
        for i, function in enumerate(functions):
            if function not in tech_terms:
                continue
            for j, effect in enumerate(effects):
                if effect in effect_terms:
                    matrix[i, j] += 1

    gap_recommendations = find_gap_recommendations(
        patents, top_n=max(top_n, 60), top_gaps=10,
    )

    return TechEffectMatrix(
        result_type="tech_effect_matrix",
        functions=functions,
        effects=effects,
        matrix=matrix.tolist(),
        gap_recommendations=gap_recommendations,
        methodology="Derwent 摘要代理功效矩阵：NOVELTY/描述段→技术手段，USE/ADVANTAGE→用途与效果。",
        result_metadata={
            "eligible_documents": len(docs), "population_size": len(patents),
            "minimum_document_support": min_support,
        },
        warnings=["零或低共现仅是人工复核候选，不能直接解释为蓝海机会。"],
    )
