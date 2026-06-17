import json

import pandas as pd
import websockets
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from sqlalchemy import text

from src.storage.postgres import engine
from src.params.constants import POSTGRES_TABLE, SUPPORTED_SYMBOLS, DEFAULT_WS_INTERVAL
from src.models.predict_model import predict_next_close
from src.utils.url_utils import build_stream_url
from src.collection.stream_live import parse_tick

app = FastAPI(title="CryptoBot API")

DEFAULT_SYMBOL = SUPPORTED_SYMBOLS[0].value


@app.get("/health")
def health():
    """Quick check that the API is running."""
    return {"status": "ok"}


@app.get("/charts")
def charts(symbol: str = DEFAULT_SYMBOL, limit: int = 100):
    """Recent historical candles from Postgres, oldest -> newest (for charting)."""
    query = text(
        f"SELECT * FROM {POSTGRES_TABLE} WHERE symbol = :s "
        f"ORDER BY open_time DESC LIMIT :n"
    )
    df = pd.read_sql(query, engine, params={"s": symbol, "n": limit})
    records = df.to_dict(orient="records")
    return records[::-1]  # reverse DESC fetch back into chronological order


@app.get("/predict")
def predict(symbol: str = DEFAULT_SYMBOL):
    """Predicted close of the next candle, from the latest candle in Mongo."""
    try:
        value = predict_next_close(symbol=symbol)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"symbol": symbol, "predicted_next_close": value}


@app.websocket("/stream")
async def stream(websocket: WebSocket):
    """Path A: relay every live tick from Binance straight to the browser."""
    await websocket.accept()
    url = build_stream_url(SUPPORTED_SYMBOLS, DEFAULT_WS_INTERVAL)
    try:
        async with websockets.connect(url) as binance:
            async for message in binance:                 # one message ~per second
                payload = json.loads(message)
                data = payload.get("data", payload)       # combined stream wraps in "data"
                candle = parse_tick(data["k"])
                await websocket.send_json(jsonable_encoder(candle))
    except WebSocketDisconnect:
        pass 