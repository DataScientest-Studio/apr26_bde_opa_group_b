from src.utils.url_utils import build_stream_url
from src.params.enums import Symbol, Interval


def test_build_stream_url_single_symbol():
    url = build_stream_url([Symbol.BTCUSDT], Interval.ONE_MINUTE)
    assert url.startswith("wss://")
    assert url.endswith("/stream?streams=btcusdt@kline_1m")


def test_build_stream_url_multiple_symbols():
    url = build_stream_url([Symbol.BTCUSDT, Symbol.ETHUSDT], Interval.ONE_MINUTE)
    assert "btcusdt@kline_1m/ethusdt@kline_1m" in url


def test_build_stream_url_uses_interval_value():
    url = build_stream_url([Symbol.BTCUSDT], Interval.FIFTEEN_MINUTES)
    assert "btcusdt@kline_15m" in url
