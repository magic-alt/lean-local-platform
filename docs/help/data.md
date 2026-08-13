# 数据

平台的股票行情事实层是仓库下的 `data/` Parquet 数据湖。MySQL 只保存任务、水位、数据集注册、质量结果、认证、账户与审计等控制平面数据，不保存日线、分钟线、复权因子或每日指标。

## 数据目录与职责

默认根目录是 `/Users/kaermax/lean-platform/data`，也可通过 `LEAN_DATA_DIR` / `LEAN_MARKET_DATA_DIR` 显式覆盖。目录职责如下：

```text
data/
├── bronze/tushare/
│   ├── current/<dataset>/trade_date=YYYYMMDD/data.parquet
│   └── revisions/<dataset>/...
├── silver/
│   ├── daily/current/trade_date=YYYYMMDD/data.parquet
│   └── reference/current/*.parquet
├── gold/
│   ├── adjusted/
│   ├── pit/
│   ├── features/
│   └── qlib_staging/
├── qlib/                 # 外部 Qlib 产物，只读
├── lean/                 # LEAN 可重建缓存
├── registry/
├── quality/
└── output/parquet/       # 平台分析/ML 派生产物
```

- Bronze 保存 Provider 原始字段。日线按交易日写入，每个分区同时保存 `manifest.json`；已有分区被修订时，旧文件和旧 manifest 先进入 `revisions/`。
- Silver 是平台统一读取的规范化行情层。A 股日线主路径为 `silver/daily/current/trade_date=*/data.parquet`。
- Gold 用于 PIT、复权视图、特征和模型输入。
- `qlib/` 与 `gold/qlib_staging/` 可被平台读取，但 lean-platform 不写入、不修改；Qlib 仓库也不在本项目改动范围内。
- LEAN、Qlib、ClickHouse 都是可由事实层生成的消费层，不是股票行情主库。

不要在根目录重新创建 `Data/`、`parquet/`、`runs/` 或 `results/` 作为运行目录。

## 股票数据下载和保存

Data 页面的一键建库/增量更新仍通过 TuShare 任务运行。股票日线的保存顺序是：

```text
TuShare daily
  -> 字段与日期校验
  -> 临时 Parquet
  -> bronze/tushare/current/daily/trade_date=YYYYMMDD
  -> 旧版本归档到 bronze/tushare/revisions
  -> silver/daily/current/trade_date=YYYYMMDD
  -> 原子替换 data.parquet 和 manifest.json
  -> MySQL 更新任务、水位、血缘和质量状态
```

写入使用临时文件加 `os.replace` 发布，读取者不会看到半个分区。股票日线、`adj_factor`、`daily_basic` 和交易状态都直接进入 Parquet 数据层；不会回写已删除的 MySQL 股票表。

全量更新用于首次建库或明确重建。增量更新从已保存的交易日水位继续，并允许 Provider 对历史日期做修订。历史分区被改写前必须先保留修订副本，因此同一日期的新版本不会静默覆盖证据。

下载进度中的常用含义：

| 字段 | 含义 |
| --- | --- |
| 下载 | Provider 返回并进入校验链路的行数 |
| 落盘 | 成功原子发布到 Parquet 分区的行数 |
| 隔离 | 未通过 schema/质量校验、未进入 current 的行数 |
| 水位 | 已完整发布且可继续增量的最后交易日 |
| checkpoint | 可重试任务已完成的工作单元 |

## 其他数据集与按需下载

财务、指数成分、停复牌、涨跌停和公司行为采用各自的 Bronze 分区及 PIT 规则。按需下载必须选择明确的数据集、范围和目标；股票类事实默认写 Parquet，控制平面只记录请求、任务和产物清单。

对于未纳入规范化模型的 Provider 响应，系统可保存校验过的压缩原始归档。原始归档不能替代 Bronze/Silver 分区，也不能把逐行 JSON 当作新的股票事实表。

`LEAN_TUSHARE_TYPED_SOURCE_WRITES` 默认关闭。它只用于仍需保留的参考类 typed source 兼容表，不得用于重新建立 MySQL 行情或每日指标表。

## 后端如何读取

所有行情服务经 `app.services.market_lake` 读取。该层把现有文件字段统一成平台契约，例如：

- `ts_code=600519.SH` / `symbol=SH600519` 统一为 `600519`；
- `trade_date=20260812` 统一为 `2026-08-12`；
- `vol`、`pre_close`、`pct_chg` 映射为 `volume`、`prev_close`、`pct_change`；
- Silver 中的 `paused`、`known_suspended`、`is_st` 和涨跌停价形成交易状态视图。

DuckDB 直接查询 Parquet，并进行列裁剪和条件下推。API 示例：

```text
GET /api/data/query?source=parquet&providerSource=tushare&market=china&symbol=600519
```

`source` 只接受 `parquet`、`duckdb`，以及已配置的可选 `clickhouse`；`mysql`、`database`、`local` 不再是行情查询来源。Preview 也只读本地 Parquet/归档，不会因为打开页面而调用 Provider。

在 Python 服务内应使用 `market_lake.query_rows()`、`query_matching()` 或领域 repository，不要直接拼接某个分区路径，也不要查询已删除的 `market_daily_bars`、`market_intraday_bars`、`market_trade_status`、`adjustment_factors`、`daily_basic_values` 表。

## Qlib 与 LEAN

Qlib 产物是外部派生层。lean-platform 可以参考现有 Qlib 数据层次并读取 `gold/qlib_staging` 中的基准数据，但不能修改 Qlib 仓库、`data/qlib` 或 Qlib 自己的缓存。

LEAN 数据由 Silver/Gold 生成或恢复。回测前的缓存准备、fingerprint 和校验都必须指向同一数据版本；删除 LEAN 缓存不会删除事实数据。平台不再执行“MySQL 导出 Parquet”，旧的 export/rebuild API 已移除；现在的 Parquet registry 操作只负责发现、注册和校验已有数据湖。

## 数据质量和可复现

每个可用于生产的范围至少需要：

1. Provider、请求参数、抓取时间和批次 ID；
2. 分区行数、日期范围和 SHA-256；
3. schema、重复键、OHLC、交易日和异常值检查；
4. PIT 生效时间与摄取时间；
5. 数据集版本、认证状态和撤销原因；
6. 回测/研究 Run 中保存的数据版本和文件指纹。

任何 current 分区改变都会使旧认证失效，重新完成文件哈希、DuckDB 可读性和质量检查后才能重新认证。MySQL 中的 registry 是目录，不是行情副本；以 Parquet 文件内容和 manifest 校验和为准。

## 备份与恢复

股票数据备份必须覆盖整个 `data/`，至少包含 Bronze current/revisions、Silver、Gold、registry、quality 和需要保留的 LEAN/Qlib 派生产物。MySQL 逻辑备份只覆盖控制平面，不能恢复股票行情。

恢复顺序建议为：

1. 恢复 `data/` 并校验 manifest/SHA-256；
2. 启动 MySQL，恢复任务、注册、账户和审计数据；
3. 重新发现/注册 Parquet 数据集；
4. 按需重建 LEAN、ClickHouse 和其他缓存；
5. 做代码、数据版本、行数、日期和抽样 OHLC 校验。

## 主要接口

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/data/query` | DuckDB/Parquet 行情查询 |
| `POST` | `/api/data/resolve` | 解析 Data Scope 与可用覆盖 |
| `GET` | `/api/data/parquet/datasets` | 浏览已发现/注册的数据集 |
| `POST` | `/api/data/parquet/consistency` | 校验分区、manifest 和可读性 |
| `POST` | `/api/data/on-demand/downloads` | 创建按需下载任务 |
| `GET` | `/api/data/derived/watermarks` | 查看可选派生层水位 |

详细路径和 schema 以 [API Reference](api-reference.md) 为准。
