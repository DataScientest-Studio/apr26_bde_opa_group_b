# CryptoBot — Complete Application Flow

This document explains, step by step, **what happens when you run the whole
system** — both the **first time from scratch** and **every later run**.

> **How to view the diagrams:** the flowcharts below are written in **Mermaid**.
> They render automatically on **GitHub**. In **VS Code**, install the extension
> *“Markdown Preview Mermaid Support”* and open the Markdown preview (`Ctrl+Shift+V`).
> Even without rendering, every diagram is followed by a plain numbered explanation.

---

## 1. The components at a glance

| Component | Type | Job |
|---|---|---|
| **postgres** | always-on | Stores historical candles (`ohlcv_data`) — the **training** data |
| **mongodb** | always-on | Stores live closed candles (`closed_candles`) + forecasts (`predictions`) |
| **init** | one-shot | Creates the Postgres table + Mongo indexes, then exits |
| **historical** | one-shot | Backfills / catches up historical candles into Postgres, then exits |
| **streamer** | always-on | Live Binance WebSocket → writes closed candles to Mongo |
| **api** | always-on | FastAPI: `/charts`, `/predict`, `/predictions`, `/stream`, `/health` |
| **dashboard** | always-on | Streamlit UI (reads everything from the API) |
| **airflow** | always-on | Schedules the batch jobs (orchestration) |
| **model.pkl** | shared file | The trained model, on a shared volume (`train_model` writes, `api` reads) |

```mermaid
flowchart TD
    B["Binance API"]
    FH["fetch_historical<br/>(batch)"]
    SL["stream_live<br/>(always-on)"]
    PG[("PostgreSQL<br/>ohlcv_data")]
    MG[("MongoDB<br/>closed_candles + predictions")]
    MODEL["model.pkl<br/>(shared volume)"]
    API["FastAPI<br/>/charts /predict /predictions /stream"]
    DASH["Streamlit dashboard"]
    TRAIN["train_model"]
    AF["Airflow scheduler"]

    B -->|"REST klines"| FH --> PG
    B -->|"WebSocket"| SL --> MG
    PG --> API
    MG --> API
    MODEL --> API
    API --> DASH
    PG --> TRAIN --> MODEL
    AF -.->|"every 15 min"| FH
    AF -.->|"daily"| TRAIN
```

---

## 2. Where the data lives

| Store | Filled by | Read by | Notes |
|---|---|---|---|
| **PostgreSQL `ohlcv_data`** | `fetch_historical` (REST) | `/charts`, `train_model` | Training source; fixed schema |
| **MongoDB `closed_candles`** | `streamer` (WebSocket) | `/predict`, `/predictions` | Freshest closed candles |
| **MongoDB `predictions`** | `/predict` (each call) | `/predictions` | One forecast per target candle |
| **`model.pkl`** (volume) | `train_model` | `/predict` | Shared between Airflow + API |

---

## 3. ❄️ COLD START — first run, from scratch (empty volumes)

Command:

```bash
docker compose up --build
```

```mermaid
flowchart TD
    A["docker compose up --build"] --> B["Build images:<br/>cryptobot-app + cryptobot-airflow"]
    B --> C["Create network + empty volumes"]
    C --> D["Start postgres + mongodb (empty)"]
    D --> E{"DB healthchecks pass?"}
    E -->|"no - wait & retry"| E
    E -->|"yes"| F["init: CREATE TABLE + create indexes -> exit 0"]
    F --> G["historical: empty DB -> fetch ALL history -> exit"]
    F --> H["streamer: connect WebSocket -> write Mongo (forever)"]
    F --> I["api: serve endpoints"]
    I --> J["dashboard: Streamlit UI on :8501"]
    D --> K["airflow: standalone (UI on :8080)"]
```

**Step by step:**

1. **Build images.** Docker builds `cryptobot-app` (your code + runtime deps) and
   `cryptobot-airflow` (Airflow + Docker provider). Slow the first time.
2. **Create network + volumes.** `cryptobot_network`, and the empty volumes
   `postgres_data`, `mongo_data`, `cryptobot_models`, `airflow_data`.
3. **Start databases.** `postgres` and `mongodb` boot with **no data**.
4. **Wait for health.** Compose holds dependent services until `pg_isready` and
   Mongo `ping` succeed (the `condition: service_healthy` gates).
5. **`init` runs** (once healthy): creates the `ohlcv_data` table from `schema.sql`,
   and the unique indexes on `closed_candles` and `predictions`. Then **exits 0**.
6. **`historical` runs** (after init): reads `MAX(close_time)` from Postgres →
   **empty** → starts from `HISTORICAL_START_DATE` (Jan 1 2026) → paginates the
   Binance REST API (1000 candles/page) → saves to Postgres. This is the **long**
   one on a cold start (hundreds of thousands of candles). Then **exits**.
7. **`streamer` starts** (after init): opens the Binance WebSocket. Every time a
   1-minute candle **closes**, it upserts that candle into `closed_candles`.
   Runs forever (now with auto-reconnect).
8. **`api` starts** (after init): serves `/charts` (Postgres), `/predict` +
   `/predictions` (Mongo + model), `/stream` (live relay).
9. **`dashboard` starts** (after api): the Streamlit UI. Historical candles show
   immediately; the **live** candle and **prediction** appear within ~1–2 minutes
   (once the streamer has written the first closed candle to Mongo).
10. **`airflow` starts**: initializes its own SQLite metadata DB and launches the
    scheduler + UI. The two DAGs appear **paused** until you enable them.

> **Cold-start gotcha:** `/predict` returns *“unavailable”* until the streamer has
> saved at least one closed candle to Mongo (≈ 1 minute). That’s expected.

---

## 4. ♻️ WARM START — running again after some time (volumes kept)

Command (same one):

```bash
docker compose up        # add --build only if code changed
```

```mermaid
flowchart TD
    A["docker compose up"] --> C["Reuse existing network + volumes (data already there)"]
    C --> D["Start postgres + mongodb (with saved data)"]
    D --> E{"DB healthchecks pass?"}
    E -->|"yes"| F["init: IF NOT EXISTS / create_index -> no-op -> exit"]
    F --> G["historical: read MAX(close_time) -> fetch ONLY the gap -> exit (fast)"]
    F --> H["streamer: reconnect -> resume writing new closed candles"]
    F --> I["api: serve existing + new data"]
    I --> J["dashboard: shows full history immediately"]
    D --> K["airflow: resume scheduler (DAG history preserved)"]
```

**What’s different from a cold start:**

1. **No data loss.** `postgres_data` / `mongo_data` volumes still hold everything,
   so the databases come up **already populated**.
2. **`init` is a no-op.** `CREATE TABLE IF NOT EXISTS` and `create_index` are
   idempotent — they do nothing because the table/indexes already exist.
3. **`historical` is fast & incremental.** It reads `MAX(close_time)`, resumes
   **1 ms after the last stored candle**, and fetches **only the new candles**
   since the last run. Duplicates are impossible (`ON CONFLICT DO NOTHING`).
   → *This is what closes the “stale data gap” automatically.*
4. **`streamer` resumes.** It reconnects and continues writing new closed candles.
   (Candles that closed **while it was down** are not in Mongo — a known gap;
   auto-reconnect just keeps that window small.)
5. **`model.pkl` is already present** in the shared volume, so `/predict` works
   right away.
6. **Airflow keeps its history** (run logs, DAG on/off state) thanks to
   `airflow_data`.

---

## 5. Continuous runtime flows (always happening once up)

### 5a. Live streaming pipeline (every second)

```mermaid
flowchart LR
    BW["Binance WebSocket"] --> SL["stream_live"]
    SL -->|"is_candle_closed = true"| MG[("Mongo<br/>closed_candles")]
    BW --> API["API /stream"] --> DASH["Dashboard<br/>live candle"]
```

- The **streamer** persists a candle to Mongo **only when it closes**.
- The **dashboard** gets *every* tick live via the API’s `/stream` relay (a
  separate Binance connection) — that’s the candle forming in real time.

### 5b. Prediction lifecycle — how predicted-vs-actual is built

```mermaid
flowchart TD
    P1["/predict called (every ~1s by dashboard)"] --> P2["Read latest closed candle M from Mongo"]
    P2 --> P3["model.pkl predicts close of M+1"]
    P3 --> P4["Upsert prediction (target = M+1) into predictions"]
    M1["Minute M+1 later CLOSES"] --> M2["streamer writes closed_candles (kline_start_time = M+1)"]
    P4 --> J["/predictions JOINS prediction.target == closed_candle.time"]
    M2 --> J
    J --> R["actual_close fills in -> green line catches up to orange"]
```

1. `/predict` reads the **latest closed candle (M)**, forecasts **M+1’s close**,
   and **upserts** a prediction keyed on the target candle (so one row per candle).
2. Later, when **M+1 actually closes**, the streamer writes it to `closed_candles`.
3. `/predictions` **joins** each prediction to the matching actual candle → the
   dashboard shows predicted (orange) vs actual (green); the newest points have no
   actual yet (their candle hasn’t closed).

### 5c. Airflow scheduled automation

```mermaid
flowchart TD
    subgraph cryptobot_ingest["DAG: cryptobot_ingest (every 15 min)"]
      I1["DockerOperator -> cryptobot-app:<br/>python -m fetch_historical"] --> PG[("Postgres")]
    end
    subgraph cryptobot_train["DAG: cryptobot_train (daily)"]
      T1["fetch_historical"] --> T2["train_model"]
      T2 --> MODEL["model.pkl (shared volume)"]
    end
    MODEL --> API["API /predict reads the new model"]
```

- **`cryptobot_ingest`** keeps Postgres fresh every 15 minutes.
- **`cryptobot_train`** catches data up, then retrains the model daily. The new
  `model.pkl` lands on the shared volume → the API serves it on the next
  `/predict` (no restart needed).

---

## 6. Endpoint reference (what each one reads)

| Endpoint | Reads from | Used by |
|---|---|---|
| `GET /health` | — | dashboard health gate |
| `GET /charts` | PostgreSQL `ohlcv_data` | dashboard historical candles |
| `GET /predict` | Mongo `closed_candles` + `model.pkl` → writes `predictions` | dashboard metric + forecast marker |
| `GET /predictions` | Mongo `predictions` ⋈ `closed_candles` | dashboard predicted-vs-actual chart |
| `WS /stream` | Binance WebSocket (relay) | dashboard live candle |

---

## 7. Startup dependency order (who waits for whom)

```mermaid
flowchart LR
    PGc["postgres (healthy)"] --> init
    MGc["mongodb (healthy)"] --> init
    init -->|"completed"| historical
    init -->|"completed"| streamer
    init -->|"completed"| api
    api --> dashboard
    PGc --> airflow
    MGc --> airflow
```

---

## 8. Command cheat-sheet

```bash
docker compose up --build        # first run / after code changes
docker compose up -d             # later runs, in the background
docker compose logs -f api       # follow one service's logs
docker compose down              # stop everything (KEEPS data volumes)
docker compose down -v           # stop AND wipe volumes -> next run is a COLD start
```

| URL | What |
|---|---|
| http://localhost:8501 | Streamlit dashboard |
| http://localhost:8000/docs | FastAPI docs |
| http://localhost:8080 | Airflow UI |
