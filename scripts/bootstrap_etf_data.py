from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from asr.config.settings import load_settings
from asr.ingestion.etf_importer import ETFDataImporter
from asr.utils.dates import today_yyyymmdd
from asr.utils.logging import setup_logging


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date", default="20050101")
    parser.add_argument("--end-date", default=today_yyyymmdd())
    parser.add_argument("--status", default="L")
    args = parser.parse_args()

    setup_logging()
    settings = load_settings(ROOT_DIR)
    importer = ETFDataImporter(settings)

    etf_basic = importer.import_etf_basic()
    etf_fund_basic = importer.import_etf_fund_basic(status=args.status)
    etf_daily_summary = importer.import_etf_daily(start_date=args.start_date, end_date=args.end_date)
    etf_adj_summary = importer.import_etf_adj_factor(start_date=args.start_date, end_date=args.end_date)
    etf_share_size_summary = importer.import_etf_share_size(start_date=args.start_date, end_date=args.end_date)
    qdii_t0_summary = importer.build_qdii_t0_subset()

    print(f"Imported etf_basic rows={len(etf_basic)}")
    print(f"Imported etf_fund_basic rows={len(etf_fund_basic)}")
    print(f"Imported etf_daily summary={etf_daily_summary}")
    print(f"Imported etf_adj_factor summary={etf_adj_summary}")
    print(f"Imported etf_share_size summary={etf_share_size_summary}")
    print(f"Built qdii_t0 subset summary={qdii_t0_summary}")


if __name__ == "__main__":
    main()
