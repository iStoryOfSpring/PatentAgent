"""专利引证分析（对应书第6章 + von Wartburg et al. 2005 多步引证模型）

Engine 层 — 纯计算:
  - 引证图构建
  - PageRank 核心专利识别
  - 引证路径寻找
  - 技术周期时间计算
  - 引证网络子群识别

Phase 4 新增 (von Wartburg et al. 2005):
  - 直接引文权重 (1/N 归一化)
  - 可达性出度 (Reachability Out-degree, 间接引证链)
  - 书目耦合度 (Bibliographical Coupling, 共享引用)
  - 共享专业化 (Shared Specialization, RO + BC 综合)
"""

from collections import defaultdict
import numpy as np
import re


# ═══════════════════ Phase 1-3: 基础引证分析 ═══════════════════

def build_citation_graph(patents: list,
                         collapse_families: bool = True) -> 'nx.DiGraph':
    """从专利引证关系构建有向图。

    Args:
        patents: FullPatent 列表，需含 backward_citations 字段

    Returns:
        networkx.DiGraph: 默认节点=专利族主公开号，边=引用关系 (A引用B → A→B)
    """
    import networkx as nx
    G = nx.DiGraph()

    member_to_primary: dict[str, str] = {}
    def key(value: str) -> str:
        return re.sub(r'[^A-Z0-9]', '', str(value).upper())
    if collapse_families:
        for patent in patents:
            primary = getattr(patent, 'patent_number', '')
            if not primary:
                continue
            member_to_primary.setdefault(key(primary), primary)
            for number in getattr(patent, 'publication_numbers', []) or []:
                member_to_primary.setdefault(key(number), primary)
            for member in getattr(patent, 'family_members', []) or []:
                member_to_primary.setdefault(key(member), primary)

    for p in patents:
        original_src = getattr(p, 'patent_number', '')
        src = member_to_primary.get(key(original_src), original_src)
        if not src:
            continue
        year = _safe_year(p)
        G.add_node(
            src, title=getattr(p, 'title', '')[:100], year=year,
            family_members=list(getattr(p, 'family_members', []) or []),
        )

        backward = getattr(p, 'backward_citations', []) or []
        for ref in backward:
            target = member_to_primary.get(key(ref), ref)
            if target and target != src:
                G.add_node(target)
                G.add_edge(src, target)

    return G


def compute_pagerank(graph: 'nx.DiGraph') -> dict[str, float]:
    import networkx as nx
    if graph.number_of_nodes() == 0:
        return {}
    scores = nx.pagerank(graph, alpha=0.85, max_iter=100)
    return dict(sorted(scores.items(), key=lambda x: x[1], reverse=True))


def find_citation_paths(graph: 'nx.DiGraph',
                        start: str, end: str,
                        max_depth: int = 5) -> list[list[str]]:
    import networkx as nx
    if start not in graph or end not in graph:
        return []
    try:
        paths = list(nx.all_simple_paths(
            graph, source=start, target=end, cutoff=max_depth))
        return paths[:10]
    except nx.NetworkXNoPath:
        return []


def compute_technology_cycle_time(graph: 'nx.DiGraph') -> float:
    if graph.number_of_nodes() == 0:
        return 0.0
    total_diff = 0.0
    count = 0
    for u, v in graph.edges():
        yu = graph.nodes[u].get('year', 0) or 0
        yv = graph.nodes[v].get('year', 0) or 0
        if yu > 0 and yv > 0:
            total_diff += abs(yu - yv)
            count += 1
    return total_diff / count if count > 0 else 0.0


def identify_technology_clusters(
    graph: 'nx.DiGraph',
) -> dict[str, list[str]]:
    import networkx as nx
    if graph.number_of_nodes() < 3:
        return {"0": list(graph.nodes())}
    undirected = graph.to_undirected()
    try:
        from networkx.algorithms.community import greedy_modularity_communities
        communities = greedy_modularity_communities(undirected)
        return {str(i): list(c) for i, c in enumerate(communities)}
    except ImportError:
        from networkx.algorithms.community import label_propagation_communities
        communities = label_propagation_communities(undirected)
        return {str(i): list(c) for i, c in enumerate(communities)}


def find_key_patents(graph: 'nx.DiGraph', top_k: int = 10) -> list[dict]:
    if graph.number_of_nodes() == 0:
        return []
    pr = compute_pagerank(graph)
    results = []
    for node in graph.nodes():
        results.append({
            "patent_number": node,
            "title": graph.nodes[node].get("title", ""),
            "pagerank": round(pr.get(node, 0), 6),
            "in_degree": graph.in_degree(node),
            "out_degree": graph.out_degree(node),
        })
    results.sort(key=lambda x: (x["pagerank"], x["in_degree"]), reverse=True)
    return results[:top_k]


def build_citation_network_from_patents(patents: list) -> dict:
    graph = build_citation_graph(patents)
    return {
        "graph": graph,
        "key_patents": find_key_patents(graph, top_k=20),
        "tech_cycle_time": compute_technology_cycle_time(graph),
        "communities": identify_technology_clusters(graph),
        "node_count": graph.number_of_nodes(),
        "edge_count": graph.number_of_edges(),
    }


# ═══════════════════ Phase 4: von Wartburg et al. (2005) 多步引证 ═══════════════════

# 审查员引用类别权重（当前 WoS 数据不可用，保留接口）
TYPE_WEIGHTS = {'X': 1.0, 'Y': 0.6, 'A': 0.2, 'DEFAULT': 0.5}




def compute_direct_citation_weight(graph: 'nx.DiGraph',
                                   citing: str, cited: str,
                                   edge_types: dict = None) -> float:
    """计算直接引文权重 P(A→B) = 1/N_A。

    von Wartburg Eq.(1): 如果 A 引用了 N 篇专利，每篇权重 = 1/N。
    如果 edge_types 提供了 X/Y/A 分类，使用 α-type / Σα 加权。
    """
    out_degree = graph.out_degree(citing)
    if out_degree == 0:
        return 0.0
    if not edge_types:
        return 1.0 / out_degree
    # 审查员类别加权
    total_alpha = 0.0
    edge_alpha = TYPE_WEIGHTS['DEFAULT']
    for target in graph.successors(citing):
        et = edge_types.get((citing, target), 'DEFAULT')
        alpha = TYPE_WEIGHTS.get(et, 0.5)
        total_alpha += alpha
        if target == cited:
            edge_alpha = alpha
    return edge_alpha / total_alpha if total_alpha > 0 else 0.0


def compute_reachability_out_degree(graph: 'nx.DiGraph',
                                     target: str,
                                     edge_types: dict = None,
                                     max_depth: int = 3) -> float:
    """计算可达性出度 RO: 沿最多三阶段引证链传播权重。

    von Wartburg Eq.(2): RO = Σ (1/N_A × 1/N_B_i)
    走 2 步: target → first → second

    Returns: 原始的三阶段概率权重和。任何分布变换应在下游评分中完成，
    不能混入论文指标定义。
    """
    ro = 0.0
    frontier = [(target, 1.0, {target})]
    for depth in range(1, max_depth + 1):
        next_frontier = []
        for node, path_weight, visited in frontier:
            for successor in graph.successors(node):
                if successor in visited:
                    continue
                weight = path_weight * compute_direct_citation_weight(
                    graph, node, successor, edge_types,
                )
                # 多阶段信号均计入，并随阶段自然按分支概率衰减。
                ro += weight
                next_frontier.append((successor, weight, visited | {successor}))
        frontier = next_frontier
        if not frontier:
            break

    return ro


def compute_bibliographical_coupling(graph: 'nx.DiGraph',
                                      target: str) -> float:
    """计算书目耦合度 BC: 全网中与该专利共享引用的程度。

    von Wartburg Eq.(3): BC(A,D) = 2 / (N_A + N_D)
    使用倒排索引避免 O(N²) 循环。

    Returns: 所有耦合边强度的总和
    """
    target_succ = set(graph.successors(target))
    if not target_succ:
        return 0.0
    n_target = graph.out_degree(target)
    if n_target == 0:
        return 0.0

    # 倒排索引: 被引用专利 → 引用了它的专利列表
    cited_by = defaultdict(set)
    for node in graph.nodes():
        for succ in graph.successors(node):
            cited_by[succ].add(node)

    # 只对与 target 共享引用的专利计算 BC
    total_bc = 0.0
    seen = set()
    for ref in target_succ:
        co_citers = cited_by.get(ref, set())
        for peer in co_citers:
            if peer == target or peer in seen:
                continue
            seen.add(peer)
            n_peer = graph.out_degree(peer)
            if n_peer > 0:
                total_bc += 2.0 / (n_target + n_peer)

    return total_bc


def compute_shared_specialization(graph: 'nx.DiGraph',
                                   target: str,
                                   edge_types: dict = None) -> dict:
    """计算共享专业化综合得分。

    von Wartburg: SS = RO + BC。论文中的相关性仅来自可变气门领域的
    107 个专利族，不能外推为财务价值或通用质量结论。

    Returns: {"reachability": ..., "bib_coupling": ..., "shared_specialization": ...}
    """
    ro = compute_reachability_out_degree(graph, target, edge_types)
    bc = compute_bibliographical_coupling(graph, target)
    return {
        "patent_number": target,
        "title": graph.nodes[target].get("title", "")[:100],
        "out_degree": graph.out_degree(target),
        "reachability_out_degree": round(ro, 4),
        "bibliographical_coupling": round(bc, 4),
        "shared_specialization": round(ro + bc, 4),
    }


def compute_all_shared_specialization(graph: 'nx.DiGraph') -> dict[str, dict]:
    """一次构建倒排索引并计算全图指标，避免对每个节点重复扫描全网。"""
    cited_by = defaultdict(set)
    successors = {}
    for node in graph.nodes():
        refs = set(graph.successors(node))
        successors[node] = refs
        for ref in refs:
            cited_by[ref].add(node)

    output = {}
    for target, target_refs in successors.items():
        if not target_refs:
            continue
        n_target = len(target_refs)
        peers = set()
        for ref in target_refs:
            peers.update(cited_by[ref])
        peers.discard(target)
        bc = sum(
            2.0 / (n_target + len(successors.get(peer, ())))
            for peer in peers if successors.get(peer)
        )
        ro = compute_reachability_out_degree(graph, target, max_depth=3)
        output[target] = {
            "shared_specialization": round(ro + bc, 4),
            "reachability_out_degree": round(ro, 4),
            "bibliographical_coupling": round(bc, 4),
        }
    return output


def _safe_year(patent) -> int:
    """安全提取专利年份"""
    pub = getattr(patent, 'publication_date', '') or ''
    if pub and len(pub) >= 4:
        try:
            return int(pub[:4])
        except ValueError:
            pass
    return 0


def rank_by_shared_specialization(graph: 'nx.DiGraph',
                                   top_k: int = 20) -> list[dict]:
    """对所有专利计算 SS 并排名。

    Returns: 按 shared_specialization 降序排列的列表
    """
    results = []
    for node in graph.nodes():
        # 只计算有出度（有引用）的专利
        if graph.out_degree(node) > 0:
            ss = compute_shared_specialization(graph, node)
            results.append(ss)

    results.sort(key=lambda x: x["shared_specialization"], reverse=True)
    return results[:top_k]
