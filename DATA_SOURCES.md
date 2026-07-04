# Data Sources for Local LEAN Backtesting

This local platform can run without a QuantConnect paid account because it uses the open-source LEAN Docker image directly. The tradeoff is that you are responsible for data acquisition, licensing, conversion, and quality control.

## Practical Sources

| Source | Best Use | Access | Notes |
|---|---|---|---|
| Existing `QuantConnect/Lean` sample data | Smoke tests and demos | Already in `Data/` | Small sample only, not enough for research. |
| Alpha Vantage | Daily equities and ETFs | API key | Easy CSV endpoint. Free/premium limits apply. Full history may require premium entitlement. |
| Binance public klines | Crypto spot daily OHLCV | Public REST | Good for local crypto demos; region, symbols, and rate limits can change. |
| Generic CSV exports | Durable local workflow | Any vendor/export | Recommended path: export OHLCV, then `import-csv`. |
| Tiingo | US equities/ETFs EOD and intraday | API key | Better for serious work; check license and plan. |
| Polygon.io | Equities/ETF/minute/tick style workflows | API key | Good API surface; historical depth and real-time access depend on plan. |
| Nasdaq Data Link | EOD/fundamental/economic datasets | API key / dataset license | Dataset coverage and license vary. |
| Databento | Futures/equities market data | API key | Strong structured data source; plan and symbols vary. |
| Yahoo Finance / Stooq | Exploration/manual CSV | Website/API behavior varies | Scripted downloads can be rate-limited or blocked; prefer manual CSV plus `import-csv`. |

## Current Platform Scope

The web platform indexes multiple LEAN data trees:

```text
Data/equity/{market}/{resolution}/
Data/crypto/{venue}/{resolution}/
Data/future/{venue}/{resolution}/
```

The equity converter targets LEAN daily TradeBar format:

```text
Data/equity/{market}/daily/{ticker}.zip
  {ticker}.csv
  YYYYMMDD 00:00,open,high,low,close,volume
```

Prices are stored in deci-cents, so the platform multiplies dollar prices by `10000`.

Crypto and futures CSV import writes daily TradeBar zip files without the equity price multiplier:

```text
Data/crypto/{venue}/daily/{symbol}_trade.zip
Data/future/{venue}/daily/{symbol}_trade.zip
```

It also creates minimal auxiliary files:

```text
Data/equity/{market}/map_files/{ticker}.csv
Data/equity/{market}/factor_files/{ticker}.csv
```

These placeholders are enough to run simple raw-price daily backtests, but they do not reconstruct corporate actions.

Futures research needs more than OHLCV. Validate contract multipliers, margin files, factor/map files, open interest, and continuous contract mapping before using imported futures data for conclusions.

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
python3 local_platform.py symbols
```

Download Alpha Vantage daily data:

```bash
export ALPHAVANTAGE_API_KEY="your-key"
python3 local_platform.py fetch-alpha-vantage MSFT --outputsize compact
```

Local provider secrets can be stored in the repository root `.env`; this file is ignored by git. Use `.env.example` as the template:

```bash
cp .env.example .env
# edit .env
TUSHARE_TOKEN=your_tushare_pro_token
```

TuShare Pro adapter status:

- Minimum verified permission: `pro.daily()`.
- Optional tables used when permission exists: `adj_factor`, `stk_limit`, `trade_cal`, `stock_basic`.
- If optional permissions are unavailable, daily import continues with raw OHLCV, `adj_factor=1.0` fallback where needed, and OHLCV-inferred trade-status QA warnings.

Import a CSV with `timestamp,open,high,low,close,volume` columns:

```bash
python3 local_platform.py import-csv MSFT ~/Downloads/MSFT.csv
```

Run a backtest:

```bash
python3 local_platform.py backtest \
  --symbol SPY \
  --start 2013-01-01 \
  --end 2013-06-30 \
  --fast 10 \
  --slow 30 \
  --open
```
