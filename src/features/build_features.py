"""Shared feature definitions — used by BOTH train_model and predict_model
so the model is trained and queried with the exact same columns."""

# Inputs the model learns from (one candle's OHLCV + trade count).
FEATURE_COLUMNS = ["open", "high", "low", "close", "volume", "number_of_trades"]


def make_features(df):
    """Return the feature matrix X from an OHLCV dataframe."""
    return df[FEATURE_COLUMNS].astype(float)


def make_target(df):
    """Target = the NEXT candle's close price (current row shifted up by one)."""
    return df["close"].astype(float).shift(-1)
