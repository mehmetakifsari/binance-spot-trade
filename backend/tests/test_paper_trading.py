from app.paper_trading import BalanceState, execute_buy, execute_sell


def test_execute_buy_uses_notional_and_updates_balance():
    balance = BalanceState(cash_usdt=15, asset_qty=0)

    updated, qty = execute_buy(balance, price=100, notional_usdt=3)

    assert round(updated.cash_usdt, 8) == 12
    assert round(qty, 8) == 0.03
    assert round(updated.asset_qty, 8) == 0.03


def test_execute_sell_liquidates_position():
    balance = BalanceState(cash_usdt=12, asset_qty=0.03)

    updated, qty, proceeds = execute_sell(balance, price=120)

    assert round(qty, 8) == 0.03
    assert round(proceeds, 8) == 3.6
    assert round(updated.cash_usdt, 8) == 15.6
    assert round(updated.asset_qty, 8) == 0
