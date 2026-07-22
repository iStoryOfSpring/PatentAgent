# 数据源能力矩阵

“支持”表示有正式文件适配器和回归 fixture，不表示来源字段始终完整，也不表示法律状态
实时有效。每次导入后的 `ImportReport` 才是该批数据的实际能力声明。

| 来源/格式 | 状态 | 书目 | 多语言 | 权利要求/全文 | 分类/引证/同族 | 审查事件 | 关键边界 |
|---|---|---:|---:|---:|---:|---:|---|
| WoS Derwent tagged text | 正式支持 | 是 | 有限 | 通常否 | IPC、后引、部分同族 | 否 | 取决于导出字段；不能据此作 FTO |
| Google Patents Public Data JSONL | 正式支持 | 是 | 是 | 导出存在时 | IPC/CPC、引证、同族 | 否 | Google 展示/聚合字段不是实时法律意见 |
| USPTO grant full-text XML | 正式支持 | 是 | 主要英文 | 是 | 分类、引证 | 否 | 授权时点全文，不代表当前有效性 |
| USPTO Patent File Wrapper JSON | 正式支持 | 补充 | 否 | 事件附件视导出而定 | 否 | 是 | 事件是来源时点记录，需按申请号合并 |
| 多语言 MiniLM + lexical RRF | 实验性 Beta | — | 是 | 可用于嵌入 | — | — | 代理标签验证，不是查新/FTO 查全检索 |
| EPO OPS | 规划中 | — | — | — | — | — | 仅保留适配器接口，不内置账号或抓取 |
| CNIPA 公共服务导出 | 规划中 | — | — | — | — | — | 仅保留能力清单，不宣称可用 |

正式导入目录可以提供 `patentagent-import.json`，记录格式、来源、获取日期、Schema
版本、许可说明、文件和 SHA-256。规范化链路为：

`原始文件 → PatentRecord v3 → ImportReport → DatasetSnapshot → DatasetView → Tool`

缺省 `auto` 使用扩展名和内容签名识别上述四类正式格式，不依赖文件名；标准 fixture
覆盖无清单自动识别。`ImportReport.file_detections` 会逐文件返回识别格式、依据和是否匹配；
这里刻意不提供未经校准的概率式“置信度”。
这不是对所有历史版本、第三方二次封装或未来 Schema 的 100% 保证：无法唯一识别时系统
拒绝猜测并返回 `unsupported_format`，用户可指定格式作为解析兜底。带格式与 SHA-256 的
导入清单才是可复现批次的推荐方式。

工具不得读取 WoS 标签或新增来源专用分支。跨来源合并保留原始号码、规范号码、字段级
provenance 和冲突值；当前法律状态始终携带来源和 `as_of` 日期。

公开格式和复现入口：

- [Google Patents Public Data Schema](https://github.com/google/patents-public-data/blob/master/tables/dataset_Google%20Patents%20Public%20Datasets.md)
- [USPTO Open Data Portal](https://data.uspto.gov/apis/bulk-data/search)
- [EPO OPS](https://www.epo.org/en/searching-for-patents/data/web-services/ops)
- [CNIPA 公共服务说明](https://www.cnipa.gov.cn/art/2024/4/1/art_3359_191346.html)
- 仓库内固定导出清单：`samples/official/`
