# Strategy Templates

Strategy templates are managed by `web/backend/app/services/strategies.py` and exposed through `GET /api/strategies/templates`.

## Current Template Model

Each template is a dictionary entry:

```python
{
    "key": "sma_cross",
    "name": "SMA Cross",
    "description": "...",
    "parameters": [
        {"key": "fast", "label": "Fast SMA", "type": "number", "default": 20, "min": 1}
    ],
    "body": "... Python QCAlgorithm body ..."
}
```

`render_python_template(class_name, template_key)` combines:

- `COMMON_HEADER`
- selected template body
- `COMMON_FOOTER`

Projects created from the UI are persisted under `web/runtime/projects`.

## Existing Templates

- `buy_hold`
- `ema_cross`
- `sma_cross`
- `macd`
- `rsi_reversion`
- `donchian_breakout`
- `bollinger_reversion`
- `etf_rotation`
- `crypto_momentum`
- `future_trend`
- `blank`

## Recommended Manifest Shape

The current in-code dictionary is sufficient for P1. For P2, move each template into a directory:

```text
strategies/templates/<key>/
  manifest.json
  main.py
  README.md
  tests/
```

Recommended `manifest.json`:

```json
{
  "key": "sma_cross",
  "name": "SMA Cross",
  "version": 1,
  "description": "Simple moving average crossover.",
  "author": "local",
  "assetClasses": ["equity"],
  "markets": ["usa", "china"],
  "resolutions": ["daily"],
  "riskLevel": "medium",
  "parameters": [
    {
      "key": "fast",
      "type": "number",
      "default": 20,
      "min": 1,
      "required": true
    }
  ],
  "expectedArtifacts": ["result.json", "summary.json", "order-events.json"],
  "minimumData": {
    "bars": 120,
    "benchmark": true
  }
}
```

## Parameter Schema Rules

- Every parameter must have a stable `key`.
- Numeric parameters should define `min`, and when useful `max` and `step`.
- Boolean parameters should use a boolean type, not string flags.
- Symbol lists should be strings only at the UI boundary; services should normalize to arrays.
- Template defaults must produce a runnable backtest with available fixture data.

## A-Share Helper Usage

A-share strategies must avoid raw `set_holdings()` when `self.ashare_execution` is available.

Use:

```python
self.ashare_execution.target_percent(self.symbol, 1)
self.ashare_execution.exit(self.symbol)
```

Fallback for non-A-share:

```python
self.set_holdings(self.symbol, 1)
self.liquidate(self.symbol)
```

The helper enforces:

- T+1 sell restriction.
- suspended day block.
- limit-up buy block.
- limit-down sell block.
- lot rounding.
- cash buffer.
- fee/slippage assumptions.

## Benchmark Rule

A-share templates must require a real benchmark. Constant benchmark fallback is disabled in both `DockerDemoAlgorithm.py` and generated templates. Missing benchmark data should block the run before Docker execution.

## Testing Expectations

Every production template should eventually have:

- render test: generated Python contains expected class and helper usage.
- parameter schema test.
- minimum LEAN integration test with fixture data.
- A-share rule test if it supports China equity.
- result parser smoke test.

