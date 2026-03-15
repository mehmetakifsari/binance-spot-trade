# Database Schema Notes

Migration: `migrations/001_init.sql`

## Tables

1. `bot_state`
   - Per-symbol runtime state including block counters, cooldown, panic mode, and latest RSI/price.

2. `trades`
   - All paper buy/sell actions with reason, notional, qty, and PnL fields.

3. `positions`
   - Current and historical position snapshots per symbol.

4. `balance_snapshots`
   - Equity and balance time series for dashboard reporting.

5. `report_cache`
   - Cached daily/weekly/monthly summaries for UI and Telegram delivery.

## Indexing

- `trades(symbol, created_at)` for history queries
- `balance_snapshots(symbol, snapshot_time)` for charting
- `report_cache(symbol, period_type, period_start)` for summaries
