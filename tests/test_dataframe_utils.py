from src.utils.dataframe_utils import raw_to_dataframe


def test_raw_to_dataframe_types_and_values():
    # one raw Binance kline row (12 fields, in API order)
    raw = [[
        0,        # open_time (ms)
        "100",    # open
        "110",    # high
        "90",     # low
        "105",    # close
        "12.5",   # volume
        59_999,   # close_time (ms)
        "0",      # quote_asset_volume
        42,       # number_of_trades
        "0",      # taker_buy_base_volume
        "0",      # taker_buy_quote_volume
        "0",      # ignore
    ]]
    df = raw_to_dataframe(raw)

    assert df.loc[0, "open"] == 100.0
    assert df.loc[0, "close"] == 105.0
    assert df.loc[0, "volume"] == 12.5
    assert df.loc[0, "number_of_trades"] == 42
    # ms timestamps are converted to real datetimes
    assert str(df.loc[0, "open_time"]) == "1970-01-01 00:00:00"
