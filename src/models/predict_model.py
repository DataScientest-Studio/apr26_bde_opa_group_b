from pathlib import Path

import joblib
import pandas as pd

from src.storage.mongo import get_collection
from src.features.build_features import make_features
from src.params.constants import (
    SUPPORTED_SYMBOLS,
    MONGO_COLLECTION,
    MODEL_FILENAME,
)

MODEL_PATH = Path(__file__).resolve().parents[2] / "models" / MODEL_FILENAME
SYMBOL = SUPPORTED_SYMBOLS[0].value


def predict_next_close(symbol=SYMBOL, n=1):
    # 1. Load the trained model
    model = joblib.load(MODEL_PATH)

    # 2. Get the last N completed candles from Mongo (newest first)
    col = get_collection(MONGO_COLLECTION)
    docs = list(col.find({"symbol": symbol}).sort("kline_start_time", -1).limit(n))
    if not docs:
        raise ValueError("No candles in Mongo yet — run stream_live.py first.")

    # 3. Build the SAME features used in training, then predict
    df = pd.DataFrame(docs)
    X = make_features(df)
    prediction = model.predict(X)

    # Prediction for the most recent candle
    return float(prediction[0])


if __name__ == "__main__":
    print("Predicted next close:", predict_next_close())
