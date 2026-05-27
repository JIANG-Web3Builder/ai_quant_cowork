from __future__ import annotations

from pathlib import Path

import polars as pl


def build_daily_base(eod_root: Path, adj_root: Path, basic_root: Path) -> pl.LazyFrame:
    eod = pl.scan_parquet(str(eod_root / "**/*.parquet"))
    adj = pl.scan_parquet(str(adj_root / "**/*.parquet"))
    basic = pl.scan_parquet(str(basic_root / "**/*.parquet"))

    return (
        eod.join(adj, on=["trade_date", "ts_code"], how="left")
        .join(basic, on=["trade_date", "ts_code"], how="left")
        .with_columns(
            [
                (pl.col("close") * pl.col("adj_factor")).alias("adj_close"),
            ]
        )
        .sort(["trade_date", "ts_code"])
    )
