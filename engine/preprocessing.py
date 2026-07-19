"""数据预处理 — 分词、停用词、词性过滤、数据清洗"""

import re
import os
from typing import Optional

import pandas as pd

# jieba is imported lazily in tokenize_text() — loading its 5 MB dictionary
# at module import time adds ~300ms to cold start. Defer until first use.

_jieba = None

# ── 统一停用词表 ──
STOP_WORDS: set[str] = {
    # 中文
    "一种", "装置", "方法", "系统", "设备", "用于", "及其", "基于",
    "的", "和", "与", "在", "中", "其", "及", "了", "进行", "实现",
    "是", "有", "不", "或", "属于", "以及", "被", "通过", "所述",
    "具有", "包括", "该", "至少", "之一", "其中", "之间",
    # 英文冠/介/连词
    "and", "of", "for", "with", "is", "in", "to", "has", "as",
    "at", "on", "by", "from", "which", "the", "are", "that", "whose",
    "a", "an", "or", "be", "been", "its", "each", "other",
    "said", "their", "than", "also", "into", "more", "can", "may",
    # 专利常用动词
    "comprises", "comprising", "provided", "used", "using",
    "involves", "containing", "connected", "including", "disclosed",
    "relates", "obtained", "configured", "adapted", "characterized",
    # 专利文献高频名词
    "system", "method", "device", "unit", "module", "part", "apparatus",
    "process", "material", "structure", "surface", "section", "portion",
    "element", "member", "component", "means", "layer", "region",
    # 摘要专用词
    "novelty", "use", "advantage", "description", "claim", "drawing",
    "independent", "preferred", "example", "figure", "fig",
    # ── 专利说明书高频废词（Phase 1 增强） ──
    "utility", "model", "schematic", "diagram", "shows", "presents",
    "detailed", "where", "thereof", "invention",
    "view", "views", "shown", "described", "herein", "embodiment",
    "embodiments", "according", "present", "related", "including",
    "includes", "include", "comprise", "comprises", "comprising",
    "various", "thereby", "hereby", "thereon", "hereon",
    "drawings", "accompanying", "following", "particularly",
    "without", "therein", "therefrom", "thereto", "hereto",
    "discloses", "disclose", "provides", "provide", "provided",
    "different", "another", "additional", "respectively",
    "preparing", "adding", "forming", "using", "based",
    "configure", "configured", "configure", "comprising",
    "approximately", "substantially", "preferably",
    "diagrammatically", "schematically",
    # ── 法律/说明书套话 ──
    "claimed", "claim", "claims", "obtain", "obtained", "obtaining",
    "according", "accordance", "invention", "inventions",
    "prior", "hereof", "thereof", "wherein", "therein", "herein",
    "hereby", "thereby", "thereon", "hereon", "hereto", "thereto",
    "described", "disclosed", "illustrated", "depicted", "represented",
    "specified", "defined", "referenced", "mentioned", "indicated",
    "determined", "selected", "chosen", "applied", "executed",
    "performed", "conducted", "carried", "implemented", "utilized",
    "employed", "deployed", "arranged", "positioned", "located",
    "disposed", "mounted", "attached", "coupled", "affixed",
    "secured", "fastened", "supported", "held", "received",
    "supplied", "delivered", "fed", "discharged", "removed",
    "extracted", "collected", "gathered", "recovered", "separated",
    "transferred", "transmitted", "conveyed", "directed", "guided",
    "controlled", "regulated", "adjusted", "modified", "changed",
    "altered", "varied", "switched", "toggled", "activated",
    "deactivated", "enabled", "disabled", "initiated", "terminated",
    "generated", "produced", "created", "established", "formed",
    # ── TechNet 补充（USPTO + technical stopwords） ──
    "above-mentioned", "accordingly", "across", "along", "alternatively",
    "among", "and/or", "anything", "anywhere", "better",
    "could", "desired", "disclosure", "due", "easily", "easy", "eg",
    "either", "elsewhere", "enough", "especially", "essentially",
    "et al", "etc", "eventually", "excellent", "finally",
    "furthermore", "good", "he/she", "hence", "him/her", "his/her",
    "however", "ie", "ii", "iii", "instead", "later", "like",
    "little", "many", "meanwhile", "might", "moreover", "must",
    "never", "often", "onto", "otherwise", "overall",
    "particularly", "preferably", "preferred", "present", "rather",
    "relatively", "respectively", "should", "significantly",
    "simply", "since", "sometimes", "specifically", "straight forward",
    "substantially", "such", "suitable", "thereafter", "therebetween",
    "therefor", "therefrom", "thereinto", "thereon", "therethrough",
    "therefore", "therewith", "these", "they", "this", "those",
    "thus", "together", "toward", "towards", "typical", "typically",
    "upon", "vice versa", "via", "whatever", "whereas", "whereat",
    "whereby", "wherever", "whether", "which", "while", "who",
    "whose", "within", "without", "would", "yet",
    # 多词短语的单词拆分
    "et", "al", "straight", "forward", "vice", "versa",
    # ── 语境相关噪音词（在复合词中有意义，但作为孤立 unigram 是废词） ──
    #   body → valve body 有意义，但单独出现毫无价值
    #   set → set point 有意义，但单独出现无价值
    #   high/low → 作为单独维度无归纳意义
    "main", "top", "bottom", "value", "body", "set", "end",
    "high", "low", "through", "product", "good", "state",
    "type", "side", "front", "back", "left", "right",
    "upper", "lower", "inner", "outer", "middle", "center",
    "large", "small", "long", "short", "new", "old",
    "total", "whole", "full", "half", "single", "double",
    "first", "second", "third", "number", "amount",
    "time", "times", "way", "ways", "case", "cases",
    "example", "examples", "result", "results", "point",
    "points", "level", "levels", "rate", "rates",
}

# ── 明显非名词的后缀（降级方案，NLTK 不可用时使用） ──
# 注意: -tion/-sion/-ment/-ness/-ity/-ance/-ence/-ure/-age 是名词后缀，不过滤
_NON_NOUN_SUFFIXES = (
    # 动词
    "ing", "ized", "ised", "fied", "ated", "uted", "cted", "pted",
    # 形容词
    "able", "ible", "less", "ful", "tive", "sive",
    "like", "based", "related", "ical", "ous",
    # 副词
    "ally", "lly", "ward", "wise",
)

# 即使以这些结尾，仍可能是技术名词的例外
_NOUN_EXCEPTIONS = {
    "coating", "heating", "cooling", "casting", "molding", "welding",
    "bearing", "housing", "coupling", "tubing", "piping", "wiring",
    "coating", "sealing", "milling", "drilling", "grinding",
    "spring", "ring", "wing", "thing", "king", "sing",
    "carbon", "silicon", "nylon", "cushion", "fusion",
    "nitrogen", "hydrogen", "oxygen", "halogen", "chalcogen",
    "membrane", "surface", "interface", "lattice", "cathode", "anode",
}


def load_stopwords(filepath: str) -> set[str]:
    if not filepath or not os.path.exists(filepath):
        return set()
    with open(filepath, 'r', encoding='utf-8') as f:
        return {line.strip() for line in f if line.strip()}


def tokenize_text(text: str, min_len: int = 2) -> list[str]:
    """智能分词: 含中文 → jieba，纯英文 → 正则提取"""
    if not text:
        return []
    text = clean_derwent_text(str(text))
    has_chinese = bool(re.search(r'[一-鿿]', text))
    if has_chinese:
        global _jieba
        if _jieba is None:
            import jieba as _j
            _j.setLogLevel(20)
            _jieba = _j
        words = _jieba.lcut(text)
    else:
        words = re.findall(r'[a-zA-Z]{2,}', text.lower())
    return [w for w in words if len(w) >= min_len and _valid_technical_token(w)]


def clean_derwent_text(text: str) -> str:
    """移除 Derwent 摘要模板标签、单位粘连和常见解析碎片。"""
    cleaned = re.sub(
        r'\b(?:NOVELTY|USE|ADVANTAGE|DETAILED DESCRIPTION|DESCRIPTION|ACTIVITY)\s*[:\-]?',
        ' ', text, flags=re.I,
    )
    cleaned = re.sub(r'\bdegrees?[cfk]\b', ' ', cleaned, flags=re.I)
    cleaned = re.sub(r'(?<=\d)(?:degrees?[cfk]|[a-z]{1,3})\b', ' ', cleaned, flags=re.I)
    return re.sub(r'\s+', ' ', cleaned).strip()


def _valid_technical_token(word: str) -> bool:
    if re.search(r'(?:degreesc|degreesf|ium)$', word, re.I):
        return False
    if not re.search(r'[aeiouy]', word, re.I) and len(word) > 4:
        return False
    if re.search(r'(.)\1\1', word):
        return False
    return True


def detect_language(text: str) -> str:
    if not text:
        return 'en'
    return 'zh' if re.search(r'[一-鿿]', text) else 'en'


def filter_stopwords(words: list[str],
                     stopwords: Optional[set[str]] = None) -> list[str]:
    sw = STOP_WORDS.copy()
    if stopwords:
        sw |= stopwords
    return [w for w in words if w not in sw]


def filter_english_nouns(words: list[str]) -> list[str]:
    """词性过滤：只保留英文名词/名词短语。

    优先使用 NLTK POS tagging。NLTK 不可用时使用后缀规则降级方案。
    """
    if not words:
        return []

    # 尝试 NLTK
    try:
        import nltk
        try:
            nltk.data.find('taggers/averaged_perceptron_tagger_eng')
        except LookupError:
            nltk.download('averaged_perceptron_tagger_eng', quiet=True)
        tagged = nltk.pos_tag(words)
        # 只保留名词：NN, NNS, NNP, NNPS
        return [w for w, tag in tagged if tag.startswith('NN') and w not in STOP_WORDS]
    except Exception:
        pass

    # 降级：后缀规则 + 例外表
    result = []
    for w in words:
        if w in STOP_WORDS:
            continue
        if w in _NOUN_EXCEPTIONS:
            result.append(w)
            continue
        # 过滤明显非名词后缀
        is_non_noun = False
        for suffix in _NON_NOUN_SUFFIXES:
            if w.endswith(suffix) and len(w) > len(suffix) + 2:
                is_non_noun = True
                break
        if not is_non_noun:
            result.append(w)

    return result


def extract_keywords(texts: list[str],
                     stopwords: Optional[set[str]] = None,
                     top_n: int = 100,
                     pos_filter: bool = True) -> list[tuple[str, int]]:
    """完整关键词提取流水线：分词 → 停用词 → 词性过滤 → 词频统计。

    Args:
        texts: 文本列表
        stopwords: 额外停用词
        top_n: 返回 Top N
        pos_filter: 是否启用词性过滤（仅英文）

    Returns:
        [(word, count), ...]
    """
    from collections import Counter
    if not texts:
        return []

    all_words = []
    for text in texts:
        words = tokenize_text(text)
        words = filter_stopwords(words, stopwords)
        if pos_filter and detect_language(text) == 'en':
            words = filter_english_nouns(words)
        all_words.extend(words)

    counter = Counter(all_words)
    return counter.most_common(top_n)


def prepare_patent_df(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure year, month, country columns exist. Minimises computation.

    v2.1: Parser now generates 'year' column directly — skip pd.to_datetime
    when year already present. No copy unless columns need adding.
    """
    needs_year = 'year' not in df.columns or df['year'].isna().all()
    needs_month = 'month' not in df.columns
    needs_country = 'country' not in df.columns

    if not (needs_year or needs_month or needs_country):
        return df  # Already prepared — zero work

    # Only copy if we need to add columns
    if needs_year or needs_month:
        df = df.copy() if needs_year else df
        if needs_year and 'date' in df.columns:
            dates = pd.to_datetime(df['date'], errors='coerce')
            if needs_year:
                df['year'] = dates.dt.year
            if needs_month:
                df['month'] = dates.dt.month
        elif needs_year:
            df['year'] = None

    if needs_country:
        df['country'] = (
            df['patent_number']
            .astype(str)
            .str.extract(r'^([A-Za-z]{2})')[0]
            .fillna('Unknown')
            .str.upper()
        )

    return df


# ============================================================
#  Algorithm 1: Multi-word Keyphrase Extraction
#  Tseng, Lin & Lin (2007) §3.3
#  https://doi.org/10.1016/j.ipm.2006.11.011
# ============================================================

def extract_multiword_phrases(texts: list,
                              stopwords: set | None = None,
                              min_freq: int = 3,
                              min_stickiness: float = 0.5,
                              top_n: int = 100) -> list:
    """统计复合短语提取 — 将高频共现单字合并为有意义的复合词。

    Tseng (2007) 算法:
      Stickiness(w1,w2) = freq(w1+w2)^2 / (freq(w1) * freq(w2))
      若 Stickiness > threshold → 合并为复合短语 (如 solid_electrolyte)
    """
    from collections import Counter
    sw = STOP_WORDS.copy()
    if stopwords:
        sw |= stopwords

    unigram_freq = Counter()
    bigram_freq = Counter()
    for text in texts:
        words = tokenize_text(str(text).lower(), min_len=2)
        words = [w for w in words if w not in sw]
        unigram_freq.update(words)
        for i in range(len(words) - 1):
            if words[i] not in sw and words[i + 1] not in sw:
                bigram_freq[(words[i], words[i + 1])] += 1

    phrases = []
    for (w1, w2), cnt in bigram_freq.items():
        if cnt < min_freq:
            continue
        f1 = unigram_freq.get(w1, 1)
        f2 = unigram_freq.get(w2, 1)
        stickiness = (cnt * cnt) / (f1 * f2)
        if stickiness >= min_stickiness:
            phrases.append((f"{w1}_{w2}", cnt, stickiness))

    phrases.sort(key=lambda x: (-x[1], -x[2]))
    seen_words = set()
    result = []
    for phrase, count, _ in phrases:
        parts = phrase.split('_')
        if parts[0] in seen_words and parts[1] in seen_words:
            continue
        result.append((phrase, count))
        seen_words.update(parts)
        if len(result) >= top_n:
            break
    return result


# ============================================================
#  Algorithm 4: Patent Summary Extraction
#  Tseng, Lin & Lin (2007) §3.2
#  https://doi.org/10.1016/j.ipm.2006.11.011
# ============================================================

_CUE_PHRASES = [
    "the present invention", "the invention relates", "comprises",
    "characterized in that", "provided is", "disclosed is",
    "an object of", "advantageously", "preferably",
    "in accordance with", "according to the present",
]


def extract_summary_sentences(text, title="", max_sentences=5):
    """加权句子评分提取专利摘要。

    Score(S) = 0.35 * kw_density + 0.25 * title_match + 0.20 * cue_phrase + 0.20 * position

    其中:
      kw_density = sum(tf_w / avg_tf) / |S|    关键词 TF 密度
      title_match = |S n title_words| / |title_words|
      cue_phrase = 1 if S contains patent cue phrase else 0
      position = 1.0 (首句) / 0.8 (首段) / 0.5 (其他)
    """
    import re
    from collections import Counter

    if not text or not text.strip():
        return []

    sentences = re.split(r'(?<=[.!?])\s+', text.replace('\n', ' '))
    sentences = [s.strip() for s in sentences if len(s.strip()) > 20]
    if not sentences:
        return [str(text)[:500]]

    title_words = set(tokenize_text(str(title).lower(), min_len=3)) if title else set()

    all_words = []
    for s in sentences:
        all_words.extend(tokenize_text(s.lower(), min_len=3))
    word_freq = Counter(all_words)
    if not word_freq:
        return sentences[:max_sentences]
    avg_tf = sum(word_freq.values()) / max(len(word_freq), 1)

    scored = []
    for i, s in enumerate(sentences):
        words = tokenize_text(s.lower(), min_len=3)
        if not words:
            continue
        tf_sum = sum(word_freq.get(w, 0) for w in words)
        kw_density = (tf_sum / max(avg_tf, 1)) / len(words)
        title_overlap = len(set(words) & title_words)
        title_score = title_overlap / max(len(title_words), 1) if title_words else 0
        s_lower = s.lower()
        cue_score = 1.0 if any(cp in s_lower for cp in _CUE_PHRASES) else 0.0
        pos_score = 1.0 if i == 0 else (0.8 if i < 3 else 0.5)
        total = 0.35 * kw_density + 0.25 * title_score + 0.20 * cue_score + 0.20 * pos_score
        scored.append((i, total, s))

    scored.sort(key=lambda x: -x[1])
    selected = scored[:max_sentences]
    selected.sort(key=lambda x: x[0])
    return [s for _, _, s in selected]
