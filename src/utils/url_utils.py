from src.params.constants import BINANCE_WS_BASE_URL


def build_stream_url(symbols, interval):
    """Build a combined Binance WebSocket stream URL for several symbols.

    Example:
        wss://stream.binance.com:9443/stream?streams=btcusdt@kline_1m/ethusdt@kline_1m
    """
    streams = "/".join(f"{s.value.lower()}@kline_{interval.value}" for s in symbols)
    return f"{BINANCE_WS_BASE_URL}/stream?streams={streams}"
