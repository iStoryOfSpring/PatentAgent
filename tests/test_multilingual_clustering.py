"""Chinese and mixed-language clustering uses a multilingual-safe space."""

from engine.clustering import run_clustering_pipeline
from tools.clustering_tool import _stratified_sample


def test_chinese_topics_are_separated_by_char_ngram_clustering():
    battery = [f"固态电池 固体电解质 锂离子 导电材料 {i}" for i in range(8)]
    robots = [f"工业机器人 机械臂 伺服控制 关节驱动 {i}" for i in range(8)]
    result = run_clustering_pipeline(
        battery + robots, n_clusters=2, vectorization_mode="char_ngram_tfidf",
    )
    battery_labels = result.labels[:8]
    robot_labels = result.labels[8:]
    assert max(battery_labels.count(0), battery_labels.count(1)) >= 7
    assert max(robot_labels.count(0), robot_labels.count(1)) >= 7
    assert battery_labels[0] != robot_labels[0]
    assert result.result_metadata["vectorization_mode"] == "char_ngram_tfidf"
    assert any("电池" in word for words in result.cluster_keywords.values() for word in words)


def test_stratified_sample_retains_rare_year_ipc_stratum():
    import pandas as pd

    frame = pd.DataFrame([
        {"year": 2024, "ipc": "H01M", "patent_number": f"A{i}"} for i in range(20)
    ] + [{"year": 2010, "ipc": "C01B", "patent_number": "RARE"}])
    sampled = _stratified_sample(frame, 5)
    assert "RARE" in set(sampled["patent_number"])
