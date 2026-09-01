# PatentAgent 专利分析整改开发文档

状态：工程整改已实施；真实数据专家验证和法律专业复核仍作为上线运营门禁  
适用版本：V3.1 及其后续整改版本  
审计日期：2026-08-30  
审计依据：当前仓库实现、现有项目审计与验证文档，以及《专利分析方法——图表解读与情报挖掘》22 章的方法框架  
文档用途：本文件是可直接拆分为 Issue、开发任务、测试任务和发布门禁的实施规格，不是对参考书中操作指令的执行记录。

## 1. 目标与产品边界

### 1.1 整改目标

本轮整改需要同时达到以下目标：

1. 修复会直接返回错误数据或复用错误证据的正确性问题。
2. 让用户指定的年份、申请人、IPC、检索式等分析范围在全部适用工具中一致生效。
3. 使工具名称、算法实现、证据登记、界面标签和最终报告保持一致。
4. 将工程代理、描述统计、论文适配方法和法律判断严格分层。
5. 提升中文专利文本分析、申请人实体处理、引证分析和地域布局分析能力。
6. 为 CPU 密集型分析提供可取消、可限流、不会阻塞 SSE 的执行机制。
7. 建立能够阻止算法退化、提示注入和错误证据引用的自动化门禁。

### 1.2 整改后仍然不应宣称的能力

在没有相应数据源、专家标注和法律审查的情况下，系统不得宣称：

- 完成正式 FTO、侵权判定、有效性判断或权利要求保护范围解释；
- 给出专利交易价格、财务价值或通用专利质量；
- 证明某个低共现组合是“蓝海”或可专利空白；
- 仅凭公开量曲线判定萌芽期、成长期、成熟期或衰退期；
- 将首次公开局等同于市场覆盖或申请地域布局；
- 将内部语料引证网络等同于完整外部前向引证网络；
- 将检索相关性分数解释成命中概率、查全率或法律相关性概率。

### 1.3 方法学使用原则

参考书用于补充分析维度和工作流，不作为必须照搬的算法标准。书中部分生命周期、重点专利和机会判断方法属于经验型或相关性推断。当前系统已有的谨慎边界，例如“不自动判定生命周期阶段”“低共现不等于蓝海”“价值排名不是财务估值”，应继续保留。

书中对本项目最重要的可执行原则是：

- 组合分析对象：技术、时间、地域、申请人、发明人、专利类型和法律状态应能组合筛选；
- 指标交叉验证：单一公开量、单一引证数或单一文本频率不能直接推出因果结论；
- 专利与非专利信息联合验证：公司事件、市场、政策、标准、论文和诉讼信息用于解释拐点和矛盾；
- 定量结果后必须保留代表专利、原始记录和人工复核入口；
- 技术路线、规避设计、专利预警等高阶任务需要权利要求、同族、引证、法律状态和业务信息支持。

## 2. 优先级、里程碑与依赖关系

### 2.1 当前验证基线

本次审计执行结果：

| 项目 | 结果 | 说明 |
|---|---|---|
| Python 测试 | 156 passed | 有 Starlette TestClient 弃用和 joblib 物理核心探测两个警告 |
| 前端测试 | 34 passed | 8 个测试文件全部通过 |
| 前端生产构建 | 通过 | `VisualizationPanel` chunk 约 763 KB，gzip 后约 258 KB |
| P0 最小复现 | 已复现 | 年份过滤失效、申请人过滤空结果、内容变化指纹不变 |

### 2.1.1 实施后验证基线（2026-09-01）

| 项目 | 结果 | 说明 |
|---|---|---|
| Python 测试 | 208 passed | 仅剩上游 Starlette `TestClient`/httpx 兼容层弃用警告 |
| 前端测试 | 43 passed | 8 个测试文件全部通过，含 24 类结构化可视化与权利要求复核界面 |
| 前端生产构建 | 通过 | `VisualizationPanel` 10.54 KB gzip；ECharts 最大分包 190.35 KB gzip；自动 200 KB 门禁通过 |
| 契约与方法登记 | 通过 | 24 个工具契约、24 个工具和 29 个实际算法身份通过验证 |
| 官方格式 | 通过 | 3 个清单文件哈希通过；官方格式代理验证脚本通过 |
| 10 万记录基线 | 通过 | 最终峰值 RSS 682.19 MiB；详情见 `docs/benchmarks/pa016-runtime-100k-2026-09-01.json` |

审计时基线保留用于说明整改起点；实施结果与逐项证据见
`docs/remediation-implementation-report.md`。专家标注查全评估、实体/路线/权利要求专家审阅
不由自动化测试替代，未完成这些外部验证时仍不得使用“正式 FTO”“完整查全”或“法律意见”等表述。

这些结果说明工程回归基线总体稳定，但现有测试没有覆盖关键语义契约。后续整改不能以“原测试仍通过”作为充分验收，必须加入会在旧实现上失败的定向测试。

### 2.2 优先级定义

| 等级 | 定义 | 发布要求 |
|---|---|---|
| P0 | 会返回错误结果、错误复用证据或破坏数据版本一致性 | 修复前不得发布新版本 |
| P1 | 高概率造成分析范围失控、方法名实不符、证据失真或安全问题 | 应进入紧随 P0 的同一整改周期 |
| P2 | 统计口径、可解释性、性能或界面误导问题 | 应在下一次功能发布前完成 |
| P3 | 新增分析能力 | 在基础正确性和数据契约稳定后分批实现 |

### 2.3 推荐里程碑

| 里程碑 | 内容 | 进入条件 | 退出条件 |
|---|---|---|---|
| M0 正确性止血 | PA-001、PA-002 | 当前主分支可测试 | 过滤和版本复用错误均有回归测试 |
| M1 统一分析契约 | PA-003、PA-004、PA-005 | M0 完成 | 所有工具支持统一作用域；算法登记与实际运行一致 |
| M2 方法与数据质量 | PA-006 至 PA-012 | M1 完成 | NLP、路线图、矩阵、聚类、实体和价值筛查边界一致 |
| M3 安全、证据与性能 | PA-013 至 PA-016 | M1 完成，可与 M2 并行 | 注入、证据校验、取消、超时和前端口径通过门禁 |
| M4 新工具 | NT-001 至 NT-008 | M2、M3 完成 | 新工具按字段门禁和人工复核要求逐项上线 |

### 2.4 强制实施顺序

```text
PA-001 检索过滤 ─┐
                  ├─> PA-003 统一作用域 ─> PA-004 动态算法证据
PA-002 数据指纹 ─┘                         │
                                           ├─> PA-006~PA-012 方法整改
                                           └─> PA-013~PA-016 安全与性能
                                                        │
                                                        └─> NT-* 新工具
```

## 3. P0 正确性整改

## PA-001 默认检索过滤失效

**优先级：P0**  
**涉及文件：**

- `retrieval/search.py`
- `retrieval/vector_store.py`
- `tools/search_tool.py`
- `retrieval/ranking.py`
- `tests/` 下新增检索契约测试

### 现状

`PatentSearcher.hybrid_search()` 将年份条件传入向量存储，但 `InMemoryVectorStore.search()` 不处理 `filters`。内存索引元数据也不保存申请人，返回的 `PatentSummary.applicants` 固定为空。IPC 和申请人过滤发生在有限候选集之后，会丢失本应命中的记录。

已确认的最小复现：

```text
year_filter_2024_results: [('P-OLD', 2020), ('P-NEW', 2024)]
applicant_filter_beta_results: []
```

### 目标行为

1. 年份、IPC、申请人过滤在任何检索后端上语义一致。
2. 结构化过滤必须在截取 `top_k` 之前完成。
3. 申请人过滤基于规范化申请人字段，而不是空的展示摘要。
4. 默认词法检索和多语言混合检索使用相同的过滤后语料范围。
5. 空查询、无匹配和过滤字段缺失时返回明确状态，不以零结果掩盖能力缺失。

### 实施方案

1. 新建统一的 `SearchScope` 或复用第 4 节的 `AnalysisScope`。
2. 在索引构建阶段保存：
   - `year`；
   - 规范化 IPC 列表或可过滤的 IPC 前缀集合；
   - `applicant_ids` 和申请人展示名；
   - `patent_number`、`dataset_version_id`。
3. 为内存后端实现与 ChromaDB 等价的过滤求值器。
4. 对不适合在向量数据库表达的多值条件，先从 `PatentDataStore` 得到符合条件的专利号集合，再在该集合内排序。
5. 禁止使用“先取 `top_k * 3`、后过滤”作为正确性路径；该逻辑只能作为已有过滤后结果的排序优化。
6. 在 RRF 前分别确认两路结果属于同一作用域。
7. 将缓存键加入规范化作用域和数据集版本。

### API 与兼容性

- 保留现有 `year_start`、`year_end`、`ipc_filter`、`applicant_filter` 参数。
- 返回元数据新增：

```json
{
  "scope": {
    "year_start": 2020,
    "year_end": 2024,
    "ipc_prefixes": ["H01M"],
    "applicant_ids": ["entity:beta-corp"]
  },
  "candidate_count_before_ranking": 123,
  "returned_count": 20,
  "total_hits_exact": true
}
```

### 验收标准

- 限定 2024 年时不得出现 2023 年及以前记录。
- 限定申请人时，内存与 ChromaDB 后端返回相同专利号集合。
- IPC 过滤结果不因 `top_k` 从 10 改为 20 而改变前 10 个符合条件候选的可达性。
- Beta 混合检索的两路输入作用域完全一致。
- 过滤字段覆盖不足时工具不可用或显示明确降级，不得静默返回空结果。

### 必需测试

- `test_inmemory_search_applies_year_filter`
- `test_inmemory_search_preserves_applicants`
- `test_applicant_filter_matches_normalized_entity`
- `test_ipc_filter_happens_before_top_k`
- `test_lexical_and_beta_share_scope`
- `test_search_cache_key_contains_scope_and_dataset_version`
- ChromaDB 可用时增加后端契约参数化测试；不可用环境应跳过而不是伪通过。

## PA-002 数据集版本指纹不包含内容

**优先级：P0**  
**涉及文件：**

- `storage/datastore.py`
- `patent_agent/api/routes/datasets.py`
- 数据集索引缓存和会话证据复用逻辑
- SQLite 数据集版本迁移

### 现状

当前 `dataset_fingerprint()` 只散列适配器、记录数量和 `source_record_id`/`patent_number`。同一记录 ID 的标题、摘要、引证或法律状态发生变化时，指纹保持不变。

### 目标行为

- `dataset_id` 表示同一逻辑数据集。
- `version_id` 表示某一不可变内容版本。
- 任何会影响分析结果的字段变化都必须产生新的 `version_id`。
- 文件重排、DataFrame 行顺序变化和无语义的字典键顺序变化不应改变版本。

### 实施方案

1. 定义规范化记录散列，至少覆盖：
   - 规范化专利号和来源记录 ID；
   - 标题、摘要、日期；
   - 申请人、发明人、IPC/CPC；
   - 同族、引证、权利要求；
   - 法律状态和法律事件；
   - 字段来源及原始记录哈希。
2. 多值字段排序、去重后序列化；日期和空值统一表示。
3. 每条记录产生 `record_content_hash`，排序后计算数据集 Merkle 根或流式 SHA-256。
4. 若导入清单提供可信源文件 SHA-256，将其保存为来源证据，但不得只用文件名和 mtime。
5. 升级缓存键：`dataset_id + version_id + algorithm_id + algorithm_version + normalized_parameters`。
6. 数据上传去重只拒绝完全相同的版本；相同数据集的新内容应建立新版本。
7. 旧版本保留只读，历史报告继续指向原版本。

### 迁移要求

- 为既有数据集计算新版本 ID，记录 `fingerprint_scheme=v2`。
- 不覆盖旧报告中的旧哈希；增加 legacy 标记。
- 首次启动迁移必须幂等，可中断后继续。
- 如果旧版本缺少原始数据，标记 `legacy_identity_only`，禁止把它与新版本判为内容相同。

### 验收标准

- 修改任一分析字段后 `version_id` 改变。
- 仅改变行顺序或多值字段顺序，`version_id` 不改变。
- 同一版本重复上传被识别；相同 ID 但内容改变时创建新版本。
- 数据版本变化后，历史证据可展示但不能进入当前事实综合。
- 检索索引在内容变化后必定重建或命中新版本缓存。

### 必需测试

- `test_fingerprint_changes_when_title_changes`
- `test_fingerprint_changes_when_citations_change`
- `test_fingerprint_is_order_independent`
- `test_upload_creates_new_version_for_changed_content`
- `test_old_evidence_not_reused_after_content_change`
- `test_dataset_migration_is_idempotent`

## 4. P1 统一分析契约

## PA-003 所有工具使用统一分析作用域

**优先级：P1**

### 现状

16 个工具中，只有趋势和检索工具直接暴露年份、IPC、申请人等作用域参数。用户提出“2018—2022 年某公司某技术分支的聚类/路线图/矩阵”时，其余工具可能使用全数据集。

### 数据契约

新增领域对象：

```python
class AnalysisScope(BaseModel):
    year_start: int | None = None
    year_end: int | None = None
    ipc_prefixes: list[str] = []
    applicant_entity_ids: list[str] = []
    inventor_entity_ids: list[str] = []
    jurisdictions: list[str] = []
    patent_numbers: list[str] = []
    text_query: str | None = None
    family_deduplication: Literal["none", "simple", "inpadoc"] = "none"
```

### 实施方案

1. `Tool.run()` 接受保留字段 `scope`，在参数校验后、工具执行前统一创建只读 `ScopedPatentStore`。
2. 工具只接收已过滤的数据视图，不允许各自重复实现年份和申请人过滤。
3. Planner 的工具 schema 对全部数据分析工具暴露相同的 `scope` 定义。
4. 结果 provenance 强制记录：
   - 原始记录数；
   - 作用域过滤后记录数；
   - 同族去重后记录数；
   - 规范化作用域；
   - 空结果原因。
5. 对不适用作用域的工具，如 `get_dataset_summary`，schema 明确声明 `supports_scope=false`。
6. 删除或迁移隐藏的 `__filters` 兼容路径，避免形成第二套过滤协议。

### 验收标准

- 聚类、路线图、功效矩阵、申请人网络、国家分布、价值筛查和竞争演化均可限定统一作用域。
- 同一作用域在 REST、SSE、MCP、Agent 和直接 Tool 调用中得到相同记录集合。
- 用户未提供作用域时不得由 LLM 猜测。
- 用户提供工具不支持的条件时必须澄清或明确拒绝，不能丢弃参数。

### 必需测试

- 对每个工具运行统一的 `scope_contract` 参数化测试。
- 测试组合条件的交集语义。
- 测试空集、字段缺失、年份反转和非法 IPC。
- 测试 REST/MCP/Agent 的作用域序列化一致性。

## PA-004 算法 ID 和 provenance 必须按实际执行路径生成

**优先级：P1**

### 现状

工具证据登记是静态的，但检索工具可在词法、MiniLM＋RRF 和回退词法之间切换。统一封装仍可能记录默认 TF-IDF 的算法 ID。

### 实施方案

1. `Tool.execute()` 返回 `AlgorithmExecution`：

```python
class AlgorithmExecution(BaseModel):
    algorithm_id: str
    algorithm_version: str
    mode_requested: str
    mode_used: str
    fallback_reason: str | None = None
    parameters: dict
```

2. `Tool.run()` 不再覆盖工具执行阶段给出的算法事实，只负责验证它是否存在于允许登记表。
3. `knowledge/tool_evidence.json` 支持每个工具登记多个实现模式。
4. 文档矩阵继续由登记表自动生成，不允许手工修补与代码不一致的描述。
5. 报告和前端显示实际执行模式与回退原因。
6. 方法/帮助类回答必须读取完整 evidence record、公式、字段门槛、来源和禁止结论，不能只依赖工具的一行 capability description。
7. 方法回答使用独立的只读知识路径，不应为了回答“算法如何工作”而运行数据分析工具。

### 验收标准

- 词法检索记录 `tfidf_cosine_retrieval`。
- 成功的 Beta 记录 `multilingual_minilm_rrf_beta`。
- Beta 失败回退记录词法算法，同时保留请求模式和回退原因。
- 未登记算法不能进入成功结果。

## PA-005 工具声明、参数默认值和返回字段一致性

**优先级：P1**

### 整改项

- 从函数签名或 Pydantic 参数模型生成 schema，避免描述“默认 5”但执行为自动选择等偏差。
- 参数模型必须设置上下限，例如路线图 `top_n_per_year`、矩阵 `top_n`、价值筛查 `top_n`。
- `_TOOL_RESULT_FIELDS`、证据登记和实际 Typed Result 必须由单一来源生成。
- `total_hits` 改为真实匹配总量；无法计算时改名为 `returned_count`，不得伪装总量。
- 工具名称应表达实际能力：
  - `analyze_lifecycle` 建议迁移为 `analyze_publication_growth`；
  - 当前 `analyze_tech_roadmap` 建议迁移为 `analyze_annual_theme_timeline`；
  - `analyze_patent_valuation` 建议迁移为 `rank_patents_by_metadata`。
- 保留一个版本的旧名称别名，并返回弃用警告。

### 验收标准

- CI 自动比较 schema、函数参数、结果模型和登记表。
- 不存在无效默认值、未知参数被静默丢弃或文档声称返回但结果缺失的字段。

## 5. P1 方法学整改

## PA-006 关键词和逐年关键词改为真实文档频率

**优先级：P1**

### 现状

登记表和工具描述声称使用短语文档频率及最小支持，当前普通词云和逐年关键词实际统计 token 总出现次数。

### 实施方案

1. 保留文档边界，每件专利对同一术语最多贡献一次 DF。
2. 分开返回：
   - `document_frequency`；
   - `term_frequency`；
   - `document_ratio`；
   - `record_ids` 或可分页的代表专利引用。
3. 中文使用 jieba＋领域词典或字符 n-gram；英文保留词形规范化和可选词性过滤。
4. 混合语言按文本片段或 token 脚本分类处理，不应因包含中文就跳过全部英文处理。
5. 短语抽取公开 `min_support`、`min_stickiness` 和清洗版本。
6. NLTK 等资源必须在安装/启动探测阶段准备，不得在请求处理中自动下载。

### 验收标准

- 同一术语在单件专利重复 100 次，DF 仍只增加 1。
- 中文、英文和中英混合金样均得到稳定、可解释的关键词。
- 无网络环境不会触发隐式下载，也不会改变算法路径而不报警。
- 工具描述、算法登记和输出字段与实际计算完全一致。

## PA-007 中文聚类和抽样整改

**优先级：P1**

### 实施方案

1. 提供至少两种向量化模式：
   - `char_ngram_tfidf`：默认稳健中文/混合语种基线；
   - `segmented_word_tfidf`：使用固定版本领域词典。
2. MiniLM 聚类保持实验模式，与 TF-IDF 指标分开发布。
3. 大数据抽样按年份×申请人/IPC 分层；稀有层设置最低保留量。
4. 返回每簇：规模、占比、关键词、代表专利号、年份分布、主要申请人和轮廓系数。
5. 保留簇稳定性：多随机种子 ARI、不同样本重抽稳定性和低稳定簇警告。
6. 给聚类结果增加可追踪的 `record_id -> cluster_id` 下载接口。

### 验收标准

- 中文合成语料中的预设主题可被稳定区分。
- 固定种子时输出可复现；改变输入行顺序不改变规范簇 ID。
- 抽样后稀有层不会因全局随机抽样完全消失。
- 聚类标题不再只有英文词或整段中文字符串。

## PA-008 技术路线图降级命名并建设真实路线图

**优先级：P1**

### 第一阶段：立即纠正命名

- 将当前实现明确命名为“年度主题时间线”。
- 删除“完整技术路线”“发明谱系”等超出结果的表述。
- 若没有解析到引证边，结果中不得出现 citation path 能力暗示。

### 第二阶段：真实技术路线图规格

真实路线图至少需要：

1. 同族归并后的节点；
2. 技术要素或技术—功效人工/半自动分类；
3. 可解析的引证边及闭网覆盖审计；
4. 优先权时间，而不是只用公开年份；
5. 关键节点筛选依据和代表专利全文入口；
6. 主路径、分支、合流和孤立簇；
7. 非专利文献或专家验证标记；
8. 对缺失引证、公开滞后和数据库制度差异的警告。

### 验收标准

- 每条路线边都能追溯到来源引证或人工确认关系。
- 时间方向不得违反优先权/公开时间约束，异常边单独标记。
- 内部边解析率低于门禁时只生成主题时间线，不生成路线结论。
- 关键节点包含专利号、同族、技术要素、入/出边依据和人工复核状态。

## PA-009 技术—功效矩阵从低共现列表升级为复核工作流

**优先级：P1**

### 实施方案

1. 引入版本化分类体系：`taxonomy_id`、版本、创建人、适用范围。
2. 技术和功效标签允许：规则、模型建议、人工确认三种来源。
3. 有双人编码时计算 Cohen's kappa 或一致率；没有时明确 `single_coder`。
4. 每个矩阵格同时返回：
   - 实际共现数；
   - 技术边际数、功效边际数；
   - 独立假设下期望数；
   - lift、标准化残差或 PMI；
   - 最低支持是否通过；
   - 代表专利和相邻检索式。
5. 零共现项只允许命名为“低共现复核候选”。
6. 对候选执行扩展检索、同义词检索、IPC/CPC 和引证滚雪球后，仍由人工确认。
7. 抽样时采用分层策略并显示被排除记录。

### 验收标准

- 不再仅按笛卡尔积中的零值字典序挑选 Top N。
- 边际支持不足的组合不能进入默认候选列表。
- 每个候选都可下钻至专利记录和检索策略。
- UI、报告和 LLM 禁止使用“蓝海”“可专利空白”等未经验证表述。

## PA-010 申请人、权利人和发明人实体规范化

**优先级：P1**

### 数据模型

```text
Entity
  entity_id
  canonical_name
  entity_type
  jurisdiction
  parent_entity_id
  valid_from / valid_to

EntityAlias
  alias
  language
  source
  confidence
  resolution_method
  review_status

PatentPartyRole
  patent_id
  entity_id
  role = applicant | assignee | owner | inventor
  source
  observed_at
```

### 实施方案

1. 第一层仅做确定性规范化：大小写、空白、标点、公司后缀和 Unicode。
2. 第二层使用显式别名字典和来源提供的规范名。
3. 模糊匹配只生成候选，不自动合并高风险主体。
4. 母子公司关系带时间范围，避免把收购前记录错误归并。
5. 所有合并可逆并保留原始名称。
6. 申请人过滤默认使用实体 ID；仍允许选择“原始名称精确匹配”。
7. `str.contains` 使用 `regex=False`，避免特殊字符改变含义。

### 验收标准

- 同一公司的常见语言/后缀变体可汇总。
- 同名但不同主体不会因模糊匹配自动合并。
- 申请人、受让人和当前权利人角色不混用。
- 任何归并结果均能回溯原始来源和人工审核状态。

## PA-011 价值筛查缺失值、时间窗和来源偏差整改

**优先级：P1**

### 实施方案

1. 将工具定位为当前数据集内相对元数据筛查。
2. 缺失值不再直接按零分处理；每件专利按其可用维度计算并同时输出：
   - 可用权重比例；
   - 缺失维度；
   - 分数区间或置信等级；
   - 是否可与其他记录比较。
3. 引证指标按技术领域、公开年和引证窗口归一化。
4. 后向参考文献数量不得命名为影响力；前向引证必须区分内部和外部。
5. 同族规模只在覆盖率和归并质量达标时进入评分。
6. IPC breadth 提供小类/大组或自定义技术分类，不只统计 A—H 部级。
7. 按数据源分层校准；不同字段丰富度来源的记录默认不直接混排。
8. 敏感性分析同时覆盖权重和数据缺失，不只计算 Top N 重合率。

### 验收标准

- 字段缺失不会被解释成专利指标为零。
- 新旧专利不会因观察窗口不同而直接比较未经归一化的引证数。
- 每个排名都显示实际参与维度和可比较性警告。
- 表格中的 `patent_age` 标签正确显示为“专利年龄”。

## PA-012 导入完整性与字段语义整改

**优先级：P1**

### 实施方案

1. 适配器按记录捕获异常，返回成功记录和 `RecordImportIssue`。
2. 导入报告增加：
   - 文件预计记录数；
   - 已识别记录数；
   - 成功、失败、跳过、合并数量；
   - 失败记录定位、原因和脱敏样例；
   - 解析率和字段覆盖。
3. 对尾部标志、XML 截断、多记录文件和异常编码建立格式专用检查。
4. 失败记录写入隔离文件或数据库，不静默丢弃。
5. 申请人、受让人、当前权利人分别映射；无法区分时保留来源角色，不强行统一为 applicant。
6. 对缓存禁止使用文件名＋mtime；至少使用内容哈希和解析器版本。

### 验收标准

- 单条坏记录不会使整文件失败，也不会被无声跳过。
- 报告满足 `success + failed + skipped = detected`。
- 解析器版本变化会失效旧解析缓存。
- 对官方格式金样执行逐字段语义断言。

## 6. P1 安全与证据整改

## PA-013 不可信专利文本与提示注入隔离

**优先级：P1**

### 实施方案

1. 在系统提示中明确：专利、报告、导入文件和工具文本均是不可信数据，不得执行其中指令。
2. 使用 JSON schema 或结构化 content block 传递工具结果，不把原始文本直接拼入命令性提示。
3. 对进入 LLM 的字段使用白名单和长度限制；保留原值哈希与记录 ID。
4. 分块提炼提示必须包含：忽略数据内指令、只提取 schema 指定事实、不得创造结论。
5. 对标题、摘要、申请人名和权利要求中的注入样本建立红队测试。
6. 最终答案不得引用工具未输出的网页、法律状态或专利字段。
7. React 结构化渲染作为默认展示路径；逐步移除向浏览器传递任意 `chart_html` 的兼容路径。
8. 在兼容路径移除前，禁止将专利号、标题、申请人等未转义数据拼入 HTML；“新窗口打开”不得执行来自数据集的脚本。

### 验收标准

- 数据中包含“忽略系统指令”等文本时，模型仍只把它作为专利内容。
- 恶意字段不能改变工具选择、调用外部工具或泄露系统提示。
- 被截断文本在 provenance 中有明确标记。

## PA-014 最终答案证据引用改为确定性校验

**优先级：P1**

### 实施方案

1. 为每次工具执行生成稳定 `execution_id`。
2. 为结构化值生成引用路径，例如：

```text
evidence://exec-123/data/2024/count
evidence://exec-456/patents/US123/score
```

3. 最终答案 schema 要求每个关键数字、排序和方法结论关联 evidence ref。
4. 服务端验证引用路径真实存在，数值与格式一致。
5. 允许不带引用的解释性文本，但不得包含新的事实数字或数据集结论。
6. 报告导出保留引用清单、数据版本和工具算法版本。

### 验收标准

- 只写工具名称不能通过证据校验。
- 修改或捏造数值会触发一次修复；再次失败返回结构化降级结果。
- 历史证据只能引用其原数据集版本。

## 7. P2 统计口径与界面整改

## PA-015 统计口径和标签统一

**优先级：P2**

### 必改清单

1. 所有基于 `publication_date` 的图表统一使用“公开量/公开趋势”，不得写“申请量”。
2. 生命周期旧 HTML 的“年申请量”改为“年度公开量”。
3. 同比增长率的算术平均不得称“年均增长率”；改用 CAGR、Theil-Sen/稳健斜率或仅展示逐年同比。
4. 尾年完整性使用 `data_as_of` 和实际覆盖月份判断；10 或 11 个月也标为部分年度。
5. 历史年份缺月、批次缺口和公开滞后分别报警。
6. IPC 图显示“IPC 标注次数”；另提供去重专利数、分数计数和同族归一化计数模式。
7. IPC section 只允许 A—H；异常代码进入数据质量报告。
8. 检索余弦/RRF 显示为“排序分数”，不得加百分号或概率进度条。
9. `total_hits` 只在确切统计时使用；否则显示 `returned_count`。
10. 国家分布固定命名为“主公开号首次公开局分布”，不写市场覆盖。
11. 价值筛查表的 `patent_age` 显示为“专利年龄”。

### 验收标准

- 建立术语快照测试，禁止“公开日期数据＋申请量标签”等组合重新出现。
- 前端 tooltip、图题、导出报告和 LLM 提示共享同一指标定义。

## PA-016 CPU 工具执行、取消和前端性能

**优先级：P2**

### 后端实施方案

1. 将 pandas/sklearn/NLP 等 CPU 密集执行放入受限线程池或进程池。
2. 使用应用级共享并发控制，不在每次请求中单独创建固定容量信号量。
3. 为每个工具配置：
   - 最大执行时间；
   - 最大输入记录数；
   - 内存预算或预估；
   - 取消检查点；
   - 队列等待上限。
4. SSE 保持心跳并显示 queued/running/cancelling 状态。
5. 取消后不得保存成功证据；临时索引应安全清理。
6. 避免多个并发工具复制完整 DataFrame；使用只读列投影和共享不可变作用域索引。
7. 为 10 万记录分别建立词法、聚类、矩阵和并发交互基线。

### 前端实施方案

1. 对 ECharts、词云、矩阵、网络图和路线图渲染器继续按需加载。
2. 大表使用虚拟滚动；图表限制默认节点/格子数并提供下载全量数据。
3. 可视化 chunk 建立体积预算；建议 gzip 后不超过 200 KB，超出需解释。
4. 搜索列表不使用百分比相关性进度条。

### 验收标准

- 一个长聚类任务运行时，健康检查、SSE 心跳和取消请求仍能及时响应。
- 达到并发上限后进入有界队列，不无限创建 CPU 工作。
- 取消后状态最终一致，无幽灵工具结果。
- 基准脚本输出机器、Python/Node 版本、记录数、耗时和峰值 RSS。

## 8. 新工具开发规格

以下工具必须遵守统一 `AnalysisScope`、`ToolExecutionEnvelope`、字段门禁和证据引用协议。

## NT-001 实体组合与排名分析

**建议名称：** `analyze_entity_portfolio`

### 输入

- `scope`
- `entity_type`: applicant/assignee/owner/inventor
- `metric`: publications/families/grants/citations
- `top_n`
- `group_by_parent`

### 输出

- 规范实体排名、原始别名、记录数和同族数；
- 年度趋势和技术分支构成；
- 母子公司归并口径；
- 未解析实体和低置信度映射。

### 禁止结论

- 不得把公开量直接解释成研发实力、市场份额或专利质量。

## NT-002 专利集中度分析

**建议名称：** `analyze_concentration`

### 指标

- CR3、CR5、CR10；
- HHI；
- Gini；
- Shannon entropy/有效主体数；
- 按年份的置信区间或 bootstrap 稳定性。

### 维度

- 申请人、技术分类、公开局/同族地域；
- 公开记录计数和同族去重计数两种口径。

### 输出要求

- 每个指标公式、样本量、长尾截断和实体归并版本；
- 拐点仅作为待解释现象，并提供非专利信息验证任务。

## NT-003 引证网络分析

**建议名称：** `analyze_citation_network`

### 功能

- 前向/后向引证；
- 自引；
- 共引和文献耦合；
- 引证树与关键路径；
- 引证年龄/TCT；
- 申请人、国家、技术分类的引证分布。

### 强制门禁

- 明确内部/外部边；
- 报告边解析率、节点参与率、同族归并率和来源覆盖；
- 不把后向引证数称为被引影响力；
- 开放网络不足时只做描述，不输出关键路径结论。

## NT-004 同族与地域布局分析

**建议名称：** `analyze_family_geography`

### 输出必须分开

- 优先权来源地；
- 首次公开局；
- 同族公开覆盖局；
- 指定国；
- 当前有效权利地域（仅权威法律状态来源可用时）。

### 禁止结论

- 不能以 PN 前缀代替市场覆盖、出口意向或专利有效地域。

## NT-005 检索策略审计

**建议名称：** `audit_search_strategy`

### 功能

- 关键词、同义词、缩写和多语言变体；
- IPC/CPC 分类组合；
- 查询式版本与命中集差异；
- 代表已知专利回查；
- 引证和同族滚雪球；
- 随机漏检审计与人工标签回流。

### 输出

- 每版检索式、命中数、增量记录、独有记录和抽样复核结果；
- 不得输出未经专家基准验证的“查全率 100%”。

## NT-006 法律状态构成与事件分析

**建议名称：** `analyze_legal_status`

### 前置条件

- 来源具备法律状态能力；
- 每条状态有来源、司法辖区和 `as_of` 日期；
- 事件与当前状态分开保存。

### 输出

- 状态构成、年度事件、即将到期/年费事件候选；
- 数据陈旧和跨局状态不可比警告。

### 禁止结论

- 不自动给出可实施、无侵权或权利有效的法律意见。

## NT-007 持续监测与专利预警

**建议名称：** `monitor_patent_changes`

### 功能

- 保存版本化检索策略和基线结果集；
- 新公开、新同族、新引证、新法律事件和申请人变化的增量；
- 去重通知、失败重试和审计日志；
- 用户可配置阈值和通知策略。

### 上线条件

- PA-002 内容版本、NT-005 检索策略和可靠外部数据源完成后方可启用。
- “预警”只表示数据变化或规则命中，不表示已经发生侵权风险。

## NT-008 权利要求与产品映射辅助

**建议名称：** `analyze_claim_elements`

### 前置条件

- 权利要求全文覆盖达标；
- 语言、版本、授权/申请状态和 claim dependency 可识别；
- 有人工复核界面。

### 功能

- 独立/从属权利要求树；
- 要素拆分和逐项证据引用；
- 同族/审查版本差异；
- 产品特征映射草稿。

### 强制限制

- 模型拆分结果必须标为草稿；
- 不自动生成侵权、等同原则、无效或 FTO 结论；
- 高风险输出必须经过专利专业人员审阅。

## 9. 非专利信息扩展接口

参考书第 1、4、15、17、20—22 章均要求使用非专利信息解释趋势、竞争行为、出口和预警。该能力应作为可追溯数据连接层，不得由 LLM 凭常识补写。

建议定义统一 `ExternalEvidenceRecord`：

```python
class ExternalEvidenceRecord(BaseModel):
    evidence_id: str
    evidence_type: str
    title: str
    source_name: str
    source_uri: str
    published_at: str | None
    observed_at: str
    entities: list[str]
    text_excerpt: str
    content_hash: str
    license_note: str
```

优先数据类型：

1. 标准、论文和技术报告；
2. 公司并购、更名、产品发布和研发合作；
3. 诉讼、转让和许可；
4. 政策、监管和行业统计；
5. 产品、市场和出口信息。

任何因果解释必须同时显示专利证据和非专利证据，或明确标记为待验证假设。

## 10. 数据库与 API 迁移清单

### 10.1 建议新增表

- `dataset_versions`：内容版本、指纹方案、记录哈希根、来源清单；
- `record_hashes`：数据集版本内的记录内容哈希；
- `entities`、`entity_aliases`、`patent_party_roles`；
- `analysis_scopes`：规范化作用域及哈希；
- `evidence_values`：可引用结构化值及 JSON path；
- `taxonomies`、`taxonomy_labels`、`record_annotations`；
- `search_strategies`、`search_strategy_versions`；
- `monitor_runs`、`monitor_events`；
- `external_evidence`。

### 10.2 API 版本策略

1. 旧工具参数在一个次版本内继续接受，并转成 `scope`。
2. 旧工具名称返回 `deprecation` 元数据和替代名称。
3. 新结果字段只增不删；需要改语义的字段使用新名称。
4. `total_hits` 等错误语义字段不得静默改变，应并存一版后移除。
5. OpenAPI、MCP schema 和前端 TypeScript 类型从同一契约生成或由 CI 比较。

### 10.3 幂等迁移要求

- 每个迁移有唯一版本和事务边界；
- 支持空库、旧库和迁移中断后重试；
- 不删除旧报告、工具执行和证据；
- 大数据版本散列支持批处理和进度记录；
- 迁移完成后运行外键、记录数和版本引用一致性检查。

## 11. 测试与验证计划

### 11.1 测试层级

| 层级 | 内容 |
|---|---|
| 单元测试 | 过滤、散列、指标公式、实体规范化、缺失值、标签 |
| 属性测试 | 行顺序不变性、范围交集、散列确定性、随机算法稳定性 |
| 契约测试 | 所有检索后端、REST/MCP/Agent、Tool schema/result/provenance |
| 金样测试 | 中文/英文专利小语料、官方格式导入、人工计算指标 |
| 安全测试 | 提示注入、HTML 注入、越权字段、恶意文件和超大输入 |
| 性能测试 | 10 万记录索引、聚类、矩阵、并发、取消、峰值 RSS |
| 专家验证 | 检索查全抽样、实体映射、技术分类、路线和权利要求 |

### 11.2 必备金样

1. `search_scope_gold`：年份、IPC、申请人组合过滤。
2. `fingerprint_gold`：字段变化、顺序变化、多值字段顺序。
3. `zh_topic_gold`：至少 3 个中文技术主题和混合语言术语。
4. `entity_alias_gold`：公司后缀、母子公司、同名不同主体。
5. `citation_gold`：可手算的前后引、共引、耦合和自引网络。
6. `tech_effect_gold`：人工标注技术—功效格及边际数。
7. `prompt_injection_gold`：在标题、摘要、申请人、权利要求中放置攻击字符串。
8. `missingness_gold`：不同来源字段覆盖差异，验证价值筛查不把缺失当零。

### 11.3 数学手算校验

以下指标必须用小数据集手算并精确/容差比较：

- CAGR、同比、稳健趋势；
- CRn、HHI、Gini、entropy；
- TF、DF、document ratio；
- cosine、RRF；
- silhouette、ARI；
- 技术—功效矩阵期望值、lift、标准化残差；
- 共引、文献耦合、TCT；
- 缺失维度下的可用权重比例和分数区间。

### 11.4 发布门禁命令

以下命令应全部成功：

```bash
.venv/bin/python -m pytest -q
cd frontend && npm test -- --run
cd frontend && npm run build
```

另应补充并进入 CI：

```bash
.venv/bin/python -m scripts.verify_import_manifest tests/fixtures/official_formats
.venv/bin/python -m scripts.validate_official_samples
.venv/bin/python -m scripts.benchmark_retrieval --records 100000
.venv/bin/python -m scripts.verify_contracts
.venv/bin/python -m scripts.verify_methodology_registry
```

后两个脚本为本整改计划要求新增的门禁：

- `verify_contracts`：比较工具参数、结果模型、REST、MCP 和前端类型；
- `verify_methodology_registry`：比较实际算法路径、证据登记、文档矩阵和禁止结论。

## 12. 每个 Issue/PR 的完成定义

每个整改任务只有同时满足以下条件才能关闭：

- [ ] 代码实现完成，未绕过统一 Tool/Scope/Provenance 契约。
- [ ] 至少包含一个会在旧实现上失败的回归测试。
- [ ] 指标名称、公式、字段门槛、算法 ID 和禁止结论已登记。
- [ ] REST、SSE、MCP 和 Agent 行为一致或明确说明不适用。
- [ ] UI、报告和 LLM 提示使用相同术语。
- [ ] 数据缺失、空集、部分年度和抽样路径均有测试。
- [ ] 性能影响有基准；新增大依赖有体积和启动时间说明。
- [ ] 不可信输入和输出转义经过安全测试。
- [ ] 数据库迁移幂等且保留历史证据。
- [ ] 更新用户文档和变更日志。

## 13. 推荐 Issue 拆分

可以按以下顺序直接创建开发任务：

1. `PA-001 Fix structured filtering before retrieval ranking`
2. `PA-002 Introduce content-based dataset version fingerprints`
3. `PA-003 Add AnalysisScope to every dataset analysis tool`
4. `PA-004 Record actual algorithm execution and fallback provenance`
5. `PA-005 Generate schemas and result fields from typed contracts`
6. `PA-006 Align word-frequency implementation with methodology registry`
7. `PA-007 Add Chinese-aware clustering and stratified sampling`
8. `PA-008 Rename annual timeline and gate real roadmap generation`
9. `PA-009 Upgrade low-cooccurrence matrix to review workflow`
10. `PA-010 Add party-role-aware entity resolution`
11. `PA-011 Correct missingness and observation-window bias in ranking`
12. `PA-012 Add record-level import completeness accounting`
13. `PA-013 Treat corpus content as untrusted LLM data`
14. `PA-014 Validate evidence references against exact result paths`
15. `PA-015 Unify statistical labels and UI semantics`
16. `PA-016 Offload CPU tools and add bounded cancellation`
17. `NT-001 Add entity portfolio analysis`
18. `NT-002 Add concentration analysis`
19. `NT-003 Add citation network analysis`
20. `NT-004 Add family geography analysis`
21. `NT-005 Add search strategy audit`
22. `NT-006 Add legal status analysis with source/as-of gates`
23. `NT-007 Add versioned monitoring and change alerts`
24. `NT-008 Add human-reviewed claim element analysis`

## 14. 参考书章节与开发项映射

| 参考书内容 | 对应开发项 |
|---|---|
| 第 1 章趋势、生命周期、集中度 | PA-003、PA-015、NT-002 |
| 第 2 章技术、申请人、地域、法律状态构成 | NT-001、NT-004、NT-006 |
| 第 3 章排序分析 | NT-001、PA-011 |
| 第 4 章数据关联和非专利信息验证 | 第 9 节外部证据接口 |
| 第 5 章文本与引证聚类 | PA-007、NT-003 |
| 第 6 章引证分析 | NT-003、PA-008 |
| 第 7 章分析模型 | PA-011、NT-002 |
| 第 8 章技术—功效矩阵 | PA-009 |
| 第 9 章重点专利 | PA-011、NT-008 |
| 第 10 章技术路线图 | PA-008、NT-003 |
| 第 11—12 章权利要求与规避设计 | NT-008，且要求人工法律复核 |
| 第 13 章技术追踪 | NT-005、NT-007 |
| 第 14 章专利挖掘 | PA-009、NT-005、NT-008 |
| 第 15 章研发合作 | PA-010、NT-001 |
| 第 16 章专利布局 | NT-002、NT-004、PA-009 |
| 第 17—18 章诉讼与运营 | NT-006、外部诉讼/转让/许可数据 |
| 第 19—20 章技术引进与产品出口 | NT-004、NT-006、NT-008 |
| 第 21 章竞争对手 | PA-010、NT-001、NT-007 |
| 第 22 章专利预警 | NT-005、NT-006、NT-007、NT-008 |

## 15. 最终发布判定

完成 M0—M3 后，产品可定位为：

> 具备数据版本追踪、统一作用域、可验证算法来源和明确方法边界的专利数据分析与情报初筛助手。

只有在 NT-003、NT-004、NT-005 完成并经过真实数据专家验证后，才适合增强为“专利情报分析平台”。NT-006、NT-008 即使实现，也仍是法律专业人员的辅助工具，不能改写为自动 FTO、侵权判断或法律意见系统。
