from src.backtest_engine import BacktestEngine
import time
import pandas as pd

# pd.set_option("display.width", 320)
# pd.set_option("display.max_columns", None)


# Read Trade Order Data
trade_orders = pd.read_csv("src/data_store/order_input/aapl_demo_trade_order_v2.csv")

# Filter only for AAPL
trade_orders = trade_orders[trade_orders["ticker"] == "AAPL"]

# Convert the 'order_date' column to datetime
trade_orders["order_date"] = pd.to_datetime(trade_orders["order_date"], format="%Y-%m-%d")

trade_orders["limit_offset"] = trade_orders["limit_offset"].fillna(0.0)
trade_orders["limit_price"] = trade_orders["limit_price"].fillna(0.0)
trade_orders["stop_price"] = trade_orders["stop_price"].fillna(0.0)
trade_orders["trail_type"] = trade_orders["trail_type"].fillna("N.A.")
trade_orders["trail"] = trade_orders["trail"].fillna(0.0)

combined_eod = pd.read_csv("src/data_store/stock_data/aapl_nvda_eod.csv")

combined_eod["date"] = pd.to_datetime(combined_eod["date"])
combined_eod = combined_eod.sort_values(by=["date"])

# rename columns
combined_eod.rename(
    columns={
        "date": "date",
        "close": "Close",
        "adjusted_close": "Adj Close",
        "high": "High",
        "low": "Low",
        "open": "Open",
        "code": "code",
    },
    inplace=True,
)

dfs = []
aapl_eod = combined_eod[combined_eod["code"] == "AAPL"]
# set date as index
aapl_eod.set_index("date", inplace=True)
aapl_eod = aapl_eod.drop(columns=["code"])
aapl_eod.columns = pd.MultiIndex.from_product([["AAPL"], aapl_eod.columns])
dfs.append(aapl_eod)

nvda_eod = combined_eod[combined_eod["code"] == "NVDA"]
# set date as index
nvda_eod.set_index("date", inplace=True)
nvda_eod = nvda_eod.drop(columns=["code"])
nvda_eod.columns = pd.MultiIndex.from_product([["NVDA"], nvda_eod.columns])
dfs.append(nvda_eod)

# Combine all DataFrames horizontally
df_combined = pd.concat(dfs, axis=1)

# set index as timestamp
# df_combined.index = pd.to_datetime(df_combined.index)


backtest_engine = BacktestEngine(
    order_book=trade_orders,
    ohlvc=df_combined,
    initial_capital=100000.0,
)

start_time = time.time()

backtest_engine.backtest()

end_time = time.time()
print("Execution Time: ", end_time - start_time)

order_book = backtest_engine.order_book
order_book = order_book.sort_values(by=["order_id", "order_date", "attached_order"])
aapl = backtest_engine.stocks["AAPL"]
aapl_trades = aapl.trades
aapl_historical_records = aapl.holding_records

# googl = backtest_engine.stocks["GOOGL"]
# googl_trades = googl.trades
# googl_historical_records = googl.holding_records
portfolio_records = backtest_engine.combined_holding_records

# backtest_engine.generate_tear_down("results/teardown_report.html")
