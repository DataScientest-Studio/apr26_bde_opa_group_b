from enum import Enum


class Interval(str, Enum):
    ONE_MINUTE      = "1m"
    FIVE_MINUTES    = "5m"
    FIFTEEN_MINUTES = "15m"
    ONE_HOUR        = "1h"
    ONE_DAY         = "1d"


class Symbol(str, Enum):
    BTCUSDT = "BTCUSDT"
    ETHUSDT = "ETHUSDT"
