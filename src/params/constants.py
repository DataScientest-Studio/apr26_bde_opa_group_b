from src.params.enums import Interval, Symbol

# All symbols the system collects, stores, and predicts for
SUPPORTED_SYMBOLS = [Symbol.BTCUSDT, Symbol.ETHUSDT]

# REST API: daily candles for ML training
DEFAULT_REST_INTERVAL = Interval.ONE_DAY

# WebSocket: 1-minute ticks for live streaming dashboard
DEFAULT_WS_INTERVAL = Interval.ONE_MINUTE

# Binance REST API endpoint for historical OHLCV kline data
BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"

# WebSocket base URL — use build_ws_url() from src/utils/url_utils.py to get the full stream URL per symbol
BINANCE_WS_BASE_URL = "wss://stream.binance.com:9443/ws"

# The 12 fields returned by Binance per candle — order matches the API response exactly
BINANCE_KLINES_COLUMNS = [
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "quote_asset_volume",
    "number_of_trades",
    "taker_buy_base_volume",
    "taker_buy_quote_volume",
    "ignore"
]
