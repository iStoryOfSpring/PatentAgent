"""Tool: 专利聚类分析（对应书第5、7章）"""

from tools.base import Tool, tool_registry
from storage.datastore import PatentDataStore
from models.analysis_results import ClusteringResult


class ClusteringTool(Tool):
    name = "analyze_clustering"
    description = (
        "对专利文本进行聚类分析，自动发现技术主题群组。"
        "使用 TF-IDF 空间 K-means 聚类，为每个簇生成关键技术关键词。"
        "适用于用户询问'聚类'、'技术主题'、'分组'、'技术方向'等关键词。"
    )
    parameters = {
        "n_clusters": {
            "type": "integer",
            "description": "聚类数量。默认 5，建议根据专利总数调整（100-1000 → 3-5，1000+ → 5-10）。",
            "minimum": 2,
            "maximum": 20,
        },
    }
    required_fields = ("title", "abstract")
    methodology = "TF-IDF 空间 K-means；未指定 k 时以 silhouette 与多次初始化稳定性选择；簇标题使用 Tseng CC0.5 文档相关系数。"
    evidence_level = "paper_method_with_engineering_selection"

    async def execute(self, storage: PatentDataStore,
                      n_clusters: int = None) -> ClusteringResult:
        from engine.clustering import run_clustering_pipeline

        # Get only needed columns — avoids 300MB full copy
        df = storage.get_columns(['title', 'abstract', 'patent_number'])
        n_sample = min(len(df), 3000)
        df_sample = df.sample(n=n_sample, random_state=42) if len(df) > n_sample else df
        texts = (df_sample['title'].fillna('') + ' ' + df_sample['abstract'].fillna('')).tolist()

        result = run_clustering_pipeline(
            texts,
            n_clusters=n_clusters,
        )
        result.result_metadata.update({
            "sample_size": n_sample, "population_size": len(df),
            "sampled": len(df) > n_sample,
        })
        if len(df) > n_sample:
            result.warnings.append(f"聚类使用固定随机种子抽样 {n_sample:,}/{len(df):,} 件。")

        if result.labels and result.cluster_keywords:
            # 构建聚类可视化 HTML
            import json
            keywords_json = json.dumps(result.cluster_keywords, ensure_ascii=False)
            counts_json = json.dumps(result.patents_per_cluster, ensure_ascii=False)

            result_html = [
                '<div style="background:#1a1a2e;color:#e0e0e0;padding:20px;border-radius:8px">',
                '<h3 style="color:#FFD700">专利聚类分析结果</h3>',
                f'<p>聚类数: {len(result.cluster_keywords)} | 总专利: {len(result.labels)}</p>',
                '<table style="width:100%;border-collapse:collapse">',
                '<tr style="background:#333"><th>簇</th><th>数量</th><th>核心关键词</th></tr>',
            ]
            # Use CC0.5 cluster titles (Tseng 2007) if available
            titles = result.cluster_titles
            for cid in sorted(result.cluster_keywords.keys()):
                kw = result.cluster_keywords[cid]
                cnt = result.patents_per_cluster.get(cid, 0)
                title = titles.get(cid, "")
                label = f"{title}" if title else f"Cluster {cid}"
                result_html.append(
                    f'<tr><td style="padding:8px;border:1px solid #555;color:#FFD700;font-weight:bold">{label}</td>'
                    f'<td style="padding:8px;border:1px solid #555">{cnt}</td>'
                    f'<td style="padding:8px;border:1px solid #555;color:#aaa">{", ".join(kw[:8])}</td></tr>'
                )
            result_html.append('</table></div>')
            result.chart_html = '\n'.join(result_html)

        return result


tool_registry.register(ClusteringTool())
