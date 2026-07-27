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

- Built-in service templates include `buy_hold`, `ema_cross`, `sma_cross`, `macd`, `rsi_reversion`, `donchian_breakout`, `bollinger_reversion`, `etf_rotation`, `crypto_momentum`, `future_trend` and `blank`.
- File-backed manifests under `strategies/templates/` extend the catalog, currently including `risk_parity`, `dynamic_universe` and other repository templates.
- `GET /api/strategies/templates` is authoritative; documentation should not duplicate a permanently fixed list.
- `GET /api/examples` adds runnable backtest, optimization and research cases on top of strategy templates. Examples may specify batch mode, universe rules and defaults, then instantiate a project/workflow through the API.

## File-Backed Manifest Shape

Reusable templates may live in a directory:

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

For a guarded buy limit, multi-symbol A-share templates may call:

```python
self.ashare_execution.limit_buy(symbol, quantity, limit_price, tag="...")
```

The helper rechecks trade status, pending orders, lot size, cash and estimated
buy costs before it forwards the limit order to LEAN.

## Benchmark Rule

A-share templates must require a real benchmark. Constant benchmark fallback is disabled in generated production templates. Missing benchmark data should block the run before Docker execution.

## Testing Expectations

Every production template should eventually have:

- render test: generated Python contains expected class and helper usage.
- parameter schema test.
- minimum LEAN integration test with fixture data.
- A-share rule test if it supports China equity.
- result parser smoke test.
- example-catalog validation when the template is referenced by `examples/catalog.json`.
- dynamic-universe/PIT coverage test when `executionScope=dynamic_universe`.
