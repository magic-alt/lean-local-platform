# TuShare 商业级行情库契约与建库

Last reviewed: 2026-08-12.

## 审计结论

旧行情表只能覆盖平台已接入的一部分 TuShare 接口，不能据此宣称覆盖 TuShare Pro
股票、指数、期货和期权专题。旧结构的主要缺口是：接口契约没有版本化、供应商字段会被
通用 JSON/EAV 降格保存、同一业务事实缺少来源仲裁、修订历史和 point-in-time 有效期，
期权条款、期货结算、指数成分区间及高频分区也没有统一治理边界。

迁移 `0046`/`0047` 后，数据库的**结构覆盖**达到当前官方文档快照的 139/139：

| 资产类别 | 官方文档 | Active | Retired | 当前同步注册 |
| --- | ---: | ---: | ---: | ---: |
| 股票 | 100 | 98 | 2 | 21 |
| 指数 | 21 | 21 | 0 | 5 |
| 期货 | 15 | 15 | 0 | 3 |
| 期权 | 3 | 3 | 0 | 2 |
| 合计 | 139 | 137 | 2 | 31 |

这里必须区分两个结论：

- 139 个文档契约都有自然键、完整输出字段、类型、可空性、来源表和官方文档链接，因而
  MySQL/列式层已有承载全部当前文档数据的结构；
- 自动同步注册目前覆盖 31/137 个 active 契约（22.63%）。其余接口已经可发现、可建表，
  但在为必填参数、权限、分页和频率逐项配置抓取策略前，不会声称已经采集数据。

因此当前版本解决的是“库表能否无损承载和治理”的问题，不伪造“所有账号权限和数据已经
下载”的结论。账号实际权限及返回字段仍必须用受限 live sample 验证。

2026-08-12 的实现验收已在真实 TuShare Pro 上完成四个只读样本：`stock_basic`、
`index_basic`、`fut_basic`、`opt_basic` 分别返回 17、13、16、20 个已声明字段，未发现额外
字段；这只证明四个代表契约和当前账号调用有效，不替代其余接口逐项权限盘点。

## 分层和所有权

```text
TuShare 官方文档快照
  -> provider/dataset/contract 版本目录
  -> src_tushare_* 原始类型化来源表（修订、hash、有效期）
  -> provider-neutral canonical v2（仲裁后的业务事实）
  -> LEAN cache / Parquet / ClickHouse 派生层
```

- `config/tushare_contracts.v1.json` 是可审计的官方契约快照，不依赖某个 Token 权限。
- 139 张 `src_tushare_*` 表保留 provider 原生类型字段、payload hash、批次、观察时间和
  修订号。完整原始 JSON 只在内容寻址的 gzip batch archive 保存一次，避免逐行 JSON 与
  类型列重复占用 MySQL；相同 payload 不重复写，字段变化关闭上一修订并生成唯一当前修订。
- 38 个 active canonical 契约映射到供应商无关的 instrument、daily bar、financial、index、
  futures、option 等 v2 业务表；87 个 active 契约先进入 typed-source 层，待业务语义稳定后
  再增加 canonical 投影。
- 12 个 active 分钟/Tick/实时契约标记为 `columnar`。高频事实写入 ClickHouse/Parquet，
  MySQL 只保存 dataset、contract、run、partition、watermark、hash 和质量元数据。139 张来源
  表虽然随迁移创建以固定契约边界，但 columnar writer 不向它们灌入高频事实。
- SQLite 不承担任何运行数据。它只在 pytest 中作为临时、隔离的迁移兼容后端；运行配置未
  显式启用测试门禁时，SQLite 会被拒绝。

## 商业级约束

v2 使用稳定 instrument ID 和带有效期的 provider identifier，避免代码更名或换所覆盖历史；
价格和金额使用定点 `DECIMAL`，交易日使用 `DATE`，事件时间使用微秒级 `DATETIME(6)`；
来源观察、契约版本、payload hash、修订、current 标志和 valid-time 共同支持重放及审计。
provider priority、fact resolution log 和 current selection 将“来源事实”与“最终业务事实”
分离，后续增加 JQData、交易所授权源或其他供应商时无需复制一套业务表。

表级 check、unique、foreign key 和覆盖索引保护生命周期、正数条款、单一自然键修订和
依赖关系。迁移是 additive，且 rollback policy 明确要求以经过评审的前向补偿迁移处理，
不会在失败时静默丢弃来源证据。

## 契约刷新与验证

刷新命令会访问 TuShare 官方文档。审阅 JSON diff 后再生成迁移，不能手改生成 SQL：

```bash
web/backend/.venv/bin/python scripts/refresh_tushare_contracts.py --as-of YYYY-MM-DD
web/backend/.venv/bin/python scripts/generate_tushare_source_schema.py
web/backend/.venv/bin/python scripts/validate_tushare_contracts.py
```

有本地 Token 时，可执行每类资产一个、每次最多一行的只读样本探针。输出不会包含 Token；
`permission_denied` 表示账号授权不足，不表示契约缺失：

```bash
web/backend/.venv/bin/python scripts/validate_tushare_contracts.py --live-sample
```

公共契约可从 `GET /api/data/contracts` 查询，并可用 `assetClass`、`status`、
`includeFields` 过滤。Data catalog 同时返回 contract coverage，前端不应再把注册接口数当成
官方数据集总数。

## 空库一次性准备

部署代码后由正常 migration runner 创建 additive v2 表。先只读检查：

```bash
web/backend/.venv/bin/python scripts/mysql_storage_maintenance.py commercial-v2-status
web/backend/.venv/bin/python scripts/mysql_storage_maintenance.py commercial-v2-plan
```

`commercial-v2-plan` 会逐表确认 19 张旧市场数据表为空、19 张核心 v2 表和 139 张来源表
完整；项目、策略、回测、Paper、Research、设置和审计域始终在保护范围内。只有报告中
`ready=true` 时，暂停 writer 后才运行：

```bash
web/backend/.venv/bin/python scripts/mysql_storage_maintenance.py \
  prepare-commercial-v2 --confirm
```

该命令只同步契约目录、写入 9 个中国交易场所并把 schema 标为 `prepared`。它不会清表、
改兼容视图或自动切换 reader。正式 `active` 切换必须在 canonical 双写/回放对账、读取兼容
验证、代表性回测和恢复演练全部通过后通过单独版本发布；本实现没有提供危险的一键激活。

## 扩展规则

新增供应商时先注册 provider/dataset/contract，不得直接在 canonical 表增加供应商专属列；
新增 TuShare 字段时生成新 contract version 和前向迁移，旧修订继续可读；新资产类别必须先
定义 identity、生命周期、交易日历、价格精度、单位/乘数和质量门禁。高频数据不得回流
MySQL 行表，Parquet/ClickHouse 分区必须记录 row count、时间范围、schema version 和 hash。

本实现已在隔离的真实 MySQL 8.4 空库执行全部 migration、139 表计数、版本修订唯一性，
并完成上述四类 live sample。正式上线前仍需执行全量同步小样本、来源冲突仲裁、
Parquet/ClickHouse 对账和备份恢复演练。结构完整不等于运营验收。
