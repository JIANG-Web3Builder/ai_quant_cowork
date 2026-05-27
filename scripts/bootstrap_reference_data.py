from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from asr.config.settings import load_settings
from asr.ingestion.reference_importer import ReferenceDataImporter
from asr.utils.dates import today_yyyymmdd
from asr.utils.logging import setup_logging


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date", default="20220101")
    parser.add_argument("--end-date", default=today_yyyymmdd())
    parser.add_argument("--list-status", default="L")
    args = parser.parse_args()

    setup_logging()
    settings = load_settings(ROOT_DIR)
    importer = ReferenceDataImporter(settings)

    stock_basic = importer.import_stock_basic(list_status=args.list_status)
    trade_cal = importer.import_trade_calendar(start_date=args.start_date, end_date=args.end_date)
    suspend_d = importer.import_suspend_d(start_date=args.start_date, end_date=args.end_date)
    stk_limit = importer.import_stk_limit(start_date=args.start_date, end_date=args.end_date)
    index_daily_summary = importer.import_index_daily(start_date=args.start_date, end_date=args.end_date)

    print(f"Imported stock_basic rows={len(stock_basic)}")
    print(f"Imported trade_cal rows={len(trade_cal)}")
    print(f"Imported suspend_d rows={len(suspend_d)}")
    print(f"Imported stk_limit rows={len(stk_limit)}")
    print(f"Imported index_daily summary={index_daily_summary}")


if __name__ == "__main__":
    main()
