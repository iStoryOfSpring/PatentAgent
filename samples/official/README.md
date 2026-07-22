# 官方格式样例复现说明

本目录只保存固定查询、文献号和来源能力声明，不抓取网页，也不内置任何数据源账号。
可再分发的最小化格式 fixture 位于 `tests/fixtures/official_formats/`；其用途是验证字段
映射、跨源合并和数据血缘，不是构建专利语料库。

Google 样例可用 `google_patents_export.sql` 在 BigQuery 官方公共数据集中重新导出为
JSONL。USPTO 样例应从 Open Data Portal 获取授权全文 XML 与 Patent File Wrapper JSON。
每次导出后将来源 URL、获取日期、Schema 版本、许可说明及 SHA-256 写入
`patentagent-import.json`，再运行：

```bash
python -m scripts.verify_import_manifest /path/to/export
```

三个固定领域为固态电池、碳捕集和工业机器人。文献号只用于回归复现；样例规模不足以
产生行业有效性结论。EPO OPS 与 CNIPA 当前仅记录接口边界，不宣称已经支持。

检索代理标签必须注明来源与限制，可用 `python -m scripts.evaluate_retrieval` 计算
Recall@10/20、nDCG@10 和 MRR。十万条工程压力入口为
`python -m scripts.benchmark_retrieval --records 100000`；合成压力数据不能证明相关性。
