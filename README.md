# PatentAgent

基于大语言模型（LLM）驱动的智能专利分析系统。用自然语言与专利数据对话。

> PatentSmelter 的下一代演进。从"批处理工具箱"到"对话式智能分析"。

> 唯一用户入口：`frontend/` + `server.py`。MCP stdio/HTTP 服务作为可选的
> 外部 AI 客户端集成接口，与 Web 共用工具注册表，但不是另一套用户界面。

> 暂时以AGPL的形式开源。以后也许（但不保证）会转换为更宽松的模式。Contact: 2507380208@wtu.edu.cn 

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11%20-%203.13-blue" alt="Python 3.11-3.13">
  <img src="https://img.shields.io/badge/React-19-61dafb" alt="React">
  <img src="https://img.shields.io/badge/FastAPI-0.115+-009688" alt="FastAPI">
  <img src="https://img.shields.io/badge/Tools-24-orange" alt="Tools">
  <img src="https://img.shields.io/badge/Version-3.1-lightgrey" alt="Version">
</p>

## 快速开始

后端以 `pyproject.toml` 为唯一依赖声明，`uv.lock` 固定完整环境。当前支持 Python
`>=3.11,<3.14`（即 3.11、3.12、3.13），推荐使用 Python 3.13；CI 后端矩阵覆盖这三个版本：

```bash
uv sync --frozen --extra mcp --group dev
cd frontend && npm ci && cd ..
```

`requirements.txt` 是由锁文件导出的 pip 兼容清单，不应手工编辑。MiniLM 运行库属于
标准依赖；模型权重不会提交到仓库，只在首次显式启用 Beta 时下载约 471MB 到用户缓存目录。

### 一键启动（推荐）

```bash
cd PatentAgent
bash start.sh
```

自动启动后端 (FastAPI :8000) 和前端 (React :5173)，浏览器自动打开。

### 分别启动

**后端：**
```bash
cd PatentAgent
MCP_INPUT_DIR=./my_patents PATENT_DATA_ROOT=./my_patents uvicorn server:app --host 127.0.0.1 --port 8000
# API 文档: http://localhost:8000/docs
```

**前端：**
```bash
cd PatentAgent/frontend
npm ci          # 首次运行，严格按 package-lock.json 安装
npm run dev     # http://localhost:5173
```

### 可选：MCP 集成

```bash
cd PatentAgent
pip install mcp
python mcp_server.py
```
需要从 Claude Code / VS Code / Cursor 调用分析工具时再配置 MCP。详见
[MCP 使用指南](#mcp-使用指南)。

## 核心特性

- **对话式交互** — 自然语言提问，Agent 理解意图、制定计划、调用工具、输出结论
- **动态工具目录** — 工具数以 `/api/tools` 注册表为单一来源，并按当前字段能力启用或降级
- **智能关键词过滤** — 400 词专利专用停用词库 + NLTK 词性过滤，剔除说明书套话和语境噪音
- **结果可追溯** — 图表、结构化摘要、方法、字段覆盖率、警告、参数和耗时统一返回
- **原生可视化** — React/ECharts 优先读取结构化结果，支持原始尺寸、适应窗格、全屏、PNG/JSON 导出与数据表切换
- **多供应商 LLM** — 多个命名配置、OpenAI/Anthropic/DeepSeek 三类协议、OpenRouter/Ollama/vLLM 与自定义兼容服务
- **有界加载** — 受限线程并行解析 + 内容哈希校验的 Parquet 缓存；实际耗时随文件数量、记录体积和磁盘而变
- **报告导出** — HTML 报告（含完整中文排版），CSV 数据导出
- **MCP 协议支持** — 标准 MCP (Model Context Protocol) stdio/HTTP 服务器，Claude Code / VS Code / Cursor 可直接调用全部工具
- **算法证据登记表** — 24 个工具逐一登记算法 ID、版本、公式、字段门槛、论文来源与禁止结论
- **统一文件导入** — WoS、Google Patents JSONL、USPTO grant XML/PFW JSON 统一进入 PatentRecord v3，并返回字段覆盖、冲突与来源能力报告
- **多语言检索 Beta** — 单次显式启用本地 MiniLM 与词法 RRF；失败会明确回退，不替代默认 TF-IDF 基线
- **中英文界面** — 支持简体中文（zh-CN）与英文（en-US）即时切换；语言选择保存到浏览器本地存储，专利原文、用户输入、检索结果和 AI 内容保持原样
- **统一分析工作台** — 会话、数据集、九类能力、报告和设置采用独立页面，保持一个总调度 Agent
- **网页数据集库** — 多文件安全上传、异步导入、内容去重、版本审计和会话显式绑定

## 数据源能力

正式支持 WoS Derwent tagged text、Google Patents Public Data JSONL、USPTO grant
full-text XML 和 Patent File Wrapper JSON。EPO OPS 与 CNIPA 仅处于格式准备阶段，
没有账号、抓取器或生产适配器。详细字段边界和官方来源见
[数据源能力矩阵](docs/data-source-capabilities.md)。
固定样例的字段覆盖、代理指标和 10 万条工程压力结果见
[V3.1 验证报告](docs/validation-report-v3.1.md)。

`POST /api/data/load` 可传 `source_format=auto|wos_dii|google_patents_jsonl|uspto_grant_xml|uspto_file_wrapper_json`；
旧请求缺省仍为 `auto`。自动模式按内容签名识别已支持的标准格式，并在导入报告中逐文件
返回识别依据；它不对任意厂商变体承诺 100% 命中。建议导入目录提供
`patentagent-import.json` 和 SHA-256 以获得确定性识别，失败时也可手工指定格式。

## 工具清单

| 工具 | 说明 |
|------|------|
| `get_dataset_summary` | 数据集概况（总量/时间/IPC/Top申请人） |
| `analyze_patent_trend` | 专利公开趋势（月度/年度，支持IPC/申请人筛选） |
| `analyze_lifecycle` | 公开量累计与同比增长（不自动判定生命周期） |
| `analyze_ipc_distribution` | IPC 分类热力图（标注次数/去重专利/同族归一化三种口径） |
| `generate_wordcloud` | 关键词文档频率 + 词频诊断（含词性过滤） |
| `analyze_burst_terms` | 近期增长词（最小支持、平滑；非 Kleinberg Burst） |
| `analyze_yearly_keywords` | 逐年关键词对比（年份 × 技术词热力图） |
| `analyze_country_distribution` | 首个公开局分布（不等同同族市场覆盖） |
| `analyze_co_network` | 申请人合作网络（交互式可拖拽） |
| `analyze_tech_roadmap` | 默认年度技术主题时间轴；同族、优先权与引证覆盖门禁通过后附待复核路线 |
| `analyze_tech_matrix` | Derwent 摘要代理功效矩阵 + 低共现复核候选 |
| `analyze_clustering` | TF-IDF 空间 K-means + silhouette 选 k + CC0.5 标题 |
| `analyze_patent_valuation` | 当前数据集内相对工程评分；含权重敏感性与缺失影响（不是财务估值） |
| `analyze_competitor_evolution` | IPC profile cosine shift / entropy / dominant share |
| `search_patents` | 默认 TF-IDF；可单次启用多语言 MiniLM+RRF Beta（都不是查全检索） |
| `read_patent_details` | 当前数据源记录读取（Derwent 摘要不是完整说明书） |
| `analyze_entity_portfolio` | 分角色规范实体排名、别名、年度趋势与 IPC 构成 |
| `analyze_concentration` | CR3/5/10、HHI、Gini、Shannon entropy 与 bootstrap 稳定性 |
| `analyze_citation_network` | 内部/外部边分离的引证、共引与文献耦合描述 |
| `analyze_family_geography` | 优先权地、首次公开局、同族覆盖局等分口径地域统计 |
| `audit_search_strategy` | 检索策略版本、返回集差异、已知专利回查与滚雪球候选 |
| `analyze_legal_status` | 权威来源与 as-of 门禁下的状态/事件分离统计 |
| `monitor_patent_changes` | 内容指纹化检索基线与去重数据变化监测 |
| `analyze_claim_elements` | 权利要求依赖树、可逆要素拆分与产品映射人工复核草稿 |

## MCP 使用指南

PatentAgent 提供标准 MCP 服务器；可用工具数量以运行时注册表为准，与 `/api/tools` 保持一致。

### 什么是 MCP

MCP 是一种标准化的 AI 工具通信协议。有了它，AI 客户端不再局限于"只能聊天"，而是可以主动发现和调用运行时注册表中的工具。AI 客户端可以：

- 自动发现有哪些分析工具可用
- 根据用户意图选择合适的工具
- 传参调用工具，获取结构化分析结果
- 基于真实数据撰写分析结论

### 安装 MCP 依赖

```bash
pip install mcp
```

### 启动 MCP 服务器

**stdio 模式（推荐，用于 Claude Code / VS Code / Cursor）：**

```bash
python mcp_server.py
```

服务器通过标准输入输出与客户端通信，不需要网络端口。

**HTTP 模式（用于远程访问）：**

```bash
python mcp_http_server.py --port 8000 --host 127.0.0.1
```

HTTP 默认只允许本机。若确需绑定非回环地址，必须同时设置强随机
`MCP_AUTH_TOKEN`，客户端以 `Authorization: Bearer <token>` 认证；缺少令牌时服务拒绝启动。

### 环境变量配置

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `MCP_INPUT_DIR` | `./my_patents` | 专利数据文件目录 |
| `MCP_STORE_CACHE_TTL` | `300` | 数据缓存有效期（秒），超时自动从磁盘重载 |
| `MCP_LOG_LEVEL` | `INFO` | 日志级别：DEBUG / INFO / WARNING / ERROR |
| `MCP_HTTP_PORT` | `8000` | HTTP 模式监听端口 |
| `MCP_HTTP_HOST` | `127.0.0.1` | HTTP 模式监听地址 |
| `MCP_AUTH_TOKEN` | 空 | 非回环监听必填；HTTP 客户端使用 Bearer Token |
| `MCP_MAX_ITEMS_IN_RESULT` | `50` | 分析结果中列表字段的最大条目数 |
| `PATENTAGENT_MAX_UPLOAD_FILE_BYTES` | `268435456` | 网页上传的单文件大小上限 |
| `PATENTAGENT_MAX_UPLOAD_TOTAL_BYTES` | `536870912` | 单次网页上传总量上限 |
| `PATENTAGENT_DATASET_CACHE_SIZE` | `1` | 运行时同时缓存的数据集版本数 |

### 配置 Claude Code

在项目根目录创建或编辑 `.mcp.json`：

```json
{
  "mcpServers": {
    "patent-agent": {
      "command": "python3",
      "args": ["/绝对路径/PatentAgent/mcp_server.py"],
      "env": {
        "MCP_INPUT_DIR": "/绝对路径/my_patents",
        "MCP_LOG_LEVEL": "WARNING"
      }
    }
  }
}
```

重启 Claude Code 后，MCP 服务器自动启动。你可以直接说：

- "列出可用的专利分析工具"
- "给我一个专利数据集的总览"
- "分析 2018 到 2022 年的公开趋势"
- "找找技术空白点，哪些方向还没有专利布局"
- "用词云展示技术热点"

### 配置 VS Code / Cursor

在项目根目录创建 `.vscode/mcp.json`：

```json
{
  "servers": {
    "patent-agent": {
      "type": "stdio",
      "command": "python3",
      "args": ["/绝对路径/PatentAgent/mcp_server.py"],
      "env": {
        "MCP_INPUT_DIR": "/绝对路径/my_patents",
        "MCP_LOG_LEVEL": "WARNING"
      }
    }
  }
}
```

### MCP 工具清单

MCP 服务器暴露的工具接口（数量以运行时注册表为准）：

| 工具名 | 参数 | 说明 |
|--------|------|------|
| `get_dataset_summary` | 无 | 数据集概况（总量/时间/IPC/Top 申请人） |
| `analyze_patent_trend` | `chart_type`, `year_start`, `year_end`, `ipc_filter`, `applicant_filter` | 公开趋势分析 |
| `analyze_lifecycle` | 无 | 公开量累计与年增长率（不判定生命周期） |
| `analyze_ipc_distribution` | 无 | IPC 分类热力图 |
| `generate_wordcloud` | `text_source` | 关键词词云 + 词频柱状图 |
| `analyze_burst_terms` | 无 | 技术突发词检测 |
| `analyze_yearly_keywords` | `text_source` | 逐年关键词对比 |
| `analyze_country_distribution` | 无 | 首个公开局分布（不是同族市场覆盖） |
| `analyze_co_network` | 无 | 申请人合作网络 |
| `analyze_tech_roadmap` | `top_n_per_year` | 年度主题时间线；同族/优先权/引证门禁通过时附待复核路线 |
| `analyze_tech_matrix` | `top_n` | Derwent 摘要代理功效矩阵 + 低共现复核候选 |
| `analyze_clustering` | `n_clusters` | 专利文本聚类 |
| `analyze_patent_valuation` | `top_n`, `citation_mode` | 价值筛查（不是财务估值） |
| `analyze_competitor_evolution` | `top_n_applicants` | IPC 画像工程指标（不是 PatentMiner DICT） |
| `search_patents` | `query`, `top_k`, `year_start`, `year_end` | TF-IDF 词项检索 |
| `read_patent_details` | `patent_numbers`（最多 5 个） | 当前数据源字段读取 |
| `analyze_entity_portfolio` | `entity_type`, `metric`, `top_n` | 可追溯实体组合与 reviewed 母公司映射 |
| `analyze_concentration` | `dimension`, `count_mode` | CRn、HHI、Gini 与 entropy |
| `analyze_citation_network` | `top_n` | 内外部边、自引、共引与耦合分析 |
| `analyze_family_geography` | `top_n` | 分口径同族与地域布局 |
| `audit_search_strategy` | `strategies`, `known_patent_numbers` | 检索版本和返回集审计 |
| `analyze_legal_status` | `top_n` | 权威来源时点法律状态与事件分析 |
| `monitor_patent_changes` | `strategy_id`, `strategy_version`, `query` | 内容版本化变化监测 |
| `analyze_claim_elements` | `patent_numbers`, `product_features` | 权利要求要素与产品词面映射复核草稿 |

除数据集总览外，分析工具还统一接受 `scope`，用于年份、IPC、主体、司法辖区、专利号、文本和同族去重范围。

### 分析结果格式

MCP 工具调用返回结构化 JSON `text` 数据，包含结果、口径、字段覆盖、算法身份、数据版本、警告和禁止结论。工具不再返回或传输可执行 HTML；React 客户端使用受信任的本地渲染器生成图表。

### 验证 MCP 服务器

可以使用 Python 脚本验证 MCP 服务器是否正常工作：

```bash
python -m pytest tests/test_mcp_integration.py -v
```

测试覆盖：服务器初始化、动态工具列表、工具调用、错误处理。

## 架构

```
唯一用户入口: React Frontend (Vite + TypeScript)
                       ↕ HTTP + SSE
              FastAPI Backend (server.py 兼容入口)
                       ↕
可选集成接口: MCP Server (stdio/HTTP, JSON-RPC)
         ↕
patent_agent 模块化单体 (application/domain/security/infrastructure/api)
         ↕
Agent 流水线 (Intent/Plan/Policy/Execute/Validate/Synthesize)
         ↕
Tool 层 (注册表为单一来源，含能力门禁与统一结果契约)
         ↕
Engine 层 (纯计算)
         ↕
数据访问层 (Parquet 缓存 + 列投影)
         ↕
知识库层 (24 工具算法证据登记表 + 决策模板)
```

## 项目结构

```
PatentAgent/
├── server.py              # FastAPI 后端（REST、会话管理与 SSE 流式）
├── start.sh               # 一键启动脚本
├── frontend/              # React 前端
│   ├── src/
│   │   ├── App.tsx         #   主应用（三栏布局）
│   │   ├── api.ts          #   全部 API 调用 + SSE 流
│   │   ├── types.ts        #   TypeScript 类型定义
│   │   ├── features/       #   datasets/sessions/agent/tools/providers/reports
│   │   └── components/     #   原生 ECharts、工具卡与消息组件
│   └── package.json
├── patent_agent/          # 模块化单体边界与公共强类型契约
│   ├── application/      #   数据、工具、报告等用例
│   ├── domain/           #   Dataset/Task/Tool envelope
│   ├── security/         #   内存凭证仓与模型 URL 安全
│   └── infrastructure/   #   AppContainer、配置、日志与请求门禁
├── reporting/             # 后端 HTML/Word/PDF 报告生成
├── agent/                 # Agent 编排层
│   ├── orchestrator.py    #   兼容外观与状态机
│   ├── pipeline.py        #   Planner/Executor/Validator/Synthesizer
│   ├── strategy_chains.py #   旧版兼容，Web 主流程不再调用
│   ├── cross_tool_synthesis.py  # 跨工具关联推理
│   ├── recommendation_engine.py # 战略建议生成
│   ├── adaptive_planner.py      # 旧版兼容，不会自动追加工具
│   ├── proactive_discovery.py   # 主动发现引擎
├── storage/conversation_store.py # 会话、轮次与结构化证据（不保存 API Key/图表 HTML）
├── storage/provider_store.py     # 非敏感供应商配置与幂等 SQLite 迁移
│   └── prompts.py
├── tools/                 # Tool 层（24 个运行时注册工具）
├── engine/                # 分析引擎层 (13个纯计算模块)
├── patent_mcp/            # MCP 服务器
├── mcp_server.py          # MCP stdio 入口
├── mcp_http_server.py     # MCP HTTP 入口
├── models/                # Pydantic 数据模型
├── knowledge/             # 单一算法证据登记表 + 决策模板
├── storage/               # 数据访问层
├── viz/                   # 旧客户端/MCP 的 pyecharts 兼容可视化层
└── tests/                 # Python 回归测试 + 前端渲染测试
```

运行状态由 FastAPI lifespan 创建的 `AppContainer` 持有，不再由 `server.py` 的可变模块
全局变量持有。SQLite 记录数据集版本、轮次任务、工具 provenance/metrics、审批、报告和
可续传事件；进程重启会把运行中任务标记为 `interrupted`，不会自动重复 LLM 调用。

## 可复现性与质量门禁

```bash
uv lock --check
uv run python -m pytest -q
cd frontend && npm test -- --run && npm run build
```

`tests/fixtures/wos_golden/` 是固定的五年以上合成 WoS 数据集；核心工具均校验统一的
`ToolExecutionEnvelope`、数据版本、字段覆盖、算法参数和执行指标。更新合成数据集运行
`python scripts/generate_golden_wos_fixture.py`；更新工具金样必须显式运行
`uv run python scripts/generate_tool_goldens.py` 并审查差异。GitHub Actions 的后端矩阵在
Python 3.11/3.12/3.13 上运行完整测试；`contracts-lock-migrations-mcp` 在 Python 3.12
执行锁文件检查、requirements 导出一致性、官方样例/契约/方法学校验及 MCP/供应商/可复现性回归；
`performance-100k-baseline` 在 Python 3.13 执行 10 万条检索与工具基线；`frontend-node-20`
在 Node 20 上执行 `npm ci`、前端测试和生产构建。上述检查全部通过后才满足合并门禁；`V*`
标签只生成源码、前端产物与 SHA-256 校验和，不发布 PyPI。

本轮前端国际化与算法审计的验证结果（2026-09-02）：前端测试 12 个文件、61 项通过；
`npm run build` 通过；在 zh-CN/en-US 和 1440×900、768×1024、390×844、360×800
视口下检查五个页面，语言切换、持久化、`document.documentElement.lang` 和窄屏布局均通过。
后端未运行时不进行真实 API 联调。

## 配置

### LLM 设置

左侧供应商卡只显示当前名称、协议、模型与连接状态；“切换 / 设置”打开高级设置。
高级设置可以保存多个命名配置，并提供 OpenAI、Claude、DeepSeek、OpenRouter、
Ollama、vLLM 和自定义预设。显示名称只用于识别配置，请求消息格式只由
`openai_chat`、`anthropic_messages` 或 `deepseek_chat` 协议决定。

“保存”只写入非敏感配置；“测试连接”不会切换 Agent；“保存并连接”只有在完整能力
探测通过后才替换当前 Agent。探测依次验证普通文本、工具选择、本地工具结果回传、
最终文本和结构化 JSON 输出。仅能聊天但不能完成工具闭环的模型不能激活。

API Key 与标为“敏感”的 Extra Header 只保存在后端进程内存：不会写入
`.patentagent/sessions.db`、日志或 API 响应。后端重启后会恢复配置和上次选择，但必须
重新输入凭证。Ollama/vLLM 等本机端点可选择“无鉴权”；远程 Base URL 必须使用 HTTPS。
Extra Body 只接受 JSON 对象，不能覆盖 `model/messages/tools/tool_choice/response_format/max_tokens`
等编排器字段。Agent 正在生成时不能切换、编辑当前配置、删除当前配置或断开连接。

供应商配置 API：

```text
GET    /api/llm/profiles
POST   /api/llm/profiles
PATCH  /api/llm/profiles/{id}
DELETE /api/llm/profiles/{id}
POST   /api/llm/profiles/{id}/models
POST   /api/llm/profiles/{id}/probe
POST   /api/llm/profiles/{id}/activate
POST   /api/llm/disconnect
```

旧 `/api/agent/config` 继续兼容，并经过相同的 URL 校验、协议适配和完整能力探测。

Web Agent 的正常流程由 LLM 第一轮直接选择最小必要工具集，本地参数/数据/
成本门禁通过后执行，再按 OpenAI、Claude 或 DeepSeek 的官方消息协议回传结果。
第二轮禁用新工具并生成针对当前问题的结构化答案和动态追问。

你也可以在网页端利用“高级设置”来自行配置服务商，例如Openrouter等。本人致力于降低软件使用门槛。建议用户使用Deepseek作为默认模型，能大大降低使用成本。

### 数据格式

支持 Web of Science (Clarivate Derwent) 专利导出 `.txt` 文件。

将文件放入 `my_patents/` 目录，在 GUI 中加载即可。支持增量更新，缓存自动失效。

## 文档

- [V3.1 更新日志](CHANGELOG.md) — 当前版本的重要新增、变更、安全修复与兼容说明
- [内部算法审计](docs/algorithm-audit.md) — 24 个运行时注册工具、29 个登记算法身份及其调用链、数据边界和未确认项
- [项目与论文审计](docs/project-audit.md) — 数据质量、论文适用条件、优势/弱点和法律边界
- [24 工具算法证据矩阵](docs/tool-evidence-matrix.md) — 由 `knowledge/tool_evidence.json` 自动生成
- DII 基准数据状态 — 检索式、授权核验和导入审计方法（随专利数据目录提供，不包含在源码仓库中）
- [软件说明书](软件说明书.txt) — 架构设计、功能详解、技术栈、版本历史
- [操作指南](操作指南.txt) — 从零开始的手把手教程，含环境配置、工具使用、常见问题
- [导师演示流程](docs/mentor-demo-guide.md) — 从上传数据到生成可追溯 HTML 报告的完整演示脚本

## 作者

Wu Jinhong、Chen Siyu。版权与许可声明见 [LICENSE](LICENSE)。
