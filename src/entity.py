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

    HOLDING_RECORDS_COLUMNS = ["date", "closed_price", "quantity", "portfolio_value", "daily_returns", "dividends"]

    def __init__(self, symbol: str):
        self.symbol = symbol
        self.trades = self._initialize_dataframe(self.TRADE_COLUMNS)
        self.holding_records = self._initialize_dataframe(self.HOLDING_RECORDS_COLUMNS)
        self.quantity = 0.0

    @staticmethod
    def _initialize_dataframe(columns: List[str]) -> pd.DataFrame:
        return pd.DataFrame(columns=columns)

    def limit_order(self, trade: Trade, high_price: float, low_price: float) -> Tuple[bool, str]:
        if trade.action == constants.TRADE_ACTION_BUY and trade.limit_price >= low_price:
            self.update_trades(trade)
            self.quantity += trade.quantity
            # print(f"Limit Buy Order: Updated Quantity = {self.quantity}")
            return True, "Order executed"
        elif trade.action == constants.TRADE_ACTION_SELL and trade.limit_price <= high_price:
            self.update_trades(trade)
            self.quantity -= trade.quantity
            # print(f"Limit Sell Order: Updated Quantity = {self.quantity}")
            return True, "Order executed"
        return False, "Price condition not met"

    def market_order(self, trade: Trade) -> Tuple[bool, str]:
        self.update_trades(trade)
        if trade.action == constants.TRADE_ACTION_BUY:
            self.quantity += trade.quantity
            # print(f"Market Buy Order: Updated Quantity = {self.quantity}")
        elif trade.action == constants.TRADE_ACTION_SELL:
            self.quantity -= trade.quantity
            # print(f"Market Sell Order: Updated Quantity = {self.quantity}")
        return True, "Order executed"

    def update_trades(self, trade: Trade):
        # No open position, add new row to add new trade
        if self.trades.empty:
            self.trades = pd.DataFrame([trade.__dict__])
        else:
            new_trade = pd.DataFrame([trade.__dict__]).dropna(axis=1)
            self.trades = pd.concat([self.trades, new_trade], ignore_index=True)

    def update_holding_records(self, timestamp, price):
        holding_records = HoldingRecords(
            date=timestamp,
            adjusted_close=price,
            quantity=self.quantity,
            portfolio_value=self.quantity * price,
        )

        new_record = pd.DataFrame([holding_records.__dict__]).dropna(axis=1)
        new_record["date"] = pd.to_datetime(new_record["date"])  # TODO: set this as a type
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
        self.holding_records["daily_returns"] = self.holding_records["daily_returns"].apply(lambda x: 0 if x == -0 else x)

    def calculate_dividends(self, dividend_data):
        """
        Calculate dividends for a stock entity

        :param stock_entity: StockEntity class for the stock
            Holding Records Columns:
                - Index: Date of the holding record
                - adjusted_close: Adjusted close price of the stock
                - quantity: Quantity of the stock held
                - portfolio_value: Portfolio value of the stock
                - daily_returns: Daily returns of the stock
                - dividends: Dividends received for the stock
        :param dividend_data: Historical dividend data for the stock
            Dividend Data Columns:
                - declaration_date: Date of the dividend declaration
                - record_date: Date of the dividend record. Must hold the stock by this date to receive the dividend
                - payment_date: Date of the dividend payment
                - value: Dividend amount
                - period: Period of the dividend
                - unadjusted_value: Unadjusted dividend amount
                - currency: Currency of the dividend
        """
        stock_holdings = self.holding_records
        stock_dividends = dividend_data[dividend_data["code"] == self.symbol]

        # Ensure the 'dividends' column exists in stock_holdings
        if "dividends" not in stock_holdings.columns:
            stock_holdings["dividends"] = 0.0

        # Iterate through each dividend event
        for _, dividend in stock_dividends.iterrows():
            record_date = dividend["record_date"]
            payment_date = dividend["payment_date"]
            dividend_value = dividend["unadjusted_value"]

            date_range = pd.date_range(start=record_date, end=payment_date, freq="D")
            trading_dates = date_range.intersection(stock_holdings.index)

            # Check if the stock entity held the stock on the record date
            if (stock_holdings.loc[trading_dates, "quantity"] > 0).all():
                # Update the 'dividends' column for the record date
                stock_holdings.loc[record_date, "dividends"] = dividend_value * stock_holdings.loc[record_date, "quantity"]
