# Actual-environment API contract review — 2026-08-02（第二次审计）

## 1. 结论

实际 API 可认证访问，Backtests、Projects、Strategies、Experiment、Tasks、Reports、Data/Sync/QA/Parquet、Research、Factors、Paper/Accounts、Insights、Health、Object Store 和 Docs 主体路由存在；但实际 OpenAPI 与当前源码/生成文档不是同一版本。实际 225 paths、198,915 bytes；当前源码 230 paths。P1/P2 修复已经合入仓库但 API/worker/schema 未部署，这是当前最高优先级接口风险 `ACT-P0-004`。

## 2. OpenAPI、api.md、前端类型和实际行为

| 对照项 | 当前源码/文档 | 实际环境 | 状态 |
| --- | --- | --- | --- |
| OpenAPI path count | 230 | 225 | FAIL |
| migration contract | 需要0040四表 | actual latest0039 | FAIL |
| generated help reference | 当前源码检查PASS | 包含actual缺少的5 endpoints | FAIL(actual drift) |
| frontend bundle | 当前源码build assets | 已由8000端口服务 | PASS/PARTIAL |
| backend processes | 应与frontend同release | 启动早于P1/P2 commits | FAIL |
| primary list envelope | `PageEnvelope` | 仍有4种shape | FAIL |
| summary list DTO | 源码已有 | actual仍嵌入巨型JSON | FAIL |
| Paper trust response | current account-bound | actual返回deleted account evidence | FAIL |

实际缺少的五个 paths：

1. `/api/backtests/reproducibility/golden-pairs`
2. `/api/backtests/{run_id}/reproducibility-certificate`
3. `/api/data/capabilities`
4. `/api/data/quality/reports/{report_id}`
5. `/api/data/releases`

## 3. 领域 API 实际核对

| Domain | 代表性 API | 实际结果 | 契约结论 |
| --- | --- | --- | --- |
| Projects/Strategies | `/api/projects`, project files | 200；4 projects | 主体可用；写journey未测 |
| Backtests | list/detail/result/chart/log/validation/versions | 200；3 runs | 详情完整但超大；certificate缺 |
| Experiment | batches/detail/export | 200；2 batches | CSV可用；WF lineage是domain问题 |
| Tasks | list/logs | 200；9 tasks | cursor后端可用；list 5.2MB |
| Reports | list/backtest report | 200 | result/report职责有重叠 |
| Data | catalog/providers/assets/reference | 200 | capability endpoint缺 |
| Data Sync | sync-runs | 200 | actual `{items,limit}` |
| QA | quality reports | 200 | actual `{items}`；detail path缺 |
| Parquet | datasets | 200；7 | actual `{items}` |
| Research | runs/workspaces | 200 | 1 success/2 failed |
| Factors/Optimization | routes存在 | 当前optimization 0 | CODE_ONLY/PARTIAL |
| Paper accounts | list/overview/tabs/compare | 200；2 accounts | opening事实可用；trust错误、下游空 |
| Legacy Paper | session APIs | 存在 | 与Account概念并存 |
| Health/Metrics | dependencies/resources/alerts | 200 | notification false-ready |
| Object Store | artifact metadata/download paths | run1可关联 | per-file certificate缺 |
| Docs | help/static/openapi | 200/401受认证保护 | current generated docs超前actual |

## 4. 请求/响应 schema 与命名

实际 OpenAPI 使用 JSON-friendly Pydantic schema，主体字段以 camelCase 对外、Python 内部 snake_case；Decimal 和 datetime 多数序列化为 JSON number/string。已观察到以下问题：

- `datasetVersion`、Parquet `dataset_version`、source certification version 表意重叠，且实际没有 release ID。
- Paper Session 与 Paper Account API 同时存在，当前导航/文档没有明确 legacy cutoff。
- `/result` 返回约 2.01MB，而 detail 约 1.90MB、validation约1.60MB、versions约1.60MB，多个接口重复嵌入 validation/fingerprint/schedule。
- Paper overview/deployment 各约300KB，即使没有 cycle/trade 仍过大。
- preflight 返回 benchmark gate pass，但展示 benchmark coverage 0 rows；虽然 benchmark 另表有数据，字段语义会误导用户。
- actual QA/sync/parquet list response schema 在 OpenAPI 中为空对象或弱约束，current source才有显式 `PageEnvelope`。

## 5. 实际 list shape、分页、过滤和体积

```text
{items,count,limit,offset}  projects/backtests/tasks/reports/batches/research
{items,limit}               data sync runs
{items}                     Parquet datasets / QA reports
[...]                       verifications
```

| Endpoint | Items | Payload | 状态 |
| --- | ---: | ---: | --- |
| backtests | 3 | 23,342,903 bytes | FAIL |
| tasks | 9 | 5,197,127 bytes | FAIL |
| QA latest | 20 | 1,432,100 bytes | FAIL |
| one batch detail | 1 child | 2,451,773 bytes | FAIL |
| Paper overview | 1 account | ~300KB | PARTIAL |

源码中的 summary DTO、200 hard limit、server-side Backtest pagination 和统一 envelope 是正确方向，但只有 actual payload 复测达标后才能关闭 `ACT-P1-003/P2-001`。兼容方案应保留显式 detail/full endpoint，list 默认只返回 summary，并给旧 envelope 明确废弃期。

## 6. 状态码和错误契约

| Code | 当前实际证据 | 状态 |
| --- | --- | --- |
| 200 | 主要GET和preflight | PASS |
| 400 | 历史source gate/preflight返回domain details | PASS |
| 401 | 无Bearer访问API/OpenAPI | PASS |
| 403 | 未安全构造权限差异 | NOT_VERIFIED |
| 404 | 不存在路径、新P1 endpoint实际缺失 | PASS（协议）/FAIL（部署） |
| 409 | Paper compare缺参数/后端idempotency conflict代码 | PARTIAL |
| 422 | OpenAPI/Pydantic定义存在，未发送破坏性/恶意payload | NOT_VERIFIED |
| 429 | 未触发rate limit | NOT_VERIFIED |
| 503 | source/dependency路径有代码，当前不主动停服务 | NOT_VERIFIED |

要求每个 domain error 在 OpenAPI 声明具体 response model，保留 `traceId`,`retryable`,`details`,`field` 和可执行 action；`retryable` 必须由 domain exception 决定，不能仅按 HTTP status 猜测。

## 7. 幂等、重复 POST、cancel、retry、restart

后端 middleware 支持 `Idempotency-Key`，同 key/异 payload 409、进行中冲突、完成后 replay。P2 当前源码把 key 生命周期提升到一次 UI command 并仅在网络异常重试一次；这是合理修复，但 actual browser timeout replay 未验证。

Paper cycle 仍必须由数据库唯一约束保证 `(account,deployment,trading_date,generation)` 单例，HTTP middleware 只能作为第一层。当前 0 cycles，不能验证 duplicate Beat、duplicate Run-now、fill、commission 和 notification 去重。Backtest cancel、experiment failed-only retry/cancelled restart 路由存在，本轮不影响现有任务，因此未执行。

## 8. 日志、artifact 和大文件

实际 backtest log cursor：total 296,777 bytes，返回 tail 4,096 bytes，offset 292,681，cursor字段可用。current frontend源码有加载更早/follow/停止，Browser不可用使UI保持 PARTIAL。Artifact runtime-root保护和stored object关联存在；run1 raw SHA与stored object一致。实际 run fingerprint 的 LEAN zip/factor SHA为空、reproducibility certificate接口缺失。下载响应应暴露 immutable ETag、content SHA、size、media type 和release/certificate ID。

## 9. 删除保护和依赖

删除 API/前端确认只做代码审查，没有执行实际删除。历史 WF parent已不存在以及legacy Paper orphan说明旧数据库依赖约束不足。0039已将 orphan quarantine 并为新WF写入增加lineage guard，实际 orphan READY=0；但删除保护仍需对新资源用 FK RESTRICT/soft archive/immutable snapshot 验证。409 应返回 dependent types/count/IDs。

## 10. 状态一致性和竞态

- 3 backtest runs和9 tasks当前均success，未发现新task/domain错配。
- 一条 backtest success与final critical validation冲突，是terminal truth错误。
- stale Research已收敛，legacy Paper orphan已quarantine，P0整改PASS。
- 两Paper deployments标 active且nextScheduledAt已过期，但account draft、latestCycle null；scheduler projection不一致。
- notification channel实际全失败但health ok；health不是真实delivery readiness。
- actual processes/schema/frontend不是同一release，任何新字段/endpoint均可能发生404或shape mismatch。

## 11. API 问题清单

| Issue | 问题 | 严重度 | 当前状态 | 兼容/整改策略 |
| --- | --- | --- | --- | --- |
| ACT-P0-004 | actual 225/0039落后source230/0040 | P0 | OPEN | release manifest + ordered rollout |
| ACT-CRIT-001 | success/final critical矛盾 | Critical | OPEN | additive trust + atomic finalization |
| ACT-P1-001 | Paper trust dangling evidence | P1 | source fixed/not deployed | account-bound trust/default false |
| ACT-P1-003 | 巨型list DTO | P1 | source fixed/not deployed | summary default + explicit detail |
| ACT-P1-004 | capability actual缺失 | P1 | source fixed/not deployed | additive endpoint/state |
| ACT-P1-005 | release actual缺失 | P1 | source fixed/not deployed | 0040 + additive release ID |
| ACT-P1-006 | certificate/golden actual缺失 | P1 | source fixed/not deployed | additive endpoints/certificate |
| ACT-P2-001 | 4种envelope | P2 | source fixed/not deployed | deprecation adapter |
| ACT-P2-002 | log cursor UI未实测 | P2 | source fixed/browser NV | additive UI |
| ACT-P2-003 | timeout replay未实测 | P2 | source fixed/browser NV | stable operation key |
| ACT-P1-007 | notification health false-ready | P1 | OPEN | degraded health/DLQ/backoff |

## 12. 验收命令与完成定义

在获批部署后执行：

```bash
cd web/backend && .venv/bin/python scripts/db_migrate.py --status
cd web/backend && .venv/bin/python scripts/generate_help_api_reference.py --check --json
cd web/frontend && npm run build
```

并对 actual authenticated OpenAPI/GET 做 contract snapshot。完成定义：actual/host path集合相同；所有进程同 release SHA；migration 0040 applied；五新endpoint可用；primary list同envelope且payload有预算；Paper trust无dangling；日志cursor首尾可达；关键write timeout replay同resource；删除无法制造dangling lineage。
