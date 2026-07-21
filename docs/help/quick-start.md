# 快速开始

本教程完成一个最小可信闭环：启动本地平台、检查服务、建立数据、创建策略项目、执行 preflight、运行回测并打开报告。

## 1. 环境要求

- Docker Desktop 或 Docker Engine 正常运行，并允许当前用户访问 Docker socket。
- Python 3.12 和 Node.js/npm 用于本地开发；完整 Compose 使用时由镜像提供运行环境。
- 本地至少配置 MySQL、Redis、API、worker；LEAN 回测还需要可拉取或已缓存的 LEAN Docker 镜像。
- 使用 TuShare 数据时在 `.env` 配置 `TUSHARE_TOKEN`，不要把 `.env` 提交到 Git。

```bash
cp .env.example .env
# 编辑 .env，填入需要使用的 Provider 凭据
```

## 2. 启动平台

工作站推荐使用单实例启动脚本：

```bash
./scripts/start_web_single_instance.sh
```

只有 Dockerfile、Python/npm 依赖或前端构建输入发生变化时才需要：

```bash
./scripts/start_web_single_instance.sh --build
```

普通重启不需要重复构建。脚本会避免多个启动器互相替换，并在活动数据同步期间保护 data worker。

也可以直接启动 Compose：

```bash
docker compose --profile app up -d --build \
  mysql redis api worker data-worker data-demand-worker backtest-worker beat
```

## 3. 检查服务

打开 Monitoring 页面，或直接请求：

```bash
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8000/api/health/dependencies
curl http://127.0.0.1:8000/api/health/database
```

至少确认 MySQL、Redis 和 Docker 可用。出现 MySQL 2006/2013、容器退出 137 或依赖降级时，先阅读 [故障排查](troubleshooting.md)，不要直接提交长任务。

## 4. 首次建库

进入 Data 页面：

1. 确认 TuShare 权限探测成功。
2. 如果系统没有成功全量建库记录，按钮显示“一键全量更新”。
3. 启动后观察真实 API 调用数、下载/入库/隔离行、工作单元速度和 checkpoint。
4. 完成后按钮会持久化为“一键增量更新”，重启不会重置。
5. 在“按数据集预览”检查股票、交易日历、指数、期货和期权数据。

一键范围、正确性链路和磁盘规则见 [数据教程](data.md)。

## 5. 创建策略项目

进入 Projects：

1. 选择市场、资产类别、分辨率和策略模板。
2. 创建项目后在 Strategy Source 编辑代码。
3. 检查 `project.json` 中的模板、参数、基准、费用和滑点配置。
4. 保存后，回测会复制不可变项目快照；后续修改不会改变已经提交的运行。

第一次建议使用 Buy & Hold 或 EMA Cross。详细模板和案例见 [策略与模板](strategies.md)。

## 6. 运行首个回测

进入 Backtests，选择刚创建的 Project，填写股票、日期、资金和基准。

```json
{
  "projectId": "your-project-id",
  "symbol": "000001",
  "assetClass": "equity",
  "market": "china",
  "venue": "china",
  "resolution": "daily",
  "dataType": "trade",
  "start": "2024-01-02",
  "end": "2024-12-31",
  "cash": 300000,
  "parameters": {"benchmarkSymbol": "000300"}
}
```

先点击 preflight。A 股 preflight 会检查项目、参数、行情、交易日历、基准和质量门禁。通过后再提交回测，并在 Run Detail 查看状态、日志、曲线、订单、持仓、校验和运行指纹。

## 7. 生成并核对报告

成功运行可以从 Run Detail 或 Reports 生成统一 HTML/Markdown 报告。至少检查：

- 收益、Sharpe、最大回撤和交易次数是否合理；
- 策略曲线、基准和回撤曲线是否存在；
- 订单、费用、滑点和最终持仓是否符合策略；
- Validation、Data Evidence 和 Experiment Fingerprint 是否完整；
- 原始 LEAN JSON、日志和对象归档是否可访问。

不要只以 `status=success` 判断策略可信。结果说明见 [Reports](reports.md) 和 [结果格式](../backtest_result_format.md)。

## 下一步

- 同一策略覆盖股票池或多个时间窗口：[批量回测](backtests.md)。
- 寻找稳健参数并做样本外验证：[Optimization](optimization.md)。
- 使用 Notebook 或标准研究任务继续分析：[Research](research.md)。
- 使用可信历史运行启动逐日模拟：[Paper](paper.md)。
