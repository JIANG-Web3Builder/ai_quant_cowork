from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from asr.config.settings import load_settings
from asr.factors.simple_factors import build_first_factor_batch
from asr.query.duckdb_reader import DuckDBResearchReader
from asr.utils.logging import setup_logging


def main() -> None:
    setup_logging()
    settings = load_settings(ROOT_DIR)
    reader = DuckDBResearchReader(settings.storage.duckdb_path)

    frame = reader.query(
        """
        select
            ts_code,
            trade_date,
            adj_close,
            turnover_rate,
            turnover_rate_f,
            pe_ttm,
            pb,
            total_mv
        from daily_base
        order by ts_code, trade_date
        """
    )

    factors = build_first_factor_batch(frame)
    output_dir = settings.storage.factors_dir / "first_batch"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "daily_base_first_factors.parquet"
    factors.to_parquet(output_path, index=False)

    preview = factors[
        [
            "ts_code",
            "trade_date",
            "ret_5",
            "ret_20",
            "ret_60",
            "reversal_5",
            "turnover_5d_avg",
            "turnover_20d_avg",
            "log_total_mv",
            "bp",
            "ep_ttm",
        ]
    ].tail(10)
    print(preview.to_string(index=False))
    print(f"Saved factors to {output_path}")


if __name__ == "__main__":
    main()
