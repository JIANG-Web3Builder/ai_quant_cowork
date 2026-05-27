from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from asr.config.settings import load_settings
from asr.metadata.registry import MetadataRegistry
from asr.query.duckdb_reader import DuckDBResearchReader
from asr.storage.parquet_store import ParquetStore
from asr.transform.fundamental_panel import build_daily_fundamental_base
from asr.utils.logging import setup_logging


def main() -> None:
    setup_logging()
    settings = load_settings(ROOT_DIR)
    reader = DuckDBResearchReader(settings.storage.duckdb_path)

    required_tables = {"daily_base", "fina_indicator"}
    missing = required_tables.difference(reader.list_tables())
    if missing:
        raise RuntimeError(f"Missing required tables for fundamental panel build: {sorted(missing)}")

    daily_base = reader.query("select * from daily_base")
    fina_indicator = reader.query("select * from fina_indicator")
    panel = build_daily_fundamental_base(daily_base, fina_indicator)

    panel_root = settings.storage.panel_dir / "daily_fundamental_base"
    store = ParquetStore(settings.storage.data_dir)
    for trade_date, frame in panel.groupby("trade_date"):
        store.write_partition(panel_root, "trade_date", str(trade_date), frame)

    registry = MetadataRegistry(settings.storage.duckdb_path, settings.storage.sqlite_path)
    registry.update_watermark(
        "daily_fundamental_base",
        str(panel["trade_date"].min()),
        str(panel["trade_date"].max()),
        int(len(panel)),
        datetime.now().isoformat(timespec="seconds"),
        "ready",
    )
    registry.register_view("daily_fundamental_base", registry.dataset_glob_path(panel_root))

    preview_columns = [
        column
        for column in [
            "trade_date",
            "ts_code",
            "ann_date",
            "end_date",
            "roe",
            "roe_dt",
            "roa",
            "gross_margin",
            "debt_to_assets",
            "ocfps",
            "bps",
        ]
        if column in panel.columns
    ]
    print(panel[preview_columns].tail(10).to_string(index=False))
    print(f"Saved fundamental panel to {panel_root}")


if __name__ == "__main__":
    main()
