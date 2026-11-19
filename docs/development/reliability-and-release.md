# 单机版可靠性与发布维护说明

## 交付合同

从正式提交及其发布压缩包，各在新目录启动一次。按[离线演示](../mentor-demo-guide.md)上传三条合成文献，绑定会话并检查两年的申请数、成员公开号与版本 ID。无需商业账号、模型密钥或本机专利库。运维范围为单机、单个后端进程。

| 组件 | 运行约定 | 主要回归 |
|---|---|---|
| 趋势证据 | 分组、执行或页码变化后，只有对应最新请求可更新数据、错误和忙碌状态 | 延迟成功、延迟失败、空分组、页码不匹配、过期执行与分页失败 |
| 本地导入 | SQLite 写事务确定实际版本归属，版本登记和任务完成一起提交。去重任务关联原版本 | 两个相同文件并发上传、提交前中断、提交成功但未应答、连续重启 |
| 启动器 | 从脚本位置定位 uv 环境。健康接口含 `application=PatentAgent` 和 `status=ok`，前端严格绑定端口。两端在 30 秒内就绪才显示地址 | 目录外启动、正常流程、端口占用、依赖缺失、子进程退出 |
| 发布 | 在干净检出构建一次。解压同一个压缩包后运行服务与 Chromium 验收 | 网络隔离在应用回环地址，使用临时数据库和合成样例，失败保留诊断 |

## 导入中断处理

上传先记录 `queued`，进入 `parsing` 后存储目标版本意向，然后发布。已有版本的原始导入归属保留；后续导入任务各自保存实际版本 ID。启动恢复只检查仍在队列或解析中的任务。

- 明确关联到唯一版本，且登记目录、重读内容指纹和版本 ID 均匹配时补记完成。
- 缺少已发布版本时标记 `failed/import_interrupted`，用户可重新上传。待核验目录、指纹不符、关联冲突时标记 `failed/import_recovery_conflict`。
- 根据任务 ID 核对 `GET /api/imports/{id}`、数据集版本历史和对应源文件。保留冲突目录供人工比对。终态任务在重复启动时保持原结果。恢复不会外呼或自动重跑采集。

## 开发检查

在仓库根目录执行。首次安装浏览器需要访问软件包源。Linux CI 使用 `playwright install --with-deps chromium`。

```bash
uv sync --frozen --extra mcp --group dev
(cd frontend && npm ci && npx --no-install playwright install chromium)
uv run --frozen --extra mcp python -m pytest -q
(cd frontend && npm test -- --run && npm run build)
uv run --frozen --extra mcp python scripts/check_doc_links.py
uv run --frozen --extra mcp python scripts/smoke_offline.py
```

浏览器脚本从无关临时目录调用启动器，分配本机端口，使用独立输入目录及 SQLite，并禁用打开系统浏览器。失败时查看 `frontend/offline-service.log`、`frontend/test-results/` 中的截图、trace 与断言上下文。日志只用于本次合成测试。

## CI 与发布

- 常规质量门禁覆盖 PR、main 推送、每周一 03:15 UTC 和手动触发。Python 矩阵、锁文件、导入契约、方法登记表和前端构建继续使用现有命令。[检查配置](../../.github/workflows/ci.yml)
- 仅 Markdown 或许可证改动时，性能 job 以原名记录跳过原因，浏览器 job 跳过。前端代码修改运行浏览器检查，前端锁文件同时触发性能基准。其他非文档改动、依赖锁、检索或存储修改、未知文件均运行浏览器与十万条基准。无法取得基线差异、定时或手动执行时运行两项完整检查。
- 首次实施时记录 `git status --short`、`git diff --stat` 和 `git diff --cached --stat`。核对被入口引用的新源码和测试，逐项选择交付文件。从候选提交重新检出或使用 `git archive HEAD`。排除个人数据、数据库和本机开发缓存。
- 发布负责人核对提交 SHA、完整质量门禁结果、制品 SHA-256 和浏览器记录。`V*` 标签触发构建，制品包含提交跟踪文件和前端构建产物。在全新目录解压，执行 README 的依赖安装、健康探测与浏览器验收；验收失败时 GitHub 发布步骤不会执行。[发布配置](../../.github/workflows/release.yml)
- 发布记录列出候选 SHA、制品 SHA-256、实际运行命令、结果及未运行项。远端合并限制由仓库管理员设置。[分支保护现状](../../.github/branch-protection.md)
- 需要回退时，停止当前服务，用此前已验收的应用归档和锁文件重新安装，再以原配置启动。保留原数据目录和 SQLite 副本，先在副本核对恢复与版本绑定。本轮复用既有数据库字段。
