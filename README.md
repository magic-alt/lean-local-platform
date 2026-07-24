# LEAN Local Platform

本项目是基于 QuantConnect LEAN 的本地量化研究平台，正式入口是 FastAPI、
React、Celery、MySQL 和 Docker LEAN 组成的 Web 工作台。平台不依赖 Lean
CLI；回测、优化、Research 和 Paper Replay 均以版本化项目策略运行。

## 当前能力

- MySQL 是唯一运行事实库；SQLite 仅用于隔离测试。
- Data 页支持十个 TuShare 数据集首次全量建库、后续增量更新，以及其他
  数据集的按需下载和可选存储目标。
- Provider 数据经过标准化、来源判优、质量检查和隔离后写入 canonical 表；
  原始响应使用轻量索引及压缩批次归档，不重复逐行保存完整 JSON。
- Backtests、Optimization 和 Research 提供策略案例、批量实验、参数网格、
  滚动窗口和动态 PIT 股票池工作流。
- 报告使用统一的 `report-layout-v2` HTML/Markdown 格式，并保留运行指纹、
  原始结果、日志、校验和对象归档。
- 数据预览覆盖股票、交易日历、指数、期货和期权；应用内 Docs 页面支持搜索。

## 快速启动

准备本地配置：

```bash
cp .env.example .env
# 编辑 .env，至少配置需要使用的 provider 凭据，例如 TUSHARE_TOKEN
```

启动完整本地栈：

```bash
./scripts/start_web_single_instance.sh
```

启动脚本会在 `web/runtime/secrets/` 生成并复用本地 API Token，由前端代理
自动携带。直接调用 API 时必须发送 Bearer Token；正式配置不得关闭认证。

只有 Dockerfile、依赖或镜像构建内容发生变化时才需要：

```bash
./scripts/start_web_single_instance.sh --build
```

也可以直接使用 Compose：

```bash
docker compose --profile app up -d --build mysql redis api worker
```

## 数据与运行目录

```text
web/runtime/                  本地运行产物、项目副本、报告、上传和缓存；不提交
$LEAN_DATA_DIR                LEAN 行情缓存；默认是仓库父目录的 Data
$LEAN_DATA_DIR/parquet        可重建的 Parquet 派生数据
Docker volumes                MySQL、Redis、ClickHouse、Grafana 等服务数据
config/data-sources/          可移植的数据来源 manifest；纳入版本控制
```

根目录不再使用 `results/`、`runs/`、`Data/` 或 `parquet/`。详细规则见
[Repository Layout](docs/repository_layout.md)。

Data 页一键更新范围以代码中的 `BULK_DATASET_KEYS` 为准，当前为：

`stock_basic`、`trade_cal`、`daily`、`adj_factor`、`suspend_d`、
`stk_limit`、`index_basic`、`index_daily`、`fut_basic`、`opt_basic`。

首次完整成功后系统保存建库状态和水位，按钮切换为增量更新。`daily_basic`
等其他数据集通过按需操作单独下载。

同步完成状态采用证据门禁：每个数据集必须同时具有 ready item、成功
ingestion manifest、适用的 watermark，以及可读取的 raw archive。日线变更会
立即撤销旧 source certification；异步重建 Parquet 并通过 MySQL/DuckDB/文件
哈希一致性检查后，TuShare 数据才能重新进入 production 回测和 Paper。

## 回测策略约束

新回测必须提供 `projectId`。Web 页面创建或从模板克隆的项目保存在
`web/runtime/projects/`，任务创建时会复制不可变策略快照。正式 runner 不再
使用默认 demo 算法；历史上无项目的已完成回测仍可只读查看。

根目录原有的 EMA Docker 示例已移动到
[examples/lean-docker-demo](examples/lean-docker-demo/README.md)，它不参与 Web
API、Celery worker 或正式报告链路。

## 常用维护命令

```bash
# 数据库迁移状态
web/backend/.venv/bin/python scripts/db_migrate.py --status

# 仓库源码/运行产物边界检查
python3 scripts/check_repository_hygiene.py

# 重建已有回测 HTML 报告
web/backend/.venv/bin/python scripts/regenerate_backtest_reports.py --dry-run

# CSI300 PIT portable parser 示例验证（生产 manifest 需要离线官方附件包）
web/backend/.venv/bin/python scripts/import_csi300_pit_public.py \
  --manifest config/data-sources/csi300_pit_sources.example.json \
  --dry-run --validate

# TuShare CSI300 历史权重只读治理检查（仅影子 universe，不替代官方 PIT）
web/backend/.venv/bin/python scripts/import_tushare_csi300_pit.py \
  --start-date 2005-01-01 --end-date 2026-07-22 \
  --dry-run --quarantine-incomplete
```

CSI300 官方缓存重建目前从 2017-12-08 开始，不能用当前成分替代更早的历史
PIT 成分。来源哈希和人工校正位于
`config/data-sources/csi300_pit_sources.json`，原始附件只存放于
`web/runtime/source-cache/csi300-official/`。缺失附件时生产 manifest 校验必须
失败，不能把 manifest 中的声明当作源文件验证结果。

## 测试

```bash
cd web/backend
.venv/bin/python -m pytest -q

cd ../frontend
npm run build
```

需要 Docker 时再运行 LEAN 集成测试：

```bash
cd web/backend
RUN_LEAN_DOCKER_INTEGRATION=1 .venv/bin/python -m pytest -q tests/test_ashare_lean_integration.py
```

## 文档

| 文档 | 内容 |
| --- | --- |
| [架构](docs/architecture.md) | 组件边界、主链路、存储与恢复 |
| [数据源治理](docs/data_sources.md) | Provider、许可、同步范围和正确性验证 |
| [数据管线](docs/data_pipeline.md) | 全量/增量/按需同步、校验和归档 |
| [部署](docs/deployment.md) | Compose、资源、备份和故障恢复 |
| [API](docs/api.md) | 接口、错误语义与 OpenAPI |
| [测试](docs/testing.md) | 单元、前端和集成验收 |
| [Level 5 运维 Runbook](docs/operations/level5-runbook.md) | SLO、RPO/RTO、Paper 日任务、告警、恢复与发布门禁 |
| [当前 Roadmap](docs/roadmap.md) | 当前能力与后续优先级 |
| [历史审计](docs/history/platform-audit-2026-07.md) | 2026-07 起的问题、证据和状态增量 |
| [历史修复记录](docs/history/README.md) | 故障根因、修复和遗留风险 |
| [应用内文档中心](docs/help/index.md) | 可搜索的操作教程、完整 API 索引、技术参考和历史记录 |

应用内 Docs 使用 GFM Markdown，支持表格、代码复制、文章/章节深链和关键流程截图。完整端点索引由 OpenAPI 生成，可运行以下命令检查内容、链接和接口清单是否同步：

```bash
web/backend/.venv/bin/python scripts/check_help_docs.py
web/backend/.venv/bin/python scripts/generate_help_api_reference.py --check
```

## 贡献与提交

每次 Git 提交必须更新根目录 `CHANGELOG.md`：

```bash
./scripts/install_git_hooks.sh
```

提交规范、验证命令和运行产物规则见 [CONTRIBUTING.md](CONTRIBUTING.md)。
