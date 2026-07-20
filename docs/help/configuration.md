# 配置与运行资源

Settings 保存网页默认值，`.env` 保存容器和数据服务配置。不要将 TuShare Token、数据库密码或其他密钥提交到 Git。

## 关键设置

| 设置 | 说明 |
| --- | --- |
| `dockerImage` | LEAN 回测镜像 |
| `researchImage` | Jupyter Research 镜像 |
| `maxConcurrentJobs` | 同时运行的 LEAN 容器数，范围 1–8 |
| `maxBatchRuns` | 单个批次允许展开的最大子运行数，默认 5000 |
| `jobTimeoutSeconds` | 单个 LEAN 任务超时 |
| `defaultCash` | 新表单的默认初始资金 |

批量并发不会绕过 `maxConcurrentJobs`。提高并发前应观察 CPU、内存和 Docker I/O；任务队列只会维持一个小的派发窗口。

启动脚本只有在依赖、Dockerfile或前端构建内容变化时需要 `--build`；日常重启无需重复构建。
