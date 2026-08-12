# LEAN 告警转发到飞书

LEAN 告警发送通用 JSON。飞书群自定义机器人要求飞书消息 JSON，因此需要由
Pipedream 或 Make 做一次格式转换。正式认证链路必须是：

```text
LEAN -> Pipedream/Make 公网 HTTPS Trigger -> 飞书 V2 自定义机器人
```

中转端只有在飞书返回成功后才应向 LEAN 返回 HTTP 2xx；否则外部 webhook
认证只能证明中转端收到了请求，不能证明飞书投递成功。

## 当前验证状态（2026-08-13）

实际飞书 V2 机器人端点已完成签名验证并成功接收测试消息：未签名请求按预期返回
`code=19021`，使用 `FEISHU_WEBHOOK_SECRET` 生成时间戳签名后返回
`StatusCode=0`、`code=0` 和 `msg=success`。这证明机器人地址、签名密钥和飞书终端
投递可用；验证过程未把 webhook URL、签名密钥或签名值写入仓库和审计文档。

本次是飞书终端单点验证，不等于 LEAN 通用 JSON 经中转、写入
`alert_deliveries` 并持续观察 24 小时的正式认证。因此 `ACT-P1-007` 当前为
`EXTERNAL_ENDPOINT_VERIFIED_24H_PENDING`，仍需按本文“最终认证”完成持久化投递与
观察窗口。详细记录见
[飞书 Webhook 验证记录](../audit/external-webhook-verification-2026-08-13.md)。

## 飞书准备

1. 在目标飞书群的群机器人设置中添加“自定义机器人”。
2. 复制 V2 webhook URL，格式通常为
   `https://open.feishu.cn/open-apis/bot/v2/hook/...`。
3. 推荐启用签名校验并保存签名 secret。不要把 webhook URL 或 secret
   写进仓库、工作流代码或执行日志。

飞书机器人签名凭据必须命名为 `FEISHU_WEBHOOK_SECRET`。它不是
`LEAN_ALERT_WEBHOOK_BEARER_TOKEN`：后者只用于 LEAN 调用 Pipedream/Make 入口时的
Bearer 认证，不能替代飞书 HMAC 签名密钥。

## Pipedream（推荐）

1. 创建 Workflow，Trigger 选择 **HTTP / Webhook**。
2. 给 HTTP Trigger 配置 **Custom token**，不要使用无认证的公开入口。
3. 新增两个 project secret：
   - `FEISHU_WEBHOOK_URL`：飞书 V2 webhook URL。
   - `FEISHU_WEBHOOK_SECRET`：飞书签名 secret；未开启签名时留空。
4. 添加 Node.js code step，将
   `examples/webhooks/pipedream_feishu.mjs` 的内容完整粘贴进去。
5. Deploy workflow，复制 Pipedream endpoint 和 Custom token，在本项目根目录
   `.env` 配置：

```dotenv
LEAN_ALERT_WEBHOOK_URL="https://your-endpoint.m.pipedream.net"
LEAN_ALERT_WEBHOOK_BEARER_TOKEN="Pipedream Custom token"
LEAN_ALERT_MIN_SEVERITY=critical
LEAN_ALERT_WEBHOOK_TIMEOUT_SECONDS=10
```

代码会验证 LEAN `schemaVersion=1`，生成飞书文本消息，支持飞书签名校验，
并检查飞书业务响应码。只有飞书成功时才向 LEAN 返回 200。

## Make

创建以下 Scenario：

```text
Webhooks / Custom webhook
  -> JSON / Create JSON
  -> HTTP / Make a request
  -> Webhooks / Webhook response
```

在 Create JSON 中建立 `msg_type` 和 `content.text` 两个字段。`msg_type` 固定为
`text`，`content.text` 使用映射面板组合为：

```text
【LEAN severity】title
message
事件：eventType
来源：source
状态：status
次数：count
关联 ID：relatedId
最后发生：lastSeenAt
```

HTTP 模块配置：

- Method：`POST`
- URL：飞书 V2 webhook URL，作为 Make 的 secret/connection 保存
- Header：`Content-Type: application/json; charset=utf-8`
- Body type：`Raw` / `application/json`
- Request content：映射 Create JSON 的 JSON string 输出

字段应从 Custom webhook 模块的映射面板选择。使用 Create JSON 可以正确转义告警
中的引号和换行。HTTP 模块开启“将所有非 2xx/3xx 响应视为错误”。最后的
Webhook response 仅在 HTTP 模块成功后返回状态 `200` 和
`{"accepted":true}`；错误路由返回 `502`。

Make 的纯映射方案不生成飞书 HMAC 签名。如果飞书机器人启用了签名校验，使用
Pipedream 方案，或在 Make 中增加能够执行 HMAC-SHA256 的代码模块。

将 Make 生成的 Custom webhook URL 配置为 `LEAN_ALERT_WEBHOOK_URL`。如果 Make
入口使用 Bearer Token，再同步配置 `LEAN_ALERT_WEBHOOK_BEARER_TOKEN`。

## 最终认证

数据库和中转 workflow/scenario 均在线后，在仓库根目录运行：

```bash
web/backend/.venv/bin/python scripts/run_external_webhook_acceptance.py \
  --evidence web/runtime/audit/external-webhook-acceptance.json
```

同时确认：

- 命令输出 `EXTERNAL_WEBHOOK_PASS` 和 `thirdPartyCertified: true`。
- 飞书群实际收到标题为 `LEAN external webhook acceptance probe` 的消息。
- 证据文件没有保存 webhook 查询参数或密钥。
