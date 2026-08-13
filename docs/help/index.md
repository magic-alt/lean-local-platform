# LEAN Local 文档中心

LEAN Local 是面向本地研究、回测、优化、模拟交易和数据治理的 QuantConnect LEAN 工作台。Web、FastAPI、Celery、MySQL 与 Docker LEAN 构成正式运行链路；`data/` Parquet 是股票行情事实层，MySQL 是控制平面，LEAN 与 ClickHouse 是可重建消费层，DuckDB 直接查询 Parquet。

> 建议第一次使用时按“数据 → 项目 → 回测 → 报告”的顺序完成最小闭环，再进入批量实验、Optimization、Research 和 Paper。

## 推荐工作流

1. 在 [快速开始](quick-start.md) 中准备 `.env`、启动服务并检查依赖健康。
2. 在 [数据、增量更新与 PIT](data.md) 中完成首次一键全量建库，并验证 Preview 和质量报告。
3. 在 [策略与模板](strategies.md) 中从模板或案例创建独立项目副本。
4. 在 [回测与批量回测](backtests.md) 中先执行 preflight，再运行一个小范围单次回测。
5. 使用 [Reports](reports.md) 检查指标、订单、数据证据、指纹和原始产物。
6. 单次链路可信后，再进入 [Optimization](optimization.md)、[Research](research.md) 或 [Paper](paper.md)。

## 操作教程

| 主题 | 适用场景 |
| --- | --- |
| [快速开始](quick-start.md) | 安装、启动、首次建库和首个回测 |
| [策略与模板](strategies.md) | 创建项目、编辑策略、参数与 A 股规则 |
| [数据](data.md) | 全量/增量、按需下载、CSV、Preview、质量与 PIT |
| [回测](backtests.md) | 单次、批量、动态组合、取消和结果可信度 |
| [Optimization](optimization.md) | 网格、股票池稳健性、Walk-forward 和多策略 |
| [Research](research.md) | 快捷研究、因子批量评价和 Jupyter |
| [期权数据与交易边界](options-trading.md) | 当前合约、研究准备、盈亏风险、到期处理和接入要求 |
| [Paper](paper.md) | LEAN Walk-forward、信号模拟与每日复盘 |
| [Reports](reports.md) | 结果详情、比较、报告、归档与导出 |
| [高级研究能力](advanced-research.md) | Insights、因子、组合、期货、期权和可转债 |
| [配置与运行资源](configuration.md) | Settings、环境变量、Docker、目录与备份 |
| [监控与故障排查](troubleshooting.md) | Tasks、Monitoring、MySQL、同步和前端问题 |

## 技术参考

- [API 使用指南](../api.md)：接口语义、核心示例、错误与兼容规则。
- [完整 API 端点索引](api-reference.md)：由 OpenAPI 生成的全部公开操作。
- [架构](../architecture.md)：组件边界、主链路、事实库和恢复边界。
- [数据管线](../data_pipeline.md) 与 [数据来源](../data_sources.md)：同步、质量、来源和审计。
- [部署](../deployment.md)：Compose、资源、MySQL、备份和安全。
- [策略模板](../strategy_template.md) 与 [结果格式](../backtest_result_format.md)：扩展和集成契约。
- [测试](../testing.md)、[仓库目录](../repository_layout.md) 和 [Roadmap](../roadmap.md)：维护与验收规则。

历史问题与修复证据保留在 [历史记录](../history/README.md) 中。历史文章会显示“历史快照”提示，不能替代当前教程和代码状态。

## 动态事实来源

部分内容比人工文档变化更快，应以以下接口为最终事实来源：

| 内容 | 事实来源 |
| --- | --- |
| API 路由和 Schema | `/openapi.json`、`/docs` |
| 策略模板 | `GET /api/strategies/templates` |
| 回测、优化和研究案例 | `GET /api/examples` |
| Provider 与同步策略 | `GET /api/data/catalog` |
| 服务健康 | `GET /api/health/dependencies` |
| 数据库迁移 | `scripts/db_migrate.py --status` |
