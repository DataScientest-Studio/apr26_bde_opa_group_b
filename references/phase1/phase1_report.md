# Phase 1 Report — Data Discovery & Architecture

**Author:** Payal  
**Date:** May 2026  
**Branch:** Payal/dev  
**Phase deadline:** May 20, 2026

---

## 1. Overview

Phase 1 establishes the foundation for the CryptoBot system. Before writing a single line of database or pipeline code, we explored both Binance data sources — the REST API and the WebSocket stream — to understand exactly what data they provide, how it is structured, and what that means for storage design.

The core finding is that the two sources are fundamentally different in structure, frequency, and purpose. That difference directly drives the architectural decision to use two separate databases: **PostgreSQL** for historical data and **MongoDB** for live streaming data.

---

## 2. Data Source 1 — Binance REST API (Historical OHLCV)

### 2.1 What it provides

The REST API returns historical candlestick (kline) data. Each response is a list of candles, where every candle is a fixed-length array of 12 values.

**Endpoint:** `https://api.binance.com/api/v3/klines`  
**Parameters used:** `symbol`, `interval`, `startTime`, `endTime`, `limit`  
**No authentication required** for market data.

### 2.2 Raw response structure

```
[
  [
    1715385600000,        # open_time (Unix ms)
    "82210.07000000",     # open
    "82380.00000000",     # high
    "80462.97000000",     # low
    "81745.65000000",     # close
    "12951.76000000",     # volume
    1715471999999,        # close_time (Unix ms)
    "1058234567.00",      # quote_asset_volume
    2576396,              # number_of_trades
    "6123.45000000",      # taker_buy_base_volume
    "501234567.00",       # taker_buy_quote_volume
    "0"                   # ignore (reserved, always 0)
  ],
  ...
]
```

### 2.3 Key findings from notebook 01

| Finding | Detail |
|---|---|
| Earliest available candle | 2017-08-17 (BTCUSDT) |
| Maximum candles per request | 1,000 |
| Candle state | Always closed and final |
| Null values found | None — all 12 fields always populated |
| Gaps between candles | None detected — `open_time[n+1] == close_time[n] + 1ms` |
| Price precision | Up to 8 decimal places (e.g., `80959.99000000`) |

### 2.4 Field decisions

| Field | Decision | Reason |
|---|---|---|
| open_time | KEEP | Candle start — part of primary key |
| open, high, low, close | KEEP | Core ML features |
| volume | KEEP | Market activity signal |
| close_time | KEEP | Used to verify no gaps between candles |
| number_of_trades | KEEP | Activity signal independent of volume |
| quote_asset_volume | DROP | Derivable from volume × close — redundant |
| taker_buy_base_volume | DROP | Advanced order flow — not needed for basic ML |
| taker_buy_quote_volume | DROP | Redundant with above |
| ignore | DROP | Always 0 — no information value |

### 2.5 Why PostgreSQL

The REST API produces fixed, structured, batch data:
- Schema never changes — 12 fields, same format every time
- Written once per day (batch, not real-time)
- Consumed by an ML model that runs SQL queries ordered by time
- Requires no gaps and exact numeric precision for price data

PostgreSQL enforces a fixed schema, supports `NUMERIC(18,8)` for exact decimal storage, and handles ordered time-series queries efficiently with an index.

---

## 3. Data Source 2 — Binance WebSocket (Live Streaming)

### 3.1 What it provides

The WebSocket stream delivers live candlestick updates as they form, in real time. Binance sends a new message approximately every second for each active candle.

**URL pattern:** `wss://stream.binance.com:9443/ws/{symbol}@kline_{interval}`  
**Example:** `wss://stream.binance.com:9443/ws/btcusdt@kline_1m`  
**No authentication required.**

### 3.2 Raw message structure

```json
{
  "e": "kline",
  "E": 1778658166016,
  "s": "BTCUSDT",
  "k": {
    "t": 1778658120000,
    "T": 1778658179999,
    "s": "BTCUSDT",
    "i": "1m",
    "f": 6291460573,
    "L": 6291461134,
    "o": "80959.99000000",
    "c": "80960.02000000",
    "h": "80969.39000000",
    "l": "80959.99000000",
    "v": "6.26052000",
    "n": 562,
    "x": false,
    "q": "506893.82132750",
    "V": "1.43291000",
    "Q": "116015.31284260",
    "B": "0"
  }
}
```

Binance uses single-letter keys (`"o"`, `"c"`, `"x"`) to reduce WebSocket payload size. The message has two layers — an outer event envelope and an inner `"k"` kline payload.

### 3.3 Key findings from notebook 02

| Finding | Detail |
|---|---|
| Message frequency | ~1 message per second per symbol |
| Key format | Single-letter (compressed) — must be decoded |
| Candle state | `is_candle_closed=False` while forming, `True` when final |
| Data freshness | Close price updates every tick while candle is open |
| Schema flexibility | New fields could be added by Binance without notice |

### 3.4 The `is_candle_closed` field — critical behaviour

During one minute, Binance sends ~60 tick messages for the same candle. The close price, volume, and trade count all update with each tick.

```
Tick 1: close=80960.02  is_candle_closed=False   ← candle still forming
Tick 2: close=80960.02  is_candle_closed=False
Tick 3: close=80960.02  is_candle_closed=False
Tick 4: close=80960.01  is_candle_closed=False   ← price changed
Tick 5: close=80963.92  is_candle_closed=False
...
Tick 60: close=80971.44  is_candle_closed=True   ← candle is now final
```

This means:
- The **live dashboard** should show all ticks — users want to see the current price as it moves
- The **ML pipeline** should only read ticks where `is_candle_closed=True` — otherwise it trains on incomplete data

### 3.5 Parsed document structure (what MongoDB stores)

The `parse_tick()` function decodes single-letter keys and flattens the nested structure:

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

### 3.6 Why MongoDB

The WebSocket produces flexible, high-frequency, semi-structured data:
- New message every second — PostgreSQL row inserts at this rate are expensive
- Schema may evolve — Binance may add fields without notice
- JSON documents map naturally to the raw message structure
- Dashboard consumers query by symbol and time, not by joining tables

MongoDB handles high write rates natively, stores flexible JSON without migrations, and is the standard choice for real-time tick data.

---

## 4. REST API vs WebSocket — Field Comparison

Both sources share the same core OHLCV fields. They differ in metadata:

| Field | REST API | WebSocket | Notes |
|---|---|---|---|
| open | ✓ | ✓ | |
| high | ✓ | ✓ | |
| low | ✓ | ✓ | |
| close | ✓ | ✓ | |
| volume | ✓ | ✓ | |
| number_of_trades | ✓ | ✓ | |
| open_time / kline_start_time | ✓ | ✓ | Different field names |
| close_time / kline_close_time | ✓ | ✓ | Different field names |
| symbol | — | ✓ | REST: passed as query param |
| event_time | — | ✓ | When Binance sent the message |
| interval | — | ✓ | Which stream this tick came from |
| is_candle_closed | — | ✓ | Critical — False = still forming |
| quote_asset_volume | ✓ | — | Dropped from both schemas |
| taker_buy_base_volume | ✓ | — | Dropped from both schemas |
| taker_buy_quote_volume | ✓ | — | Dropped from both schemas |
| ignore | ✓ | ✓ | Dropped from both schemas |

---

## 5. Architecture Decision

```
Binance REST API  ──►  Data Cleaning  ──►  PostgreSQL (ohlcv_data)  ──►  ML Model Training
                                                                     ──►  FastAPI /charts

Binance WebSocket ──►  Data Cleaning  ──►  MongoDB (live_ticks)     ──►  FastAPI /stream
                                                                     ──►  Streamlit dashboard
```

**Airflow** orchestrates the REST → PostgreSQL pipeline on a `@daily` schedule. It reads the latest timestamp from PostgreSQL to know where to resume, then triggers a REST API fetch to fill any gap since the last run.

All internal services run inside **Docker Compose**, giving reproducible, one-command startup across all team environments.

---

## 6. Database Schemas

### PostgreSQL — `ohlcv_data`

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

**Primary key `(symbol, open_time)`** — a candle is uniquely identified by its trading pair and its start time. This prevents duplicate inserts if Airflow retries.

**`NUMERIC(18,8)` for prices** — Binance returns 8 decimal places. `FLOAT` would introduce rounding errors. `NUMERIC` is exact.

### MongoDB — `live_ticks`

```python
collection.create_index([("symbol", 1), ("kline_start_time", -1)])
```

Documents use the flat 12-field structure from `parse_tick()`. No nesting — flat documents are simpler to query and index. The `is_candle_closed` field lets consumers choose whether to read all ticks or only final candles.

---

## 7. Symbols in Scope

| Symbol | Exchange Pair | Data available from |
|---|---|---|
| BTCUSDT | Bitcoin / USD Tether | 2017-08-17 |
| ETHUSDT | Ethereum / USD Tether | ~2017-08 |

Both symbols use the same schema. The `symbol` column / field distinguishes rows and documents.

---

## 8. Phase 1 Deliverables — Status

| Deliverable | Status |
|---|---|
| `notebooks/01_binance_exploration.ipynb` | Complete |
| `notebooks/02_websocket_exploration.ipynb` | Complete |
| `src/params/constants.py` | Complete |
| `src/params/enums.py` | Complete |
| `src/utils/time_utils.py` | Complete |
| `src/utils/dataframe_utils.py` | Complete |
| `references/phase1/schema_design.md` | Complete |
| `references/architecture_diagram.html` | Complete |
| `references/phase1/phase1_report.md` | This document |
