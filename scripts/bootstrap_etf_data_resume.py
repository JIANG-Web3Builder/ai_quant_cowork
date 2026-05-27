from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from asr.config.settings import load_settings
from asr.ingestion.etf_importer import ETFDataImporter
from asr.metadata.registry import MetadataRegistry
from asr.storage.parquet_store import ParquetStore
from asr.utils.dates import today_yyyymmdd
from asr.utils.logging import setup_logging


def seed_etf_basic_from_json(json_path: Path) -> pd.DataFrame:
    settings = load_settings(ROOT_DIR)
    store = ParquetStore(settings.storage.data_dir)
    registry = MetadataRegistry(settings.storage.duckdb_path, settings.storage.sqlite_path)

    records = json.loads(json_path.read_text(encoding="utf-8"))
    frame = pd.DataFrame(records)
    if frame.empty:
        raise RuntimeError(f"No etf_basic records found in {json_path}")

    frame["ts_code"] = frame["ts_code"].astype(str)
    frame["list_date"] = frame.get("list_date", pd.Series("", index=frame.index)).fillna("").astype(str)
    frame["etf_type"] = frame.get("etf_type", pd.Series("", index=frame.index)).fillna("").astype(str)
    frame["is_exchange_traded"] = frame["ts_code"].str.endswith((".SH", ".SZ"))
    frame["is_qdii"] = frame["etf_type"].eq("QDII")
    frame["is_t0_qdii"] = frame["is_exchange_traded"] & frame["is_qdii"]
    frame = frame.sort_values(["ts_code"]).reset_index(drop=True)

    raw_root = settings.storage.raw_dir / "tushare" / "etf_basic"
    canonical_root = settings.storage.canonical_dir / "etf_basic"
    store.write_dataset(raw_root, frame)
    store.write_dataset(canonical_root, frame)

    valid_list_dates = frame.loc[frame["list_date"] != "", "list_date"]
    min_date = str(valid_list_dates.min()) if not valid_list_dates.empty else today_yyyymmdd()
    max_date = str(valid_list_dates.max()) if not valid_list_dates.empty else today_yyyymmdd()
    now = datetime.now().isoformat(timespec="seconds")
    registry.update_watermark("etf_basic", min_date, max_date, len(frame), now, "ready")
    registry.register_view("etf_basic", registry.dataset_glob_path(canonical_root))
    return frame


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date", default="20050101")
    parser.add_argument("--end-date", default=today_yyyymmdd())
    parser.add_argument("--status", default="L")
    parser.add_argument("--etf-basic-json", default="")
    args = parser.parse_args()

    setup_logging()

    etf_basic_rows = None
    if args.etf_basic_json:
        seeded = seed_etf_basic_from_json(Path(args.etf_basic_json))
        etf_basic_rows = len(seeded)

    settings = load_settings(ROOT_DIR)
    importer = ETFDataImporter(settings)

    if etf_basic_rows is None:
        etf_basic_rows = len(importer.import_etf_basic())
    etf_fund_basic = importer.import_etf_fund_basic(status=args.status)
    etf_daily_summary = importer.import_etf_daily(start_date=args.start_date, end_date=args.end_date)
    etf_adj_summary = importer.import_etf_adj_factor(start_date=args.start_date, end_date=args.end_date)
    etf_share_size_summary = importer.import_etf_share_size(start_date=args.start_date, end_date=args.end_date)
    qdii_t0_summary = importer.build_qdii_t0_subset()

    print(f"Imported etf_basic rows={etf_basic_rows}")
    print(f"Imported etf_fund_basic rows={len(etf_fund_basic)}")
    print(f"Imported etf_daily summary={etf_daily_summary}")
    print(f"Imported etf_adj_factor summary={etf_adj_summary}")
    print(f"Imported etf_share_size summary={etf_share_size_summary}")
    print(f"Built qdii_t0 subset summary={qdii_t0_summary}")


if __name__ == "__main__":
    main()
