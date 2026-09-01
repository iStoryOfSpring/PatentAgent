"""Tool: 技术功效矩阵分析（对应书第8-9章）"""

from tools.base import Tool, tool_registry
from storage.datastore import PatentDataStore
from models.analysis_results import TechEffectMatrix


class TechMatrixTool(Tool):
    name = "analyze_tech_matrix"
    description = (
        "从 Derwent 摘要标签构建代理技术功效矩阵，分析技术手段与用途/效果的共现；"
        "低共现仅列为需要逐件复核的候选，不直接解释为创新空白。"
        "适用于用户询问'技术热点'、'空白点'、'功效矩阵'、'创新方向'等关键词。"
    )
    parameters = {
        "top_n": {
            "type": "integer",
            "description": "保留的Top N关键词数量。默认 30。",
            "default": 30,
            "minimum": 5,
            "maximum": 120,
        },
    }
    required_fields = ("abstract",)
    methodology = "从 Derwent NOVELTY/详细描述代理技术手段，从 USE/ADVANTAGE 代理用途与效果；空白仅作复核候选。"
    evidence_level = "derwent_abstract_proxy"

    async def execute(self, storage: PatentDataStore,
                      top_n: int = 30) -> TechEffectMatrix:
        from engine import tech_matrix
        from tools.search_tool import _row_to_pseudo_patent

        # Sample up to 5000 patents for performance (NLP is O(n²) on keywords)
        df = storage.get_columns(['title', 'abstract', 'patent_number', 'year',
                                   'publication_date', 'ipc', 'applicants', 'cited_refs',
                                   'family_members', 'forward_citations'])
        n_sample = min(len(df), 5000)
        if len(df) > n_sample:
            from tools.clustering_tool import _stratified_sample
            df_sample = _stratified_sample(df, n_sample)
        else:
            df_sample = df
        patents = [_row_to_pseudo_patent(row) for _, row in df_sample.iterrows()]

        result = tech_matrix.build_tech_effect_matrix_results(patents, top_n=top_n)
        result.result_metadata.update({
            "sample_size": n_sample, "population_size": len(df),
            "sampled": len(df) > n_sample,
            "sampling_method": "year_ipc_stratified_seed_42" if len(df) > n_sample else "none",
        })
        if len(df) > n_sample:
            result.warnings.append(f"功效矩阵抽样 {n_sample:,}/{len(df):,} 件，使用固定随机种子。")

        return result


tool_registry.register(TechMatrixTool())
