import typing
from dataclasses import dataclass
from datetime import datetime
from typing import List

import pandas as pd
from tqdm import tqdm

from src import constants
from src.entity import StockEntity, Trade
from src.ibkr_fees import calculate_ibkr_fixed_cost
import quantstats as qs

from src.utils import get_split_data


@dataclass
class Order:
    order_id: int
    attached_order: bool
    ticker: str
    order_type: str
    action: str
    limit_price: float
    time_in_force: str
    quantity: float
    status: str = ""
    order_date: str = ""
    stop_price: float = 0.0
    trail_type: str = ""
    trail: float = 0.0

    @staticmethod
    def get_pandas_timestamp(date) -> pd.Timestamp:
        return pd.Timestamp(date)


class BacktestEngine:
    ORDER_BOOK_COLUMNS = [
        "order_date",
        "ticker",
        "order_type",
        "action",
        "price",
        "quantity",
        "trail_type",
        "trail",
        "time_in_force",
        "order_status",
        "filled_price",
        "filled_date",
        "comments",
    ]

    PORTFOLIO_RECORDS_COLUMNS = [
        "date",
        "total_fees",
        "capital",
    ]

    PORTFOLIO_STATS_COLUMNS = [
        "date",
        "sharpe",
        "turnover",
        "returns",
        "max_drawdown",
        "margin",
        "long_count",
        "short_count",
    ]

    def __init__(
        self,
        order_book: pd.DataFrame,
        ohlvc: pd.DataFrame,
        initial_capital: float = 100000.0,
    ):
        self.order_book = order_book.copy()
        self.stocks = {}  # Dictionary to store the stock entities
        self.ohlvc = ohlvc.copy()
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.fees = 0.0
        self.portfolio_records = self._initialize_dataframe(self.PORTFOLIO_RECORDS_COLUMNS)
        self.portfolio_stats = self._initialize_dataframe(self.PORTFOLIO_STATS_COLUMNS)
        self.combined_holding_records = pd.DataFrame()

        self.order_book["status"] = ""
        self.order_book["comments"] = ""
        self.order_book["filled_date"] = ""
        self.order_book["filled_price"] = ""

    @staticmethod
    def _initialize_dataframe(columns: List[str]) -> pd.DataFrame:
        return pd.DataFrame(columns=columns)

    @staticmethod
    def calculate_fees(qty, price_per_share):
        return calculate_ibkr_fixed_cost(qty=qty, price_per_share=price_per_share)

    @staticmethod
    def stop_loss_trigger(stop_price, action, price) -> bool:
        """
        Check if the stop loss price is triggered

        If the action is BUY, then the price will be the HIGH price
        If the action is SELL, then the price will be the LOW price

        :param stop_price:
        :param action:
        :param price:
        :return:
        """
        if action == constants.TRADE_ACTION_BUY:
            return price >= stop_price
        elif action == constants.TRADE_ACTION_SELL:
            return price <= stop_price

    @staticmethod
    def update_trailing_stop_price(trail_type, trail, action, price) -> float:
        """
        Update the trailing stop price based on the trail type and trail value

        If the action is BUY, then the price will be the LOW price + trail
        If the action is SELL, then the price will be the HIGH price - trail

        :param trail_type:
        :param trail:
        :param action:
        :param price:
        :return:
        """
        if trail_type == constants.TRAIL_TYPE_VALUE:
            if action == constants.TRADE_ACTION_BUY:
                return price + trail
            elif action == constants.TRADE_ACTION_SELL:
                return price - trail
        elif trail_type == constants.TRAIL_TYPE_PERCENTAGE:
            if action == constants.TRADE_ACTION_BUY:
                return price + (1 + trail)
            elif action == constants.TRADE_ACTION_SELL:
                return price * (1 - trail)

    def create_limit_order(self, order: Order):
        """
        Create a limit order and append it to the order book

        Limit order will only execute when the price reaches the limit price

        :param order:
        :return:
        """
        # Add order into order book
        new_order = pd.DataFrame(
            {
                "order_id": order.order_id,
                "order_date": order.order_date,
                "ticker": order.ticker,
                "order_type": order.order_type,
                "action": order.action,
                "limit_price": order.limit_price,
                "time_in_force": order.time_in_force,
                "quantity": order.quantity,
                "stop_price": order.stop_price,
                "trail_type": order.trail_type,
                "trail": order.trail,
                "attached_order": order.attached_order,
                "status": order.status,
                "comments": "",
                "filled_date": "",
            },
            index=[0],
        )

        new_order["order_date"] = pd.to_datetime(new_order["order_date"])
        if self.order_book.empty:
            self.order_book = new_order
        else:
            self.order_book = pd.concat([self.order_book, new_order], ignore_index=True)

    def get_active_orders(self, current_timestamp):
        return self.order_book[
            (self.order_book["order_date"] <= current_timestamp) & (self.order_book["status"] == constants.ORDER_STATUS_PENDING)
        ]

    def initialize_stocks(self):
        for stock in self.order_book["ticker"].unique():
            self.stocks[stock] = StockEntity(symbol=stock)

    def update_portfolio_records(self, current_timestamp):
        new_record = pd.DataFrame(
            {
                "total_fees": [self.fees],
                "capital": [self.current_capital],
            },
            index=[current_timestamp],
        )

        if self.portfolio_records.empty:
            self.portfolio_records = new_record
        else:
            self.portfolio_records = pd.concat([self.portfolio_records, new_record])

    def combine_holding_records(self):
        holding_records_list = []

        # Add the stock symbol as a level in the DataFrame's columns
        for symbol, stock_entity in self.stocks.items():
            stock_holding_records = stock_entity.holding_records[["quantity", "portfolio_value"]].copy()

            stock_holding_records.columns = pd.MultiIndex.from_product([[symbol], stock_holding_records.columns])
            holding_records_list.append(stock_holding_records)

        # Add the portfolio capital as a level in the DataFrame's columns
        portfolio_capital = self.portfolio_records[["capital", "total_fees"]].copy()
        portfolio_capital.columns = pd.MultiIndex.from_product([["Portfolio"], portfolio_capital.columns])
        holding_records_list.append(portfolio_capital)

        # Concatenate all holding records along the columns axis
        combined_holding_records = pd.concat(holding_records_list, axis=1)

        # Calculate portfolio value (capital + all stock portfolio value) TODO: check this calculation
        sum_all_portfolio_value = combined_holding_records.xs("portfolio_value", level=1, axis=1).sum(axis=1)

        combined_holding_records[("Portfolio", "portfolio_value")] = (
            sum_all_portfolio_value + combined_holding_records[("Portfolio", "capital")]
        )

        # Calculate returns
        combined_holding_records[("Portfolio", "returns")] = combined_holding_records[
            ("Portfolio", "portfolio_value")
        ].pct_change()

        self.combined_holding_records = combined_holding_records

    def generate_tear_down(self, file_name):
        returns = self.combined_holding_records[("Portfolio", "returns")]
        qs.reports.html(returns, "SPY", output=file_name)

    def adjust_stock_entity_for_splits(self, split):
        """
        Adjust stock entity for a stock split event.
        """
        stock_entity = self.stocks[split["code"]]
        stock_entity.quantity *= split["split_ratio"]

    def adjust_order_for_splits(self, stock_split, order, idx, current_timestamp):
        """
        Adjust order book for a stock split event.
        :param stock_split:
        :param order:
        :param idx:
        :param current_timestamp:
        :return:
        """
        if order["ticker"] in stock_split["code"].tolist():
            split_ratio = stock_split[stock_split["code"] == order["ticker"]]["split_ratio"].values[0]

            # Set existing orders to "Cancelled" with status "Stock Split Adjustment" and create new orders to replace
            self.order_book.at[idx, "status"] = constants.ORDER_STATUS_SPLIT_ADJ
            self.order_book.at[idx, "comments"] = f"Stock Split Adjustment of {split_ratio}"
            self.order_book.at[idx, "filled_date"] = current_timestamp
            print("Stock Split Event: Creating new entry order for idx ", idx)

            # Create new order to replace the cancelled order
            self.create_limit_order(
                Order(
                    order_id=order["order_id"],
                    attached_order=order["attached_order"],
                    order_date=current_timestamp.strftime(format="%Y-%m-%d %H:%M:%S"),
                    ticker=order["ticker"],
                    order_type=order["order_type"],
                    action=order["action"],
                    limit_price=order["limit_price"] / split_ratio,
                    time_in_force=order["time_in_force"],
                    quantity=order["quantity"] * split_ratio,
                    stop_price=order["stop_price"] / split_ratio,
                    trail_type=order["trail_type"],
                    trail=(
                        order["trail"] if order["trail_type"] == constants.TRAIL_TYPE_PERCENTAGE else order["trail"] / split_ratio
                    ),
                    status=constants.ORDER_STATUS_PENDING,
                )
            )

            # Account for bracket orders that are not pending as the entry order is not executed yet
            if not order["attached_order"]:
                # Find index of the other attached_order with the same order id and update status to cancelled
                attached_order_idx_list = self.order_book[
                    (self.order_book["order_id"] == order["order_id"]) & (self.order_book["attached_order"])
                ].index.tolist()
                if len(attached_order_idx_list) != 0:
                    for order_idx in attached_order_idx_list:
                        self.order_book.loc[order_idx, "status"] = constants.ORDER_STATUS_SPLIT_ADJ
                        self.order_book.at[order_idx, "comments"] = f"Stock Split Adjustment of {split_ratio}"
                        self.order_book.loc[order_idx, "filled_date"] = current_timestamp

                        order = self.order_book.loc[order_idx]
                        # Create new orders to replace the cancelled attached orders
                        print("Stock Split Event: Creating new attached order for idx", order_idx)
                        self.create_limit_order(
                            Order(
                                order_id=order["order_id"],
                                attached_order=True,
                                order_date=current_timestamp.strftime(format="%Y-%m-%d %H:%M:%S"),
                                ticker=order["ticker"],
                                order_type=order["order_type"],
                                action=order["action"],
                                limit_price=order["limit_price"] / split_ratio,
                                time_in_force=order["time_in_force"],
                                quantity=order["quantity"] * split_ratio,
                                stop_price=order["stop_price"] / split_ratio,
                                trail_type=order["trail_type"],
                                trail=(
                                    order["trail"]
                                    if order["trail_type"] == constants.TRAIL_TYPE_PERCENTAGE
                                    else order["trail"] / split_ratio
                                ),
                                status="",
                            )
                        )

    def backtest(self):
        # Create StockEntity for each stock and store in the stocks dictionary
        self.initialize_stocks()

        # Set all attached order with status False status to Pending
        self.order_book.loc[(self.order_book["attached_order"] == False), "status"] = constants.ORDER_STATUS_PENDING

        # Load stock split data
        unique_stocks = self.order_book.ticker.unique().tolist()
        stock_split_data = get_split_data(unique_stocks)

        for current_timestamp, row in tqdm(self.ohlvc.iterrows(), total=len(self.ohlvc)):
            # Convert current_timestamp to pd.Timestamp type
            current_timestamp = typing.cast(pd.Timestamp, current_timestamp)

            # Fetch all pending orders that are earlier or equal to the current timestamp and status not filled or cancelled
            active_orders = self.get_active_orders(current_timestamp)

            # Check if there is a stock split event happening
            stock_split = stock_split_data[stock_split_data["date"] == current_timestamp]

            if len(stock_split) != 0:
                # Update stock entity for stock split
                for _, split in stock_split.iterrows():
                    self.adjust_stock_entity_for_splits(split)

                # Update order_book for the stock entities w stock split to adjust for price n qty
                for idx, order in active_orders.iterrows():
                    self.adjust_order_for_splits(
                        stock_split=stock_split, order=order, idx=idx, current_timestamp=current_timestamp
                    )

            # Fetch updated active orders
            active_orders = self.get_active_orders(current_timestamp)

            # Using while loop because there are additional orders created and appended into the active_orders df
            while len(active_orders) != 0:
                idx = active_orders.head(1).index[0]
                order = active_orders.loc[idx]

                # Fetch Order Details
                order_id = order["order_id"]
                date = order["order_date"]
                symbol = order["ticker"]
                order_type = order["order_type"]
                action = order["action"]
                limit_price = order["limit_price"]
                limit_offset = order["limit_offset"]
                stop_price = order["stop_price"]
                quantity = order["quantity"]
                trail_type = order["trail_type"]
                trail = order["trail"]
                time_in_force = order["time_in_force"]
                attached_order = order["attached_order"]
                order_status = False
                msg = ""
                filled_price = 0.0
                stock_entity = self.stocks[symbol]

                """
                Unattached Order: Orders that are sent to the market without any attached orders
                Example: 
                1. Long Position: BUY 100 AAPL @ 150
                2. Short Position: SELL 100 AAPL @ 170
                
                Attached Order: Orders that are tagged to an order to act like the stop loss / take profit orders
                Example:
                1. BUY 100 AAPL @ 150 (Unattached Order)
                2. Attached a sell order to the BUY order to sell 100 AAPL @ 170 (Attached Order)
                3. Attached a stop limit order to the BUY order to create a limit order of 125 when price goes under 130 (Attached Order)
                    a. When price reaches 130 --> Stop Limit Order is triggered and a Stop Limit order is created @ 125
                    b. When price reaches 125 --> Stop Limit Order is executed
                """

                if attached_order:
                    # If it is a Day order, check if the order is still valid
                    if time_in_force == constants.TIME_IN_FORCE_DAY:
                        if current_timestamp.date() != order["order_date"].date():
                            self.order_book.loc[idx, "status"] = constants.ORDER_STATUS_EXPIRED
                            self.order_book.loc[idx, "comments"] = "Order Expired"
                            self.order_book.loc[idx, "filled_date"] = current_timestamp
                            continue

                    if order_type == constants.LIMIT_ORDER:
                        filled_price = limit_price
                        order_status, msg = stock_entity.limit_order(
                            trade=Trade(
                                date=current_timestamp.strftime(format="%Y-%m-%d %H:%M:%S"),
                                symbol=symbol,
                                order_type=order_type,
                                action=action,
                                limit_price=limit_price,
                                quantity=quantity,
                                fees=self.calculate_fees(qty=quantity, price_per_share=filled_price),
                            ),
                            high_price=row[symbol]["High"],
                            low_price=row[symbol]["Low"],
                        )
                    elif order_type == constants.MARKET_ORDER:
                        filled_price = row[symbol]["Open"]
                        order_status, msg = stock_entity.market_order(
                            trade=Trade(
                                date=current_timestamp.strftime(format="%Y-%m-%d %H:%M:%S"),
                                symbol=symbol,
                                order_type=order_type,
                                action=action,
                                limit_price=row[symbol]["Open"],  # Use Open price as the limit price for Market Order
                                quantity=quantity,
                                fees=self.calculate_fees(qty=quantity, price_per_share=filled_price),
                            )
                        )
                    elif order_type in constants.STOP_LOST_TRIGGERS:
                        if action == constants.TRADE_ACTION_BUY:
                            if order_type in [constants.TRAILING_STOP_ORDER, constants.TRAILING_STOP_LIMIT_ORDER]:
                                new_stop_price = min(
                                    self.update_trailing_stop_price(
                                        trail_type=trail_type, trail=trail, action=action, price=row[symbol]["High"]
                                    ),
                                    stop_price,
                                )
                                new_limit_price = new_stop_price + limit_offset  # Limit Price = Stop Price - Limit Offset
                                self.order_book.at[idx, "stop_price"] = new_stop_price
                                self.order_book.at[idx, "limit_price"] = new_limit_price
                                # Update Active Orders stop and limit price
                                active_orders.loc[idx, "stop_price"] = new_stop_price
                                active_orders.loc[idx, "limit_price"] = new_limit_price

                            if self.stop_loss_trigger(stop_price=stop_price, action=action, price=row[symbol]["High"]):
                                print(f"{order_type} Triggered for idx: {idx}")
                                self.create_limit_order(
                                    Order(
                                        order_id=order_id,
                                        attached_order=True,
                                        order_date=current_timestamp.strftime(format="%Y-%m-%d %H:%M:%S"),
                                        ticker=symbol,
                                        order_type=constants.LIMIT_ORDER,
                                        action=constants.TRADE_ACTION_BUY,
                                        limit_price=limit_price,
                                        time_in_force=constants.TIME_IN_FORCE_GTC,  # Defaults to GTC order for now
                                        quantity=quantity,
                                        status=constants.ORDER_STATUS_PENDING,
                                    )
                                )
                                # Update the status of the current order to "Filled"
                                self.order_book.loc[idx, "status"] = constants.ORDER_STATUS_FILLED
                                self.order_book.loc[idx, "filled_date"] = current_timestamp
                                self.order_book.loc[idx, "filled_price"] = stop_price
                                new_order = self.order_book.tail(1)
                                active_orders = pd.concat([active_orders, new_order])

                        else:
                            if order_type in [constants.TRAILING_STOP_ORDER, constants.TRAILING_STOP_LIMIT_ORDER]:
                                # TODO: check if we need to see if it is triggered on the same day or not
                                new_stop_price = max(
                                    self.update_trailing_stop_price(
                                        trail_type=trail_type, trail=trail, action=action, price=row[symbol]["High"]
                                    ),
                                    stop_price,
                                )
                                new_limit_price = new_stop_price - limit_offset  # Limit Price = Stop Price - Limit Offset

                                # Update Order Book stop and limit price
                                self.order_book.at[idx, "stop_price"] = new_stop_price
                                self.order_book.at[idx, "limit_price"] = new_limit_price
                                # Update Active Orders stop and limit price
                                active_orders.loc[idx, "stop_price"] = new_stop_price
                                active_orders.loc[idx, "limit_price"] = new_limit_price

                            if self.stop_loss_trigger(stop_price=stop_price, action=action, price=row[symbol]["Low"]):
                                print(f"{order_type} Triggered for idx: {idx}")
                                self.create_limit_order(
                                    Order(
                                        order_id=order_id,
                                        attached_order=True,
                                        order_date=current_timestamp.strftime(format="%Y-%m-%d %H:%M:%S"),
                                        ticker=symbol,
                                        order_type=constants.LIMIT_ORDER,
                                        action=constants.TRADE_ACTION_SELL,
                                        limit_price=limit_price,
                                        time_in_force=constants.TIME_IN_FORCE_GTC,  # Defaults to GTC order for now
                                        quantity=quantity,
                                        status=constants.ORDER_STATUS_PENDING,
                                    )
                                )
                                # Update the status of the current order to "Filled"
                                self.order_book.loc[idx, "status"] = constants.ORDER_STATUS_FILLED
                                self.order_book.loc[idx, "filled_date"] = current_timestamp
                                self.order_book.loc[idx, "filled_price"] = stop_price
                                # Append the new order to the active orders df
                                new_order = self.order_book.tail(1)
                                active_orders = pd.concat([active_orders, new_order])

                    # Check if attached order is filled
                    if order_status:
                        print("Order Filled for idx: ", idx)
                        self.order_book.loc[idx, "status"] = constants.ORDER_STATUS_FILLED
                        self.order_book.loc[idx, "filled_date"] = current_timestamp
                        self.order_book.loc[idx, "filled_price"] = filled_price
                        # Find index of the other attached_order with the same order id and update status to cancelled
                        attached_order_idx_list = self.order_book[
                            (self.order_book["order_id"] == order_id)
                            & (self.order_book["status"] == constants.ORDER_STATUS_PENDING)
                        ].index.tolist()
                        if len(attached_order_idx_list) != 0:
                            for order_idx in attached_order_idx_list:
                                self.order_book.loc[order_idx, "status"] = constants.ORDER_STATUS_CANCELLED
                                self.order_book.loc[order_idx, "comments"] = "Attached Order Cancelled"
                                self.order_book.loc[order_idx, "filled_date"] = current_timestamp

                        # Update Capital and fees
                        fees_incurred = self.calculate_fees(qty=quantity, price_per_share=filled_price)
                        if action == constants.TRADE_ACTION_BUY:
                            self.current_capital -= filled_price * quantity
                            self.current_capital -= fees_incurred
                        else:
                            self.current_capital += filled_price * quantity
                            self.current_capital -= fees_incurred
                        self.fees += fees_incurred

                else:
                    # If it is a Day order, check if the order is still valid
                    if time_in_force == constants.TIME_IN_FORCE_DAY:
                        if current_timestamp.date() != order["order_date"].date():
                            self.order_book.loc[idx, "status"] = constants.ORDER_STATUS_EXPIRED
                            self.order_book.loc[idx, "comments"] = "Order Expired"
                            self.order_book.loc[idx, "filled_date"] = current_timestamp
                            print("Order Expired for idx: ", idx)
                            continue

                        if order_type == constants.LIMIT_ORDER:
                            filled_price = limit_price
                            order_status, msg = stock_entity.limit_order(
                                trade=Trade(
                                    date=current_timestamp.strftime(format="%Y-%m-%d %H:%M:%S"),
                                    symbol=symbol,
                                    order_type=order_type,
                                    action=action,
                                    limit_price=limit_price,
                                    quantity=quantity,
                                    fees=self.calculate_fees(qty=quantity, price_per_share=filled_price),
                                ),
                                high_price=row[symbol]["High"],
                                low_price=row[symbol]["Low"],
                            )
                        elif order_type == constants.MARKET_ORDER:
                            filled_price = row[symbol]["Open"]
                            order_status, msg = stock_entity.market_order(
                                trade=Trade(
                                    date=current_timestamp.strftime(format="%Y-%m-%d %H:%M:%S"),
                                    symbol=symbol,
                                    order_type=order_type,
                                    action=action,
                                    limit_price=row[symbol]["Open"],  # Use Open price as the limit price
                                    quantity=quantity,
                                    fees=self.calculate_fees(qty=quantity, price_per_share=filled_price),
                                )
                            )
                        if order_status:
                            print("Order Filled for idx: ", idx)
                            self.order_book.loc[idx, "status"] = constants.ORDER_STATUS_FILLED
                            self.order_book.loc[idx, "filled_date"] = current_timestamp
                            self.order_book.loc[idx, "filled_price"] = filled_price
                            # Find the attached orders and mark the status and pending
                            attached_order_idx_list = self.order_book[
                                (self.order_book["order_id"] == order_id)
                                & (self.order_book.index != idx)
                                & (self.order_book["status"] == "")
                            ].index.tolist()
                            if len(attached_order_idx_list) != 0:
                                # Send all the attached orders to "Pending"
                                for order_idx in attached_order_idx_list:
                                    self.order_book.loc[order_idx, "status"] = constants.ORDER_STATUS_PENDING
                                    self.order_book.loc[order_idx, "order_date"] = current_timestamp
                                    # Add orders into active_orders to check if limit or stop loss orders triggered on the same day
                                    new_order = self.order_book.loc[[order_idx]]
                                    active_orders = pd.concat([active_orders, new_order])

                            # Update Capital and fees
                            fees_incurred = self.calculate_fees(qty=quantity, price_per_share=filled_price)
                            if action == constants.TRADE_ACTION_BUY:
                                self.current_capital -= filled_price * quantity
                                self.current_capital -= fees_incurred
                            else:
                                self.current_capital += filled_price * quantity
                                self.current_capital -= fees_incurred
                            self.fees += fees_incurred

                        else:
                            self.order_book.loc[idx, "status"] = constants.ORDER_STATUS_CANCELLED
                            self.order_book.loc[idx, "comments"] = msg
                            self.order_book.loc[idx, "filled_date"] = current_timestamp
                            # Cancel the attached orders
                            attached_order_idx_list = self.order_book[
                                (self.order_book["order_id"] == order_id) & (self.order_book.index != idx)
                            ].index.tolist()
                            if len(attached_order_idx_list) != 0:
                                # Send all the attached orders to "Cancelled"
                                for order_idx in attached_order_idx_list:
                                    self.order_book.loc[order_idx, "status"] = constants.ORDER_STATUS_CANCELLED
                                    self.order_book.loc[order_idx, "filled_date"] = current_timestamp
                                    self.order_book.loc[order_idx, "comments"] = "Original Order Cancelled"

                    elif time_in_force == constants.TIME_IN_FORCE_GTC:
                        if order_type == constants.LIMIT_ORDER:
                            if order_type == constants.LIMIT_ORDER:
                                filled_price = limit_price
                                order_status, msg = stock_entity.limit_order(
                                    trade=Trade(
                                        date=current_timestamp.strftime(format="%Y-%m-%d %H:%M:%S"),
                                        symbol=symbol,
                                        order_type=order_type,
                                        action=action,
                                        limit_price=limit_price,
                                        quantity=quantity,
                                        fees=self.calculate_fees(qty=quantity, price_per_share=filled_price),
                                    ),
                                    high_price=row[symbol]["High"],
                                    low_price=row[symbol]["Low"],
                                )
                            elif order_type == constants.MARKET_ORDER:
                                filled_price = row[symbol]["Open"]
                                order_status, msg = stock_entity.market_order(
                                    trade=Trade(
                                        date=current_timestamp.strftime(format="%Y-%m-%d %H:%M:%S"),
                                        symbol=symbol,
                                        order_type=order_type,
                                        action=action,
                                        limit_price=row[symbol]["Open"],  # Use Open price as the limit price
                                        quantity=quantity,
                                        fees=self.calculate_fees(qty=quantity, price_per_share=filled_price),
                                    )
                                )
                        if order_status:
                            print("Order Filled for idx: ", idx)
                            self.order_book.loc[idx, "status"] = constants.ORDER_STATUS_FILLED
                            self.order_book.loc[idx, "filled_date"] = current_timestamp
                            self.order_book.loc[idx, "filled_price"] = filled_price
                            # Find the attached orders and mark the status and pending
                            attached_order_idx_list = self.order_book[
                                (self.order_book["order_id"] == order_id)
                                & (self.order_book.index != idx)
                                & (self.order_book["status"] == "")
                            ].index.tolist()
                            if len(attached_order_idx_list) != 0:
                                for order_idx in attached_order_idx_list:
                                    self.order_book.loc[order_idx, "status"] = constants.ORDER_STATUS_PENDING
                                    self.order_book.loc[order_idx, "order_date"] = current_timestamp

                            # Update Capital and fees
                            fees_incurred = self.calculate_fees(qty=quantity, price_per_share=filled_price)
                            if action == constants.TRADE_ACTION_BUY:
                                self.current_capital -= filled_price * quantity
                                self.current_capital -= fees_incurred
                            else:
                                self.current_capital += filled_price * quantity
                                self.current_capital -= fees_incurred
                            self.fees += fees_incurred

                # Remove row from df
                active_orders = active_orders.drop(index=idx)

            # Update Stock Records
            for ticker, stock_entity in self.stocks.items():
                stock_entity.update_holding_records(timestamp=current_timestamp, price=row[ticker]["Close"])

            # Update Portfolio Records
            self.update_portfolio_records(current_timestamp)

        # Combine all the positions from all stock entities and portfolio capital
        self.combine_holding_records()
