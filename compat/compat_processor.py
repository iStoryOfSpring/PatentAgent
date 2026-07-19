"""PatentSmelter 兼容层（Phase 1 过渡用）

保持旧 PatentProcessor 接口，内部调用新 engine + viz。
旧 UI (app.py) 只需改一行 import 即可正常运行。
"""

import os
from collections import Counter
from types import SimpleNamespace
from typing import Optional

import pandas as pd

from engine import (
    trend, lifecycle, ipc_analysis, nlp, network_analysis,
    country_analysis, roadmap,
)
from engine.preprocessing import prepare_patent_df
from viz import charts


def _make_result(**kwargs):
    """构建兼容的简单对象，供 viz 函数使用"""
    return SimpleNamespace(**kwargs)


class PatentProcessorV2:
    """兼容层: 保持旧 PatentProcessor 的接口签名，
    内部委托给 engine/ 分析函数 + viz/ 图表函数"""

    def __init__(self, df: pd.DataFrame,
                 stopwords: Optional[set[str]] = None) -> None:
        self.df = df
        self.export_dir = './output'
        self.stopwords: set[str] = stopwords or set()
        os.makedirs(self.export_dir, exist_ok=True)

    # ── 数据处理 ──
    def _prepare_columns(self) -> None:
        self.df = prepare_patent_df(self.df)

    # ── 趋势 ──
    def compute_stats(self):
        result = trend.compute_monthly_trend(self.df)
        monthly_df = pd.DataFrame(
            [{"year": int(d["year_month"].split("-")[0]),
              "month": int(d["year_month"].split("-")[1]),
              "count": d["count"]}
             for d in result.data]
        ).sort_values(["year", "month"])
        from engine.trend import compute_ipc_counts
        ipc_data = compute_ipc_counts(self.df)
        ipc_counts = Counter({d["ipc"]: d["count"] for d in ipc_data})
        return monthly_df, ipc_counts

    def visualize_trend(self, monthly_trend: pd.DataFrame) -> None:
        data = [
            {"year_month": f"{int(r['year'])}-{int(r['month']):02d}",
             "count": int(r['count'])}
            for _, r in monthly_trend.iterrows()
        ]
        chart = charts.plot_monthly_trend(_make_result(data=data))
        out_path = os.path.join(self.export_dir, 'monthly_trend.html')
        chart.render(out_path)
        print(f"[UI 生成] 月度趋势图已保存至: {out_path}")

    # ── NLP ──
    def generate_nlp_charts(self) -> None:
        titles = self.df['title'].dropna().tolist()
        result = nlp.compute_word_frequency(titles, self.stopwords, top_n=100)
        if not result.data:
            print("警告：没有足够的标题关键词生成词云。")
            return
        from models.analysis_results import WordFreqResult
        wf = WordFreqResult(
            result_type="word_freq",
            data=[{"word": d["word"], "count": d["count"]} for d in result.data],
        )
        wc = charts.plot_wordcloud(wf, "专利标题关键词云")
        wc_path = os.path.join(self.export_dir, 'title_wordcloud.html')
        wc.render(wc_path)
        print(f"[UI 生成] 标题词云已保存至: {wc_path}")
        bar = charts.plot_wordfreq_bar(wf, "专利标题高频词 Top 20")
        bar_path = os.path.join(self.export_dir, 'title_wordfreq_bar.html')
        bar.render(bar_path)
        print(f"[UI 生成] 标题词频图已保存至: {bar_path}")

    def generate_abstract_nlp_charts(self) -> None:
        abstracts = self.df['abstract'].dropna().tolist()
        if not abstracts:
            print("[跳过] 没有摘要数据")
            return
        result = nlp.compute_word_frequency(abstracts, self.stopwords, top_n=100)
        if not result.data:
            return
        from models.analysis_results import WordFreqResult
        wf = WordFreqResult(
            result_type="word_freq",
            data=[{"word": d["word"], "count": d["count"]} for d in result.data],
        )
        wc = charts.plot_wordcloud(wf, "摘要关键词云")
        wc_path = os.path.join(self.export_dir, 'abstract_wordcloud.html')
        wc.render(wc_path)
        print(f"[UI 生成] 摘要词云已保存至: {wc_path}")
        bar = charts.plot_wordfreq_bar(wf, "摘要高频词 Top 20")
        bar_path = os.path.join(self.export_dir, 'abstract_wordfreq_bar.html')
        bar.render(bar_path)
        print(f"[UI 生成] 摘要词频图已保存至: {bar_path}")

    # ── 国家分布 ──
    def generate_country_pie_charts(self) -> None:
        yearly = country_analysis.compute_country_distribution_by_year(self.df)
        for year_int, data in yearly.items():
            if not data:
                continue
            pie = charts.plot_country_pie(_make_result(data=data), year_int)
            pie_path = os.path.join(
                self.export_dir, f'country_distribution_{year_int}.html',
            )
            pie.render(pie_path)
            print(f"[UI 生成] {year_int}年国家分布饼图已保存至: {pie_path}")

    # ── S 曲线 ──
    def fit_s_curve(self) -> dict:
        yearly = self.df.groupby('year').size().reset_index(name='count')
        yearly = yearly.sort_values('year')
        scurve = lifecycle.fit_logistic_curve(yearly)
        return {
            'years': scurve.years,
            'counts': scurve.counts,
            'cumulative': scurve.cumulative,
            'fitted': scurve.fitted,
            'params': scurve.params,
        }

    def identify_stages(self, s_result: dict) -> list:
        from models.analysis_results import SCurveResult
        scurve = SCurveResult(
            result_type="s_curve",
            years=s_result['years'],
            counts=s_result['counts'],
            cumulative=s_result['cumulative'],
            fitted=s_result['fitted'],
            params=s_result['params'],
        )
        return lifecycle.identify_lifecycle_stages(scurve)

    def visualize_s_curve(self, s_result: dict,
                          stages: list) -> None:
        from types import SimpleNamespace
        data = [{"year": int(y), "count": int(c)}
                for y, c in zip(s_result['years'], s_result['counts'])]
        chart = charts.plot_yearly_trend(
            SimpleNamespace(data=data, result_type="yearly_trend")
        )
        out_path = os.path.join(self.export_dir, 's_curve.html')
        chart.render(out_path)
        print(f"[UI 生成] 年度趋势图已保存至: {out_path}")

    # ── IPC ──
    def generate_ipc_heatmap(self) -> None:
        result = ipc_analysis.compute_ipc_year_matrix(self.df)
        if not result.sections:
            print("[跳过] 没有足够的 IPC 数据生成热力图")
            return
        chart = charts.plot_ipc_heatmap(result)
        out_path = os.path.join(self.export_dir, 'ipc_heatmap.html')
        chart.render(out_path)
        print(f"[UI 生成] IPC热力图已保存至: {out_path}")

    # ── 逐年关键词 ──
    def analyze_text_by_year(self, df: pd.DataFrame,
                             text_col: str = 'title',
                             top_n: int = 10) -> dict:
        result = nlp.compute_yearly_keywords(df, text_col, top_n)
        return {y: [(w, c) for w, c in pairs] for y, pairs in result.data.items()}

    def generate_yearly_keyword_chart(self,
                                      yearly_counts: dict) -> None:
        if not yearly_counts:
            return
        data = {y: [[w, c] for w, c in pairs] for y, pairs in yearly_counts.items()}
        from models.analysis_results import YearlyKeywordsResult
        ykr = YearlyKeywordsResult(result_type="yearly_keywords", data=data)
        chart = charts.plot_yearly_keywords(ykr)
        out_path = os.path.join(self.export_dir, 'yearly_keywords.html')
        chart.render(out_path)
        print(f"[UI 生成] 逐年关键词对比图已保存至: {out_path}")

    # ── 突发词 ──
    def detect_burst_terms(self, yearly_texts: dict,
                           top_n: int = 20) -> list:
        result = nlp.compute_burst_terms(yearly_texts, self.stopwords, top_n)
        return [(d["term"], d["burst"], d["early_freq"], d["late_freq"])
                for d in result.data]

    def visualize_burst_terms(self, burst_data: list) -> None:
        if not burst_data:
            return
        data = [{"term": t, "burst": b, "early_freq": ef, "late_freq": lf}
                for t, b, ef, lf in burst_data]
        from models.analysis_results import BurstTermResult
        btr = BurstTermResult(result_type="burst_terms", data=data)
        chart = charts.plot_burst_terms(btr)
        out_path = os.path.join(self.export_dir, 'burst_terms.html')
        chart.render(out_path)
        print(f"[UI 生成] 突发词图已保存至: {out_path}")

    # ── 气泡图 ──
    def generate_bubble_chart(self, s_result: dict,
                              stages: list) -> None:
        from models.analysis_results import SCurveResult
        scurve = SCurveResult(
            result_type="s_curve",
            years=s_result['years'],
            counts=s_result['counts'],
            cumulative=s_result['cumulative'],
            fitted=s_result['fitted'],
            params=s_result['params'],
        )
        chart = charts.plot_bubble_chart(scurve, stages)
        out_path = os.path.join(self.export_dir, 'bubble_chart.html')
        chart.render(out_path)
        print(f"[UI 生成] 气泡图已保存至: {out_path}")

    # ── 技术路线图 ──
    def generate_roadmap_timeline(self, top_n_per_year: int = 3) -> None:
        result = roadmap.compute_roadmap_data(self.df, top_n_per_year)
        if not result.data:
            print("[跳过] 没有年份数据生成技术路线图")
            return
        chart = charts.plot_roadmap_timeline(result)
        out_path = os.path.join(self.export_dir, 'technology_roadmap.html')
        chart.render(out_path)
        print(f"[UI 生成] 技术路线图已保存至: {out_path}")

    # ── 合作网络 ──
    def analyze_co_occurrence(self) -> 'Counter':
        result = network_analysis.compute_co_occurrence(self.df)
        counts = Counter()
        for e in result.edges:
            counts[(e["source"], e["target"])] = e["weight"]
        return counts

    def build_network(self, edge_weights: 'Counter'):
        if not edge_weights:
            print("没有足够的合作数据来生成网络图。")
            return None
        edges = [
            {"source": src, "target": tgt, "weight": w}
            for (src, tgt), w in edge_weights.items()
        ]
        from models.analysis_results import CoOccurrenceResult
        cor = CoOccurrenceResult(
            result_type="co_occurrence",
            edges=edges,
            node_count=len(set(n for e in edges for n in (e["source"], e["target"]))),
            edge_count=len(edges),
        )
        chart = charts.plot_network(cor)
        out_path = os.path.join(self.export_dir, 'co_applicant_network.html')
        chart.render(out_path)
        print(f"[UI 生成] 网络图已保存至: {out_path}")

    # ── 导出 ──
    def save_dataframe(self, df: pd.DataFrame) -> None:
        out_path = os.path.join(self.export_dir, 'cleaned_patent_data.csv')
        df.to_csv(out_path, index=False, encoding='utf-8-sig')
        print(f"[数据导出] 清洗明细已保存至: {out_path}")
