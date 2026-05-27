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
from asr.transform.tradable_panel import build_tradable_daily_base
from asr.utils.logging import setup_logging


def main() -> None:
    setup_logging()
    settings = load_settings(ROOT_DIR)
    reader = DuckDBResearchReader(settings.storage.duckdb_path)

    required_tables = {"daily_base", "stock_basic", "suspend_d", "stk_limit"}
    available_tables = set(reader.list_tables())
    missing = required_tables.difference(available_tables)
    if missing:
        raise RuntimeError(f"Missing required tables for tradable panel build: {sorted(missing)}")

    daily_base = reader.query("select * from daily_base")
    stock_basic = reader.query("select * from stock_basic")
    suspend_d = reader.query("select * from suspend_d")
    stk_limit = reader.query("select * from stk_limit")
    stock_st = reader.query("select * from stock_st") if "stock_st" in available_tables else None

    panel = build_tradable_daily_base(daily_base, stock_basic, suspend_d, stk_limit, stock_st=stock_st)

    panel_root = settings.storage.panel_dir / "tradable_daily_base"
    store = ParquetStore(settings.storage.data_dir)
    for trade_date, frame in panel.groupby("trade_date"):
        store.write_partition(panel_root, "trade_date", str(trade_date), frame)

    registry = MetadataRegistry(settings.storage.duckdb_path, settings.storage.sqlite_path)
    registry.update_watermark(
        "tradable_daily_base",
        str(panel["trade_date"].min()),
        str(panel["trade_date"].max()),
        int(len(panel)),
        datetime.now().isoformat(timespec="seconds"),
        "ready",
    )
    registry.register_view("tradable_daily_base", registry.dataset_glob_path(panel_root))

    print(panel[["trade_date", "ts_code", "is_suspended", "is_st", "hit_up_limit", "hit_down_limit", "can_buy", "can_sell", "is_tradable", "listed_days"]].tail(10).to_string(index=False))
    print(f"Saved tradable panel to {panel_root}")


if __name__ == "__main__":
    main()
