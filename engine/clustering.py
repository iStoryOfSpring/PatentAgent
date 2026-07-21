"""专利聚类分析（对应书第5、7章）

Engine 层 — 纯计算:
  - TF-IDF 向量化
  - PCA 降维
  - K-means / 层次聚类
  - 簇中心关键词提取（纯统计）
"""

import numpy as np
from collections import Counter
from models.analysis_results import ClusteringResult


def tfidf_vectorize(texts: list[str]) -> 'np.ndarray':
    """TF-IDF 向量化。

    Returns:
        (n_docs, n_features) 稀疏矩阵转稠密
    """
    if not texts:
        return np.zeros((0, 0))
    from sklearn.feature_extraction.text import TfidfVectorizer
    vectorizer = TfidfVectorizer(max_features=500, stop_words='english')
    return vectorizer.fit_transform(texts).toarray()


def pca_reduce(vectors: 'np.ndarray',
               n_components: int = 2) -> 'np.ndarray':
    """PCA 降维到 2D/3D 用于可视化。

    Returns:
        (n_docs, n_components) 降维坐标
    """
    if vectors.size == 0 or vectors.shape[0] < 2:
        return np.zeros((vectors.shape[0], n_components))
    from sklearn.decomposition import PCA
    n = min(n_components, vectors.shape[1], vectors.shape[0])
    if n < 2:
        return vectors[:, :n_components] if vectors.shape[1] >= n_components else vectors
    pca = PCA(n_components=n)
    return pca.fit_transform(vectors)


def kmeans_cluster(vectors: 'np.ndarray',
                   n_clusters: int = 5) -> tuple['np.ndarray', 'np.ndarray']:
    """K-means 聚类。

    Returns:
        (labels, centroids): labels 形状 (n_docs,)，centroids 形状 (n_clusters, n_features)
    """
    if vectors.size == 0 or vectors.shape[0] < 2:
        return np.zeros(vectors.shape[0], dtype=int), np.zeros((0, vectors.shape[1]))
    from sklearn.cluster import KMeans
    k = min(n_clusters, vectors.shape[0])
    model = KMeans(n_clusters=k, random_state=42, n_init=10)
    labels = model.fit_predict(vectors)
    return labels, model.cluster_centers_


def hierarchical_cluster(vectors: 'np.ndarray',
                         method: str = "ward") -> 'np.ndarray':
    """层次聚类，返回树状图链接矩阵。

    Returns:
        (n-1, 4) linkage matrix
    """
    if vectors.size == 0 or vectors.shape[0] < 2:
        return np.zeros((0, 4))
    from scipy.cluster.hierarchy import linkage
    return linkage(vectors, method=method)


def compute_cluster_centroid_keywords(
    vectors: 'np.ndarray',
    labels: 'np.ndarray',
    vocabulary: list[str],
    top_k: int = 10,
) -> dict[int, list[str]]:
    """基于 TF-IDF 中心词为每个簇生成关键词（纯统计，不用 LLM）。

    Args:
        vectors: TF-IDF 矩阵 (n_docs, n_features)
        labels: 聚类标签 (n_docs,)
        vocabulary: 特征词列表
        top_k: 每簇返回的关键词数量

    Returns:
        {cluster_id: [keyword, ...]}
    """
    if vectors.size == 0 or len(labels) == 0:
        return {}

    unique_labels = sorted(set(int(l) for l in labels))
    result = {}
    for cid in unique_labels:
        mask = labels == cid
        if not mask.any():
            result[cid] = []
            continue
        cluster_vectors = vectors[mask]
        centroid = cluster_vectors.mean(axis=0)
        # 取 centroid 中权重最高的特征索引
        top_indices = np.argsort(centroid)[::-1][:top_k]
        if vocabulary and len(vocabulary) > max(top_indices, default=0):
            keywords = [vocabulary[i] for i in top_indices if i < len(vocabulary)]
        else:
            keywords = [f"feature_{i}" for i in top_indices]
        result[cid] = keywords
    return result


def run_clustering_pipeline(texts: list[str],
                            n_clusters: int | None = None) -> ClusteringResult:
    """TF-IDF 空间聚类；PCA/SVD 仅用于二维展示。

    Returns:
        ClusteringResult
    """
    if not texts:
        return ClusteringResult(
            result_type="clustering",
            labels=[], centroids=[[]],
            cluster_keywords={}, patents_per_cluster={},
        )

    # TF-IDF
    from sklearn.feature_extraction.text import TfidfVectorizer
    vec = TfidfVectorizer(max_features=500, stop_words='english')
    sparse_vectors = vec.fit_transform(texts)
    vectors = sparse_vectors.toarray()
    vocab = vec.get_feature_names_out().tolist()

    # PCA 降维
    from sklearn.decomposition import TruncatedSVD
    n_pca = min(2, vectors.shape[1], vectors.shape[0])
    centroids_2d = []
    if n_pca >= 2:
        algorithm = "arpack" if n_pca < min(sparse_vectors.shape) else "randomized"
        pca = TruncatedSVD(
            n_components=n_pca, algorithm=algorithm, random_state=42,
        )
        reduced = pca.fit_transform(sparse_vectors)
    else:
        reduced = vectors[:, :2] if vectors.shape[1] >= 2 else vectors

    # K-means
    from sklearn.cluster import KMeans
    if n_clusters is None:
        k, selection_diagnostics = _select_cluster_count(sparse_vectors)
    else:
        k = min(n_clusters, vectors.shape[0])
        selection_diagnostics = {"selection": "user_specified"}
    if k >= 2:
        model = KMeans(n_clusters=k, random_state=42, n_init=10)
        labels = model.fit_predict(sparse_vectors)
        for c in range(k):
            mask = labels == c
            if mask.any():
                centroids_2d.append(reduced[mask].mean(axis=0).tolist())
    else:
        labels = np.zeros(vectors.shape[0], dtype=int)
        if reduced.shape[1] >= 2:
            centroids_2d = [reduced.mean(axis=0).tolist()]

    # 关键词
    keywords = compute_cluster_centroid_keywords(vectors, labels, vocab)

    # 每簇专利数
    counts = {}
    for lbl in labels:
        cid = int(lbl)
        counts[cid] = counts.get(cid, 0) + 1

    # 每簇标题 (Tseng 2007 §4.4 CC0.5 方法)
    titles = {}
    for cid in range(k):
        mask = labels == cid
        if mask.any():
            cluster_vecs = vectors[mask]
            titles[int(cid)] = generate_cluster_title(
                cluster_vecs, vocab, int(cid), all_vectors=vectors,
            )

    return ClusteringResult(
        result_type="clustering",
        labels=labels.tolist(),
        centroids=centroids_2d,
        cluster_keywords=keywords,
        patents_per_cluster=counts,
        cluster_titles=titles,
        silhouette_score=_silhouette(sparse_vectors, labels),
        result_metadata={
            "sample_size": len(texts), "sampled": False,
            "selected_k": int(k), "display_reduction": "TruncatedSVD-2D",
            "k_selection": selection_diagnostics,
        },
    )


def _silhouette(vectors, labels) -> float | None:
    if len(set(int(x) for x in labels)) < 2 or len(labels) < 3:
        return None
    from sklearn.metrics import silhouette_score
    sample_size = min(len(labels), 1500)
    return round(float(silhouette_score(
        vectors, labels, metric="cosine", sample_size=sample_size,
        random_state=42,
    )), 4)


def _select_cluster_count(vectors) -> tuple[int, dict]:
    """以平均 cosine silhouette 与多随机种子标签稳定性选择 k。"""
    from sklearn.cluster import KMeans
    from sklearn.metrics import adjusted_rand_score, silhouette_score
    n_docs = vectors.shape[0]
    if n_docs < 4:
        return max(1, min(2, n_docs)), {"selection": "small_sample"}
    upper = min(10, max(2, int(np.sqrt(n_docs))), n_docs - 1)
    best_k, best_score = 2, -1.0
    diagnostics = []
    for k in range(2, upper + 1):
        label_runs = []
        silhouettes = []
        for seed in (42, 52, 62):
            labels = KMeans(
                n_clusters=k, random_state=seed, n_init=5,
            ).fit_predict(vectors)
            label_runs.append(labels)
            if len(set(int(value) for value in labels)) >= 2:
                silhouettes.append(float(silhouette_score(
                    vectors, labels, metric="cosine",
                    sample_size=min(n_docs, 1000), random_state=seed,
                )))
        if not silhouettes:
            diagnostics.append({
                "k": k, "mean_cosine_silhouette": -1.0,
                "adjusted_rand_stability": 0.0, "combined_score": -1.0,
                "invalid": "fewer_than_two_distinct_clusters",
            })
            continue
        stability_values = [
            adjusted_rand_score(label_runs[i], label_runs[j])
            for i in range(len(label_runs))
            for j in range(i + 1, len(label_runs))
        ]
        mean_silhouette = float(np.mean(silhouettes))
        stability = float(np.mean(stability_values)) if stability_values else 1.0
        combined = 0.8 * mean_silhouette + 0.2 * stability
        diagnostics.append({
            "k": k,
            "mean_cosine_silhouette": round(mean_silhouette, 4),
            "adjusted_rand_stability": round(stability, 4),
            "combined_score": round(combined, 4),
        })
        if combined > best_score:
            best_k, best_score = k, combined
    return best_k, {
        "selection": "0.8_mean_cosine_silhouette_plus_0.2_ari_stability",
        "candidates": diagnostics,
    }


# ============================================================
#  Algorithm 2: Cluster Title Generation
#  Tseng, Lin & Lin (2007) §4.4 — Modified Correlation Coefficient CC0.5
#  https://doi.org/10.1016/j.ipm.2006.11.011
# ============================================================

def generate_cluster_title(cluster_vectors: 'np.ndarray',
                            vocabulary: list,
                            cluster_id: int,
                            all_vectors: 'np.ndarray' = None,
                            top_k: int = 2) -> str:
    """用改进相关系数(CC0.5)为聚类簇自动生成概括性标题。

    按 Tseng 等定义，以文档是否包含术语构造 TP/FP/FN/TN，计算 Matthews
    correlation coefficient；CC0.5 只保留簇内文档频率超过 50% 的术语。
    选出 Top-K 个代表性词拼接为簇标题。

    Args:
        cluster_vectors: 该簇的 TF-IDF 向量矩阵 (n_docs_in_cluster × n_features)
        vocabulary: 特征词列表
        cluster_id: 簇编号
        all_vectors: 全部文档的 TF-IDF 向量 (用于计算专一度)
        top_k: 选取的代表性词数量

    Returns:
        簇标题字符串, 如 "Coating Electrode Material"
    """
    import numpy as np

    if cluster_vectors.size == 0 or len(vocabulary) == 0:
        return f"Cluster_{cluster_id}"

    cluster_presence = np.asarray(cluster_vectors > 0, dtype=bool)
    all_presence = np.asarray(
        (all_vectors if all_vectors is not None else cluster_vectors) > 0,
        dtype=bool,
    )
    cluster_docs = cluster_presence.shape[0]
    all_docs = all_presence.shape[0]
    if cluster_docs == 0:
        return f"Cluster_{cluster_id}"

    # 计算每个词的 CC0.5 得分
    scores = []
    for i in range(min(len(vocabulary), cluster_presence.shape[1])):
        tp = int(cluster_presence[:, i].sum())
        if tp <= cluster_docs * 0.5:
            continue
        total_with_term = int(all_presence[:, i].sum())
        fp = max(0, total_with_term - tp)
        fn = cluster_docs - tp
        tn = max(0, all_docs - cluster_docs - fp)
        denominator = np.sqrt(
            (tp + fp) * (tp + fn) * (tn + fp) * (tn + fn)
        )
        cc = ((tp * tn) - (fp * fn)) / denominator if denominator else 0.0
        scores.append((vocabulary[i], float(cc), tp / cluster_docs))

    # 按 CC0.5 排序，取 Top-K
    scores.sort(key=lambda x: -x[1])
    top_keywords = [w for w, _, _ in scores[:top_k]]

    return "_".join(top_keywords) if top_keywords else f"Cluster_{cluster_id}"
