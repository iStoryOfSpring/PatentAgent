"""Tool: NLP 文本分析 — 词云、词频、关键词、突发词"""

from tools.base import Tool, tool_registry
from storage.datastore import PatentDataStore
from engine import nlp
from viz import charts
from models.analysis_results import WordFreqResult, BurstTermResult, YearlyKeywordsResult


class NLPWordCloudTool(Tool):
    name = "generate_wordcloud"
    description = (
        "分析专利标题或摘要中的关键词，生成词云和词频柱状图。"
        "适用于用户询问'热点'、'关键词'、'词云'、'高频词'等。"
    )
    parameters = {
        "text_source": {
            "type": "string",
            "enum": ["title", "abstract"],
            "description": "文本来源: title=标题, abstract=摘要。默认 title。",
        },
    }
    required_fields = ("title",)
    optional_fields = ("abstract",)
    methodology = "Derwent 模板清洗、词形规范化、文档频率过滤后的技术术语频次。"
    evidence_level = "engineering_approximation"

    async def execute(self, storage: PatentDataStore,
                      text_source: str = "title") -> WordFreqResult:
        df = storage.get_all()
        texts = df[text_source].dropna().tolist()
        result = nlp.compute_word_frequency(texts, top_n=100)
        if result.data:
            wc = charts.plot_wordcloud(result, f"专利{text_source}关键词云")
            bar = charts.plot_wordfreq_bar(result, f"专利{text_source}高频词 Top 20")
            result.chart_html = (
                '<div style="display:flex;flex-direction:column;gap:40px">'
                f'<div>{wc.render_embed()}</div>'
                f'<div>{bar.render_embed()}</div>'
                '</div>'
            )
        return result


class BurstTermTool(Tool):
    name = "analyze_burst_terms"
    description = (
        "检测近期增长词——通过平滑的近期/历史文档频率变化，"
        "识别近期快速增长的新兴技术关键词。适用于用户询问'新兴技术'、"
        "'热点方向'、'趋势变化'等。"
    )
    required_fields = ("publication_date", "title", "abstract")
    methodology = "带最小文档支持、加性平滑和时间覆盖检查的近期增长分数；不是 Kleinberg Burst。"
    evidence_level = "engineering_heuristic"

    async def execute(self, storage: PatentDataStore) -> BurstTermResult:
        df = storage.get_columns(['year', 'title', 'abstract'])
        # 保留文档边界，用文档频率抑制重复模板和低支持噪声。
        df['_text'] = df['title'].fillna('') + ' ' + df['abstract'].fillna('')
        yearly_texts = (
            df.groupby('year')['_text']
            .apply(list)
            .to_dict()
        )
        yearly_texts = {int(k): v for k, v in yearly_texts.items()
                        if not (isinstance(k, float) and k != k)}
        result = nlp.compute_burst_terms(yearly_texts, top_n=20)
        if result.data:
            chart_obj = charts.plot_burst_terms(result)
            result.chart_html = chart_obj.render_embed()
        return result


class YearlyKeywordsTool(Tool):
    name = "analyze_yearly_keywords"
    description = (
        "逐年关键词对比分析，生成分组柱状图展示每年 Top 关键词的变化趋势。"
        "适用于用户询问'关键词变化'、'逐年对比'、'热点迁移'等。"
    )
    parameters = {
        "text_source": {
            "type": "string",
            "enum": ["title", "abstract"],
            "description": "文本来源。默认 title。",
        },
    }
    required_fields = ("publication_date", "title")
    optional_fields = ("abstract",)
    methodology = "按公开年份统计经过清洗与最小支持过滤的技术术语。"
    evidence_level = "descriptive_statistics"

    async def execute(self, storage: PatentDataStore,
                      text_source: str = "title") -> YearlyKeywordsResult:
        df = storage.get_all()
        result = nlp.compute_yearly_keywords(df, text_col=text_source, top_n=10)
        if result.data:
            chart_obj = charts.plot_yearly_keywords(result)
            result.chart_html = chart_obj.render_embed()
        return result


tool_registry.register(NLPWordCloudTool())
tool_registry.register(BurstTermTool())
tool_registry.register(YearlyKeywordsTool())
