from dataclasses import dataclass


@dataclass
class BalanceState:
    cash_usdt: float
    asset_qty: float


def execute_buy(balance: BalanceState, price: float, notional_usdt: float) -> tuple[BalanceState, float]:
    spend = min(balance.cash_usdt, notional_usdt)
    qty = spend / price if price > 0 else 0
    balance.cash_usdt -= spend
    balance.asset_qty += qty
    return balance, qty


def execute_sell(balance: BalanceState, price: float) -> tuple[BalanceState, float, float]:
    qty = balance.asset_qty
    proceeds = qty * price
    balance.cash_usdt += proceeds
    balance.asset_qty = 0
    return balance, qty, proceeds
