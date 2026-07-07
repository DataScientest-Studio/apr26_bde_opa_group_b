from src.collection.stream_live import parse_tick


def test_parse_tick_decodes_kline_payload():
    # the inner 'k' object of a Binance kline WebSocket message
    k = {
        "s": "BTCUSDT",
        "t": 0,            # kline start time (ms)
        "T": 59_999,       # kline close time (ms)
        "i": "1m",
        "o": "100.0",
        "h": "110.0",
        "l": "90.0",
        "c": "105.0",
        "v": "12.5",
        "n": 42,
        "x": True,         # is_candle_closed
    }
    candle = parse_tick(k)

    assert candle["symbol"] == "BTCUSDT"
    assert candle["interval"] == "1m"
    assert candle["open"] == 100.0
    assert candle["high"] == 110.0
    assert candle["low"] == 90.0
    assert candle["close"] == 105.0
    assert candle["volume"] == 12.5
    assert candle["number_of_trades"] == 42
    assert candle["is_candle_closed"] is True
    # ms timestamps are converted to real datetimes
    assert str(candle["kline_start_time"]) == "1970-01-01 00:00:00"


def test_parse_tick_marks_forming_candle_open():
    k = {
        "s": "BTCUSDT", "t": 0, "T": 59_999, "i": "1m",
        "o": "1", "h": "1", "l": "1", "c": "1", "v": "1", "n": 1,
        "x": False,
    }
    assert parse_tick(k)["is_candle_closed"] is False
