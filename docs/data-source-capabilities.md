# 数据来源能力与接入边界

核实日期：2026-10-15。中国优先、全球补充；免费优先，商业可选。下列“文档核实”“已实现”“授权状态”“真实调用”相互独立。当前交付与复核步骤见[维护说明](development/reliability-and-release.md)。

| 来源 | 文件导入 | 在线采集实现 | 真实账号验证 |
|---|---|---|---|
| WoS / Google / USPTO | 对应受支持格式 | 本轮使用文件流程 | 离线流程不需要账号 |
| EPO OPS | 采集结果可重放为 canonical JSONL | 两阶段确认、题录、最多 1,000 条、集合不完整不发布 | 待验证 |
| CNIPA | 官方导出需核对实际文件格式 | 尚无在线 REST 适配器 | 未调用 |

| 渠道 | 官方依据与收费/接入方式 | 当前应用接入 | 字段与限制 | 真实账号状态 |
|---|---|---|---|---|
| CNIPA | [官方咨询答复](https://www.cnipa.gov.cn/jact/front/mailpubdetail.do?sysid=12&transactId=496965)；注册IPDPS说明不足以确认公众REST | 官方导出/文件流程；未实现在线REST | 以实际导出schema与许可为准；不猜测实时法律状态 | 未调用 |
| EPO OPS | [官方OPS](https://www.epo.org/en/searching-for-patents/data/web-services/ops)；免费4GB/week，需consumer凭据 | 已实现两阶段确认、固定OPS主机的题录search/biblio | 题录、摘要、IPC/CPC、family_id；claims/description/完整同族/legal未采集；单任务最多1000条；查询集合不完整不发布 | 后端环境配置时显示configured_unverified；无凭据credentials_required；真实账号待验证 |
| Google Patents Public Data | [官方公开仓库](https://github.com/google/patents-public-data)；公开数据/BigQuery导出，查询费用另按平台 | Google JSONL离线adapter | 多语题录/摘要/raw localized claims/分类/引用/已提供family_id；blob无权利要求结构，法律状态不推断 | 在线采集未实现 |
| USPTO | [PatentsView迁移ODP公告](https://www.uspto.gov/subscription-center/2026/patentsview-migrating-uspto-open-data-portal-march-20) | grant XML与Patent File Wrapper JSON离线adapter | XML结构claims；PFW申请级事件和来源时点状态，不伪造公开文献；不沿用迁移前接口假设 | 在线采集未实现 |
| 智慧芽 | [操作级API文档](https://open.zhihuiya.com/devportal/api-reference/patent-search/task)；商业Bearer授权 | 默认disabled，商业可选，未实现在线客户端 | 不把操作级Bearer简化为所有接口共用匿名REST | 未授权、未调用 |
| Lens | [官方API说明](https://support.lens.org/knowledge-base/lens-patent-and-scholar-api/)；14天试用，长期付费 | 默认disabled，商业可选 | 需核实账号许可、计划、额度和字段合同 | 未授权、未调用 |
| WIPO | [PATENTSCOPE数据说明](https://www.wipo.int/en/web/patentscope/data/index)；PCT付费SOAP/SFTP | 未实现在线客户端 | 不宣称免费全球REST或完整法律状态API | 未授权、未调用 |

## 当前接口

- `GET /api/sources` 提供每渠道能力、文档核实、授权配置、最近任务状态与限制。
- `POST /api/acquisitions` 首次只返回10分钟确认摘要与一次性token；第二次原请求+token才领取任务；token仅存hash，不从GET/日志回显。
- `GET /api/acquisitions/{id}` 提供持久状态、页数、记录数、匹配集合完整性、字段状态、脱敏错误和发布版本。
- `POST /api/acquisitions/{id}/cancel` 取消可取消阶段；发布事务已领取时明确返回冲突。
- 上传/采集共享版本发布服务；已绑定会话不会自动切换数据版本。

## OPS实现合同与资源上限

固定token URL：`https://ops.epo.org/3.2/auth/accesstoken`；Basic key:secret + form `grant_type=client_credentials`；遵守expires_in。固定REST根：`https://ops.epo.org/3.2/rest-services`；GET `/published-data/search/biblio`，CQL query，`X-OPS-Range: 1-100`等范围。仅后端环境变量 `EPO_OPS_CONSUMER_KEY`/`EPO_OPS_CONSUMER_SECRET` 提供凭据，前端没有provider secret字段。

应用默认100/max1000条；每页≤100/max10页；实际业务HTTP请求≤20（重试也计数）；任务180秒、连接10秒、单请求30秒；单响应10MiB、token64KiB、累计20MiB；每次业务请求最多2次重试。搜索本身最多可访问2000条，不把预算截断称完整。达到配额拒绝立即停止，429/503仅有界退避。

来源契约：[指南1.3.20](https://link.epo.org/web/searching-for-patents/data/en-ops-v3.2-documentation-version-1.3.20.pdf)、[OPS YAML](https://ops.epo.org/wsdl/ops.yaml)、[exchange-documents XSD](https://ops.epo.org/schema/exchange-documents.xsd)。YAML OAuth标注与指南差异按已核实client_credentials指南处理；不使用未经核实的通用document下载路径。

## 完整性和可用性

`matched_set_complete` 表示匹配集合是否完全获取，`field_status` 单独表示题录、摘要、分类、family_id及未采集字段。完整题录集合可以发布有限字段数据集；分页/预算/解析/服务错误导致集合partial时不能发布、替换版本或推进监测基线。空结果完整任务可完成，但不制造空文献。

canonical JSONL v4 + hash manifest 是受控、可重放的发布形式。原始XML只计算hash，未进入聊天。来源/许可、规范query、观测时间、页数、受控配额字段和原始响应hash在采集结果持久。观测时间不伪装为源数据截止时间；缺截止明确未知。

能力与记录覆盖共同限制工具：没有当前法律状态来源能力时不能判断权利有效性；family_id不代表完整同族；Google raw claims不代表独立项/依赖树。缺失不解释为零，不作侵权、FTO或正式估值结论。

## 安全边界

外发只允许固定EPO HTTPS主机；DNS全部地址须为公网，连接验证IP并保持EPO Host/TLS SNI；不跟重定向、不用环境代理。拒绝压缩响应、DOCTYPE/XML实体；raw stream分块、累计前检查限额。token/key/secret/query不写传输日志，配额header只存有界数字和受控类别。

本轮合成测试验证接口、取消/恢复、预算、日志、XML和发布规则；不等同真实账号、真实供应商数据完整性或许可验收。
