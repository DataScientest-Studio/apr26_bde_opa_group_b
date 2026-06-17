import sys
import os
from time import sleep, time_ns

sys.path.append(os.path.abspath(os.path.join(os.getcwd(), '..')))

import requests
import pandas as pd
from dotenv import load_dotenv
load_dotenv()

from src.utils.time_utils import to_ms
from src.params.constants import BINANCE_KLINES_URL, HISTORICAL_START_DATE, DEFAULT_REST_INTERVAL
from src.utils.dataframe_utils import raw_to_dataframe

from src.storage.postgres_writer import save_to_postgres, get_last_close_ms



def get_binance_data(
    symbol: str = "BTCUSDT",
    interval: str = "1m",
    start_time: int | None = None,
    end_time: int | None = None,
    limit: int = 1000
    ):
    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": limit,
    }
    if start_time is not None:
        params["startTime"] = start_time
    if end_time is not None:
        params["endTime"] = end_time

    response = requests.get(BINANCE_KLINES_URL, params=params, timeout=10)
    response.raise_for_status()
    return response.json()


SYMBOL = "BTCUSDT"

all_data = []

last_close_ms = get_last_close_ms(SYMBOL)
if last_close_ms is not None:
    start_time = last_close_ms + 1              # resume 1ms after last stored candle
else:
    start_time = to_ms(HISTORICAL_START_DATE)   # empty DB → default start

end_time  = time_ns() // 1_000_000          # now, in ms

while start_time < end_time:
    batch = get_binance_data(
        symbol=SYMBOL,
        interval=DEFAULT_REST_INTERVAL,
        start_time=start_time,
        end_time=end_time,
        limit=1000,
    )
    if not batch:
        break
    all_data += batch
    start_time = batch[-1][6] + 1           # 1ms after last candle's close_time
    if len(batch) < 1000:                   # last (partial) page → done
        break
    sleep(0.15)                             # respect rate limits



if not all_data:
    print("No new candles to fetch — database is already up to date.")
    raise SystemExit(0)

df_btc = raw_to_dataframe(all_data)

df_btc["symbol"] = SYMBOL
df_btc_cleaned = df_btc[["symbol","open_time","open","high","low","close",
                 "volume","close_time","number_of_trades"]]

save_to_postgres(df_btc_cleaned)
print(f"Saved {len(df_btc_cleaned)} candles for {SYMBOL}.")

