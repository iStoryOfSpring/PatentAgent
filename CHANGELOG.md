# PatentAgent 更新日志

本项目采用面向用户的 `V主版本.次版本` 发布标识；Python 与前端包元数据使用对应的语义版本号。

## V3.1 — 2026-07-22

作者：Wu Jinhong、Chen Siyu

### 新增

- 新增多个命名 LLM 供应商配置，支持 OpenAI Chat、Anthropic Messages 和 DeepSeek Chat 三类兼容协议。
- 新增供应商预设、模型发现、分阶段能力探测、激活/断开状态机，以及内存凭证仓。
- 新增 `AppContainer`、版本化 `DatasetSnapshot`、`ToolExecutionEnvelope` 和可拆分的 Agent 六段流水线。
- 新增数据集版本、任务事件、审批、报告和工具 provenance/metrics 的 SQLite 持久化。
- 新增任务查询、取消、恢复接口，以及贯穿 HTTP、SSE、任务、工具和 LLM 调用的 `trace_id`。
- 新增 `uv.lock`、Python 3.10–3.12 兼容矩阵、GitHub Actions、合成 WoS fixture 和 16 个工具的黄金回归结果。
- 前端引入 TanStack Query，并按应用壳、数据集、Agent、工具、供应商和报告逐步拆分 feature 模块。

### 变更

- React Web（`frontend/` + `server.py`）成为唯一持续维护的用户界面；MCP stdio/HTTP 保留为可选集成接口。
- `server.py` 改用 lifespan、应用容器和依赖注入管理服务；现有 REST、SSE 和 MCP 契约保持兼容。
- 报告生成迁移至 `reporting/generator.py`，`/api/report/export` 的路由和响应格式不变。
- 工具结果强制附带数据版本、字段覆盖、算法参数、执行指标、证据、警告和结构化错误。
- Agent 内部职责拆分为意图解析、规划、策略、执行、校验和综合，综合阶段只读取已校验结果。
- 算法仍遵循项目论文边界；仅修复确定性排序、空值处理和版本证据登记等正确性问题。

### 安全

- API Key 与敏感 Header 仅保存在后端进程内存，不写入 SQLite、日志或 API 响应。
- 自定义模型地址增加 DNS 解析检查，拒绝非回环私网、链路本地、云元数据、特殊用途地址和重定向。
- 报告标题与消息统一 HTML 转义，并限制可进入报告的图表产物。
- 增加请求体大小、Agent/工具并发上限、MCP 非回环认证要求、错误分类和敏感信息脱敏。

### 移除

- 删除根目录旧 mock React 工程及其依赖。
- 删除 Streamlit、Chainlit、空壳 CLI 和旧 UI 专用同步 LLM/Orchestrator 调用链。
- 删除迁移后为空的 `ui/` 包。

### 兼容性

- 保持现有 `/api/*`、SSE 事件、报告导出和 MCP 工具名称兼容。
- 旧 `/api/agent/config` 继续可用，并经过统一协议适配与能力探测。
- SQLite 迁移保持版本化、事务化和幂等；现有用户配置、会话与数据不会被主动清除。

## V3.0 — 2026-07

- 建立 React + FastAPI 的对话式专利分析入口。
- 提供 16 个可追溯分析工具、SSE 流式响应、MCP 集成与 HTML/CSV 报告导出。
- 建立 SQLite 会话、执行快照和初版供应商配置能力。
