import pandas as pd

STOCK_DIVIDEND_DATA = "src/data_store/stock_data/dividend_data_02072024.parquet"
STOCK_SPLIT_DATA = "src/data_store/stock_data/stock_split_02072024.parquet"


def load_parquet_file(file_path):
    return pd.read_parquet(file_path)


def get_dividend_data(unique_tickers):
    stock_dividend_data = load_parquet_file(STOCK_DIVIDEND_DATA)
    stock_dividend_data = stock_dividend_data[stock_dividend_data["code"].isin(unique_tickers)]
    stock_dividend_data["date"] = pd.to_datetime(stock_dividend_data["date"])

    return stock_dividend_data


def get_split_data(unique_tickers):
    stock_split_data = load_parquet_file(STOCK_SPLIT_DATA)
    stock_split_data = stock_split_data[stock_split_data["code"].isin(unique_tickers)]
    stock_split_data["date"] = pd.to_datetime(stock_split_data["date"])

    return stock_split_data


# TODO: Add currency converter as some dividends are in JPY and SEK
