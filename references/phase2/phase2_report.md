# Phase 2 Report — Data Consumption & API

**Author:** Payal
**Date:** June 2026
**Branch:** Payal/dev
**Phase deadline:** June 10, 2026

---

## 1. Overview

Phase 1 was design work: we explored both Binance data sources and *designed* two schemas on paper. Phase 2 turns those designs into **running code** — two independent data pipelines that ingest real market data into two databases, an ML model that forecasts the next candle, and a FastAPI layer that exposes everything.

The system is built around **two pipelines that converge at a single API layer**:

```
Binance REST API   ──► clean ──► PostgreSQL (ohlcv_data)   ──► ML training ──► model.pkl
                                                            ──► FastAPI /charts

Binance WebSocket  ──► Path A (every tick) ──────────────────► FastAPI /stream  ──► live chart
                   ──► Path B (on candle close) ──► MongoDB (closed_candles) ──► ML predict ──► FastAPI /predict
```

See `references/phase2/architecture_diagram.png` for the full diagram.

---

## 2. Batch Pipeline — REST API → PostgreSQL

### 2.1 Collector — `src/collection/fetch_historical.py`

Fetches historical candlestick data from the Binance REST `klines` endpoint and stores it in PostgreSQL.

Key behaviours:
- **Pagination** — Binance returns a maximum of 1,000 candles per request. The collector loops, advancing `startTime` to `last_candle.close_time + 1ms` each round, until a partial page (< 1,000 rows) signals the present has been reached.
- **Resume / incremental load** — before fetching, `get_last_close_ms(symbol)` reads `MAX(close_time)` from PostgreSQL. If data exists, fetching resumes 1ms after the last stored candle; if the table is empty, it falls back to `HISTORICAL_START_DATE`. This makes the same script usable for both the first backfill and daily top-ups.
- **Idempotency** — inserts use `ON CONFLICT (symbol, open_time) DO NOTHING`, so re-runs and overlapping ranges never create duplicates.

### 2.2 Storage decision — PostgreSQL

The REST API produces fixed, structured, batch data with a stable schema, consumed by SQL queries ordered by time. PostgreSQL enforces the schema, supports `NUMERIC(18,8)` for exact decimal prices, and serves ordered time-series queries efficiently via an index.

### 2.3 Result

239,610 one-minute BTC/USDT candles loaded, covering 2026-01-01 → present, with **0 gaps** confirmed by the verification notebook.

---

## 3. Stream Pipeline — WebSocket → MongoDB

### 3.1 Consumer — `src/collection/stream_live.py`

Connects to the Binance combined WebSocket stream and reacts to each message. Unlike the batch collector, it does not loop-and-pull — Binance *pushes* a message roughly every second.

The consumer produces **two paths** (per the architecture):
- **Path A (every tick):** every message is forwarded to FastAPI `/stream` → the live chart. Not persisted — it only drives the real-time display.
- **Path B (on candle close):** when `is_candle_closed == True`, the completed candle is written to MongoDB.

`parse_tick()` decodes Binance's single-letter keys (`o`, `c`, `x`, …) into a flat, readable document and reuses `ms_to_timestamp()` so live and historical timestamps are produced identically.

### 3.2 Storage decision — MongoDB

The WebSocket produces high-frequency, semi-structured data. MongoDB handles high write rates, stores flexible JSON without migrations, and is queried by symbol and time rather than by joins. The `closed_candles` collection holds only **completed** candles (Path B).

### 3.3 Idempotency

A **unique index** on `(symbol, kline_start_time)` plus an **upsert** in `save_closed_candle()` give MongoDB the same guarantee PostgreSQL gets from its primary key: a re-sent candle updates in place rather than duplicating.

---

## 4. Storage Layer (`src/storage/`)

| File | Responsibility |
|---|---|
| `postgres.py` | SQLAlchemy `engine` from `.env`; fail-fast if credentials missing |
| `mongo.py` | `MongoClient` from `.env` (with `authSource=admin`); fail-fast |
| `schema.sql` | DDL for `ohlcv_data` (table + index), idempotent (`IF NOT EXISTS`) |
| `init_db.py` | Initialises **both** databases: applies `schema.sql` + creates the Mongo unique index |
| `postgres_writer.py` | `save_to_postgres` (upsert) + `get_last_close_ms` (resume) |
| `mongo_writer.py` | `save_closed_candle` (upsert on the unique key) |

Both connection modules **fail fast at import time** if any credential is absent, raising a clear `EnvironmentError` instead of building a `None`-filled connection string.

---

## 5. ML Layer (`src/`)

Kept deliberately simple — accuracy is not the project's goal; the pipeline wiring is.

- **`features/build_features.py`** — shared feature definition (`FEATURE_COLUMNS`, `make_features`, `make_target`). Used by **both** train and predict so the model is always trained and queried with the identical columns. `make_target` = `close.shift(-1)` (the next candle's close).
- **`models/train_model.py`** — reads historical candles from PostgreSQL → `LinearRegression` → saves `models/model.pkl` (via `joblib`). Trained on 239,609 rows.
- **`models/predict_model.py`** — loads `model.pkl`, pulls the latest completed candle from MongoDB, and predicts the next candle's close (single-candle model, N=1).

**Forecast logic:** the model learns "given candle *i*'s features → candle *i+1*'s close." Feeding the latest closed candle produces a prediction for the candle that is about to form — shown on the chart *before* the real value arrives, enabling a live predicted-vs-actual comparison.

---

## 6. API Layer — FastAPI (`src/api/main.py`)

The convergence point of both pipelines.

| Endpoint | Source | Purpose |
|---|---|---|
| `GET /health` | — | liveness check |
| `GET /charts` | PostgreSQL | recent historical candles (chronological) |
| `GET /predict` | model.pkl + MongoDB | next-candle close forecast |
| `WS /stream` | Binance WebSocket | Path A — relay live ticks to the browser |

`/stream` is a WebSocket endpoint using the async `websockets` library so it does not block FastAPI's event loop. (WebSocket routes do not appear in the `/docs` Swagger page — OpenAPI only documents HTTP.) Run locally with `uvicorn src.api.main:app --reload`.

---

## 7. Configuration — single source of truth (`src/params/constants.py`)

Shared names live in one place and are imported everywhere, so a rename changes one line:

```python
SUPPORTED_SYMBOLS = [Symbol.BTCUSDT]   # ETHUSDT supported by schema, currently disabled
DEFAULT_REST_INTERVAL = Interval.ONE_MINUTE
DEFAULT_WS_INTERVAL   = Interval.ONE_MINUTE
POSTGRES_TABLE   = "ohlcv_data"
MONGO_COLLECTION = "closed_candles"
MODEL_FILENAME   = "model.pkl"
HISTORICAL_START_DATE = "01.01.2026T00:00"
```

---

## 8. Key Engineering Decisions

| Decision | Why |
|---|---|
| Resume from `MAX(close_time)`, not a fixed date | One script serves both first backfill and daily updates |
| `ON CONFLICT` / unique-index upsert on both DBs | Reruns and overlaps are safe — no duplicates |
| Store prices as `Decimal`, not `float` | `NUMERIC(18,8)` is exact; `float` would round (8-dp Binance prices) |
| MongoDB stores only **closed** candles | ML must not train on still-forming candles (`is_candle_closed`) |
| Streaming (WS) + batch (REST) together | WS is low-latency but lossy on disconnect; REST can backfill gaps → completeness |
| Published host port `5433` for Postgres | A native PostgreSQL install occupied `localhost:5432`; remapping avoided the conflict |
| Mongo URI needs `authSource=admin` | The root user lives in the `admin` DB; auth fails without it |
| Databases containerised, code from venv | DBs must persist; app code is iterated with `--reload`. API containerisation is Phase 4 |

---

## 9. Verification

| Notebook | Confirms |
|---|---|
| `notebooks/03_db_verification.ipynb` | PostgreSQL: 239,610 rows, 0 gaps, expected == actual |
| `notebooks/04_mongo_verification.ipynb` | MongoDB: candles stored, **0 duplicates** (proves unique index + upsert) |

API verified via `/docs` (HTTP endpoints) and a WebSocket client (`/stream`).

---

## 10. Phase 2 Deliverables — Status

| Deliverable | Status |
|---|---|
| `docker-compose.yml` — Postgres + Mongo (healthy) | Complete |
| Storage layer (`src/storage/`) | Complete |
| Batch collector with resume + idempotency | Complete |
| Stream consumer (Path A + Path B) | Complete |
| ML train + predict (`model.pkl`) | Complete |
| FastAPI (`/charts`, `/predict`, `/stream`, `/health`) | Complete |
| Verification notebooks (both DBs) | Complete |
| `references/phase2/phase2_report.md` | This document |

---
