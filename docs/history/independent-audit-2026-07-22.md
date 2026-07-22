# 2026-07-22 独立成熟度审计与修复状态

本记录保留 2026-07-22 全链路独立审计的失败结论、修复范围和仍未关闭的
证据缺口。修复代码通过测试不等于重新获得成熟度评级；评级只能由新的独立、
production-like 验收改变。

## 审计原始结论

审计评分为 26/100，并给出以下硬结论：

```text
LEVEL3_FAIL
LEVEL4_FAIL
LEVEL5_REPLAY_BLOCKED
LEVEL5_OPERATIONAL_NOT_READY
LIVE_NOT_READY
```

关键失败包括：provider 名称代替数据认证、合成数据冒充 TuShare production、
A 股 QA/reference critical 未阻断真实 LEAN、指纹包含运行期字段、归档对象孤儿、
预览错误、容器/API 隔离不足，以及 Paper/故障恢复/灾备证据不完整。

## 本轮已实施修复

- Production source 只允许 TuShare 候选，且仍必须具有持久化 dataset ID、文件
  manifest 哈希、production 环境、QA `ok` 和一致性报告；provider 名称本身不
  构成证据。只有正式 sync 写入且同时关联成功 ingestion manifest 与 raw archive
  的 batch 才能晋级，直接 TuShare 导入默认仍是 research。
- 新迁移撤销所有旧认证。canonical 行发生变化会再次撤销认证；只有成功的
  TuShare 批次 lineage 和 MySQL/Parquet/DuckDB/file-hash 一致性能够重新认证。
- 合成 E2E 批次显式标为 `environment=research`、`synthetic=true`，不能被提升
  为 production；受控 E2E 必须显式启用 research override。
- 回测创建和 worker 启动前重复执行 Source、QA、benchmark、PIT/reference
  门禁；Paper 候选拒绝 research、truncated 或未认证运行。
- 输入身份指纹排除 run ID、时间、运行路径和 batch UUID，并纳入资金、实际行情
  内容、交易状态与 benchmark 内容哈希；结果增加排除 LEAN 主机时间与随机 trade
  UUID 的 canonical digest，同时保留 raw digest。
- 数据同步 success 增加 item、manifest、watermark、archive 和 derived
  certification 完成谓词。
- Preview 跳过孤儿归档，读取对象时验证行、chunk、长度和 SHA-256；维护删除
  阻止删除仍被 raw archive 引用的对象，依赖健康暴露孤儿计数。
- API 默认启用本地 bearer token；Compose 端口绑定 loopback。LEAN/Research
  镜像必须 digest allowlist，运行容器使用资源/PID限制、能力删除、no-new-privileges、
  缩小挂载；LEAN 默认无网络、只读根和每次运行独立对象目录。
- 修复迁移 CLI 兼容入口、备份脚本、Grafana host URL、真实 LEAN 集成调用和
  报告/重复提交/移动端布局 E2E。

## 本轮验证

- 后端：`317 passed, 1 skipped`（SQLite 单元/服务回归，不能替代生产 MySQL）。
- Source/QA/Parquet/sync 聚焦回归：`87 passed`。
- 前端 production build：通过；Ant Design/ECharts 仍有大 chunk 警告。
- 浏览器完整 Chromium E2E：`15 passed, 1 skipped`；包含真实 LEAN SPY 与显式
  research-only 的 synthetic A 股链路，不能作为 certified production 数据验收。
- 正式 MySQL 已应用 migration `0020`，20/20 migration 无 checksum mismatch；
  旧 Parquet certification 已全部撤销（certified=0、production=0）。
- 加固后真实 LEAN Docker 集成曾完成通过；完整独立审计未重跑。

## 仍未关闭

- 生产 CSI300 manifest 依赖的官方 XLS/XLSX/PDF 离线附件未随仓库提供，缺失或
  hash 不一致必须失败；2005-2017 PIT 仍是 coverage gap。
- 未完成真实 21 交易日 LEAN Paper、多阶段中断与幂等矩阵。
- 未完成五任务并发、取消阶段、Redis/MySQL/worker、OOM、磁盘不足等隔离故障注入。
- 未完成生产规模备份/对象/Parquet 恢复及正式 RPO/RTO。
- Python hash lock、镜像供应链签名/SBOM、默认服务凭据轮换仍未完成。
- `backtest-worker` 为启动 sibling LEAN 仍持有 Docker socket；它属于可信基础设施，
  尚不能视为多租户安全边界。
- 正式库发现的 37 条历史 raw archive 孤儿引用已完整迁入
  `provider_raw_archive_issues`，活动 archive 目录不再含悬空引用；原始对象已不存在，
  不能伪造恢复，依赖健康会持续暴露隔离记录数量。

因此当前仍保持：

```text
LEVEL3_FAIL
LEVEL4_FAIL
LEVEL5_REPLAY_BLOCKED
LEVEL5_OPERATIONAL_NOT_READY
LIVE_NOT_READY
```
