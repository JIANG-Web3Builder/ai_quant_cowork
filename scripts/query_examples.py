from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from asr.config.settings import load_settings
from asr.query.duckdb_reader import DuckDBResearchReader
from asr.utils.logging import setup_logging


def main() -> None:
    setup_logging()
    settings = load_settings(ROOT_DIR)
    reader = DuckDBResearchReader(settings.storage.duckdb_path)

    print("TABLES:", reader.list_tables())
    print("\nLATEST SAMPLE:")
    print(reader.sample_daily_base(limit=5).to_string(index=False))

    print("\nCROSS SECTION SAMPLE:")
    print(
        reader.get_cross_section(
            trade_date="20220104",
            columns=["trade_date", "ts_code", "close", "adj_close", "pe_ttm", "pb", "total_mv"],
            limit=5,
        ).to_string(index=False)
    )

    print("\nSTOCK HISTORY SAMPLE:")
    print(
        reader.get_stock_history(
            ts_code="000001.SZ",
            start_date="20220104",
            end_date="20220131",
        )[["trade_date", "ts_code", "close", "adj_close", "turnover_rate", "pe_ttm", "pb"]].head(10).to_string(index=False)
    )


if __name__ == "__main__":
    main()
