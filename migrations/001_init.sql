CREATE TABLE IF NOT EXISTS bot_state (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(20) UNIQUE NOT NULL,
    state VARCHAR(32) NOT NULL,
    drop_blocks INTEGER NOT NULL DEFAULT 0,
    rise_blocks INTEGER NOT NULL DEFAULT 0,
    bearish_moves INTEGER NOT NULL DEFAULT 0,
    bullish_moves INTEGER NOT NULL DEFAULT 0,
    panic_mode BOOLEAN NOT NULL DEFAULT FALSE,
    cooldown_until TIMESTAMPTZ,
    latest_price NUMERIC(18,8) NOT NULL DEFAULT 0,
    latest_rsi NUMERIC(10,4) NOT NULL DEFAULT 0,
    cash_usdt NUMERIC(18,8) NOT NULL DEFAULT 0,
    asset_qty NUMERIC(28,12) NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS trades (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(8) NOT NULL CHECK (side IN ('BUY', 'SELL')),
    qty NUMERIC(28,12) NOT NULL,
    price NUMERIC(18,8) NOT NULL,
    notional_usdt NUMERIC(18,8) NOT NULL,
    realized_pnl_usdt NUMERIC(18,8),
    reason TEXT NOT NULL,
    signal_snapshot JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_trades_symbol_time ON trades(symbol, created_at DESC);

CREATE TABLE IF NOT EXISTS positions (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'OPEN',
    entry_price NUMERIC(18,8),
    avg_entry_price NUMERIC(18,8),
    qty NUMERIC(28,12) NOT NULL DEFAULT 0,
    invested_usdt NUMERIC(18,8) NOT NULL DEFAULT 0,
    current_value_usdt NUMERIC(18,8) NOT NULL DEFAULT 0,
    unrealized_pnl_usdt NUMERIC(18,8) NOT NULL DEFAULT 0,
    opened_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    closed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS balance_snapshots (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    cash_usdt NUMERIC(18,8) NOT NULL,
    asset_qty NUMERIC(28,12) NOT NULL,
    mark_price NUMERIC(18,8) NOT NULL,
    equity_usdt NUMERIC(18,8) NOT NULL,
    snapshot_time TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_balance_symbol_time ON balance_snapshots(symbol, snapshot_time DESC);

CREATE TABLE IF NOT EXISTS report_cache (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    period_type VARCHAR(16) NOT NULL CHECK (period_type IN ('daily', 'weekly', 'monthly')),
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    summary_json JSONB NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(symbol, period_type, period_start)
);
CREATE INDEX IF NOT EXISTS idx_report_cache_lookup ON report_cache(symbol, period_type, period_start DESC);
