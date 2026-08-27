# 快速开始

本教程完成最小可信闭环：启动平台、检查依赖、准备数据、创建项目、执行 preflight、运行回测并核对报告。当前架构矩阵见 [Current State](../current-state.md)。

## 1. 准备配置

Docker 部署需要 Docker Desktop/Engine；本地开发还需要 Python 3.12 与 Node.js/npm。复制示例配置后，为 PostgreSQL、RabbitMQ、API 和 runner 设置不同的本地密钥，并只配置实际启用的 Provider 凭据：

```bash
cp .env.example .env
python scripts/platformctl.py --mode docker --profile full doctor
```

不要提交、粘贴或截图 `.env` 内容。

## 2. 启动

Docker 完整栈：

```bash
python scripts/platformctl.py --mode docker --profile full start
```

依赖顺序由平台管理：

```text
PostgreSQL healthy -> postgres-init -> migration -> API/workers/beat/runner
RabbitMQ healthy -------------------------------> API/workers/beat
```

Windows 无 Docker 开发机使用：

```powershell
.\scripts\start_windows_native.ps1
```

该入口默认管理用户态本地进程。只有显式设置 `LEAN_NATIVE_MANAGER=windows-scm` 或生产模式时才操作 Windows 服务。

## 3. 检查服务

```bash
python scripts/platformctl.py --mode docker --profile full status
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8000/api/health/dependencies
curl http://127.0.0.1:8000/api/health/database
```

至少确认 PostgreSQL、RabbitMQ、迁移状态、目标 worker 和 LEAN runner 正常。依赖降级时先按 [故障排查](troubleshooting.md) 保存证据，不要直接提交长任务或整体重启。

## 4. 准备数据

进入 Data 页面，确认 Provider 权限和存储目标，再运行一键全量或增量同步。一键范围以代码中的 `BULK_DATASET_KEYS` 为准；不要依赖文档中的固定数量。完成状态要求 ready item、成功 manifest、水位和可读取的 Bronze/Parquet 归档同时成立。

Parquet 是行情事实层；PostgreSQL 只保存同步、血缘、质量、认证和业务控制状态。详细规则见 [数据教程](data.md)。

## 5. 创建项目并回测

在 Projects 创建项目、保存 Strategy Source，然后在 Backtests 选择项目和数据范围。先执行 preflight；通过后再提交回测。正式示例省略 `dockerImage`，平台会使用已配置、digest-pinned 且在 allowlist 中的默认镜像。

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

Run Detail 中至少核对状态、日志、指标、订单、基准、Validation、Data Evidence、运行指纹和原始 LEAN 产物。不要只以 `status=success` 判断结果可信。

## 6. Research 与 Paper

Research 执行、Notebook、训练和 walk-forward research 位于外部 `qlib-platform`。它通过 Artifact Contract v2 与内容寻址的 `TARGET_PORTFOLIO` 交给 platform 导入和 LEAN 验证。可信且已验证的运行才可进入 Paper；P9/live activation 仍禁用。

下一步可阅读 [Backtests](backtests.md)、[Research 边界](research.md)、[Paper](paper.md) 和 [Reports](reports.md)。
