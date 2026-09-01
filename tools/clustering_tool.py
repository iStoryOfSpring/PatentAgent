"""Tool: 专利聚类分析（对应书第5、7章）"""

from tools.base import Tool, tool_registry
from storage.datastore import PatentDataStore
from models.analysis_results import ClusteringResult
from patent_agent.domain import AlgorithmExecution


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
            "description": "聚类数量；不填时用 silhouette 与稳定性自动选择。",
            "minimum": 2,
            "maximum": 20,
        },
        "vectorization_mode": {
            "type": "string",
            "enum": ["char_ngram_tfidf", "segmented_word_tfidf"],
            "default": "char_ngram_tfidf",
            "description": "默认字符 n-gram，适合中文和混合语种；分词词项模式用于领域词典已校准的语料。",
        },
    }
    required_fields = ("title", "abstract")
    methodology = "默认字符 n-gram TF-IDF 空间 K-means；采用固定种子的多次随机样本初始化，标签使用分词词项与 Tseng CC0.5；未指定 k 时以 silhouette 与 ARI 稳定性选择。"
    evidence_level = "paper_method_with_engineering_selection"

    async def execute(self, storage: PatentDataStore,
                      n_clusters: int = None,
                      vectorization_mode: str = "char_ngram_tfidf") -> ClusteringResult:
        from engine.clustering import run_clustering_pipeline

        # Get only needed columns — avoids 300MB full copy
        df = storage.get_columns([
            'title', 'abstract', 'patent_number', 'year', 'ipc', 'applicants',
        ])
        n_sample = min(len(df), 3000)
        df_sample = _stratified_sample(df, n_sample) if len(df) > n_sample else df.copy()
        texts = (df_sample['title'].fillna('') + ' ' + df_sample['abstract'].fillna('')).tolist()

        result = run_clustering_pipeline(
            texts,
            n_clusters=n_clusters,
            vectorization_mode=vectorization_mode,
        )
        result.record_ids = df_sample.get('patent_number', '').fillna('').astype(str).tolist()
        representatives: dict[int, list[dict]] = {}
        profiles: dict[int, dict] = {}
        for position, cluster_id in enumerate(result.labels):
            cluster_id = int(cluster_id)
            profile = profiles.setdefault(cluster_id, {
                "record_count": 0, "year_distribution": {},
                "top_applicants": {},
            })
            profile["record_count"] += 1
            row = df_sample.iloc[position]
            year = str(row.get("year", "") or "unknown")
            profile["year_distribution"][year] = profile["year_distribution"].get(year, 0) + 1
            for applicant in str(row.get("applicants", "") or "").split(";"):
                applicant = applicant.strip()
                if applicant:
                    profile["top_applicants"][applicant] = profile["top_applicants"].get(applicant, 0) + 1
            items = representatives.setdefault(int(cluster_id), [])
            if len(items) >= 3:
                continue
            items.append({
                "patent_number": str(row.get("patent_number", "")),
                "title": str(row.get("title", ""))[:160],
            })
        result.representative_patents = representatives
        for cluster_id, profile in profiles.items():
            profile["share"] = round(profile["record_count"] / max(1, len(df_sample)), 6)
            profile["year_distribution"] = [
                {"year": year, "count": count}
                for year, count in sorted(profile["year_distribution"].items())
            ]
            profile["top_applicants"] = [
                {"applicant": applicant, "count": count}
                for applicant, count in sorted(
                    profile["top_applicants"].items(),
                    key=lambda item: (-item[1], item[0]),
                )[:10]
            ]
        result.cluster_profiles = profiles
        result.result_metadata.update({
            "sample_size": n_sample, "population_size": len(df),
            "sampled": len(df) > n_sample,
            "sampling_method": "year_ipc_stratified_seed_42" if len(df) > n_sample else "none",
        })
        result.algorithm_execution = AlgorithmExecution(
            algorithm_id=(
                "multilingual_char_ngram_kmeans_cc05"
                if vectorization_mode == "char_ngram_tfidf"
                else "segmented_word_tfidf_kmeans_cc05"
            ),
            algorithm_version="3.2" if vectorization_mode == "char_ngram_tfidf" else "1.2",
            mode_requested=vectorization_mode,
            mode_used=vectorization_mode,
            parameters={"n_clusters": n_clusters},
        )
        if len(df) > n_sample:
            result.warnings.append(f"聚类使用固定随机种子抽样 {n_sample:,}/{len(df):,} 件。")

        return result


tool_registry.register(ClusteringTool())


def _stratified_sample(df, limit: int):
    """Retain rare year×IPC strata, then fill the remaining sample deterministically."""
    if len(df) <= limit:
        return df.copy()
    work = df.copy()
    import pandas as pd
    years = work.get('year', pd.Series('unknown', index=work.index)).fillna('unknown').astype(str)
    ipc = work.get('ipc', pd.Series('', index=work.index)).fillna('').astype(str).str.split(';').str[0].str[:4]
    work['_stratum'] = years + '|' + ipc
    first = (
        work.sample(frac=1, random_state=42)
        .groupby('_stratum', sort=True, group_keys=False)
        .head(1)
    )
    if len(first) >= limit:
        selected = first.sample(n=limit, random_state=42)
    else:
        remainder = work.drop(index=first.index)
        selected = work.loc[list(first.index) + list(
            remainder.sample(n=limit - len(first), random_state=42).index
        )]
    return selected.drop(columns=['_stratum']).reset_index(drop=True)
