# Backtest Engine

Backtest Engine is a backtesting framework written in Python. Backtest Engine aims to decouple the strategies from the backtesting logic. Backtest Engine takes in various trade orders and performs backtesting

## Installation

Install the required packages from requirements.txt

```bash
pip install -r requirements.txt
```

## Usage

```python
import pandas as pd
import yfinance as yf

from src.backtest_engine import BacktestEngine

# Read Trade Order Data
trade_orders = pd.read_csv("src/data_store/order_input/aapl_demo_trade_order_v2.csv")

# Convert the 'order_date' column to datetime
trade_orders["order_date"] = pd.to_datetime(trade_orders["order_date"], format="%Y-%m-%d")

# Fetching data for three stocks
symbols = ["AAPL", "GOOGL", "MSFT"]
dfs = []

# Fetch and store each stock's data in a DataFrame
for symbol in symbols:
    # df = yf.download(symbol, start="2022-09-01", end="2022-10-01")
    df = yf.download(symbol, start="2022-01-01", end="2024-02-01")
    df.columns = pd.MultiIndex.from_product([[symbol], df.columns])
    dfs.append(df)

# Combine all DataFrames horizontally
df_combined = pd.concat(dfs, axis=1)

# No need volume

backtest_engine = BacktestEngine(
    order_book=trade_orders,
    ohlvc=df_combined,
    initial_capital=100000.0,
)

backtest_engine.backtest()
order_book = backtest_engine.order_book
order_book = order_book.sort_values(by=["order_id", "order_date"])
aapl = backtest_engine.stocks["AAPL"]
aapl_trades = aapl.trades

```
Additional Documentation: https://docs.google.com/document/d/13Vj3Qjgm4Ls_Qh6Sily42LoXTyEOJuWBn0nKeimbm5Y/edit
