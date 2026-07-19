"""合作关系网络分析（对应书第4、15章）"""

from collections import Counter
from itertools import combinations

import pandas as pd

from models.analysis_results import CoOccurrenceResult, NetworkResult


def compute_co_occurrence(df: pd.DataFrame) -> CoOccurrenceResult:
    """申请人合作共现边权重"""
    edge_weights = Counter()
    for apps in df['applicants'].dropna():
        app_list = [a.strip() for a in apps.split(';') if a.strip()]
        if len(app_list) >= 2:
            for combo in combinations(sorted(app_list), 2):
                edge_weights[combo] += 1

    edges = [
        {"source": src, "target": tgt, "weight": w}
        for (src, tgt), w in edge_weights.items()
    ]
    node_count = len(set(
        n for e in edges for n in (e["source"], e["target"])
    ))
    return CoOccurrenceResult(
        result_type="co_occurrence",
        edges=edges,
        node_count=node_count,
        edge_count=len(edges),
    )


def compute_co_inventor_network(df: pd.DataFrame) -> NetworkResult:
    """发明人合作网络（扩展功能）"""
    edge_weights = Counter()
    # 注意：当前 WoS 格式导出不包含发明人字段（IN 标签）
    for inventors_str in df['inventors'].dropna() if 'inventors' in df.columns else []:
        inv_list = [i.strip() for i in str(inventors_str).split(';') if i.strip()]
        if len(inv_list) >= 2:
            for combo in combinations(sorted(inv_list), 2):
                edge_weights[combo] += 1
    nodes = list(set(n for pair in edge_weights for n in pair))
    edges = [{"source": s, "target": t, "weight": w}
             for (s, t), w in edge_weights.items()]
    return NetworkResult(result_type="network", nodes=nodes, edges=edges)


def compute_citation_network(citations: list[dict]) -> NetworkResult:
    """引证网络分析（Phase 6 完整实现，此处为占位）"""
    return NetworkResult(result_type="network", nodes=[], edges=[])
