# 飞书 Webhook 验证记录 — 2026-08-13

## 结论

`FEISHU_SIGNED_WEBHOOK_PASS`。

实际飞书 V2 自定义机器人端点已接受签名文本消息。飞书业务响应为
`StatusCode=0`、`StatusMessage=success`、`code=0`、`msg=success`，证明当前端点与
`FEISHU_WEBHOOK_SECRET` 匹配，飞书终端投递链路可用。

## 验证范围

| 项目 | 结果 |
| --- | --- |
| HTTPS 端点 | `open.feishu.cn`，路径与查询参数不记录 |
| 未签名请求 | `code=19021`，按预期拒绝并证明签名校验已启用 |
| 签名请求 | HTTP 请求完成，飞书业务码 `0` |
| 测试消息 | `LEAN 平台飞书 Webhook 验证成功` |
| 密钥变量 | `FEISHU_WEBHOOK_SECRET` |
| 敏感信息 | webhook 路径、密钥和签名值均未写入仓库或本文 |

`FEISHU_WEBHOOK_SECRET` 是飞书 HMAC 签名密钥；它与中转入口可选的
`LEAN_ALERT_WEBHOOK_BEARER_TOKEN` 是两个不同凭据，不得混用。

## 尚未关闭的门禁

本次验证直接按飞书消息格式发送，不经过 LEAN 通用告警 payload、Pipedream/Make
转换和 `alert_deliveries` 持久化。因此 ACT-P1-007 从
`OPEN_EXTERNAL_CHANNEL_AND_24H` 前进到
`EXTERNAL_ENDPOINT_VERIFIED_24H_PENDING`，但仍未关闭。正式关闭还需要：

1. 由中转端将 LEAN `schemaVersion=1` payload 转换成飞书消息并完成签名；
2. 运行 `scripts/run_external_webhook_acceptance.py`，取得 persisted external 2xx；
3. 连续观察 24 小时，证明 attempts 有界、无重试风暴、DLQ 可回归且 health 恢复；
4. 保存不含 webhook 查询参数、Bearer token、签名密钥或签名值的审计证据。
