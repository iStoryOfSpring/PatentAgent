# PatentAgent 内部工具与算法审计

> 审计日期：2026-09-02。本文是基于当前代码快照的内部实现审计，不是对任何专利、法律状态或商业价值的意见。

## 1. 范围、证据等级与结论摘要

本审计只盘点实际存在、已经注册、被 REST/Agent/MCP 暴露或由生产编排路径调用的 PatentAgent `Tool`。审计范围包括 `tools/`、`engine/`、`retrieval/`、`agent/`、`patent_agent/api/`、`patent_mcp/`、`storage/`、`knowledge/tool_evidence.json` 及相关测试；不读取或摘录 `.env*`、`.patentagent/`、`my_patents/`、`output/`、日志、PDF 和完整专利原文。

当前代码确认：

- 注册表中有 **24 个工具名称**，每个名称在本文有且只有一个主条目。
- `knowledge/tool_evidence.json` 为 24 个名称提供登记算法；IPC 计数有 3 个登记实现，技术路线有 2 个，检索有 2 个，聚类有 2 个，因此共有 **29 个登记算法身份（algorithm_id/version）**。工具数量不等于算法身份数量。
- 工具的确定性计算、规则门禁、数据质量和来源追踪由本地代码完成；生产 Agent 的工具选择、失败参数修正和结果综合会调用配置的 LLM。外部模型内部算法在本文标记为“未确认”。
- 检索默认是词法 TF-IDF；多语言 MiniLM/RRF 是显式 Beta 模式。工具本身不调用在线翻译服务。
- 价值、法律状态、监测和权利要求工具都声明了数据门禁或人工复核边界；代码不应据此推导财务价值、FTO、侵权、有效性、查全率或完整技术谱系。

### 1.1 判定语义

- **已由代码确认**：可由类、函数、注册调用、schema、结果模型、运行时代码或测试直接核对。
- **根据代码推断**：由多个已确认调用点推断出的运行关系或含义，本文会明确说明推断依据。
- **未确认**：代码没有提供足够证据的内容，例如外部模型的内部训练/推理算法、专家查全率、来源服务内部法律状态判定，以及未接入生产主路径的旧编排实现。

### 1.2 清单完整性确认方法

完整性通过以下交叉核对确认，而不是按文件名猜测：

1. 读取 `tools/__init__.py` 的副作用导入列表和每个工具模块末尾的 `tool_registry.register(...)`；以 `ToolRegistry.get_all_names()` 和 `list_tools()` 得到运行时注册集合。
2. 对照 `tools/base.py` 的 `_TOOL_COST_WEIGHTS`、`_TOOL_RESULT_FIELDS`、`Tool.definition` 和 `Tool.to_llm_schema`，确认每个注册名称都有公共 schema、成本和输出字段边界。
3. 对照 `patent_agent/api/routes/tools.py` 的 `GET /api/tools`、`GET /api/capabilities` 和 `POST /api/tools/{tool_name}`，确认 REST 暴露及调用入口。
4. 对照 `agent/orchestrator.py` 的 `_select_tools_with_llm`、`_execute_llm_plan`、`_execute_with_retry` 以及 `server.py` 的聊天流，确认生产 Agent 的选择、执行、重试和综合调用链。
5. 对照 `patent_mcp/server.py` 的 `create_server`、`tools/list` 和 `tools/call`。MCP prompts/list/get 和 Agent 控制 schema 是编排接口，不计入 24 个分析工具；`_ensure_tools_imported` 的显式列表较旧，但 `from tools.base` 先触发 `tools/__init__.py` 的完整副作用导入，运行时注册表仍是本审计的唯一工具集合来源。
6. 对照 `knowledge/tool_evidence.json` 的 `tools` 键、每个主 `algorithm_id/version` 和 `implementations`，并用 `tests/test_quality_contract.py::test_registry_covers_every_registered_tool_and_declares_boundaries`、`tests/test_api_evidence.py::test_tools_api_exposes_single_source_algorithm_registry` 和 `tests/test_mcp_integration.py` 交叉验证。
7. 对照 `tests/test_reproducibility.py::test_all_core_tools_emit_traceable_contract`、`tests/test_advanced_tools.py` 等专项测试，确认结果包含 provenance、algorithm execution、质量和失败边界。本文没有把仅定义但未注册的 engine helper 或旧 strategy chain 误计为公共 Tool。

## 2. 24 个注册工具总览

| # | 注册名称 | 代码入口 | 主登记算法 | 其它登记实现 |
|---:|---|---|---|---|
| 1 | `analyze_patent_trend` | `tools.trend_tool.TrendTool` | `publication_count_trend/2.0` | — |
| 2 | `analyze_lifecycle` | `tools.lifecycle_tool.LifecycleTool` | `publication_growth_summary/2.0` | — |
| 3 | `analyze_ipc_distribution` | `tools.ipc_tool.IPCTool` | `ipc_publication_matrix_assignment_count/2.1` | `unique_patents/2.1`、`family_normalized/2.1` |
| 4 | `generate_wordcloud` | `tools.nlp_tool.NLPWordCloudTool` | `derwent_phrase_frequency/2.0` | — |
| 5 | `analyze_burst_terms` | `tools.nlp_tool.BurstTermTool` | `recent_document_frequency_growth/2.1` | — |
| 6 | `analyze_yearly_keywords` | `tools.nlp_tool.YearlyKeywordsTool` | `yearly_phrase_frequency/2.0` | — |
| 7 | `analyze_co_network` | `tools.network_tool.NetworkTool` | `co_applicant_network/2.1` | — |
| 8 | `analyze_country_distribution` | `tools.country_tool.CountryTool` | `primary_publication_office_count/2.0` | — |
| 9 | `analyze_tech_roadmap` | `tools.roadmap_tool.RoadmapTool` | `annual_theme_timeline/2.2` | `family_citation_route_draft/1.0` |
| 10 | `get_dataset_summary` | `tools.dataset_tool.DatasetSummaryTool` | `dataset_field_audit/2.0` | — |
| 11 | `search_patents` | `tools.search_tool.SearchTool` | `tfidf_cosine_retrieval/2.2` | `multilingual_minilm_rrf_beta/1.0-beta` |
| 12 | `read_patent_details` | `tools.search_tool.ReadPatentDetailsTool` | `structured_record_lookup/2.0` | — |
| 13 | `analyze_tech_matrix` | `tools.tech_matrix_tool.TechMatrixTool` | `derwent_abstract_proxy_te_matrix/2.3` | — |
| 14 | `analyze_clustering` | `tools.clustering_tool.ClusteringTool` | `multilingual_char_ngram_kmeans_cc05/3.2` | `segmented_word_tfidf_kmeans_cc05/1.2` |
| 15 | `analyze_patent_valuation` | `tools.valuation_tool.ValuationTool` | `patent_family_citation_screening/3.1` | — |
| 16 | `analyze_competitor_evolution` | `tools.competitor_evolution_tool.CompetitorEvolutionTool` | `ipc_profile_evolution/2.0` | — |
| 17 | `analyze_entity_portfolio` | `tools.advanced_tools.EntityPortfolioTool` | `deterministic_entity_portfolio/1.1` | — |
| 18 | `analyze_concentration` | `tools.advanced_tools.ConcentrationTool` | `fractional_concentration_metrics/1.1` | — |
| 19 | `analyze_citation_network` | `tools.advanced_tools.CitationNetworkTool` | `internal_external_citation_network/1.1` | — |
| 20 | `analyze_family_geography` | `tools.advanced_tools.FamilyGeographyTool` | `separated_family_geography_counts/1.1` | — |
| 21 | `audit_search_strategy` | `tools.advanced_tools.SearchStrategyAuditTool` | `versioned_lexical_search_set_audit/1.1` | — |
| 22 | `analyze_legal_status` | `tools.advanced_tools.LegalStatusTool` | `dated_authoritative_legal_status_composition/1.1` | — |
| 23 | `monitor_patent_changes` | `tools.advanced_tools.PatentMonitorTool` | `versioned_patent_change_monitor/1.1` | — |
| 24 | `analyze_claim_elements` | `tools.advanced_tools.ClaimElementsTool` | `reversible_claim_element_draft/1.1` | — |

MCP prompts、`request_clarification`、`reuse_session_evidence`、`respond_without_analysis_tool` 等 Agent 控制 schema 不在上表，因为它们不是 `ToolRegistry` 中的分析工具。

## 3. 公共执行边界与生产调用链

### 3.1 `Tool.run` 公共边界（已由代码确认）

所有注册工具继承 `tools.base.Tool`。`Tool.run` 依次执行：

```text
params = validate_params(params)
scope = AnalysisScope.model_validate(params.scope).canonical()
execution_storage = storage.filtered_by_scope(scope)
capability = availability(execution_storage)
拒绝未知参数、缺失必填参数、非法枚举/数值、反向年份和不满足字段/数据门禁的输入
拒绝超过 max_input_records 或 memory_budget_mb 的输入
在 asyncio.timeout 内，将 cpu_bound 工具放入固定大小线程池
result = await execute(execution_storage, **params_without_scope)
校验 result.algorithm_execution 是否属于 evidence_record 的主/实现白名单
补齐 data_quality、provenance、metrics、result_metadata、visualization、warning_records
```

公共入口同时记录数据集快照、版本、内容指纹、scope 前后记录数、同族去重数、采样方式、字段覆盖、算法身份、执行耗时和运行时限制。`Tool.envelope` 只接受带 provenance 的 `AnalysisResult`。缺少可用数据、质量门禁或运行超时会抛出异常，由 REST/Agent/MCP 各自包装；不会静默把缺失字段当作测量到的零。

### 3.2 REST、Agent 与 MCP 调用链

- **REST**：[tools.py](../patent_agent/api/routes/tools.py) 的 `/api/tools` 从同一注册表返回描述、schema、登记算法和 availability；`/api/capabilities` 仅做分组展示；POST 路由解析 session 数据集后调用 `ToolExecutionService.run_tool`，最终进入 `Tool.run`，带 session 时由 `ConversationStore` 记录 execution、provenance 和 metrics。
- **生产 Agent**：`server.py` 的聊天 SSE 进入 `PatentAgentOrchestrator.stream_query`；`_select_tools_with_llm` 将可执行工具 schema 交给 LLM，`_execute_llm_plan`/`_execute_with_retry` 过滤参数、获取信号量、调用 `Tool.run` 并在失败时最多重试参数修正；`AnswerSynthesizer` 先验证 provenance，`_synthesize_tool_roundtrip` 再把去除 chart HTML 的结构化证据交给 LLM 生成报告。LLM 负责选择、参数修正和自然语言综合，不替代工具中的统计代码。
- **MCP**：`patent_mcp.server.create_server` 的 `tools/list` 由 `tool_registry.list_tools()` 生成；`tools/call` 解析名称、通过 `coerce_args` 转换参数、加载 `MCPDataStoreManager` 数据，再调用相同的 `Tool.run`，结果通过 `result_to_mcp_content` 转换。认证中间件只保护可选 HTTP transport；本文不复制 token 或配置值。
- **会话、缓存与持久化**：工具结果可进入 `ConversationStore`；Agent 复用路径以数据集指纹、工具名称、参数和算法版本形成缓存键；检索器按数据集弱引用缓存，Beta 向量索引由 `SearchIndexService` 按内容指纹和模型名落盘；监测工具另有 SQLite 基线。具体行为见各工具条目。

### 3.3 LLM 与确定性代码的边界

`tools/` 目录中的注册工具均由本地 Python、Pandas、NumPy、scikit-learn、NetworkX、SQLite 和本地检索实现完成；工具模块没有把 LLM 结果作为算法身份。可确认的 LLM 边界位于 `agent/orchestrator.py`：工具选择、失败参数修正、长证据分块提取和最终报告综合会调用 `self.llm.chat`。外部 provider 的协议适配由 `patent_agent/application/providers.py::PROTOCOL_MAP`、`ProviderService.build_client` 和 `agent/llm.py::LLMClient` 完成，供应商内部模型如何生成输出在当前代码中**未确认**。

## 4. 工具逐项审计

以下每个主条目都覆盖：入口/注册/调用链、用途、输入输出/数据源、算法、确定性与 LLM 边界、检索/排序/解析/模型/外部服务、校验和降级、状态与持久化、安全风险、测试及证据判定。动态数据值只按来源字段描述，不在文档中复制实际专利正文、会话或个人信息。

### 4.1 `analyze_patent_trend`

- **入口、注册与调用链**：[tools/trend_tool.py](../tools/trend_tool.py) 的 `TrendTool.execute`；模块末尾注册。REST/Agent/MCP 均从 `ToolRegistry` 找到该实例，公共执行经过 `Tool.run`，再调用 `engine.trend.compute_monthly_trend` 或 `compute_yearly_trend`。
- **用途与输入输出**：输入 `chart_type`、可选年份、IPC 和申请人过滤；要求 `publication_date` 覆盖至少 90%，可选 `ipc`/`applicants`。对数据集的公开日期按月或年计数，输出 `MonthlyTrendResult`/`YearlyTrendResult`、summary、时间覆盖和 warnings；来源是 `PatentDataStore.query` 的公开日期及派生年月。
- **算法与边界**：`count(records)` 按 `(year, month)` 或 `year` 分组排序；`audit_publication_time_coverage` 标记尾年缺月、历史缺月和可能的公开滞后。算法身份 `publication_count_trend/2.0`，证据类型 `descriptive_statistic`。这是公开量描述，不是申请量、技术衰退或生命周期判断。
- **确定性、检索和外部服务**：本地 Pandas 确定性聚合；无检索排名、解析模型、LLM 或外部服务。Agent 可在工具外用 LLM 解释结果，但不得改变指标定义。
- **校验、失败降级**：`Tool.validate_params` 校验枚举、年份方向和 scope；字段不足或空数据由 availability 拒绝；尾年不删除，而写入 warning。未知 IPC/主体过滤由 `PatentDataStore.query` 处理。
- **状态、缓存、持久化**：无工具专属状态或缓存；公共 `Tool.run` 只记录 provenance/metrics，带 session 的 REST/Agent 会在会话存储中记录结果。
- **安全与风险**：年份尾部不完整可能造成误读；申请人/IPC 文本来自不可信数据，仅作为筛选值。公开量结果不应被包装成预测、法律或商业结论。
- **测试与证据**：`tests/test_reproducibility.py::test_all_core_tools_emit_traceable_contract`、`::test_key_algorithm_outputs_are_stable`、`tests/test_metric_semantics.py::test_ten_or_eleven_month_tail_is_still_a_partial_calendar_year`；实现和登记由 `tools/trend_tool.py`、`engine/trend.py`、`knowledge/tool_evidence.json` 直接确认。

### 4.2 `analyze_lifecycle`

- **入口、注册与调用链**：[tools/lifecycle_tool.py](../tools/lifecycle_tool.py) 的 `LifecycleTool.execute` → `engine.lifecycle.fit_logistic_curve`，并复用 `engine.trend.audit_publication_time_coverage`。类在模块末尾注册。
- **用途与输入输出**：要求公开日期覆盖至少 90%；无业务参数，输出 `SCurveResult` 的年度 `years/counts`、累计量、同比增长和 CAGR 元数据。数据来自 `PatentDataStore.get_all()` 的派生 `year`。
- **算法与边界**：按年分组；`np.cumsum` 计算累计量；同比为 `(count_i-count_{i-1})/max(count_{i-1},1)`，CAGR 只在跨度和首年计数有效时计算。尽管历史函数名为 `fit_logistic_curve`，当前实现明确不拟合 Logistic，`fitted` 仅为累计值的兼容字段，`params=None`。登记为 `publication_growth_summary/2.0`，不输出萌芽/成长/成熟/衰退或技术成熟度。
- **确定性、检索和外部服务**：Pandas/NumPy 确定性；无检索、模型或 LLM。模型只可能在 Agent 综合层解释。
- **校验、失败降级**：公共字段/空数据/资源限制由 `Tool.run` 处理；不足年份仍返回可计算的年度统计，并把尾年完整性写入 warnings；不再用无统计意义的 Logistic 拟合制造阶段结论。
- **状态、缓存、持久化**：无专属缓存；公共执行追踪和可选会话持久化同 4.1。
- **安全与风险**：累计量、CAGR 和同比依赖收录完整性；尾年或批次缺口可能使增长偏差。`engine.lifecycle.identify_lifecycle_stages` 等旧函数不代表该公共工具重新启用了生命周期阶段。
- **测试与证据**：`tests/test_reproducibility.py::test_all_core_tools_emit_traceable_contract`、`tests/test_quality_contract.py::test_registry_covers_every_registered_tool_and_declares_boundaries`；算法实现见 `engine/lifecycle.py`，登记与禁止结论见 `knowledge/tool_evidence.json`。

### 4.3 `analyze_ipc_distribution`

- **入口、注册与调用链**：[tools/ipc_tool.py](../tools/ipc_tool.py) 的 `IPCTool.execute` → `engine.ipc_analysis.compute_ipc_year_matrix`；结果显式写入 `AlgorithmExecution`。模块末尾注册。
- **用途与输入输出**：输入 `count_mode`：`assignment_count`、`unique_patents` 或 `family_normalized`；要求公开日期和 IPC 覆盖各至少 90%。输出年份×A-H 部级矩阵、有效/无效标注计数、计数口径和 warnings；数据来自公开年、IPC、专利号和（同族模式）`family_id`。
- **算法与替代实现**：`_expand_ipc_sections` 按分号展开 IPC，取首字符 A-H；assignment 保留所有标注，unique 按 `year/section/patent_id` 去重，family 按 `year/section/family_key` 去重，pivot 后按年/部排序。一件专利可贡献多个部级 cell。3 个身份分别是 `ipc_publication_matrix_assignment_count/2.1`、`ipc_publication_matrix_unique_patents/2.1`、`ipc_publication_matrix_family_normalized/2.1`。
- **确定性、检索和外部服务**：本地字符串解析/Pandas pivot，确定性；无检索、LLM 或外部服务。
- **校验、失败降级**：枚举由公共 schema 校验；非 A-H 代码被排除并记录样例；没有有效行返回空矩阵而非虚构值；公共 `Tool.run` 校验算法白名单，防止未登记模式混入。
- **状态、缓存、持久化**：无专属缓存；结果的实际 `algorithm_execution` 和 scope/provenance 由公共层记录，会话路径可持久化。
- **安全与风险**：IPC 是来源标注的描述性口径，不等于排他技术份额；family 去重依赖 `family_id` 覆盖，低覆盖时公共门禁会拒绝或降级。
- **测试与证据**：`tests/test_metric_semantics.py::test_ipc_counts_assignments_patents_and_families_separately`、`::test_ipc_tool_reports_the_algorithm_mode_actually_used`，以及核心可追踪契约测试；实现见 `engine/ipc_analysis.py`，3 个实现见 `knowledge/tool_evidence.json`。

### 4.4 `generate_wordcloud`

- **入口、注册与调用链**：[tools/nlp_tool.py](../tools/nlp_tool.py) 的 `NLPWordCloudTool.execute` → `engine.nlp.compute_word_frequency` → `engine.preprocessing.extract_keyword_statistics`。注册于该模块末尾。
- **用途与输入输出**：输入 `text_source=title|abstract`（默认标题），要求标题覆盖至少 80%，摘要为可选字段；输出 `WordFreqResult` 的术语、文档频率以及元数据中的文档数。数据是当前数据集标题或摘要，不调用全文服务。
- **算法与边界**：预处理执行模板/停用词/词性过滤，按文档统计 unigram/phrase 的 document frequency，并同时保留词频及文档占比诊断；每篇文档对同一术语只贡献一次。身份 `derwent_phrase_frequency/2.0`，依据等级为工程筛查，论文引用只作为方法参考，不能声称完整复现论文文本挖掘或技术价值。
- **确定性、检索和外部服务**：本地预处理和计数；无向量检索、排序模型、LLM、在线翻译或外部 API。
- **校验、失败降级**：公共字段门禁、空文本和资源限制由公共层处理；没有文本时返回空结果；噪声清洗不被当作人工语义标注。
- **状态、缓存、持久化**：无专属持久化；结果可由公共 session execution 存储。
- **安全与风险**：标题/摘要是外部数据，可能包含提示注入或 HTML 字符；应作为不可信文本展示/传递，频率不等于重要性或价值。
- **测试与证据**：`tests/test_reproducibility.py::test_all_core_tools_emit_traceable_contract`、`tests/test_prompt_and_evidence_security.py::test_chunk_extraction_marks_patent_text_as_untrusted_and_records_truncation`；实现见 `engine/nlp.py`/`engine/preprocessing.py`，登记证据见 JSON。

### 4.5 `analyze_burst_terms`

- **入口、注册与调用链**：[tools/nlp_tool.py](../tools/nlp_tool.py) 的 `BurstTermTool.execute` → `engine.nlp.compute_burst_terms`；注册于同一模块。
- **用途与输入输出**：无业务参数，要求公开日期、标题、摘要覆盖门槛；按年份构造文档列表，输出近期增长术语、分数、历史/近期频率和支持度。
- **算法与边界**：按年份分为前段历史和后段近期（约三分之一年份）；对每个术语统计文档频率，最小支持度为 `max(3, floor(total_docs*0.002))`，使用 `alpha=1` 加性平滑，分数为 `recent_smoothed / early_smoothed`，按分数、支持度、术语排序。登记身份 `recent_document_frequency_growth/2.1`；明确不是 Kleinberg Burst，也不是已验证的新兴技术预测。
- **确定性、检索和外部服务**：本地文档词项统计；无检索排名、LLM 或外部服务。
- **校验、失败降级**：公共 availability 额外要求至少 5 个每年 50 件的完整年度；engine 本身年份少于 3 年返回空结果并打印跳过提示；低支持词被过滤，历史/近期年份写入元数据。
- **状态、缓存、持久化**：无专属缓存；公共 provenance、warnings 和可选会话存储有效。
- **安全与风险**：尾年/年度批次不完整会改变“近期”分母；词频增长不能直接解释因果、预测或商业机会。输入摘要不可信，不能作为控制指令。
- **测试与证据**：`tests/test_reproducibility.py::test_all_core_tools_emit_traceable_contract`、`tests/test_quality_contract.py::test_recent_growth_filters_singleton_noise`；算法见 `engine/nlp.py`，年度门禁见 `tools/base.py` 和证据 JSON。

### 4.6 `analyze_yearly_keywords`

- **入口、注册与调用链**：[tools/nlp_tool.py](../tools/nlp_tool.py) 的 `YearlyKeywordsTool.execute` → `engine.nlp.compute_yearly_keywords` → 预处理关键词统计；注册于模块末尾。
- **用途与输入输出**：输入标题或摘要字段，默认标题；要求公开日期和标题覆盖至少 80%；输出每年 Top 术语及文档频率、各年文档数。
- **算法与边界**：将每条记录按公开年放入文档集合，调用 `extract_keyword_statistics`，每篇文档对术语按文档频率计一次，结果按年份稳定排序。身份 `yearly_phrase_frequency/2.0`，显示年度词频变化，不证明因果技术迁移。
- **确定性、检索和外部服务**：本地预处理和计数，无检索/模型/LLM/外部服务。
- **校验、失败降级**：字段门禁和参数枚举由公共层处理；缺年或空文本跳过；尾年完整性由相关数据审计/warnings 提供，不补造缺失月份。
- **状态、缓存、持久化**：无专属状态；公共 execution/session 记录。
- **安全与风险**：术语来自外部专利字段，可能有模板噪声或提示文本；结果不能当作主题因果或价值结论。
- **测试与证据**：核心可追踪契约测试 `tests/test_reproducibility.py::test_all_core_tools_emit_traceable_contract`；实现见 `tools/nlp_tool.py`、`engine/nlp.py` 和 `knowledge/tool_evidence.json`。

### 4.7 `analyze_co_network`

- **入口、注册与调用链**：[tools/network_tool.py](../tools/network_tool.py) 的 `NetworkTool.execute` 读取 `applicant_canonical_names`（存在时覆盖展示列）→ `engine.network_analysis.compute_co_occurrence`；注册于模块末尾。
- **用途与输入输出**：要求申请人字段覆盖至少 90%，并有至少 30 件多申请人记录且多申请人比例至少 1%；输出无向边 `source/target/weight`、节点数、边数和 warnings。数据来自同一记录的申请人列表。
- **算法与边界**：分号分隔申请人，长度至少 2 时对排序后的每一对做组合，边权为共同出现在记录中的次数；名称先经 `entity_resolution.resolve_semicolon_names` 的确定性格式规范化，不做模糊合并。身份 `co_applicant_network/2.1`，只是共现描述，不证明联盟、技术转移或共同发明。
- **确定性、检索和外部服务**：本地字符串规范化、组合和 Counter；无检索、LLM 或外部服务。
- **校验、失败降级**：`Tool._dataset_gate_failures` 在门禁不满足时拒绝；结果没有边时仍返回空网络并说明多申请人证据不足；原始名称与规范化列由数据层保留，避免不可逆替换。
- **状态、缓存、持久化**：无专属缓存；公共执行追踪和 session 记录适用。
- **安全与风险**：实体规范化可能漏合或分裂主体；申请人字段不可信，不能作为身份认证或主体控制指令；网络稀疏时不要过度解读。
- **测试与证据**：`tests/test_quality_contract.py::test_cooperation_availability_enforces_evidence_gate`、`tests/test_entity_resolution.py::test_corporate_suffix_and_unicode_variants_share_stable_entity`，核心契约测试；代码和算法身份见 `tools/network_tool.py`、`engine/network_analysis.py`、证据 JSON。

### 4.8 `analyze_country_distribution`

- **入口、注册与调用链**：[tools/country_tool.py](../tools/country_tool.py) 的 `CountryTool.execute` → `engine.country_analysis.compute_country_distribution`；注册于模块末尾。数据层派生 `country` 来自主公开号前缀。
- **用途与输入输出**：要求 `patent_number` 覆盖至少 90%，可选同族成员；输出首个公开局的地区计数、地理语义元数据和同族字段缺失 warning。
- **算法与边界**：按主公开号/`country` 的来源前缀做 value count；本工具的登记身份 `primary_publication_office_count/2.0`，不是 family market coverage 或 market attractiveness。虽然 engine 还提供按年/趋势 helper，未作为独立注册工具。
- **确定性、检索和外部服务**：本地解析和计数，无检索、模型、LLM 或外部服务。
- **校验、失败降级**：缺少公开号字段由 availability 拒绝；无 `family_members` 只警告，不把主公开号分布升级为市场覆盖；未知/无法解析前缀由数据派生层处理。
- **状态、缓存、持久化**：无专属状态，结果由公共层可选持久化。
- **安全与风险**：公开号局不能证明申请人市场意图、出口意图或当前有效权利；地区字符串来自数据，不应作为权限边界。
- **测试与证据**：`tests/test_reproducibility.py::test_all_core_tools_emit_traceable_contract`、`tests/test_advanced_tools.py::test_citation_and_family_geography_keep_semantics_separate`；实现见 `tools/country_tool.py`、`engine/country_analysis.py` 和证据 JSON。

### 4.9 `analyze_tech_roadmap`

- **入口、注册与调用链**：[tools/roadmap_tool.py](../tools/roadmap_tool.py) 的 `RoadmapTool.execute` → `engine.roadmap.compute_roadmap_data`；当来源门禁通过时调用同文件 `_family_citation_route`。注册于模块末尾。
- **用途与输入输出**：输入每年 Top N；要求公开日期、标题、公开号覆盖分别至少 90%、80%、90%，可选 backward citations、family、priority date。默认输出年度主题、代表专利、代表性分数；通过内部边解析率至少 0.2、family_id 至少 0.5、priority_date 至少 0.8 时，才额外输出同族引证路线节点/边/最长路径草稿。
- **算法与边界**：年度模式对标题分词、停用词过滤，取当年 Top 5 主题；每条记录分数为标题主题覆盖计数加可用后向引证数，同分按公开号稳定排序。路线模式先按 family 分组，以最早 priority_date（再以公开号）选代表，构造 citing→cited 的跨族边，仅保留源数据中可解析、时间不逆行的边，并在 DAG 上调用 `networkx.dag_longest_path`。身份分别为 `annual_theme_timeline/2.2` 和 `family_citation_route_draft/1.0`。
- **确定性、检索和外部服务**：本地分词、排序和 NetworkX 图；无 LLM/外部检索。旧的 `engine.roadmap.build_technology_roadmap` 是更完整的 helper，但公共 Tool 当前调用 `compute_roadmap_data` 与受门禁路线，不能据其存在宣称完整谱系。
- **校验、失败降级**：字段/参数由公共层校验；路线门禁失败时明确回退年度主题时间线；含环时不输出任意破环路径；路线 warning 保留“待复核、非因果谱系”边界。
- **状态、缓存、持久化**：无专属缓存；公共结果含实际算法身份、门禁和 provenance，可进入会话存储。
- **安全与风险**：标题、引证和同族成员是外部数据；路线可能遗漏外部节点和未解析引用。不得把引用路径包装为因果技术演化或完整发明 genealogy。
- **测试与证据**：`tests/test_roadmap_capability_boundary.py::test_public_roadmap_tool_declares_timeline_boundary`、`::test_roadmap_emits_only_source_backed_time_respecting_family_path`，核心可追踪契约测试；实现和双算法登记见 `engine/roadmap.py::compute_roadmap_data`、`tools/roadmap_tool.py::RoadmapTool.execute`、`tools/roadmap_tool.py::_family_citation_route`、证据 JSON。

### 4.10 `get_dataset_summary`

- **入口、注册与调用链**：[tools/dataset_tool.py](../tools/dataset_tool.py) 的 `DatasetSummaryTool.execute`；注册于模块末尾。它读取 `PatentDataStore.get_summary`、`audit`、批次诊断和来源能力，公共层再补充 execution metadata。
- **用途与输入输出**：无业务参数；输出记录总数、年份范围、申请人摘要、字段覆盖、批次完整性、引证/同族/来源能力等结构化审计字段。
- **算法与边界**：计数和覆盖率来自 DataFrame/适配器审计；不是检索或模型算法。登记身份 `dataset_field_audit/2.0`，用于回答“当前数据能否支持某工具”，不推断数据集之外的总体。
- **确定性、检索和外部服务**：本地统计和 manifest 审计；无 LLM、在线服务或排序。
- **校验、失败降级**：空数据和导入失败以结构化状态/覆盖率返回；具体工具的字段门禁仍由 `Tool.availability` 独立执行，不能仅凭摘要绕过。
- **状态、缓存、持久化**：数据加载器和 `PatentDataStore` 持有当前 DataFrame/快照；公共层可将摘要随会话记录，但本工具没有独立写库。
- **安全与风险**：摘要包含来源能力、字段覆盖和批次诊断，展示时不应暴露路径、凭证或原始内容；覆盖率不是数据正确性的保证。
- **测试与证据**：`tests/test_reproducibility.py::test_all_core_tools_emit_traceable_contract`、`tests/test_api_evidence.py::test_data_summary_separates_citation_scopes_and_batch_status`；实现见 `tools/dataset_tool.py`、`storage/datastore.py`、证据 JSON。

### 4.11 `search_patents`

- **入口、注册与调用链**：[tools/search_tool.py](../tools/search_tool.py) 的 `SearchTool.execute` → `_get_searcher` → `retrieval.search.PatentSearcher.hybrid_search` → `retrieval.vector_store`；模块末尾注册。Agent/REST/MCP 均经公共 `Tool.run`。
- **用途与输入输出**：输入 query、top_k、年份、IPC、申请人和 `retrieval_mode`；要求标题、摘要、公开号覆盖。输出命中专利的公开号、截断标题/摘要、申请人、年份、相关性分数、返回数、模式和 warnings。
- **算法与替代实现**：默认 `lexical` 使用 TF-IDF 词/短语空间余弦相似度，结构化过滤在 top-k 前执行，按公开号做确定性 tie-break，身份 `tfidf_cosine_retrieval/2.2`。显式 `multilingual_hybrid_beta` 同时取词法与本地 Sentence-Transformers MiniLM 向量结果，扩大候选后使用 `retrieval.ranking.reciprocal_rank_fusion`，身份 `multilingual_minilm_rrf_beta/1.0-beta`；这是 Beta，不是专家验证查全检索。
- **确定性、检索和外部服务**：词法模式是本地确定性检索；Beta 依赖本地模型和可复用向量索引，模型内部算法**未确认**。代码支持的 `OpenAIEmbedding` 等 provider 适配并不等于本工具默认调用在线 embedding；当前公共默认模式仍为 TF-IDF。无在线翻译服务。
- **校验、失败降级**：query 必填、top_k/年份/枚举由 schema 校验；Beta 任意异常会返回词法结果、标记 `retrieval_mode_used=lexical`、`beta_fallback=true` 和 warning；索引为空时构造空/可用搜索器；字段门禁或资源限制由公共层拒绝。
- **状态、缓存、持久化**：模块级 `WeakKeyDictionary` 按数据集缓存 searcher；词法使用非持久 ANN 状态；Beta 通过 `SearchIndexService` 按数据集内容指纹和模型名保存/加载索引，结果 metadata 标记 cache hit 和索引版本。Agent execution cache 可复用已验证结果。
- **安全与风险**：query、标题、摘要和申请人均是不可信数据；检索结果不是法律新颖性意见、穷尽先前技术检索或向量语义保证。Beta 首次加载本地模型可能失败/耗时，不能把回退隐藏成同一算法。
- **测试与证据**：`tests/test_multilingual_search_beta.py::test_default_mode_remains_lexical`、`::test_beta_fuses_lexical_and_multilingual_rankings`、`::test_beta_failure_is_visible_and_uses_lexical_results`、`::test_vector_index_cache_round_trip_without_pickle`，`tests/test_search_filter_contract.py` 全部过滤测试，核心契约测试；实现见 `tools/search_tool.py`、`retrieval/search.py`、`retrieval/ranking.py`、证据 JSON。

### 4.12 `read_patent_details`

- **入口、注册与调用链**：[tools/search_tool.py](../tools/search_tool.py) 的 `ReadPatentDetailsTool.execute`；注册与 `SearchTool` 相同。生产 Agent 常由检索步骤提供最多 5 个公开号，再由 `_execute_plan` 注入 `patent_numbers`；REST/MCP 可直接调用。
- **用途与输入输出**：输入最多 5 个公开号且要求至少 90% 公开号覆盖；对 `PatentDataStore` DataFrame 做精确 `isin` 查找，输出 `PatentDetailsResult` 中当前源已有的结构化字段、Derwent 摘要、可解析 claims 和 warnings。
- **算法与边界**：仅做精确记录查找；`claims_json` 只有在字符串形如数组且每项通过 `Claim.model_validate` 时才解析，失败则置空；其余字段按分号/换行安全拆分。身份 `structured_record_lookup/2.0`，Derwent 摘要不等于全文，缺失权利要求/法律状态不推断。
- **确定性、检索和外部服务**：DataFrame exact lookup 和 JSON 解析是确定性本地代码；无检索排序、LLM 或外部服务。
- **校验、失败降级**：最多截取 5 个；空列表、空数据或缺公开号字段返回空结果和 warning；非法 claims JSON 丢弃该 claims 而保留记录；公共确认标志 `requires_confirmation=True` 由上层处理。
- **状态、缓存、持久化**：无专属缓存；结果可能写入 session evidence，但公共 evidence 过滤 chart HTML，且不应把完整专利原文再复制到审计文档或日志。
- **安全与风险**：输出包含专利正文片段、权利要求和可能的提示注入，Agent 综合时通过 `_sanitize_untrusted_evidence` 标为不可信；不得当作法律结论或执行指令。
- **测试与证据**：`tests/test_reproducibility.py::test_all_core_tools_emit_traceable_contract`、`tests/test_prompt_and_evidence_security.py::test_chunk_extraction_marks_patent_text_as_untrusted_and_records_truncation`；实现、schema 和精确上限见 `tools/search_tool.py`。

### 4.13 `analyze_tech_matrix`

- **入口、注册与调用链**：[tools/tech_matrix_tool.py](../tools/tech_matrix_tool.py) 的 `TechMatrixTool.execute` 取所需字段、最多抽样 5000 条 → `_row_to_pseudo_patent` → `engine.tech_matrix.build_tech_effect_matrix_results`；注册于模块末尾。
- **用途与输入输出**：输入 `top_n`；要求摘要覆盖至少 80%；输出代理技术手段×用途/效果矩阵、热点/低共现候选、支持度、期望值、lift、Pearson residual 和复核提示。
- **算法与边界**：从 Derwent 摘要规则解析 `NOVELTY`/`DETAILED DESCRIPTION` 为技术段，`USE`/`ADVANTAGE` 为用途/效果段；清洗词项后按文档集合统计边际支持和共现。低共现候选的期望值为 `tech_support*effect_support/population`，残差为 `(observed-expected)/sqrt(expected)`；最低支持 `max(2, floor(n*0.002))`，按负残差及支持度排序。超过 5000 条使用固定种子 42 的年度×IPC 分层抽样。身份 `derwent_abstract_proxy_te_matrix/2.3`。
- **确定性、检索和外部服务**：段落识别、统计、抽样和候选 query 结构由本地代码完成；无 LLM。后续建议字段仅是结构化检索提示，不会自动访问外部检索服务。
- **校验、失败降级**：无同时可识别两类段落时返回空矩阵和 warning；支持度不足不输出任意“机会”结论；大数据集记录样本数和固定种子；公共 schema 校验 top_n 和资源限制。
- **状态、缓存、持久化**：无专属缓存；公共结果、样本 provenance 和 warnings 可持久化。
- **安全与风险**：摘要标签是来源格式代理，不是人工编码；词项、候选专利号和“创新方向”文本来自不可信数据。低共现不能解释为蓝海、创新空白或因果机会。
- **测试与证据**：`tests/test_tech_matrix_statistics.py::test_gap_candidates_use_expected_frequency_not_arbitrary_zero_order`、核心契约测试；实现见 `engine/tech_matrix.py`、`tools/tech_matrix_tool.py`、证据 JSON。

### 4.14 `analyze_clustering`

- **入口、注册与调用链**：[tools/clustering_tool.py](../tools/clustering_tool.py) 的 `ClusteringTool.execute` 最多取 3000 条年度×IPC 分层样本 → `engine.clustering.run_clustering_pipeline`；注册于模块末尾。
- **用途与输入输出**：输入可选 `n_clusters`、`vectorization_mode`（字符 n-gram 或分词词项）；要求标题和摘要覆盖至少 80%，并在公共 gate 中要求至少 100 条有效文本。输出 labels、簇中心二维坐标、簇关键词/标题、簇规模、代表专利、silhouette、ARI 稳定性和抽样元数据。
- **算法与替代实现**：默认以字符 2–5 gram、sublinear TF-IDF 建聚类空间；显式 segmented 模式以 `document_terms` 词项 TF-IDF。K-means 为 `random_state=42,n_init=10,init=random`，标签按首次出现 canonicalize；二维展示用 TruncatedSVD。未指定 k 时在候选 k 上以 `0.8*mean cosine silhouette + 0.2*ARI stability` 选择。解释空间使用词项 TF-IDF，簇标题只保留簇内文档频率大于 50% 的术语并按 CC0.5/Matthews 相关度排序。两种登记身份是 `multilingual_char_ngram_kmeans_cc05/3.2` 与 `segmented_word_tfidf_kmeans_cc05/1.2`。
- **确定性、检索和外部服务**：sklearn、固定随机种子和 canonical labels 使代码路径可复现；无 LLM 或在线模型。名称中的 multilingual 表示字符空间适合混合语种，不表示远程翻译。
- **校验、失败降级**：少于 100 条有效文本不可执行；少样本返回有限结果/诊断；不支持的 vectorization mode 抛错；抽样、silhouette 缺失和 ARI 低稳定性均写入 metadata/warnings。公共层校验 k 范围、内存和算法白名单。
- **状态、缓存、持久化**：无专属模型缓存；结果含固定抽样和算法执行信息，可被 execution cache/session 持久化。
- **安全与风险**：标题摘要可含提示注入或敏感内容，不能作为簇名称的信任边界；聚类是工程分群，不是 ground-truth taxonomy，也不是完整论文流程。簇标题需人工复核。
- **测试与证据**：`tests/test_multilingual_clustering.py::test_chinese_topics_are_separated_by_char_ngram_clustering`、`::test_stratified_sample_retains_rare_year_ipc_stratum`、`tests/test_quality_contract.py::test_k_selection_reports_silhouette_and_stability`，核心稳定性测试；实现见 `engine/clustering.py`、`tools/clustering_tool.py`、证据 JSON。

### 4.15 `analyze_patent_valuation`

- **入口、注册与调用链**：[tools/valuation_tool.py](../tools/valuation_tool.py) 的 `ValuationTool.execute` → `_row_to_pseudo_patent` →（门禁满足时）`engine.citation.build_citation_graph` → `engine.valuation.rank_patents_by_value`；注册于模块末尾。
- **用途与输入输出**：输入 `top_n`、`citation_mode=auto|screening|replication`；要求公开号、公开日期、IPC 各至少 90%，可选同族/后向/前向引证。输出数据集内相对筛查分、区间、可用权重、同来源/同维度可比组、coverage 和 ±20% 单因子敏感性。
- **算法与边界**：默认权重含 shared specialization、family size、IPC breadth、patent age、triadic、backward reference count。数值先按来源或“公开年×IPC 小类”分组百分位；缺失维度保留为空并按可用权重归一化，输出 score interval/confidence。通过 family 覆盖至少 50%、内部边解析率至少 20%、European-style share 至少 80% 时，才把 `SS=RO+BC` 纳入论文适配筛查；RO 沿最多三层 citing→cited 传播，BC 按共享引用的 `2/(N_A+N_D)` 累加。身份 `patent_family_citation_screening/3.1`，始终 `paper_exact=false`。
- **确定性、检索和外部服务**：本地排名、引证图和固定权重敏感性；无 LLM/在线市场数据/财务模型。所引论文只提供适配参考，论文和外部模型内部算法均不等于当前实现。
- **校验、失败降级**：公共字段门禁和 `citation_mode` 枚举；不满足复现门禁或显式 screening 时移除 SS/RO/BC，并 warning；没有同组可比对象则标记不可比较；缺失不当零；资源/执行异常由公共层包装。
- **状态、缓存、持久化**：单次全量构图，无专属持久化；公共 execution cache 需含算法版本、参数和数据集指纹，防止跨版本复用。
- **安全与风险**：名称“valuation”不代表财务估值、市场价值或专利质量；引证覆盖/同族覆盖偏差会改变排名；外部 forward citations 在 WoS 不可用时不是零测量。结果仅供人工筛查。
- **测试与证据**：`tests/test_valuation_missingness.py::test_missing_family_and_references_are_not_scored_as_zero`、`::test_source_and_dimension_signature_define_comparability_group`、`tests/test_quality_contract.py::test_value_tool_downgrades_mixed_open_network_and_excludes_ss`、`tests/test_quality_contract.py::test_von_wartburg_adapted_formula_on_hand_network`；实现见 `engine/valuation.py`、`engine/citation.py`、工具和证据 JSON。

### 4.16 `analyze_competitor_evolution`

- **入口、注册与调用链**：[tools/competitor_evolution_tool.py](../tools/competitor_evolution_tool.py) 的 `CompetitorEvolutionTool.execute` → `engine.competitor_evolution.compute_competitor_evolution`；注册于模块末尾。
- **用途与输入输出**：输入 `top_n`，要求公开日期、申请人、IPC 各至少 90%；输出主要申请人、年度 IPC 画像、主导份额、熵、余弦变化、Top IPC 和规则化趋势摘要。
- **算法与边界**：按申请人和公开年统计前四位 IPC 小类/主组代理，构造年度比例向量；dominant share 为最大分量，entropy 为 `-sum(p*ln p)`，相邻年 shift 为 `1-cosine(prev,current)`。身份 `ipc_profile_evolution/2.0`，代码明确不是 Tang 等 PatentMiner DICT/PBC/HBC。
- **确定性、检索和外部服务**：本地 NumPy/Counter；无检索、LLM 或外部服务。申请人显示可使用数据层 canonical 名称。
- **校验、失败降级**：字段和 top_n 门禁；年度少于两年的申请人不进入 evolution；没有演化记录时返回空列表及摘要；不把 IPC 画像规则摘要当模型生成的战略判断。
- **状态、缓存、持久化**：无专属缓存；公共 provenance/session 记录。
- **安全与风险**：申请人实体、IPC 编码和年度收录存在噪声；“竞争对手动向/研发战略”只来自工程描述，不能推导真实研发实力、意图或市场行为。
- **测试与证据**：`tests/test_reproducibility.py::test_all_core_tools_emit_traceable_contract`、`tests/test_quality_contract.py::test_registry_covers_every_registered_tool_and_declares_boundaries`；实现见 `engine/competitor_evolution.py`、工具和证据 JSON。

### 4.17 `analyze_entity_portfolio`

- **入口、注册与调用链**：[tools/advanced_tools.py](../tools/advanced_tools.py) 的 `EntityPortfolioTool.execute` → `_party_names` → `engine.entity_resolution.resolve_semicolon_names`；底部循环注册。
- **用途与输入输出**：输入实体角色（申请人/受让人/当前权利人/发明人）、指标（公开/同族/授权/前向引证）、Top N 和可选 `reviewed_parent_map`；要求公开号，角色/指标字段另有运行时门禁。输出规范实体、别名、记录/同族/授权/前向引证计数、年度公开、IPC 构成和分辨率元数据。
- **算法与边界**：`normalize_entity_key` 仅做 Unicode NFKC、常见公司后缀、标点/空白规范化；entity_id 是角色+规范 key 的截断 SHA-256，重复实体在同一记录只计一次。母子归并只接受 mapping 中 `reviewed=true`，并以父名生成 parent id。身份 `deterministic_entity_portfolio/1.1`，角色保持分离。
- **确定性、检索和外部服务**：本地规范化、集合计数、Counter；无模糊检索、LLM 或外部服务。前向引证只使用来源明确字段。
- **校验、失败降级**：缺角色/指标来源字段抛出明确 ValueError；未提供 reviewed 映射时不归并并 warning；无法解析的记录计入 unresolved；不自动猜测并购/集团关系。
- **状态、缓存、持久化**：无专属缓存或写库；公共执行 metadata 记录 entity resolution 版本和审计数，可进入会话。
- **安全与风险**：别名和主体名称是用户/来源数据，可能包含个人信息；审计文档只描述机制，不输出实际姓名。自动规范化不是法人身份认证，不能用于控制权限或推导 R&D strength/market share/patent quality。
- **测试与证据**：`tests/test_advanced_tools.py::test_entity_portfolio_and_concentration_use_normalized_entities`、`::test_reviewed_parent_mapping_deduplicates_records`、`tests/test_entity_resolution.py`；实现见 `tools/advanced_tools.py`、`engine/entity_resolution.py` 和证据 JSON。

### 4.18 `analyze_concentration`

- **入口、注册与调用链**：[tools/advanced_tools.py](../tools/advanced_tools.py) 的 `ConcentrationTool.execute`，辅助函数 `_weights`/`_concentration_metrics`；底部注册。
- **用途与输入输出**：输入维度（申请人/IPC/首个公开局）、计数单位（公开/同族）、bootstrap 次数；要求公开号。输出整体和年度 CR3/5/10、HHI、Gini、Shannon entropy、effective entity count、领导者和 HHI 置信区间。
- **算法与边界**：多值维度按每条记录分配 `1/len(values)` 的 fractional weight；`CRn` 为前 n 大份额之和，`HHI=sum(share_i^2)`，Gini 使用排序加权公式，Shannon 为 `-sum(share_i*ln share_i)`，effective entities 为 `exp(entropy)`。同族模式先按 family_id（缺失回退公开号）去重；bootstrap 使用 `np.random.default_rng(42)`，年度使用 `42+year`。身份 `fractional_concentration_metrics/1.1`。
- **确定性、检索和外部服务**：本地 Counter/NumPy；固定种子使 bootstrap 可复现；无检索、LLM 或外部服务。
- **校验、失败降级**：维度/计数模式/采样范围由 schema 校验；空权重返回 0 值结构；样本不足时 bootstrap 区间为 null；分数不把多值归属重复计数为整件。
- **状态、缓存、持久化**：无专属状态；公共执行/session 可存储结果和种子/公式元数据。
- **安全与风险**：集中度是描述统计，不等于竞争行为、市场力或因果市场事件；实体规范化偏差和 family_id 缺失会影响结果；实际主体名不应被审计文档复制。
- **测试与证据**：`tests/test_advanced_tools.py::test_entity_portfolio_and_concentration_use_normalized_entities`、`tests/test_reproducibility.py::test_all_core_tools_emit_traceable_contract`；实现和公式见 `tools/advanced_tools.py`、证据 JSON。

### 4.19 `analyze_citation_network`

- **入口、注册与调用链**：[tools/advanced_tools.py](../tools/advanced_tools.py) 的 `CitationNetworkTool.execute` → `engine.citation.build_citation_graph`、`find_key_patents`、`compute_technology_cycle_time`；底部注册。
- **用途与输入输出**：输入 `top_n`，要求公开号覆盖至少 90%、后向引证至少 20%（其余 family/applicant/date 可选）；输出内部/外部边计数、PageRank 关键节点、共引、书目耦合、引证年龄、自引比例和可选 DAG 路径。
- **算法与边界**：引证方向是 citing→cited；默认按 publication/family alias collapse 节点。内部边两端均在当前集合，外部边只作为未闭合覆盖。PageRank 使用 NetworkX `alpha=.85,max_iter=100`；共引统计同一来源共同引用，书目耦合统计共同被引；引证年龄为公开年份差；内部边解析率至少 0.2 且内部边至少 2 条时才允许路径，DAG 才调用 `dag_longest_path`。身份 `internal_external_citation_network/1.1`。
- **确定性、检索和外部服务**：本地图算法和计数；无 LLM/外部引证补全服务。NetworkX PageRank 数值依赖库实现，但调用参数明确。
- **校验、失败降级**：字段覆盖和公共资源门禁；开放网络门禁不通过时只输出内部描述和 warning，不输出关键路径/影响力结论；图为空返回空关键节点。
- **状态、缓存、持久化**：单次建图无专属缓存；公共 provenance/session 记录内部/外部范围，结果不写外部数据库。
- **安全与风险**：外部引用未解析不应被当作不存在；后向参考文献数量不是影响力，PageRank 也不是普遍“关键专利”；循环图不被强行破环。
- **测试与证据**：`tests/test_advanced_tools.py::test_citation_and_family_geography_keep_semantics_separate`、`tests/test_quality_contract.py::test_audit_separates_external_forward_and_internal_network`、`tests/test_quality_contract.py::test_family_graph_collapses_publication_alias_and_removes_self_loop`；实现见 `engine/citation.py`、工具和证据 JSON。

### 4.20 `analyze_family_geography`

- **入口、注册与调用链**：[tools/advanced_tools.py](../tools/advanced_tools.py) 的 `FamilyGeographyTool.execute`；底部注册。它对 DataFrame 字段做五类计数，不调用 `CitationNetworkTool`。
- **用途与输入输出**：输入 Top N；要求公开号，优先权号、同族成员、法律状态为可选。输出 priority origin、first publication office、family publication offices、designated states、以及在权威当前状态门禁通过时的 active-right jurisdictions。
- **算法与边界**：对优先权号、主公开号、同族成员、指定状态分别提取两字母 office 并独立计数；当前有效权利只在来源声明 `current_legal_status`、状态 as-of 覆盖至少 80%、jurisdiction 覆盖至少 80% 时按状态和 jurisdiction 计数。身份 `separated_family_geography_counts/1.1`，每种 geography semantic 不相互替代。
- **确定性、检索和外部服务**：本地前缀/集合计数；不调用外部法律数据库或 LLM。
- **校验、失败降级**：缺公开号由公共层拒绝；权威状态门禁未通过时 active 列为空并 warning；空 family/priority 不补推断。
- **状态、缓存、持久化**：无专属缓存；公共结果和来源覆盖可持久化。
- **安全与风险**：公开号前缀不等于市场覆盖、出口意图；没有权威状态不能宣称当前有效权利地域。地区/实体值来自外部数据，审计文档不复制。
- **测试与证据**：`tests/test_advanced_tools.py::test_citation_and_family_geography_keep_semantics_separate`；实现见 `tools/advanced_tools.py`、`storage/datastore.py`、证据 JSON。

### 4.21 `audit_search_strategy`

- **入口、注册与调用链**：[tools/advanced_tools.py](../tools/advanced_tools.py) 的 `SearchStrategyAuditTool.execute` → `_get_searcher(storage,"lexical")` → 多版本 `hybrid_search`；底部注册。
- **用途与输入输出**：输入最多 10 个带 query 的 strategy、已知公开号、人工 review labels、随机未返回抽样数、top_k；要求公开号/标题/摘要覆盖。输出每版策略 hash、返回集、增量、移除、独有记录、已知专利回查率和 snowball 候选，以及人工标签和随机审计候选。
- **算法与边界**：所有版本固定使用同一词法 baseline；每版命中集为返回的公开号集合，增量与移除是相邻集合差，unique 是相对于其它版本并集的差；策略 hash 为规范化 JSON 的 SHA-256；known recovery 是已知集合交集比例；可选 family/backward citation 候选做 snowball；随机未返回抽样固定 RNG seed 42。身份 `versioned_lexical_search_set_audit/1.1`，不提供总体查全率。
- **确定性、检索和外部服务**：词法搜索与集合运算本地确定性；无 LLM、在线检索或专家标签自动生成。专家 recall benchmark 明确为 false。
- **校验、失败降级**：策略项必须有非空 query；schema 限制数组/样本；空集合仍返回版本结构；没有人工 review labels 时 precision/recall 指标为 null/false；top_k 是返回上限而非全库计数。
- **状态、缓存、持久化**：复用按数据集缓存的 lexical searcher；本工具不写基线数据库，公共 session 可记录审计结果和参数。
- **安全与风险**：query、标签、公开号和 snowball 候选是外部/用户输入；返回集差异不代表漏检或法律结论，随机候选需要专家逐件复核。
- **测试与证据**：`tests/test_advanced_tools.py::test_search_strategy_audit_reports_returned_sets_not_claimed_recall`、`::test_search_audit_exposes_label_feedback_without_claiming_recall`；实现、固定随机种子和证据见 `tools/advanced_tools.py`。

### 4.22 `analyze_legal_status`

- **入口、注册与调用链**：[tools/advanced_tools.py](../tools/advanced_tools.py) 的 `LegalStatusTool.execute`；`LegalStatusTool._dataset_gate_failures` 在公共 availability 之外增加来源能力、as-of、jurisdiction 和 adapter identity 门禁；底部注册。
- **用途与输入输出**：输入 Top N；要求法律状态覆盖至少 80%，并要求来源声明当前法律状态能力、as-of/jurisdiction 覆盖各至少 80%。输出状态构成、按年/事件码统计、司法辖区构成、过期记录数和未来一年年费/届满事件候选。
- **算法与边界**：当前 `legal_status` 先做字符串归一并计数；`legal_events_json` 经 JSON 解析后按事件年/码计数；日期在当前时点后 366 天且描述含 fee/annuity/renew/expire 等词的记录列为候选。登记 `dated_authoritative_legal_status_composition/1.1`，`deterministic=False` 因为当前时间参与 stale/未来窗口判断；当前状态和历史事件严格分开。
- **确定性、检索和外部服务**：本地状态字段和事件 JSON 解析；工具不自动查询外部法律服务，来源权威性只由 `storage.audit().source_capabilities` 声明门禁确认，来源内部判定未确认。
- **校验、失败降级**：不满足权威能力/as-of/jurisdiction/adapter 门禁则不可执行；事件 JSON 非法则按空事件处理；状态未知保留 `unknown`；warning 明确跨局不可直接比较，不能输出 FTO/有效性意见。
- **状态、缓存、持久化**：无专属缓存；公共 execution/session 记录结果；实时 `now` 使相同数据未来重跑可能产生不同 stale/候选结果。
- **安全与风险**：法律状态可能影响重大决策，必须核验来源、司法辖区和 as-of；事件 description 是不可信数据，不可作为指令；本文不记录真实来源 URL/header/config。
- **测试与证据**：`tests/test_advanced_tools.py::test_legal_status_gate_requires_authoritative_source_capability`、`::test_monitor_and_claim_tools_enforce_launch_gates`；实现和登记见 `tools/advanced_tools.py`、`knowledge/tool_evidence.json`。

### 4.23 `monitor_patent_changes`

- **入口、注册与调用链**：[tools/advanced_tools.py](../tools/advanced_tools.py) 的 `PatentMonitorTool.execute` → `_get_searcher(storage,"lexical")` 取得当前返回集 → 选择字段 hash → SQLite baseline/run/event/audit 表；底部注册。它要求确认且 `deterministic=False`。
- **用途与输入输出**：输入 strategy id/version、query、top_k、是否更新基线、通知策略和最小事件数；要求公开号、标题、摘要覆盖，且来源 adapter 可识别。输出新增、未再返回、同族/引证/前向引证/法律事件/申请人字段变化事件，及 strategy hash、run id、baseline 状态和通知判定。
- **算法与边界**：词法检索得到当前 snapshot；对每条记录选定字段做排序 JSON 的 SHA-256；基线按 `(strategy_id,strategy_version)` 持久化，集合差生成新增/移除，公共记录字段逐字段比对生成变化；run_id 为 strategy/version/dataset fingerprint 的 SHA-256，event_id 为 run/type/patent 的 SHA-256，`INSERT OR IGNORE` 去重。身份 `versioned_patent_change_monitor/1.1`，变化预警不是侵权或法律风险事件。
- **确定性、检索和外部服务**：当前搜索和 hash 规则本地；同一 fingerprint 生成稳定 run/event id，但数据源更新、当前返回集和用户选择会改变结果；无 LLM/在线监控服务。
- **校验、失败降级**：策略参数和通知枚举由 schema 校验；不可识别 adapter 由 gate 拒绝；已有基线不存在时不通知；通知仅按 all_changes/threshold 规则，更新基线失败由 SQLite 异常上抛。配置的数据库路径由运行环境决定，本文不记录实际路径值。
- **状态、缓存、持久化**：这是唯一显式 SQLite 监测持久化工具，建 `monitor_baselines`、`monitor_runs`、`monitor_events`、`monitor_audit_log`；baseline 可替换，事件和运行用幂等插入；searcher 复用数据集缓存。
- **安全与风险**：query hash/字段 hash 降低明文暴露但不消除敏感性；事件中的公开号仍是数据值；数据库文件需按部署权限保护。变化覆盖只限检索返回集和选定字段，不能称完整外部变更覆盖。
- **测试与证据**：`tests/test_advanced_tools.py::test_monitor_persists_versioned_baseline_and_deduplicates`、`::test_monitor_and_claim_tools_enforce_launch_gates`；实现和持久化表见 `tools/advanced_tools.py`、登记 JSON。

### 4.24 `analyze_claim_elements`

- **入口、注册与调用链**：[tools/advanced_tools.py](../tools/advanced_tools.py) 的 `ClaimElementsTool.execute`，先由 `_claim_items` 解析 claims JSON，再构造依赖树/要素/产品特征词面映射；`_dataset_gate_failures` 检查版本、法律状态和结构化 claims；底部注册且要求确认。
- **用途与输入输出**：输入最多 20 个公开号和 100 个产品特征词；要求 claims_json、法律状态各至少 80%，并要求至少 80% claims 有编号、语言、独立性和依赖数组，公开/授权版本可识别。输出每件专利的 claim tree 草稿、依赖、拆分元素、literal feature mapping、SHA-256 source evidence path 和版本间 claim hash 差异。
- **算法与边界**：claim 文本按分号、中文分号、句号、`wherein`/“其中”切分；产品特征用大小写折叠后的 literal substring 匹配元素；依赖关系直接读取 `depends_on`；版本差异按 application/family 分组，按 kind code/公开号排序，以 claim text SHA-256 集合差比较。身份 `reversible_claim_element_draft/1.1`，是可逆规则草稿，必须人工专利专业人员复核。
- **确定性、检索和外部服务**：本地 JSON、正则和 hash；无 LLM/在线法律检索。外部法律状态和 claims 来源的真实性、完整性未由本工具确认。
- **校验、失败降级**：非法/缺失 claims 返回空列表并不编造；版本/法律状态/结构门禁不满足则拒绝；特征没有命中只返回空匹配；输出 warning 明确不构成侵权、等同、无效或 FTO 意见。
- **状态、缓存、持久化**：无专属缓存或写库；公共执行结果可能进入会话，完整 claim text 不应写入本审计文档、日志或不必要的外部服务。
- **安全与风险**：claims、产品特征和 source evidence path 可能含敏感/提示注入内容；SHA-256 是完整性证据，不是保密或法律结论。展示和综合时仍应按不可信专利数据处理。
- **测试与证据**：`tests/test_advanced_tools.py::test_claim_elements_are_explicitly_draft_and_reversible`、`::test_monitor_and_claim_tools_enforce_launch_gates`；实现、门禁和登记见 `tools/advanced_tools.py`、证据 JSON。

## 5. 29 个登记算法身份清单

下表单独列身份，避免把多模式工具误计为多个工具。主身份和替代身份均来自 `knowledge/tool_evidence.json` 的 `algorithm_id`、`version` 和 `implementations`，不是根据名称猜测。

| algorithm_id | 版本 | 工具/模式 | 代码确认的核心实现 |
|---|---|---|---|
| `publication_count_trend` | 2.0 | `analyze_patent_trend` | 公开日期按月/年计数 |
| `publication_growth_summary` | 2.0 | `analyze_lifecycle` | 年计数、累计量、同比/CAGR |
| `ipc_publication_matrix_assignment_count` | 2.1 | IPC `assignment_count` | A-H IPC 标注展开后计数 |
| `ipc_publication_matrix_unique_patents` | 2.1 | IPC `unique_patents` | 年×部×专利号去重 |
| `ipc_publication_matrix_family_normalized` | 2.1 | IPC `family_normalized` | 年×部×family key 去重 |
| `derwent_phrase_frequency` | 2.0 | `generate_wordcloud` | 清洗后文档频率/词频 |
| `recent_document_frequency_growth` | 2.1 | `analyze_burst_terms` | 平滑近期/历史文档频率比 |
| `yearly_phrase_frequency` | 2.0 | `analyze_yearly_keywords` | 分年文档频率 |
| `co_applicant_network` | 2.1 | `analyze_co_network` | 确定性规范化申请人无向共现 |
| `primary_publication_office_count` | 2.0 | `analyze_country_distribution` | 主公开号 office 前缀计数 |
| `annual_theme_timeline` | 2.2 | `analyze_tech_roadmap` 默认 | 年度标题主题/代表记录 |
| `family_citation_route_draft` | 1.0 | `analyze_tech_roadmap` 门禁模式 | 同族、时间约束和引证边路线草稿 |
| `dataset_field_audit` | 2.0 | `get_dataset_summary` | 记录、覆盖、批次和网络审计 |
| `tfidf_cosine_retrieval` | 2.2 | `search_patents` lexical | TF-IDF 余弦 + 结构化过滤 |
| `multilingual_minilm_rrf_beta` | 1.0-beta | `search_patents` hybrid beta | 词法与本地 MiniLM 的 RRF |
| `structured_record_lookup` | 2.0 | `read_patent_details` | 公开号精确记录读取 |
| `derwent_abstract_proxy_te_matrix` | 2.3 | `analyze_tech_matrix` | Derwent 段落代理共现/残差 |
| `multilingual_char_ngram_kmeans_cc05` | 3.2 | `analyze_clustering` char mode | 字符 n-gram TF-IDF K-means/CC0.5 |
| `segmented_word_tfidf_kmeans_cc05` | 1.2 | `analyze_clustering` segmented mode | 分词词项 TF-IDF K-means/CC0.5 |
| `patent_family_citation_screening` | 3.1 | `analyze_patent_valuation` | 分层百分位及门禁 SS 筛查 |
| `ipc_profile_evolution` | 2.0 | `analyze_competitor_evolution` | IPC 熵、主导份额、余弦位移 |
| `deterministic_entity_portfolio` | 1.1 | `analyze_entity_portfolio` | 角色分离的规范实体统计 |
| `fractional_concentration_metrics` | 1.1 | `analyze_concentration` | fractional CRn/HHI/Gini/entropy |
| `internal_external_citation_network` | 1.1 | `analyze_citation_network` | 内外部引证图及网络诊断 |
| `separated_family_geography_counts` | 1.1 | `analyze_family_geography` | 五种地域语义分开计数 |
| `versioned_lexical_search_set_audit` | 1.1 | `audit_search_strategy` | 版本集合差/回查/雪崩候选 |
| `dated_authoritative_legal_status_composition` | 1.1 | `analyze_legal_status` | 状态构成与有日期事件 |
| `versioned_patent_change_monitor` | 1.1 | `monitor_patent_changes` | 基线、字段 hash、去重事件 |
| `reversible_claim_element_draft` | 1.1 | `analyze_claim_elements` | claim 依赖/规则拆分/词面映射 |

### 5.1 代码登记与算法身份的差异

`Tool.run` 以工具的 evidence record 和 `implementations` 白名单验证实际 `AlgorithmExecution`。因此 IPC 的三种 count mode、路线的 gate fallback、检索的 Beta fallback、聚类的两种 vectorization mode 会保留实际模式；不能只看工具名称或默认 description。外部模型（包括 MiniLM、LLM provider）内部如何训练、分词、优化或生成，在当前代码中**未确认**，只能记录调用边界和失败回退。

## 6. 未确认路径、遗漏边界与遗留风险

- `agent/orchestrator.py` 的 `_execute_with_adaptive_review`、`agent/adaptive_planner.py`、`agent/cross_tool_synthesis.py` 和 `agent/recommendation_engine.py` 存在规则/LLM 辅助实现；当前主 `stream_query` 明确调用 `_execute_llm_plan`，没有证据表明 adaptive review 或旧战略报告是所有请求的默认生产路径，故不把它们伪装成 24 个公共工具算法。
- `engine.roadmap.build_technology_roadmap`、旧 `strategy_chains`、`PatentAgentOrchestrator.execute_complex`/`agent/multi_agent.py` 的复杂分析路径在当前审计中标为**未确认启用路径**；它们包含 helper 或旧编排设计，但未被 24 个注册工具的主调用链确认使用。
- `engine.network_analysis.compute_citation_network` 是占位 helper，不是额外注册 Tool；其空返回不能覆盖 `analyze_citation_network` 实际调用的 `engine.citation`。
- `retrieval.embedding` 中存在 OpenAI embedding 适配器，但 `SearchTool` 默认使用 TF-IDF，只有显式 Beta 才创建本地 sentence-transformers 后端；当前配置是否在某部署中替换 provider 需由运行时配置另行核验，本文不记录真实配置值。
- 专利数据、外部服务的完整性、专家标注查全率、法律状态来源的内部判定、LLM/embedding 模型内部算法和任何未列入 `knowledge/tool_evidence.json` 的隐式服务均为**未确认**。
- 审计文档以源代码和登记表为证据，不等价于对每个外部数据源的复现验证。任何生产变更若新增注册工具、算法实现、外部服务、数据库表或新的 Agent 路径，应重新运行完整性核对和测试。

## 7. 相关证据索引

- 注册与公共边界：`tools/__init__.py`、`tools/base.py`、`knowledge/tool_evidence.json`。
- REST 暴露：`patent_agent/api/routes/tools.py`、`patent_agent/application/services.py::ToolExecutionService.run_tool`。
- Agent 编排：`agent/orchestrator.py`、`agent/pipeline.py`、`server.py`。
- MCP 暴露：`patent_mcp/server.py`、`patent_mcp/adapters.py`、`patent_mcp/data_loader.py`。
- 检索：`tools/search_tool.py`、`retrieval/search.py`、`retrieval/ranking.py`、`retrieval/embedding.py`、`retrieval/vector_store.py`。
- 数据、会话和监测：`storage/datastore.py`、`storage/conversation_store.py`、`patent_agent/application/conversations.py::ConversationService`、`patent_agent/application/services.py::SearchIndexService`、`tools/advanced_tools.py`。
- 测试：`tests/test_reproducibility.py`、`tests/test_quality_contract.py`、`tests/test_advanced_tools.py`、`tests/test_multilingual_search_beta.py`、`tests/test_multilingual_clustering.py`、`tests/test_metric_semantics.py`、`tests/test_roadmap_capability_boundary.py`、`tests/test_analysis_scope_contract.py`、`tests/test_api_evidence.py`、`tests/test_mcp_integration.py`、`tests/test_prompt_and_evidence_security.py`。
