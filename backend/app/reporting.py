def format_summary(start_balance: float, equity: float, realized_pnl: float, unrealized_pnl: float) -> str:
    return (
        f"Start balance: {start_balance:.2f} USDT\n"
        f"Current equity: {equity:.2f} USDT\n"
        f"Realized PnL: {realized_pnl:.2f} USDT\n"
        f"Unrealized PnL: {unrealized_pnl:.2f} USDT"
    )
