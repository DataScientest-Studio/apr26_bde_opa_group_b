CREATE TABLE IF NOT EXISTS ohlcv_data (
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

CREATE INDEX IF NOT EXISTS idx_ohlcv_symbol_time
    ON ohlcv_data (symbol, open_time DESC);
