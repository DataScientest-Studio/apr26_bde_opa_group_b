from src.storage.mongo import get_collection
from src.params.constants import MONGO_COLLECTION


def save_closed_candle(doc, collection_name=MONGO_COLLECTION):
    """Idempotently store one completed candle.

    Upsert keyed on (symbol, kline_start_time) — the same fields as the
    unique index. A re-inserted candle updates in place instead of
    creating a duplicate, mirroring Postgres' ON CONFLICT DO NOTHING.
    """
    collection = get_collection(collection_name)
    collection.update_one(
        {"symbol": doc["symbol"], "kline_start_time": doc["kline_start_time"]},
        {"$set": doc},
        upsert=True,
    )
