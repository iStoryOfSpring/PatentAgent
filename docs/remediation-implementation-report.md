# PatentAgent 整改实施与验收报告

日期：2026-09-01  
依据：`docs/patent-analysis-remediation-development-plan.md`  
结论：PA-001—PA-016 与 NT-001—NT-008 的工程实现、自动化测试和发布门禁均已落地。真实数据专家验证与法律专业复核仍是运营上线门禁，自动化结果不能替代该门禁。

## 1. 逐项实施结果

| 编号 | 实施结果 | 主要落点 | 自动化证据 |
|---|---|---|---|
| PA-001 | 结构化过滤在排序和 `top_k` 前执行；申请人元数据不再丢失 | `retrieval/search.py`, `retrieval/vector_store.py` | `test_search_filter_contract.py` |
| PA-002 | 内容型 v2 数据指纹、不可变数据版本、缓存键和 schema 迁移 | `storage/datastore.py`, `storage/conversation_store.py` | `test_dataset_fingerprint_contract.py` |
| PA-003 | 所有适用工具统一 `AnalysisScope`；移除隐藏 `__filters`；支持 simple/INPADOC 同族去重并分别记录计数 | `patent_agent/domain/datasets.py`, `tools/base.py`, `agent/orchestrator.py` | `test_analysis_scope_contract.py` |
| PA-004 | 记录实际算法模式、版本和回退原因；未登记算法硬失败 | `patent_agent/domain/tools.py`, `tools/base.py`, `knowledge/tool_evidence.json` | `test_multilingual_search_beta.py`, `verify_methodology_registry` |
| PA-005 | 严格未知参数、上下限、返回字段和登记表契约校验 | `tools/base.py`, `scripts/verify_contracts.py` | `verify_contracts` |
| PA-006 | TF、DF、document ratio 分离；保留文档边界 | `engine/nlp.py` | `test_nlp_document_frequency.py` |
| PA-007 | 中英混合字符 n-gram 聚类、分层抽样、稳定性、代表专利与簇画像 | `engine/clustering.py`, `tools/clustering_tool.py` | `test_multilingual_clustering.py` |
| PA-008 | 低覆盖输出年度主题时间线；门禁通过时输出来源引证支持、时间约束的同族路线草稿 | `tools/roadmap_tool.py` | `test_roadmap_capability_boundary.py` |
| PA-009 | 技术—功效边际数、期望数、lift、Pearson 残差、分类体系与复核检索策略 | `engine/tech_matrix.py` | `test_tech_matrix_statistics.py` |
| PA-010 | 可逆确定性实体规范化，申请人/受让人/当前权利人/发明人角色分离，母子公司仅接受 reviewed 映射 | `engine/entity_resolution.py`, `models/patent.py` | `test_entity_resolution.py`, `test_advanced_tools.py` |
| PA-011 | 缺失不作零值；按可用维度归一、分数区间、可比组、引证窗口和 IPC 小类广度 | `engine/valuation.py`, `tools/valuation_tool.py` | `test_valuation_missingness.py`, `test_metric_semantics.py` |
| PA-012 | 逐记录导入诊断、核算恒等式、隔离清单、解析器版本/哈希与官方格式语义 | `engine/adapters/`, `patent_agent/domain/imports.py` | `test_official_adapters.py`, `validate_official_samples` |
| PA-013 | 专利/工具文本按不可信数据隔离、白名单截断与哈希；任意 HTML 不进入浏览器 | `agent/prompts.py`, `agent/orchestrator.py`, `VisualizationPanel.tsx` | `test_prompt_and_evidence_security.py`, `VisualizationPanel.test.tsx` |
| PA-014 | `evidence://execution/path` 精确解析、标量持久化和数字事实覆盖验证 | `agent/orchestrator.py`, `storage/conversation_store.py` | `test_prompt_and_evidence_security.py`, `test_schema_v7_external_evidence.py` |
| PA-015 | 公开量、CAGR、部分年度、IPC 计数模式、排序分数、地域和专利年龄口径统一 | `engine/trend.py`, `engine/lifecycle.py`, `engine/ipc_analysis.py`, 前端渲染器 | `test_metric_semantics.py` |
| PA-016 | 共享有界线程池/信号量、排队超时、任务状态、内存估算、虚拟表格、分包预算与 10 万记录基线 | `tools/base.py`, `server.py`, `frontend/vite.config.ts`, `scripts/benchmark_tool_runtime.py` | `test_tool_runtime.py`, 前端 build budget |
| NT-001 | 实体组合、角色、指标、年度趋势、IPC 构成和 reviewed 母公司映射 | `tools/advanced_tools.py` | `test_advanced_tools.py` |
| NT-002 | CR3/5/10、HHI、Gini、entropy、有效主体和逐年 bootstrap | `tools/advanced_tools.py` | `test_advanced_tools.py` |
| NT-003 | 内外部边、自引、共引、文献耦合、引证年龄、分布和关键路径门禁 | `tools/advanced_tools.py` | `test_advanced_tools.py` |
| NT-004 | 优先权来源、首次公开局、同族局、指定国和权威当前有效地域分栏 | `tools/advanced_tools.py` | `test_advanced_tools.py` |
| NT-005 | 策略版本、集合差异、已知专利回查、滚雪球、人工标签回流和随机未返回抽样 | `tools/advanced_tools.py` | `test_advanced_tools.py` |
| NT-006 | 权威来源、司法辖区和 as-of 硬门禁；当前状态、年度事件和年费/届满候选分离 | `tools/advanced_tools.py` | `test_advanced_tools.py` |
| NT-007 | 可靠来源门禁、持久化基线、逐事件去重、审计日志和通知阈值 | `tools/advanced_tools.py` | `test_advanced_tools.py` |
| NT-008 | 权利要求语言/版本/状态/依赖硬门禁、依赖树、要素证据、版本差异、产品词面映射和人工复核 UI | `tools/advanced_tools.py`, `VisualizationPanel.tsx` | `test_advanced_tools.py`, `VisualizationPanel.test.tsx` |

## 2. 数据库与外部证据

SQLite schema v7 幂等创建 `record_hashes`、实体与角色、`analysis_scopes`、`evidence_values`、分类体系与标注、检索策略版本、监控运行/事件和 `external_evidence`。`ExternalEvidenceRecord` 要求来源、观测时间、内容哈希和许可说明；同一证据 ID 不允许静默改写成另一内容版本。

任何趋势拐点、竞争行为或市场因果解释只有在同时引用专利证据与外部证据时才可作为有来源的解释，否则必须标记为待验证假设。

## 3. 性能验收

同机 10 万记录修复前后对比：

| 指标 | 修复前 | 修复后 | 变化 |
|---|---:|---:|---:|
| 词法检索峰值 RSS | 1101.03 MiB | 591.27 MiB | -46.30% |
| 整套基线最终峰值 RSS | 1196.72 MiB | 682.19 MiB | -43.00% |
| 词法检索耗时 | 8.2145 s | 8.3329 s | 基本持平（同机运行波动） |

改进来自保留 CSR 稀疏 TF-IDF，不再把 100k×特征矩阵转成稠密数组。完整机器信息与各阶段结果见 `docs/benchmarks/pa016-runtime-100k-2026-09-01.json`。

前端构建分包全部低于 200 KiB gzip：应用主包 137.62 KiB、ECharts 190.35 KiB、zrender 59.26 KiB、可视化业务包 10.54 KiB。`npm run build` 会自动执行体积门禁。

## 4. 最终门禁结果

```text
Python:             208 passed
Frontend tests:     43 passed
Frontend build:     passed; every JS chunk <= 200 KiB gzip
Tool contracts:     24 verified
Method identities:  29 verified across 24 tools
Import manifest:    3 files verified
Official samples:   passed
100k baseline:      passed
```

当前仅剩上游 Starlette `TestClient` 对 httpx 兼容层的弃用警告，不影响运行结果。未完成专利检索专家查全抽样、真实实体映射审核、路线专家验证及权利要求法律复核前，产品仍定位为“专利数据分析与情报初筛助手”，不得宣传为自动 FTO、侵权判定或法律意见系统。
