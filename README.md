# PatentAgent

基于大语言模型（LLM）驱动的智能专利分析系统。用自然语言与专利数据对话。

> PatentSmelter 的下一代演进。从"批处理工具箱"到"对话式智能分析"。

> 推荐且唯一持续维护的用户入口：`frontend/` + `server.py`。根目录旧 mock 前端、
> Streamlit/Chainlit 兼容入口仅为迁移保留，不代表当前能力。

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-blue" alt="Python">
  <img src="https://img.shields.io/badge/React-19-61dafb" alt="React">
  <img src="https://img.shields.io/badge/FastAPI-0.115+-009688" alt="FastAPI">
  <img src="https://img.shields.io/badge/Tools-16-orange" alt="Tools">
  <img src="https://img.shields.io/badge/Version-3.0-lightgrey" alt="Version">
</p>

## 快速开始

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
npm install     # 首次运行
npm run dev     # http://localhost:5173
```

### MCP Server

```bash
cd PatentAgent
pip install mcp
python mcp_server.py
```
在 Claude Code / VS Code / Cursor 中配置 MCP 连接。详见 [MCP 使用指南](#mcp-使用指南)。

## 核心特性

- **对话式交互** — 自然语言提问，Agent 理解意图、制定计划、调用工具、输出结论
- **动态工具目录** — 工具数以 `/api/tools` 注册表为单一来源，并按当前字段能力启用或降级
- **智能关键词过滤** — 400 词专利专用停用词库 + NLTK 词性过滤，剔除说明书套话和语境噪音
- **结果可追溯** — 图表、结构化摘要、方法、字段覆盖率、警告、参数和耗时统一返回
- **原生可视化** — React/ECharts 优先读取结构化结果，支持原始尺寸、适应窗格、全屏、PNG/JSON 导出与数据表切换
- **多供应商 LLM** — Claude / OpenAI / DeepSeek，支持本地模型隐私模式
- **极速加载** — 8 线程并行解析 + Pickle 缓存，首次 10s，缓存命中 0.3s
- **报告导出** — HTML 报告（含完整中文排版），CSV 数据导出
- **MCP 协议支持** — 标准 MCP (Model Context Protocol) stdio/HTTP 服务器，Claude Code / VS Code / Cursor 可直接调用全部工具
- **中英双语** — 顶栏一键切换界面语言
- **算法证据登记表** — 16 个工具逐一登记算法 ID、版本、公式、字段门槛、论文来源与禁止结论

## 工具清单

| 工具 | 说明 |
|------|------|
| `get_dataset_summary` | 数据集概况（总量/时间/IPC/Top申请人） |
| `analyze_patent_trend` | 专利公开趋势（月度/年度，支持IPC/申请人筛选） |
| `analyze_lifecycle` | 公开量累计与同比增长（不自动判定生命周期） |
| `analyze_ipc_distribution` | IPC 分类热力图（年份 × A-H 部级） |
| `generate_wordcloud` | 关键词词云 + 词频柱状图（含词性过滤） |
| `analyze_burst_terms` | 近期增长词（最小支持、平滑；非 Kleinberg Burst） |
| `analyze_yearly_keywords` | 逐年关键词对比（年份 × 技术词热力图） |
| `analyze_country_distribution` | 首个公开局分布（不等同同族市场覆盖） |
| `analyze_co_network` | 申请人合作网络（交互式可拖拽） |
| `analyze_tech_roadmap` | 年度技术主题时间轴（引证充分时显示内部路径） |
| `analyze_tech_matrix` | Derwent 摘要代理功效矩阵 + 低共现复核候选 |
| `analyze_clustering` | TF-IDF 空间 K-means + silhouette 选 k + CC0.5 标题 |
| `analyze_patent_valuation` | 稳健百分位价值筛查（不是财务估值） |
| `analyze_competitor_evolution` | IPC profile cosine shift / entropy / dominant share |
| `search_patents` | TF-IDF 词项相似度检索（不是语义嵌入或查全检索） |
| `read_patent_details` | 当前数据源记录读取（Derwent 摘要不是完整说明书） |

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

### 环境变量配置

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `MCP_INPUT_DIR` | `./my_patents` | 专利数据文件目录 |
| `MCP_STORE_CACHE_TTL` | `300` | 数据缓存有效期（秒），超时自动从磁盘重载 |
| `MCP_LOG_LEVEL` | `INFO` | 日志级别：DEBUG / INFO / WARNING / ERROR |
| `MCP_HTTP_PORT` | `8000` | HTTP 模式监听端口 |
| `MCP_HTTP_HOST` | `127.0.0.1` | HTTP 模式监听地址 |
| `MCP_MAX_ITEMS_IN_RESULT` | `50` | 分析结果中列表字段的最大条目数 |

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
| `analyze_tech_roadmap` | `top_n_per_year` | 技术路线图 |
| `analyze_tech_matrix` | `top_n` | Derwent 摘要代理功效矩阵 + 低共现复核候选 |
| `analyze_clustering` | `n_clusters` | 专利文本聚类 |
| `analyze_patent_valuation` | `top_n`, `citation_mode` | 价值筛查（不是财务估值） |
| `analyze_competitor_evolution` | `top_n_applicants` | IPC 画像工程指标（不是 PatentMiner DICT） |
| `search_patents` | `query`, `top_k`, `year_start`, `year_end` | TF-IDF 词项检索 |
| `read_patent_details` | `patent_numbers`（最多 5 个） | 当前数据源字段读取 |

### 分析结果格式

MCP 工具调用返回两种内容类型：

- **`text`** — 结构化 JSON 数据，包含分析结果的主要数据（如趋势数据点、词频列表、矩阵数值等）
- **`resource`**（可选）— 嵌入式 HTML 图表（text/html MIME），客户端渲染为交互式 pyecharts 图表

### 验证 MCP 服务器

可以使用 Python 脚本验证 MCP 服务器是否正常工作：

```bash
python -m pytest tests/test_mcp_integration.py -v
```

测试覆盖：服务器初始化、动态工具列表、工具调用、错误处理。

## 架构

```
React Frontend (Vite + TypeScript)  |  MCP Server (stdio/HTTP)
         ↕ HTTP + SSE                         ↕ JSON-RPC
FastAPI Backend (server.py)
         ↕
Agent 编排层 (条件/依赖/重试 + 完整证据分块综合 + SQLite 持久会话)
         ↕
Tool 层 (注册表为单一来源，含能力门禁与统一结果契约)
         ↕
Engine 层 (纯计算)
         ↕
数据访问层 (Parquet 缓存 + 列投影)
         ↕
知识库层 (16 工具算法证据登记表 + 决策模板)
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
│   │   └── components/     #   原生 ECharts 注册表、兼容 ChartFrame、工具卡与消息组件
│   └── package.json
├── agent/                 # Agent 编排层
│   ├── orchestrator.py    #   状态机 + 工具编排
│   ├── strategy_chains.py #   旧版兼容，Web 主流程不再调用
│   ├── cross_tool_synthesis.py  # 跨工具关联推理
│   ├── recommendation_engine.py # 战略建议生成
│   ├── adaptive_planner.py      # 旧版兼容，不会自动追加工具
│   ├── proactive_discovery.py   # 主动发现引擎
├── storage/conversation_store.py # 会话、轮次与结构化证据（不保存 API Key/图表 HTML）
│   └── prompts.py
├── tools/                 # Tool 层（16 个运行时注册工具）
├── engine/                # 分析引擎层 (13个纯计算模块)
├── patent_mcp/            # MCP 服务器
├── mcp_server.py          # MCP stdio 入口
├── models/                # Pydantic 数据模型
├── knowledge/             # 单一算法证据登记表 + 决策模板
├── storage/               # 数据访问层
├── viz/                   # 旧客户端/MCP 的 pyecharts 兼容可视化层
└── tests/                 # Python 回归测试 + 前端渲染测试
```

## 配置

### LLM 设置

```
Claude API   → 长上下文 + 工具调用最成熟（推荐）
OpenAI API   → 兼容性最广
DeepSeek API → 中文性价比最优，支持国内直接访问

默认模型: Claude `claude-sonnet-4-6` / OpenAI `gpt-4.1` /
DeepSeek `deepseek-v4-flash`

本地隐私模式: vLLM + Qwen3-32B / DeepSeek-V3 + BGE-M3 Embedding
```

连接检查不只测试一次文本回复，还会完成一次无副作用的
`tool_call → 本地结果回传 → 最终文本`，并校验一次结构化 JSON 输出。只有全部通过，前端才显示
“LLM 工具调用已就绪”。

Web Agent 的正常流程由 LLM 第一轮直接选择最小必要工具集，本地参数/数据/
成本门禁通过后执行，再按 OpenAI、Claude 或 DeepSeek 的官方消息协议回传结果。
第二轮禁用新工具并生成针对当前问题的结构化答案和动态追问。

### 数据格式

支持 Web of Science (Clarivate Derwent) 专利导出 `.txt` 文件。

将文件放入 `my_patents/` 目录，在 GUI 中加载即可。支持增量更新，缓存自动失效。

## 文档

- [项目与论文审计](docs/project-audit.md) — 数据质量、论文适用条件、优势/弱点和法律边界
- [16 工具算法证据矩阵](docs/tool-evidence-matrix.md) — 由 `knowledge/tool_evidence.json` 自动生成
- DII 基准数据状态 — 检索式、授权核验和导入审计方法（随专利数据目录提供，不包含在源码仓库中）
- [软件说明书](软件说明书.txt) — 架构设计、功能详解、技术栈、版本历史
- [操作指南](操作指南.txt) — 从零开始的手把手教程，含环境配置、工具使用、常见问题
