# Data Sources for Local LEAN Backtesting

This local platform can run without a QuantConnect paid account because it uses the open-source LEAN Docker image directly. The tradeoff is that you are responsible for data acquisition, licensing, conversion, and quality control.

## Practical Sources

| Source | Best Use | Access | Notes |
|---|---|---|---|
| Existing `QuantConnect/Lean` sample data | Smoke tests and demos | Already in `Data/` | Small sample only, not enough for research. |
| Alpha Vantage | Daily equities and ETFs | API key | Easy CSV endpoint. Free/premium limits apply. Full history may require premium entitlement. |
| Generic CSV exports | Durable local workflow | Any vendor/export | Recommended path: export OHLCV, then `import-csv`. |
| Tiingo | US equities/ETFs EOD and intraday | API key | Better for serious work; check license and plan. |
| Polygon.io | Equities/ETF/minute/tick style workflows | API key | Good API surface; historical depth and real-time access depend on plan. |
| Nasdaq Data Link | EOD/fundamental/economic datasets | API key / dataset license | Dataset coverage and license vary. |
| Databento | Futures/equities market data | API key | Strong structured data source; plan and symbols vary. |
| Yahoo Finance / Stooq | Exploration/manual CSV | Website/API behavior varies | Scripted downloads can be rate-limited or blocked; prefer manual CSV plus `import-csv`. |

## Current Platform Scope

The implemented converter targets LEAN's US equity daily TradeBar format:

```text
Data/equity/usa/daily/{ticker}.zip
  {ticker}.csv
  YYYYMMDD 00:00,open,high,low,close,volume
```

Prices are stored in deci-cents, so the platform multiplies dollar prices by `10000`.

It also creates minimal auxiliary files:

```text
Data/equity/usa/map_files/{ticker}.csv
Data/equity/usa/factor_files/{ticker}.csv
```

These placeholders are enough to run simple raw-price daily backtests, but they do not reconstruct corporate actions.

## Data Quality Warnings

Daily OHLCV data is enough for learning and strategy prototyping, but not enough for production-grade equity research by itself. Important gaps:

- Splits and dividends
- Delisted symbols and survivorship bias
- Ticker changes and symbol mapping
- Bid/ask spreads and realistic slippage
- Market holidays and early closes
- Vendor-specific adjustment rules
- Volume corrections and bad ticks

For serious research, use a licensed vendor with corporate-action-aware data and keep a reproducible data import log.

## Commands

List available local symbols:

```bash
python3 docker-demo/local_platform.py symbols
```

Download Alpha Vantage daily data:

```bash
export ALPHAVANTAGE_API_KEY="your-key"
python3 docker-demo/local_platform.py fetch-alpha-vantage MSFT --outputsize compact
```

Import a CSV with `timestamp,open,high,low,close,volume` columns:

```bash
python3 docker-demo/local_platform.py import-csv MSFT ~/Downloads/MSFT.csv
```

Run a backtest:

```bash
python3 docker-demo/local_platform.py backtest \
  --symbol SPY \
  --start 2013-01-01 \
  --end 2013-06-30 \
  --fast 10 \
  --slow 30 \
  --open
```
