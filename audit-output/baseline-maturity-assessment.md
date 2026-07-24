# LEAN Local Platform 修改前成熟度基线

审计日期：2026-07-24（Asia/Shanghai）
基线提交：`f4a130106408b810eeff6e8c104c606701fe6728`
分支：`main`
修改前工作树：除既有未跟踪 `audit-output/` 外无源码修改
证据优先级：当前代码/实跑 > 2026-07-24 独立复审 > 07-23 整改 > 07-22 原审计 > 声明文档

## 基线判定

```text
LEVEL3_BLOCKED
LEVEL4_FAIL
LEVEL5_REPLAY_FAIL
LEVEL5_OPERATIONAL_NOT_READY
LIVE_NOT_READY
```

`LEVEL3_BLOCKED` 是修改前一键审计入口的可复验状态：标准入口默认访问
`127.0.0.1:8003`，而当前 production-like Compose API 运行于 8000，实跑结果为
`LEVEL3_FAIL`（health/daily pipeline connection refused）。同一数据集的 Source
Gate、21/21 migration、identifier coverage、独立 A 股约束 fixture 和真实
Docker/LEAN integration 均通过；显式绑定 8000 的控制复验正在执行，因此此处不把
07-24 的历史 PASS 直接改写为当前 PASS。

## 成熟度矩阵

| 领域 | 当前声明 | 当前代码 | 当前实跑证据 | 缺陷 | 结论 |
| --- | --- | --- | --- | --- | --- |
| Source Gate | 07-24 PASS | production certification 需要 lineage、QA、manifest/file hash；research 默认拒绝 | TuShare dataset `a75936aa-...` certified，17,668,931 行；AData/Baostock/test 均 research | 完整伪造/认证后变更/API-worker 双阶段矩阵本轮未全部实跑 | FIXED_PENDING_REAUDIT |
| QA Gate | 07-24 PASS | create/worker 共用 fail-closed gate | 约束 fixture 中 `qa_failed` 拒单通过 | 真实 LEAN worker 的当日 Paper report 硬编码 QA ok | PARTIAL |
| Benchmark | 07-24 PASS | A 股要求 `000300` | 数据与 identifier 存在；历史 golden 有 118/118 | 本轮 controlled shadow 未完成 | FIXED_PENDING_REAUDIT |
| PIT | Level 4 blocked | official CSI300 仅 2017-12-08 后；TuShare 使用独立 shadow 名称 | dry-run 明确 `shadow_only` | 官方 2005–2017 coverage gap | PARTIAL |
| Reference Data | Level 3 PASS | preflight/worker reference gate 存在 | fixture/历史审计通过 | real Paper finalize 不重新保存真实当日 reference gate | PARTIAL |
| Fingerprint | 07-24 PASS | schema v2 canonical digest 排除运行元数据 | 历史双 golden 一致；本轮尚未重做五类单变量扰动 | 缺本次独立完整扰动矩阵 | FIXED_PENDING_REAUDIT |
| LEAN 回测 | PASS | Docker LEAN 为正式引擎 | `RUN_LEAN_DOCKER_INTEGRATION=1 ... test_ashare_lean_integration.py`: 1 passed | release JUnit 未长期归档 | FIXED_PENDING_REAUDIT |
| Level 4 实验 | blocked | batch、rolling、walk-forward、dynamic PIT 接口存在 | MySQL `experiment_batches=0`；Level 4 preview 因脚本未携带 API token 返回 401 | 无 3×3 实跑、无 restart/browser evidence；walk-forward 只有 train/test | OPEN |
| Paper Replay | blocked | 真实 LEAN 累计 walk-forward 存在 | 两个 21 日 session；均 0 rejected，最多 1 filled | 不满足同 session 成交+拒单；拒单来自独立 simulation helper | PARTIAL |
| 订单约束 | implemented | 约束集中在 `signal_simulation` | fixture 7 类拒单通过 | real LEAN finalize 绕过约束，直接导入 fills | OPEN |
| 幂等与恢复 | partial | session/date unique、LEAN event key unique | 重复末日 HTTP 400，计数稳定 | 无 intent/fill/fee ledger，未覆盖六阶段中断 | PARTIAL |
| 调度 | implemented | Celery beat 定时调用 Paper scheduler | 代码/单测存在 | 无完整交易日状态机、漏跑阻断链和 production-like 多日证据 | PARTIAL |
| 告警与升级 | implemented | alert_events/deliveries、webhook、cooldown、升级 | 单测通过；当前 12 alert rows | 未验证真实 INFO/WARNING/CRITICAL 到 RESOLVED 全链及真实外投 | PARTIAL |
| 备份恢复 | partial | dump、SHA、隔离 restore 脚本存在 | 07-23 仅小规模服务恢复证据 | 无生产规模加密异卷 DR、正式 RPO/RTO | OPEN |
| 容器隔离 | partial | LEAN runner 有 digest/readonly/cap/resource 参数 | Compose inspect 证实 backtest-worker 挂载 raw Docker socket 且仓库/Data 可写 | raw socket 仍为主机级权限，无 restricted runner | OPEN |
| 凭据治理 | partial | API runtime token 0600 恢复 | API auth 开启 | Compose 明文默认 MySQL/ClickHouse/Grafana；Redis 无认证 | OPEN |
| 供应链 | partial | 5 个 Compose 镜像和 Docker base digest 固定；npm lock 存在 | `check_supply_chain.py` 正确失败 | Python 无 hash lock、无漏洞门禁/例外账本、无可信签名/provenance | OPEN |
| Web E2E | 历史 15 pass/1 skip | Playwright 基础 Backtest/Docs/响应式存在 | 本轮仅 frontend build 通过 | 指定 20 场景未覆盖，Paper/Level4/恢复证据缺失 | PARTIAL |
| 生产发布门禁 | roadmap only | 无 `.github` CI workflow | repository/help/OpenAPI/build 本地检查通过 | 无强制 PR/Main/Nightly/Release gate | OPEN |

## 历史问题回答

1. 07-22 Critical 中 Source lineage、认证撤销、API auth、loopback、artifact
   integrity 和真实 LEAN integration 的根因已有代码修复，但本次独立矩阵未全部关闭。
2. AUD-001/003/004/005/006/007/010/011/013/015/016/017 仍最多为
   `FIXED_PENDING_REAUDIT`，不能由开发者自测改成独立关闭。
3. AUD-002/009/012/014/018/019 是 `PARTIAL`；AUD-008 仍 `OPEN`。
4. 07-24 Level 3 PASS 的标准入口本次未直接复现，当前标记
   `EVIDENCE_NOT_REPRODUCIBLE`，待显式 8000 控制复验。
5. 新回归/新发现包括：Level 4 audit 不带 token；其 validation 即使收集到
   failures 仍无条件返回 `passed`；README 标准 `.venv/bin/python` 链接失效；
   API/architecture 文档陈旧。
6. Level 4 未通过，因为没有 MySQL integration lane、数据库中没有任何 batch
   实跑、没有 3×3、validation/OOS、restart、cancel/retry 和浏览器证据。
7. Level 5 Replay 的确切阻塞是 real LEAN finalize 直接写 fills/positions，
   没有统一 intent -> constraint -> matching -> ledger 链；21 日 session 为 0 拒单。
8. Level 5 Operational 的确切阻塞是 raw Docker socket、默认凭据、无完整故障
   矩阵、无生产规模 DR/RPO/RTO、无强制 release gate。
9. 当前系统是具备 production-like 回测链的研究生产平台和受限模拟回放平台，
   不是可连接真实券商的交易系统。
10. Level 4、真实 Paper 约束/账本、完整调度恢复、DR、安全 runner、镜像签名等
    仍属于“接口或脚本存在，但无合格 production-like 证据”。
