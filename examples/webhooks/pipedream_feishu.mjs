import { createHmac } from "node:crypto";


function required(value, name) {
  const resolved = String(value || "").trim();
  if (!resolved) throw new Error(`${name} is not configured`);
  return resolved;
}


function feishuSignature(timestamp, secret) {
  return createHmac("sha256", `${timestamp}\n${secret}`)
    .update("")
    .digest("base64");
}


function alertText(alert) {
  const details = alert.details && typeof alert.details === "object"
    ? JSON.stringify(alert.details, null, 2)
    : String(alert.details || "");
  return [
    `【LEAN ${String(alert.severity || "unknown").toUpperCase()}】${alert.title || "Operational alert"}`,
    alert.message || "",
    `事件：${alert.eventType || "unknown"}`,
    `来源：${alert.source || "unknown"}`,
    `状态：${alert.status || "open"}`,
    `次数：${alert.count || 1}`,
    `关联 ID：${alert.relatedId || "—"}`,
    `首次发生：${alert.firstSeenAt || "—"}`,
    `最后发生：${alert.lastSeenAt || "—"}`,
    details ? `详情：\n${details}` : "",
  ].filter(Boolean).join("\n").slice(0, 12000);
}


export default defineComponent({
  async run({ steps, $ }) {
    const webhookUrl = required(process.env.FEISHU_WEBHOOK_URL, "FEISHU_WEBHOOK_URL");
    const rawBody = steps.trigger.event.body;
    const alert = typeof rawBody === "string" ? JSON.parse(rawBody) : rawBody;
    if (!alert || typeof alert !== "object" || Number(alert.schemaVersion) !== 1) {
      throw new Error("Unsupported LEAN alert payload");
    }

    const payload = {
      msg_type: "text",
      content: { text: alertText(alert) },
    };
    const secret = String(process.env.FEISHU_WEBHOOK_SECRET || "").trim();
    if (secret) {
      const timestamp = Math.floor(Date.now() / 1000);
      payload.timestamp = timestamp;
      payload.sign = feishuSignature(timestamp, secret);
    }

    const response = await fetch(webhookUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json; charset=utf-8" },
      body: JSON.stringify(payload),
    });
    const responseText = await response.text();
    let result;
    try {
      result = JSON.parse(responseText);
    } catch {
      result = { raw: responseText };
    }
    const feishuCode = result.code ?? result.StatusCode;
    if (!response.ok || Number(feishuCode ?? 0) !== 0) {
      throw new Error(
        `Feishu delivery failed: HTTP ${response.status}, code ${String(feishuCode ?? "unknown")}`
      );
    }

    await $.respond({
      status: 200,
      headers: { "Content-Type": "application/json" },
      body: {
        accepted: true,
        alertId: alert.id,
        feishuCode: Number(feishuCode ?? 0),
      },
    });
    return { accepted: true, alertId: alert.id };
  },
});
