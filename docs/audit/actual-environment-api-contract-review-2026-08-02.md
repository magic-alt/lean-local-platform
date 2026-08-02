# Actual-environment API contract review — 2026-08-02

## 1. 基线与结论

事实基线为当前受认证的 `/openapi.json`：OpenAPI 3.1.0、222 paths、196,561 bytes。`docs/api.md`、`web/frontend/src/api/index.ts`、`types.ts` 和实际响应作为对照。总体状态 `PARTIAL`：认证、结构化错误、核心资源 schema 和大多数 CRUD 路由清晰；分页 envelope、Research 文档、日志 cursor、客户端幂等键与列表 DTO 未统一。

## 2. 实际端点抽样

| Path | HTTP | 实际大小 | Shape/Count | 结论 |
| --- | ---: | ---: | --- | --- |
| `/api/health/dependencies` | 200 | 动态 | `{status,executionStatus,dependencies,...}` | PASS |
| `/api/projects` | 200 | 4,946 B | paged / 4 | PASS |
| `/api/backtests` | 200 | 23,342,904 B | paged / 3 | FAIL：summary 过大 |
| `/api/tasks` | 200 | 5,197,128 B | paged / 9 | FAIL：summary 过大 |
| `/api/data/quality/reports` | 200 | 3,811,338 B | `{items}` | PARTIAL：无 count/limit/offset |
| `/api/experiment-batches` | 200 | 9,423 B | paged / 2 | PASS |
| `/api/optimizations` | 200 | 45 B | paged / 0 | PASS（空） |
| `/api/research/runs` | 200 | 5,624 B | paged / 3 | PARTIAL：2 stale running |
| `/api/reports` | 200 | 4,595 B | paged / 3 | PASS |
| `/api/data/sync-runs` | 200 | 35,321 B | `{items,limit}` | PARTIAL |
| `/api/data/parquet/datasets` | 200 | 7,705 B | `{items}` | PARTIAL |
| `/api/verifications` | 200 | 156,835 B | raw array / 4 | FAIL：不统一 |
| `/api/paper/accounts` | 200 | 小 | paged / 0 + `dataTrust` | FAIL：trust 指向不存在账户 |
| `/api/paper/accounts/compare`（无 ids） | 409 | 小 | structured error | PASS |
| `/api/backtests/preflight`（认证降级时） | 400 | 小 | structured error | PASS：fail-closed |

响应计时在容器内本地网络上很低，但 payload 本身会直接影响浏览器解析、缓存、内存、移动网络与 polling；23.3 MB 不能因 0.3s 本机响应而判为可接受。

## 3. OpenAPI 与 `docs/api.md` 差异

| 项目 | `docs/api.md` | OpenAPI/实际 | 状态/修复 |
| --- | --- | --- | --- |
| Research | `/api/research`, `/{session_id}`, `/stop`, `/restart`, `/logs` | `/api/research/runs*` 与 `/api/research/workspaces*` | FAIL；从 OpenAPI 生成 reference 并标旧路由 |
| Primary list | 宣称返回 `items,count,limit,offset` | sync/Parquet/QA/verifications 不一致 | FAIL；统一 envelope |
| 日志 | 一处写 bounded tail | 后文写 cursor；实际有 cursor | 文档自相矛盾 |
| `/result`/`/results` | canonical singular + compatibility redirect | 实际 `/results` 隐藏 308 | PASS |
| 错误 | structured error + trace/workflow | 实测 400/404/409 一致 | PASS |
| migration/API 版本 | 文档手工维护 | OpenAPI 222 paths | PARTIAL；需 CI contract diff |

## 4. OpenAPI 与前端类型/调用差异

| 项目 | 后端事实 | 前端事实 | 影响 |
| --- | --- | --- | --- |
| list pagination | 多数 endpoint 支持 page envelope | 大量调用加 `paged=false&limit=1000` | 绕过分页，放大 payload |
| task logs | `{logs,offset,cursor,nextCursor,hasMore}` | `request<{logs:string}>` | 无法继续翻页 |
| research | runs/workspaces 两种概念 | 已使用新路径 | 前端正确，文档旧 |
| Paper trust | global `dataTrust` | UI 只在 false 时告警 | stale true 会抑制告警 |
| large run snapshot | list item 包含 parameters/validation/fingerprint | 页面先取全 list | 23.3 MB 首屏风险 |
| datetime | 后端多为 ISO UTC string | 前端按 string | 可用；需统一显示 timezone |
| Decimal | Paper 精确列/JSON number/string 混用可能 | TS 多为 number | 当前无账户，实际 precision 未验证 |
| enum/null | OpenAPI anyOf null 多 | TS 有部分可选 | build 通过，不等于运行历史兼容通过 |

## 5. 实际响应差异

Primary list 至少有四种格式：

```text
{items,count,limit,offset}  projects/backtests/tasks/reports/batches/research
{items,limit}               data sync runs
{items}                     Parquet datasets / QA reports
[...]                       verifications
```

建议所有默认 list 使用 `{items,count,limit,offset}`，大集合再增加 `nextCursor/hasMore`。兼容期间可由 `paged=false` 返回旧数组，但必须有废弃日期，前端不得继续默认 1000 条。

## 6. 错误码与状态码

- 401：未带有效 Bearer 时 OpenAPI/API 返回 `UNAUTHORIZED`，PASS。
- 400：preflight 数据认证不通过返回 source-specific code、validation details、retryable 和 trace ID，PASS。
- 404：不存在路径返回结构化 `NOT_FOUND`，PASS。
- 409：Paper compare 缺 ids 返回 workflow-aware conflict，PASS。
- 422：Pydantic 字段校验 schema 存在；本轮未发送恶意/无效写入，`NOT_VERIFIED`。
- 403/429/503：代码/OpenAPI 有路径，但未安全构造实际环境场景，`NOT_VERIFIED`。

改进要求：每个 error_code 在 OpenAPI 声明具体 response model；`retryable` 由 domain exception 显式给出，不从 HTTP status 泛化；前端展示 field/details/action，而不是只显示 trace ID。

## 7. 分页、排序和过滤

- Projects/backtests/tasks/report/batch/research 基本分页字段存在。
- 前端 `projects`,`experimentBatches`,`dataAssets`,`tasks`,`optimizations`,`portfolioOptimizations`,`researchRuns`,`researchWorkspaces`,`reports` 默认 `paged=false&limit=1000`。
- Backtest 历史页面有 URL/filter 代码，但浏览器刷新/返回保持未验证。
- QA、Parquet、verification 不符合统一契约。
- 大 schedule 应在 detail endpoint 分页或作为 artifact 下载，而不是 list item。

## 8. 幂等、重复提交、cancel/retry/restart

后端 middleware 支持 `Idempotency-Key`，同 key 异 payload 会 409、进行中会冲突、完成请求可 replay；这是合理设计。问题在客户端：`client.ts:55-57` 在每次 write call 生成新随机 key。网络超时后用户再次点击属于新 key，无法复用后端 replay。

修复方式：UI command 创建 operation ID，保存在组件/route state 或 durable mutation store，直到收到 terminal response；调用层把相同 key 传给 retry。Paper cycle 仍需 domain 唯一约束作为第二层保护，不能只依赖 HTTP middleware。

取消、failed-only retry、cancelled restart 的代码/API 存在；本轮没有对当前任务执行写操作，因此实际竞态为 `NOT_VERIFIED`。

## 9. 删除保护与资源依赖

项目、回测、Paper account 等删除路径有确认/保护代码；本轮禁止真实删除。实际 Walk-Forward 与 Paper legacy 孤儿证明数据库级资源依赖并不完整：

- `walk_forward_runs.batch_id` 指向不存在 batch；windows project/batch 不存在；
- 143 paper daily jobs 和 139 reconciliation 指向不存在 session。

因此删除保护只能判 `CODE_ONLY`，必须用 FK RESTRICT、soft archive 或 immutable snapshot 补强。删除 API 应在 409 中返回具体 dependent type/count/IDs，而不是由前端猜测。

## 10. 日志与 artifact 下载

后端 task logs 有 offset/cursor/nextCursor/hasMore；前端只用 `.logs`。需补“加载更早”“follow”“terminal stop polling”并限制每次 chunk。Artifact 路径有 runtime-root 保护和 stored object；run1 raw object hash 与本地文件一致。manifest 缺独立 per-file SHA，fingerprint 的 `docker_image_digest`、LEAN zip/factor hash 为 null；下载响应应同时返回/暴露 content digest、size、media type 和 immutable ETag。

## 11. 兼容性问题清单

| ID | 问题 | 严重度 | 兼容策略 |
| --- | --- | --- | --- |
| API-01 | list summary 巨型 JSON | P1 | 新增 v2 summary 或 fields；旧 full 明确废弃 |
| API-02 | 四种分页 envelope | P2 | adapter + deprecation window |
| API-03 | docs Research 旧路径 | P2 | OpenAPI 生成文档，不改变当前前端 |
| API-04 | log cursor 前端丢弃 | P2 | additive TS/UI |
| API-05 | retry 新 Idempotency-Key | P2 | 调用层稳定 key，无服务端破坏 |
| API-06 | Paper stale trust | P1 | trust 增 resource binding/TTL；默认 false |
| API-07 | dangling delete lineage | P0 | 先 quarantine，再加 FK/soft archive |

## 12. 验收标准

1. 所有 primary list 的 schema、文档、TS 与实际响应一致。
2. 默认 list payload 有预算；当前数据量下 backtests/tasks 各小于 200 KB。
3. 日志首尾都可经 cursor 到达，terminal 后无无限 polling。
4. 相同用户操作重试复用 key；相同 key/不同 payload 返回 409。
5. 删除/归档无法生成 dangling lineage。
6. Paper trust 不引用不存在资源。
7. OpenAPI contract snapshot 与 `docs/api.md` CI 检查通过。
