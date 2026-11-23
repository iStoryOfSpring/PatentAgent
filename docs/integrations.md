# 配置与集成

[返回首页](../README.md) · [离线图文演示](mentor-demo-guide.md)

| 使用场景 | 入口 | 数据从哪里来 |
|---|---|---|
| 分析师直接执行本地工具 | Web → 能力与工具 | 网页导入并绑定到会话的数据版本 |
| 用自然语言分派工具和归纳结果 | Web → 设置 → 保存并连接 | 同一会话的版本和工具执行结果 |
| 外部 AI 客户端直接调用工具 | MCP stdio → `mcp_server.py` | MCP 进程的 `MCP_INPUT_DIR` |

## Web 与语言模型

1. 在「设置」新建命名配置，选择供应商预设，填写模型和 Base URL。支持 `openai_chat`、`anthropic_messages` 和 `deepseek_chat` 三类协议，Ollama、vLLM、OpenRouter 和自定义兼容服务按其请求协议配置。
2. 远程服务使用 HTTPS；本机 Ollama 或 vLLM 可以选择无鉴权。请求将发送到所选端点，使用自有数据前应核对服务提供方及会话中的材料。
3. 「保存」写入配置。「测试连接」探测能力。「保存并连接」在普通文本、工具选择、工具结果回传和结构化输出探测通过后激活模型。能生成文本的端点也可能在工具探测环节失败。
4. 打开已绑定数据的会话，问「按申请日统计申请数，按年分组」。展开工具步骤，检查日期依据、计数单位和输出，随后可在「报告」页生成会话报告。

API Key 与标记为敏感的额外请求头保存在后端内存。服务重启后恢复命名配置，敏感凭据需重新填写。Extra Body 接受 JSON 对象，`model`、`messages`、`tools` 和 `tool_choice` 等编排字段由应用管理。

## MCP stdio

先在项目根目录执行 `uv sync --frozen --extra mcp --group dev`。Web 和 MCP 共享工具注册表；单独启动的 MCP 进程从自己的输入目录读取数据。仓库的 [samples/offline](../samples/offline) 只包含一份三条记录的 JSONL，很适合第一次验证。

```bash
MCP_INPUT_DIR=./samples/offline uv run --frozen --extra mcp python mcp_server.py
```

正常启动后进程等待 MCP 客户端。使用客户端的工具列表查找 `get_dataset_summary`，以空参数 `{}` 调用。在上述目录下，结果内的 `data_quality.total_patents` 应为 **3**。要改用自己的数据，将输入目录换为受支持文件所在的目录并重新启动客户端连接。

在使用 `mcpServers` 配置结构的客户端（如项目原有的 Claude Code 示例）中，可把以下内容写入项目的 `.mcp.json`。将两处项目绝对路径替换为你的实际位置；客户端需要能找到 `uv`。

```json
{
  "mcpServers": {
    "patent-agent": {
      "command": "uv",
      "args": ["run", "--directory", "/绝对路径/PatentAgent", "--frozen", "--extra", "mcp", "python", "mcp_server.py"],
      "env": {
        "MCP_INPUT_DIR": "/绝对路径/PatentAgent/samples/offline",
        "MCP_LOG_LEVEL": "WARNING"
      }
    }
  }
}
```

使用 VS Code 项目配置时，文件位置为 `.vscode/mcp.json`，顶层键为 `servers`，在 `patent-agent` 内加上 `"type": "stdio"`。复用上面的命令、参数与输入目录。工具逐项列在[证据矩阵](tool-evidence-matrix.md)，结果包含本次统计方法、数据质量和警告。

### MCP HTTP 入口的当前状态

在应用提交 `0bcc172` 与锁定的 Python MCP SDK `1.28.1` 上，启动 `mcp_http_server.py` 会在监听端口前报 `ImportError: cannot import name 'streamable_http_server'`。当前可复现的 MCP 接入方式为上面的 stdio。浏览器使用 FastAPI 的 REST 与 SSE，独立于这个 HTTP 传输入口。

## 分别启动前后端

先完成[首页依赖安装](../README.md#快速开始)。从项目根目录打开两个终端。第一个终端运行：

```bash
MCP_INPUT_DIR=./my_patents PATENT_DATA_ROOT=./my_patents \
  uv run --frozen --extra mcp python -m uvicorn server:app --host 127.0.0.1 --port 8000
```

第二个终端运行：

```bash
(cd frontend && npm run dev -- --host 127.0.0.1 --port 5173 --strictPort)
```

打开 `http://127.0.0.1:5173`。如果自行更改后端端口，启动前端时同步设置 `VITE_API_TARGET`，例如 `http://127.0.0.1:8100`。后端 `GET /api/health` 返回应用标识 `PatentAgent`，`GET /api/tools` 返回工具清单。

| 配置 | 缺省设置或单位 | 用途 |
|---|---|---|
| `PATENTAGENT_FRONTEND_PORT` / `PATENTAGENT_BACKEND_PORT` | 5173 / 8000 | 一键启动器的前后端口 |
| `PATENTAGENT_OPEN_BROWSER` | 设为 0 时关闭自动打开 | 无桌面环境启动 |
| `MCP_INPUT_DIR` | 默认数据目录 `my_patents` | 指定进程读取的本地数据 |
| `PATENT_DATA_ROOT` | 启动器默认沿用输入目录 | Web 数据根目录 |
| `PATENTAGENT_SESSION_DB` | `.patentagent/sessions.db` | 指定 Web 会话与执行证据的 SQLite 文件 |
| `PATENTAGENT_MAX_UPLOAD_FILE_BYTES` / `PATENTAGENT_MAX_UPLOAD_TOTAL_BYTES` | 256 MiB / 512 MiB | 单文件与单次网页上传总量上限，设置值以字节计 |
| `PATENTAGENT_DATASET_CACHE_SIZE` | 1 个版本 | 运行时同时缓存的数据版本数 |
| `MCP_STORE_CACHE_TTL` / `MCP_MAX_ITEMS_IN_RESULT` | 300 秒 / 50 项 | MCP 数据缓存时间与结果列表上限 |
| `MCP_LOG_LEVEL` | INFO | MCP 日志级别 |
