# V3.1 数据与检索验证报告

验证日期：2026-07-22。所有数字都可由仓库脚本重新产生。这里的“官方格式样例”表示
字段结构来自官方公开 Schema/导出格式，不表示三条最小记录构成真实行业基准。

## 导入与跨源合并

固定样例覆盖固态电池、碳捕集和工业机器人；Google JSONL 3 条、USPTO grant XML
1 条、USPTO File Wrapper JSON 1 条。导入共解析 5 条，按规范申请号/公开号合并为
3 条，合并重复 2 条，保留 3 个字段冲突及各来源值；解析失败 0 条。

合并后的字段覆盖：标题、摘要、IPC/CPC、申请号、权利要求均为 100%；后向引证
66.67%；说明书、法律/审查事件与法律状态各 33.33%；外部前向被引和同族成员为
0%。Google family ID 虽存在，不能替代完整同族成员。法律状态均不标记为实时状态。

复现：

```bash
python -m scripts.verify_import_manifest tests/fixtures/official_formats
python -m scripts.validate_official_samples
```

## 代理检索指标

三个英文领域查询在三条样例上的词法基线均将对应固定文献排在第 1 位，因此
Recall@10=1.0、Recall@20=1.0、nDCG@10=1.0、MRR=1.0（3 个查询）。这是一个
解析/排序冒烟基线，样本过小且标签来自固定领域身份，不得解释成专业查新查全率、
FTO 覆盖或法律相关性。MiniLM Beta 指标必须与词法基线分开发布。

真实 MiniLM 冒烟于 Python 3.13.14、sentence-transformers 5.6.0、torch 2.13.0 下完成：
中英混合查询“二氧化碳捕集膜 carbon capture membrane”使用
`paraphrase-multilingual-MiniLM-L12-v2` + lexical RRF，未回退，三条样例中目标
`US11325075B2` 排名第 1；首次生成 3 条记录索引，第二次运行确认 `cache_hit=true`。
这只证明真实模型、索引持久化和混排链路可用，不构成统计有效性结论。可复现命令：

```bash
python -m scripts.verify_minilm
```

## 10 万条工程压力基线

在 Apple/macOS、本地锁定 Python 3.12 环境中运行 100,000 条合成记录：DataFrame
构建 0.134 秒；首次词法建索引并查询 3.810 秒；进程峰值 RSS 约 1.003 GB（平台
报告值 1,002,700,800 字节）。这是单机单次观测，不是跨平台 SLA；合成重复文本也不能
证明真实大型语料的相关性或内存上界。

复现：

```bash
python -m scripts.benchmark_retrieval --records 100000
```

## 尚未验证

- 无专利检索专家标签、正式查新集合或 FTO 结论；
- 无中文大规模样本、跨行业专家一致性或与商业数据库的对照；
- 无 10 万条 MiniLM Beta 索引性能结果；
- 无实时法律状态核验；
- EPO OPS 与 CNIPA 尚无正式适配器。

因此 V3.1 的可成立表述是“官方文件格式可重复导入、跨源字段可追溯、默认算法可复现、
多语言检索提供显式实验入口”，而不是“已经达到专业专利检索或法律分析产品水平”。
