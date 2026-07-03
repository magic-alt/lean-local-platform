# QuantConnect LEAN Docker Demo

这个 demo 不依赖 Lean CLI，直接使用你已经拉取的 `quantconnect/lean:latest` 镜像运行 Python 回测。它现在包含一个轻量本地平台，用来导入公开 OHLCV 数据、选择标的、运行 Docker LEAN 回测并生成 HTML 报告。

策略文件：

- `DockerDemoAlgorithm.py`：SPY 日线 10/30 EMA 交叉策略
- `config.json`：LEAN Launcher 配置
- `run.sh`：一键 Docker 运行脚本
- `local_platform.py`：本地数据导入、参数化回测和报告生成工具
- `DATA_SOURCES.md`：公开数据源和数据质量说明
- `web/`：FastAPI + React Web 平台
- `results/`：回测结果输出目录，运行后自动创建

运行：

```bash
cd /Users/kaermax/Lean
chmod +x docker-demo/run.sh
./docker-demo/run.sh
```

脚本会挂载：

- `/Users/kaermax/Lean/Data` 到容器 `/Lean/Data`
- `docker-demo/DockerDemoAlgorithm.py` 到容器 `/Lean/DockerDemoAlgorithm.py`
- `docker-demo/config.json` 到容器 `/Lean/Launcher/bin/Debug/config.json`
- `docker-demo/results` 到容器 `/Lean/Results`

回测结束后查看：

```bash
ls -la docker-demo/results
```

常见输出文件：

- `docker-demo-backtest.json`
- `docker-demo-backtest-summary.json`
- `docker-demo-backtest-log.txt`
- `docker-demo-backtest-order-events.json`

生成本地图表 HTML：

```bash
python3 docker-demo/plot_results.py
open docker-demo/results/report.html
```

图表脚本只使用 Python 标准库，不需要安装 `matplotlib`、`pandas` 或 Lean CLI。

## 本地平台用法

查看可用数据源建议：

```bash
python3 docker-demo/local_platform.py sources
```

查看本地已有可回测标的：

```bash
python3 docker-demo/local_platform.py symbols
```

运行参数化回测：

```bash
python3 docker-demo/local_platform.py backtest \
  --symbol SPY \
  --start 2013-01-01 \
  --end 2013-06-30 \
  --fast 10 \
  --slow 30 \
  --open
```

结果会写入：

```text
docker-demo/runs/{run-id}/results/
```

从 Alpha Vantage 下载日线数据并转换成 LEAN 格式：

```bash
export ALPHAVANTAGE_API_KEY="your-key"
python3 docker-demo/local_platform.py fetch-alpha-vantage MSFT --outputsize compact
python3 docker-demo/local_platform.py backtest --symbol MSFT --start 2026-01-01 --end 2026-07-01 --open
```

导入任意 CSV：

```bash
python3 docker-demo/local_platform.py import-csv MSFT ~/Downloads/MSFT.csv
```

CSV 默认需要这些列：

```text
timestamp,open,high,low,close,volume
```

如果列名不同，可以用 `--date-col`、`--open-col`、`--high-col`、`--low-col`、`--close-col`、`--volume-col` 指定。

如果 Docker 报权限或 daemon 错误，先确认 Docker Desktop 正在运行：

```bash
open -a Docker
docker info
```

## Web 平台

Web 平台现在是一个本地工作台：FastAPI 提供 API，React 提供浏览器界面，Redis + Celery 负责后台回测/优化/报告任务，SQLite 记录项目、任务和结果索引。

安装：

```bash
cd /Users/kaermax/Lean/docker-demo/web/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cd ../frontend
npm install
npm run build
```

启动 Redis：

```bash
redis-server --port 6379
```

启动 API：

```bash
cd /Users/kaermax/Lean/docker-demo/web/backend
source .venv/bin/activate
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

启动 Celery worker：

```bash
cd /Users/kaermax/Lean/docker-demo/web/backend
source .venv/bin/activate
celery -A app.tasks.celery_app worker --loglevel=info --pool=solo
```

打开：

```text
http://127.0.0.1:8000
```

Web 端支持：

- 查看本地 Docker 版 LEAN 能力矩阵
- 项目制工作区：项目概览、代码编辑、数据准备、回测提交、结果和任务日志在一个页面完成
- 创建/编辑本地 Python/C# 策略项目
- 查看本地 LEAN daily 标的
- CSV 导入并转换成 LEAN 格式
- 当前道指 30 只成分股数据面板，支持批量选择缺失标的并下载到本地 LEAN 数据目录
- Yahoo Finance、Stooq、Alpha Vantage 日线数据导入
- 选择项目、股票、日期、资金、EMA 参数并运行 Docker 回测
- 参数网格优化
- Research 容器启动
- Object Store 文件管理
- 后台任务和日志查看
- 查看状态、日志、指标、图表、订单和原始结果文件
- 回测曲线显示权益、基准、标的价格、EMA、回撤，并在权益/价格曲线上标记订单时间点

如果 `8000` 已被占用，可以先找出旧进程：

```bash
lsof -nP -iTCP:8000 -sTCP:LISTEN
```

也可以换端口启动 API，但开发模式下要同步修改 `docker-demo/web/frontend/vite.config.ts` 的代理端口。

数据源注意：

- Yahoo Finance 和 Stooq 是免费公开端点，适合本地实验，但可能因网络、限流、验证码或服务条款变化而失败。
- Alpha Vantage 需要 API key，免费额度有限，但在公开 API 里通常更稳定，适合先搭建可靠的自动化下载流程。
- Web 平台会把下载后的日线数据转换成 LEAN zip 格式并登记到 SQLite；回测时仍由 Docker 版 LEAN 读取本地 `Data/`。

状态和索引存入 SQLite：

```text
docker-demo/web/runtime/lean_web.sqlite3
```

原始 LEAN JSON、日志和报告仍按 run 保存在：

```text
docker-demo/web/runtime/runs/
```
