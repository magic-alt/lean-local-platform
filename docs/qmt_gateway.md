# Platform QMT read-only gateway

The MiniQMT/XtQuant adapter is owned by `platform` under
`web/backend/app/broker/qmt_gateway`. It is an observation boundary for the
execution domain, not a research service. The gateway exposes current-day
account, position, order, fill and quote snapshots through authenticated GET
requests. It contains no order submission, cancellation or replacement API.

The process must bind to a loopback IP. Start it from `web/backend` with the
repository-local interpreter:

```powershell
& .\.venv\python.exe -m app.broker.qmt_gateway serve --host 127.0.0.1 --port 8765
```

Configure `QMT_USERDATA_PATH`, `QMT_ACCOUNT_ID`, `QMT_ACCOUNT_TYPE`,
`QMT_SESSION_ID` and `QMT_GATEWAY_TOKEN` in the local process environment.
`QMT_XTQUANT_SITE_PACKAGES` may point at the broker-approved XtQuant package.
Never persist or log the credential values.

The gateway deliberately returns raw broker totals only. Daily PnL, cash-flow
adjustments, hard risk, reconciliation and ledger state are computed and
persisted by the platform execution domain. No SQLite state is created by the
gateway.

The API is available at `/v1/health`, `/v1/account`, `/v1/positions`,
`/v1/orders`, `/v1/fills` and `/v1/quotes`. Except for health, every endpoint
requires `Authorization: Bearer <REDACTED>` and a `trade_date` equal to the
current Asia/Shanghai date.
