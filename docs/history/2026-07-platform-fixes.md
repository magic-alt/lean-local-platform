# 2026-07 平台稳定性与数据同步修复

状态更新时间：2026-07-21。

本文保留 2026-07 已出现问题的症状与根因。状态变化只追加到对应条目，不删除历史问题。

## 数据同步进度停滞和恢复任务失败

- 症状：`stk_limit` 等长任务已继续写入，但网页进度长时间停在同一股票；恢复任务曾报 `Unknown column 'heartbeat_at'`。
- 根因：运行容器与数据库迁移版本不一致，且长批次的进度/心跳提交粒度过大。
- 修复：迁移 `0016_data_sync_heartbeat.sql` 增加同步心跳；同步批次持久化 checkpoint 和 heartbeat，恢复任务只接管真正失联的运行；前端从数据库读取持久化进度。
- 状态：`resolved`。部署时仍必须先完成迁移并重启 API、worker 和 beat。
- 遗留风险：超大 SQL 批次仍可能延迟一次进度提交，不能把单次 UI 静止直接判定为任务停止。

## Provider 逐行 JSON 写放大

- 症状：每行重复序列化并写入完整 Provider JSON，造成写入变慢、表和索引膨胀、磁盘持续下降。
- 根因：`provider_raw_records` 同时承担查询索引和原始响应归档，规范化表已有同一数据后仍重复保留 JSON。
- 修复：`provider_raw_records` 改为轻量键/日期/哈希索引；有无损标准表的数据不保留逐行 JSON；不能无损映射的数据通过迁移 `0017_provider_raw_batch_archives.sql` 进入内容寻址 gzip 批次归档。历史 JSON 使用 `scripts/cleanup_provider_raw_json.py` 分段验证、清空并可选重建表空间。
- 状态：`resolved`，历史清理工具保留。
- 遗留风险：清理前必须确认目标数据集已有标准表或批次归档；不能直接 `TRUNCATE provider_raw_records`，否则会丢失索引与审计关系。

## 一键更新容量判断口径不一致

- 症状：页面 MySQL 大小与物理占用不同，一键更新曾受 50 GB 配置拒绝，磁盘空间却继续下降。
- 根因：逻辑表统计、InnoDB 物理文件和 Docker 卷占用是不同口径；旧配置把按需缓存上限错误用于全库建库。
- 修复：API 和 worker 通过同一只读 observer mount 报告 MySQL 物理占用；`LEAN_MYSQL_ON_DEMAND_MAX_DATABASE_GB` 只限制按需写入；一键更新仅受磁盘安全线约束，至少保留 500 GiB 或总容量的 50%（取较大值）。
- 状态：`resolved`。
- 遗留风险：InnoDB 删除行后通常只形成表内可复用空间，宿主机可用容量不会立即增加；回收物理空间需要低峰维护操作和足够临时空间。

## 单实例启动、重建和退出行为

- 症状：重复启动造成多套容器/前端轮询；收到退出信号后脚本可能等待活动同步或 Compose 关闭而看似无法退出；用户不确定每次是否需要 `--build`。
- 根因：启动器缺少完整的单实例协调和活动同步保护，构建与重启语义混在一起。
- 修复：`scripts/start_web_single_instance.sh` 使用进程锁和幂等 Compose 协调；活动同步期间不替换数据 worker，也不默认关闭服务；仅 Dockerfile、依赖或前端构建输入变化时使用 `--build`，普通重启无需构建。
- 状态：`resolved`。
- 遗留风险：强制停止活动同步必须显式设置允许开关，并接受一个小批次的幂等重放。

## 数据集 Preview 导致前端空白

- 症状：指数、期货或期权 Preview 打开后整个 Web 页面空白，随后只显示“前端无法展示的字段”。
- 根因：通用渲染器直接把对象/非常规字段作为 React 子节点，且页面级错误没有被局部边界隔离。
- 修复：预览值统一转为安全可展示文本，按股票、交易日历、指数、期货和期权使用数据集感知布局，并在预览区域内捕获渲染错误。
- 状态：`resolved`，对应代码里程碑 `5091fa4`。
- 遗留风险：新增 Provider 字段仍应先通过 JSON-safe API schema 和前端值格式化测试。

## MySQL OOM 与 2013 连接中断

- 症状：API、周期恢复和批次协调同时报 `OperationalError(2013, 'Lost connection to MySQL server during query')`，列表接口返回 500。
- 根因：Docker Desktop 总内存约束下，MySQL buffer pool/redo 与多个 worker、LEAN 容器竞争，MySQL 被 OOMKill；客户端连接没有统一的短暂故障重试和 API 降级语义。
- 修复：MySQL 默认 buffer pool 调整为 1 GiB、redo 为 256 MiB，服务使用 `restart: unless-stopped`；连接建立对 1040/2003/2006/2013 做有界重试；API 映射为可重试的 503 `DATABASE_UNAVAILABLE`，周期 Celery 任务自动重试。
- 状态：`resolved`，对应代码里程碑 `058ee75`。
- 遗留风险：Docker 总内存不足或同时运行过多 LEAN/Research 容器仍可触发 OOM；需要结合 Monitoring、`docker inspect` 和宿主机资源判断。

## 报告表头溢出与旧页面缓存

- 症状：报告把结果路径和所有图表名称挤在一行；代码更新后 Reports 页面仍可能展示旧 HTML。
- 根因：报告元信息未结构化，浏览器/代理对同一报告 URL 复用缓存。
- 修复：报告表头改为分区元信息和图表标签，长路径折叠；报告文件响应使用 `no-store`，前端预览 URL 带布局版本和时间戳。
- 状态：`resolved`。2026-07-21 已用 `report-layout-v2` 原子重建现存 81 份 HTML 报告，并将 81 个新版对象归档到 MySQL；旧对象版本未删除。
- 遗留风险：从旧备份恢复报告后需再次运行 `scripts/regenerate_backtest_reports.py --archive`；缓存控制只保证取到当前文件，不能主动迁移外部备份副本。
