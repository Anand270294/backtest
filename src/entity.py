from dataclasses import dataclass
from typing import List, Tuple

import pandas as pd

from src import constants


@dataclass
class Trade:
    date: str
    symbol: str
    order_type: str
    action: str
    limit_price: float
    quantity: float
    fees: float


@dataclass
class HoldingRecords:
    date: str
    adjusted_close: float
    quantity: float
    portfolio_value: float


class StockEntity:
    TRADE_COLUMNS = [
        "date",
        "symbol",
        "order_type",
        "action",
        "limit_price",
        "quantity",
    ]

    HOLDING_RECORDS_COLUMNS = ["date", "adjusted_close", "quantity", "portfolio_value", "daily_returns"]

    def __init__(self, symbol: str):
        self.symbol = symbol
        self.trades = self._initialize_dataframe(self.TRADE_COLUMNS)
        self.holding_records = self._initialize_dataframe(self.HOLDING_RECORDS_COLUMNS)

    @staticmethod
    def _initialize_dataframe(columns: List[str]) -> pd.DataFrame:
        return pd.DataFrame(columns=columns)

    @staticmethod
    def calculate_pnl(
        entry_quantity,
        entry_price,
        exit_quantity,
        exit_price,
        entry_fees,
        exit_fees,
        position_type,
    ):

        if position_type == constants.LONG_POSITION:
            return (exit_quantity * exit_price) - (entry_quantity * entry_price) - entry_fees - exit_fees
        else:
            return (entry_quantity * entry_price) - (exit_quantity * exit_price) - entry_fees - exit_fees

    def limit_order(
        self,
        trade: Trade,
        high_price: float,
        low_price: float,
    ) -> Tuple[bool, str]:
        if trade.action == constants.TRADE_ACTION_BUY:
            if high_price >= trade.limit_price >= low_price:
                self.update_trades(trade)
                return True, ""
        elif trade.action == constants.TRADE_ACTION_SELL:
            if low_price <= trade.limit_price <= high_price:
                self.update_trades(trade)
                return True, ""

        return False, "Ask/Bid price is not met"

    def market_order(self, trade: Trade) -> Tuple[bool, str]:
        self.update_trades(trade)
        return True, ""

    def update_trades(self, trade: Trade):
        # No open position, add new row to add new trade
        if self.trades.empty:
            self.trades = pd.DataFrame([trade.__dict__])
        else:
            new_trade = pd.DataFrame([trade.__dict__]).dropna(axis=1)
            self.trades = pd.concat([self.trades, new_trade], ignore_index=True)

    def update_holding_records(self, timestamp, price):
        long_positions = self.trades[self.trades["action"] == constants.TRADE_ACTION_BUY]
        short_positions = self.trades[self.trades["action"] == constants.TRADE_ACTION_SELL]
        long_position_quantity = long_positions["quantity"].sum()
        short_position_quantity = short_positions["quantity"].sum()
        net_position = long_position_quantity - short_position_quantity

        holding_records = HoldingRecords(
            date=timestamp,
            adjusted_close=price,
            quantity=net_position,
            portfolio_value=net_position * price,
        )

        new_record = pd.DataFrame([holding_records.__dict__]).dropna(axis=1)
        new_record["date"] = pd.to_datetime(new_record["date"])
        new_record = new_record.set_index("date")

        if self.holding_records.empty:
            self.holding_records = new_record
        else:
            self.holding_records = pd.concat([self.holding_records, new_record])

        # Calculate daily returns
        self.holding_records["daily_returns"] = self.holding_records["portfolio_value"].pct_change().fillna(0)

        # Correct daily returns where the previous day's portfolio value was zero
        previous_portfolio_value = self.holding_records["portfolio_value"].shift(1)
        self.holding_records.loc[previous_portfolio_value == 0, "daily_returns"] = 0

        # Adjust returns for short positions
        short_return_indices = self.holding_records["quantity"] < 0
        self.holding_records.loc[short_return_indices, "daily_returns"] *= -1

        # Format the daily returns to avoid negative zero
        self.holding_records["daily_returns"] = self.holding_records["daily_returns"].apply(
            lambda x: 0 if x == -0 else x
        )
