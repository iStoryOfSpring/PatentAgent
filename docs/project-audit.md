# PatentAgent 项目审查与方法边界

## 结论

PatentAgent 适合降低专利全景、公开趋势、主题聚类、IPC 分布和初步相关专利筛查的人工成本。它只有在数据来源、字段覆盖、算法等级与结果限制同时可见时，才适合作为决策辅助工具。当前系统不替代 FTO 法律意见、有效性判断、权利要求比对或财务估值。

## 推荐工作流

`WoS 数据加载与字段审计 → 会话历史+用户原问题+动态能力目录输入 LLM → LLM 返回真实 tool calls/复用/澄清决策 → 本地参数、数据能力和成本门禁 → 并行执行必要 Tool/Engine → 按供应商官方协议回传完整结果 → 禁用新工具的第二轮结构化综合 → 动态且去重的追问建议`

正常 Web 主流程不再运行 `analysis_type → strategy chain`、关键词评分或中间结果触发的自动追加。“技术路线”与其他问题使用同一套能力目录和工具选择协议。每轮最多自动执行 4 个工具、成本权重不超过 6；超限时先向用户确认。

供应商显示名称与协议分开实现：多个任意命名配置只按 `openai_chat`、`anthropic_messages` 或 `deepseek_chat` 选择适配器。OpenAI/DeepSeek 保留完整 assistant `tool_calls` 并以 `role=tool` + `tool_call_id` 回传；Claude 保留 `tool_use` blocks，所有 `tool_result` 放在紧邻的单个 user 消息且排在文本之前。DeepSeek 思考模式所需的 `reasoning_content` 只在当前往返中临时保留，不写入会话库。

会话、轮次、消息和去除 chart_html 的结构化工具证据保存在本地 SQLite。解释型追问直接复用历史证据；数据集指纹变化后旧证据保留展示但退出当前事实综合。LLM 空回复、综合异常或 SSE 提前结束不再表现为“只有工具没有总结”。

用户端唯一入口是 `frontend/` 与 `server.py`。MCP 是可选的外部 AI 客户端集成接口，使用相同 Tool 注册表和 `Tool.run` 契约，不构成第二套用户界面。

## 工程基线与模块边界

项目采用模块化单体，不引入微服务或外部任务队列。`pyproject.toml` 是依赖声明源，
`uv.lock` 固定 Python 3.10+ 的解析结果，推荐本地使用 3.13 或 3.14，`requirements.txt`
仅为自动导出的 pip 兼容清单。GitHub Actions 对 Python 3.10–3.14、Node 20、MCP、SQLite 幂等迁移、前端
测试/构建和固定合成 WoS 金样执行持续门禁；标签发布只生成源码、前端产物和校验和。

新增的 `patent_agent` 包按 application、domain、security、infrastructure 和 api 划定
用例、契约及运行边界，现有 engine/tools/agent 算法包保持原位渐进迁移。FastAPI lifespan
创建 `AppContainer`，进程状态不再散落为 `server.py` 可变模块全局变量。`FullPatent` 以
兼容方式演进为 `PatentRecord` v2，`DatasetSnapshot` 固定数据集内容哈希、schema、来源、
记录数和字段覆盖；DataFrame 仍是性能实现，不再充当业务契约。

16 个工具现在公开 `ToolDefinition`，并能形成统一 `ToolExecutionEnvelope`：结果、证据、
警告、结构化错误、数据版本、输入/分析数量、采样、字段覆盖、算法/参数、耗时、缓存和重试
指标均为强制执行元数据。REST 保留扁平结果并附加这些字段，MCP 与 Agent 复用相同内部契约。
主 Agent 流水线已拆为 IntentParser、Planner、ExecutionPolicy、ToolExecutor、
ResultValidator 和 AnswerSynthesizer；`PatentAgentOrchestrator` 保留为迁移期兼容外观。

SQLite 中既有 turns 被提升为持久 Agent 任务，同时增加数据集版本、trace、状态版本、错误
分类、取消标记和事件流；工具执行保存 provenance/metrics，另有 datasets、imports、
approvals 和 reports。重启把运行中任务标记为 `interrupted`，不会自动重放 LLM；恢复只复用
已持久化证据或重试综合。前端保持现有布局，但按 datasets/sessions/agent/tools/providers/
reports feature 拆分，并用 TanStack Query 管理服务端状态。

## 数据语义与质量门禁

- `UT` 是 DII 批次去重主键；缺失时才退回主公开号。当前 10 个批次含 10,000 个唯一 UT，解析率 100%，解析器已排除文件尾 `EF` 伪记录。
- `PN` 首个公开号是主公开号，其他 `PN` 公开号及 `FD` 关联公开号进入同族列表；`PI` 优先权号另存，不混入同族成员。
- `CP` 提取专利后向引证，并排除当前记录全部公开号；`CR` 是非专利参考文献，不进入专利引证图。
- `PD` 是公开日期，因此时间图表称“专利公开趋势”。尾年月份不足时必须警告。
- WoS Derwent 样例不含权利要求全文、法律状态和可靠的外部前向被引数据。FTO 只能输出初步相关专利筛查。
- 工具通过 `/api/tools` 公布必需字段、可选字段、可用性、不可用原因和证据等级。所有结果包含 `summary`、`methodology`、`data_quality`、`warnings` 与 `result_metadata`。

当前样例的关键审计结果：公开日期、IPC、申请人均约 99.99%；后向引证字段覆盖 41.02%，但 35,242 条引证中只有 719 条解析到当前语料，内部边解析率仅 2.04%，参与内部图的节点为 10.71%；同族覆盖 35.28%；欧洲式主公开号占 10.29%；外部前向被引、权利要求和法律状态均为 0。因此该样例不满足 von Wartburg 论文适配复现、Kim–Bae 潜力预测或正式 FTO 的门禁。

## DII 基准数据获取结果

2026-07-19 已通过 CARSI 成功认证为 `WUHAN TEXTILE UNIV`。Clarivate 对 `/wos/diidw/basic-search` 返回 `not-entitled?db=diidw`，并明确说明学校未订阅 Derwent Innovations Index。故三个计划基准集均没有下载，状态记录为 `blocked_not_entitled`；系统没有用 WoS Core Collection 论文记录或其他来源伪装成 DII 专利数据。检索式、目标规模和导出格式保存在 `my_patents/dii_benchmark_20260719/`。获得合规授权导出后可用 `scripts/audit_dii_dataset.py` 自动补齐哈希、UT 去重、解析率和字段覆盖。

## 论文—算法映射

| 模块 | 当前实现 | 证据等级与边界 |
|---|---|---|
| 聚类标题 | Tseng、Lin & Lin (2007) 的文档级 TP/FP/FN/TN phi/Matthews 相关系数；术语簇内文档频率须严格超过 50% | CC0.5 标题准则为论文原公式；整体聚类不是论文完整流程 |
| 聚类 | TF-IDF 空间 K-means；SVD 仅展示；未指定 k 时以 3 个随机种子的平均 cosine silhouette（80%）和 ARI 稳定性（20%）选择 | 工程近似；Tseng 原文使用多阶段聚类，不能等同 |
| 近期增长词 | 文档频率、最小支持度、加性平滑、近期/历史窗口 | 启发式；明确不是 Kleinberg Burst |
| 功效矩阵 | Derwent `NOVELTY`/描述段代理技术手段，`USE`/`ADVANTAGE` 代理用途与效果 | 数据源代理；零共现不是蓝海结论 |
| 引证价值 | 边方向为引用者→被引者；专利族别名折叠；三阶段路径直接权重为 1/引用数；BC 成对权重为 2/(nA+nD)；SS=RO+BC | 仅 `paper_adapted`。原文部分矩阵细节需向作者索取，当前没有 `paper_exact`；普通混合 DII 模式不把 SS 纳入评分 |
| 三方专利 | US + EP + JP | 定义修正；依赖同族覆盖 |
| 竞对演化 | IPC 小类画像余弦变化、IPC 熵、主导 IPC 份额 | 工程启发式；不是 Tang (2012) DICT/PBC/HBC |
| PatentMiner | Tang 等的 DICT 动态主题模型及 PBC/HBC | 本轮未实现，不能借用其算法名称 |
| 潜力指标 | Kim/Bae 的前向引证、三方专利、独立权利要求等 | 当前 WoS 缺关键字段，不伪装计算 |

主要原文：Tseng et al., *Information Processing & Management* 43 (2007), DOI `10.1016/j.ipm.2006.11.011`；Tang et al., KDD 2012 PatentMiner；von Wartburg et al., *Research Policy* 34 (2005), DOI `10.1016/j.respol.2005.08.001`；Kim & Bae, *Technological Forecasting & Social Change* 117 (2017), DOI `10.1016/j.techfore.2016.11.023`。完整的逐工具登记见 `docs/tool-evidence-matrix.md`。

von Wartburg 原文的实证边界尤其重要：节点是专利族，网络包含核心和非核心族，样本是可变气门领域 107 个专利族，数据以 DE/EP/GB/WO 等欧洲式引证为主；论文明确警告混合 US 引证制度会造成偏差。SS 与专家“技术附加值”的相关系数 0.45 不能推广为财务价值或通用质量。代码中的复制模式因此要求同族覆盖≥50%、内部边解析率≥20%、欧洲式公开局占比≥80%，仍标为 `paper_adapted_replication` 而非 `paper_exact`。

## 优势、弱点与必要性

优势是 Engine/Tool 分层清楚、Pydantic Typed Result、单一 React/FastAPI 用户入口、可选 MCP 集成、10,000 件去重后的 DII 样例、已有测试与多 LLM 适配。统一执行契约可以把参数、耗时、字段覆盖、算法 ID、禁止结论和错误沿 REST、SSE、MCP 与 AI 证据通道传递。

正式文件链路已扩展到 Google Patents JSONL、USPTO grant XML 和 Patent File Wrapper JSON，缓解但没有消除数据字段天花板：来源导出仍可能缺失全文、外部前向引证、完整同族或最新法律状态。其他主要弱点是内部引证网络不闭合、文本算法的领域依赖、部分重分析需抽样，以及 LLM 报告依赖供应商稳定性。动态能力门禁避免把这些限制隐藏成“正常的零值”；EPO/CNIPA 仍为规划中。

其必要性在于把重复的数据清洗、统计、图表和证据整理自动化，并让分析人员把时间投入到检索策略、权利要求解释和业务判断。系统定位是透明的分析助手，不是自动法律结论机器。

## 安全与运行边界

- 服务默认绑定 `127.0.0.1`，CORS 默认仅允许本机 Vite 来源。
- `/api/data/load` 仅允许 `PATENT_DATA_ROOT` 内的目录。
- API Key 与敏感 Header 仅保存在后端进程内的凭证仓和 LLM client，不写入日志、API 响应或磁盘；SQLite 只保存非敏感配置及敏感 Header 的字段名。
- 远程 Base URL 强制 HTTPS，本机回环地址可用 HTTP；URL 用户信息、query、fragment、Header 换行注入和编排器保留 JSON 字段均被拒绝。
- 模型连接前重新解析 DNS；私网、链路本地、云元数据、特殊用途和公私混合解析结果均被拒绝，HTTP 客户端禁用重定向。
- 请求体和 Agent/工具并发均有本地有界门禁；报告标题与消息统一 HTML 转义，只有内部生成图表能进入受控图表容器。
- 请求、SSE、轮次、工具和 LLM 上下文传播 `trace_id`；结构化日志不记录 API Key、敏感 Header 或推理内容。
- MCP HTTP 默认只监听回环地址；非回环监听必须配置 `MCP_AUTH_TOKEN` 并通过 Bearer 认证。
- 完整探测通过前不能激活；Agent 生成期间不能切换、编辑/删除当前配置或断开连接。
- 默认详细回复；简洁模式由 `response_mode=concise` 显式选择。

## 验收

回归门禁包括固定五年以上合成 WoS 金样、16 工具 envelope/provenance/metrics、算法合成
数据、Agent 审批/失败/恢复、MCP 一致性、SQLite 迁移、安全边界、前端组件和生产构建及
10,000 件去重样例全工具冒烟。计数和标识符精确比较，浮点指标使用显式容差；随机算法固定
种子和线程配置。更新金样必须执行显式生成脚本并接受代码审查。抽样工具必须公开总体、
样本量、随机种子或抽样标记。
