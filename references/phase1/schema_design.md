# Schema Design — CryptoBot Phase 1

**Author:** Payal Patel
**Date:** May 2026  
**Branch:** Payal/dev

---

## 1. Why Two Databases?

The CryptoBot system collects data from two different Binance sources that have fundamentally different characteristics:

| Characteristic | REST API (Historical) | WebSocket (Streaming) |
|---|---|---|
| Data type | Fixed 12-field candles | JSON events with nested payload |
| Candle state | Always closed and final | Can be in-progress (is_candle_closed=False) |
| Write frequency | Batch (once per day) | High frequency (every second) |
| Schema stability | Fixed forever | May evolve (new fields possible) |
| Consumer | ML model training | Live dashboard |

A single database cannot serve both well:
- PostgreSQL enforces a fixed schema and is optimised for structured queries — ideal for ML training
- MongoDB stores flexible JSON documents and handles high write rates — ideal for live ticks

---

## 2. PostgreSQL — Historical OHLCV Data

### Table name: `ohlcv_data`

### Column decisions (from notebook 01 field analysis)

| Column | Data Type | Decision | Reason |
|---|---|---|---|
| symbol | VARCHAR(20) | KEEP | Identifies the trading pair — part of primary key |
| open_time | TIMESTAMP | KEEP | Candle start — part of primary key, used for ordering |
| open | NUMERIC(18,8) | KEEP | ML feature |
| high | NUMERIC(18,8) | KEEP | ML feature — used for volatility calculation |
| low | NUMERIC(18,8) | KEEP | ML feature — used for volatility calculation |
| close | NUMERIC(18,8) | KEEP | ML feature — used to compute price change label |
| volume | NUMERIC(18,8) | KEEP | ML feature — market activity signal |
| close_time | TIMESTAMP | KEEP | Used to verify no gaps between consecutive candles |
| number_of_trades | INTEGER | KEEP | ML feature — activity signal independent of volume |
| quote_asset_volume | NUMERIC(18,8) | DROP | Redundant — volume in USD, derivable from volume × close |
| taker_buy_base_volume | NUMERIC(18,8) | DROP | Advanced order flow — not needed for basic ML model |
| taker_buy_quote_volume | NUMERIC(18,8) | DROP | Redundant with above |
| ignore | — | DROP | Reserved by Binance, always 0, no information value |

### SQL Schema

```sql
CREATE TABLE ohlcv_data (
    symbol            VARCHAR(20)    NOT NULL,
    open_time         TIMESTAMP      NOT NULL,
    open              NUMERIC(18,8)  NOT NULL,
    high              NUMERIC(18,8)  NOT NULL,
    low               NUMERIC(18,8)  NOT NULL,
    close             NUMERIC(18,8)  NOT NULL,
    volume            NUMERIC(18,8)  NOT NULL,
    close_time        TIMESTAMP      NOT NULL,
    number_of_trades  INTEGER        NOT NULL,

    PRIMARY KEY (symbol, open_time)
);

CREATE INDEX idx_ohlcv_symbol_time ON ohlcv_data (symbol, open_time DESC);
```

### Key design decisions

**Primary key: `(symbol, open_time)`**  
A candle is uniquely identified by its trading pair and its start time. Using a composite primary key enforces uniqueness and prevents duplicate inserts.

**Index on `(symbol, open_time DESC)`**  
The ML model queries data ordered by time for a specific symbol. This index makes that query fast even with years of data.

**`NUMERIC(18,8)` for prices**  
Binance returns prices with up to 8 decimal places (e.g. `80959.99000000`). `FLOAT` would introduce rounding errors. `NUMERIC` is exact.

### Example row

| symbol | open_time | open | high | low | close | volume | close_time | number_of_trades |
|---|---|---|---|---|---|---|---|---|
| BTCUSDT | 2026-05-11 00:00:00 | 82210.07 | 82380.00 | 80462.97 | 81745.65 | 12951.76 | 2026-05-11 23:59:59 | 2576396 |

---

## 3. MongoDB — Live Streaming Ticks

### Collection name: `live_ticks`

### Document structure (from notebook 02 `parse_tick()`)

Raw Binance WebSocket messages use single-letter keys (e.g. `"o"`, `"c"`, `"x"`) compressed for speed. We decode and flatten them into a readable document before storing.

```json
{
  "symbol":           "BTCUSDT",
  "event_time":       "2026-05-13T07:42:46.016Z",
  "kline_start_time": "2026-05-13T07:42:00Z",
  "kline_close_time": "2026-05-13T07:42:59.999Z",
  "interval":         "1m",
  "open":             80959.99,
  "high":             80969.39,
  "low":              80959.99,
  "close":            80960.02,
  "volume":           6.26052,
  "number_of_trades": 562,
  "is_candle_closed": false
}
```

### Field decisions

| Field | Type | Decision | Reason |
|---|---|---|---|
| symbol | String | KEEP | Identifies the trading pair |
| event_time | DateTime | KEEP | When Binance sent the event — useful for latency tracking |
| kline_start_time | DateTime | KEEP | Candle start — used for ordering and querying |
| kline_close_time | DateTime | KEEP | Candle end — used to know when candle is complete |
| interval | String | KEEP | Documents which stream this tick came from |
| open | Double | KEEP | Price data |
| high | Double | KEEP | Price data |
| low | Double | KEEP | Price data |
| close | Double | KEEP | Current close — updates every tick |
| volume | Double | KEEP | Cumulative volume for this candle so far |
| number_of_trades | Integer | KEEP | Cumulative trades for this candle so far |
| is_candle_closed | Boolean | KEEP | Critical — False means candle is still updating, True means final |
| first_trade_id | Integer | DROP | Internal Binance trade ID — no value for this project |
| last_trade_id | Integer | DROP | Internal Binance trade ID — no value for this project |
| taker_buy volumes | Double | DROP | Advanced order flow — not needed for dashboard |
| ignore | — | DROP | Reserved by Binance, always 0 |

### Key design decisions

**Flat document structure — no nesting**  
Raw WebSocket messages have a nested `"k"` object. We flatten it before storing. Flat documents are simpler to query and index in MongoDB.

**`is_candle_closed` is critical**  
Binance sends a new tick every second while the candle is forming. `is_candle_closed=False` means the candle is still updating — values will change. `is_candle_closed=True` means the candle is final. The dashboard displays all ticks. The ML pipeline should only read closed candles.

### Recommended MongoDB index

```python
collection.create_index([("symbol", 1), ("kline_start_time", -1)])
```

---

## 4. Summary — How the Two Schemas Relate

```
Binance REST API  ──►  PostgreSQL (ohlcv_data)  ──►  ML Model Training
                                                 ──►  FastAPI /charts endpoint

Binance WebSocket ──►  MongoDB (live_ticks)      ──►  FastAPI /stream endpoint
                                                 ──►  Streamlit live dashboard
```

Both databases share the same core OHLCV fields (open, high, low, close, volume, number_of_trades).  
They differ in metadata: PostgreSQL tracks candle boundaries precisely; MongoDB tracks event timing and candle state.
