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
    parser.add_argument("--industry-source", default="SW2021")
    parser.add_argument("--limit-index-codes", type=int, default=0)
    parser.add_argument("--index-member-is-new", default="N")
    args = parser.parse_args()

    setup_logging()
    settings = load_settings(ROOT_DIR)
    importer = ReferenceDataImporter(settings)

    stock_st = importer.import_stock_st(start_date=args.start_date, end_date=args.end_date)
    index_classify = importer.import_index_classify(source=args.industry_source)

    index_codes: list[str] | None = None
    code_column = "index_code" if "index_code" in index_classify.columns else "industry_code"
    if args.limit_index_codes > 0:
        index_codes = index_classify[code_column].dropna().astype(str).head(args.limit_index_codes).tolist()

    index_member_summary = importer.import_index_member(
        source=args.industry_source,
        is_new=args.index_member_is_new,
        index_codes=index_codes,
    )

    print(f"Imported stock_st rows={len(stock_st)}")
    print(f"Imported index_classify rows={len(index_classify)}")
    print(f"Imported index_member summary={index_member_summary}")


if __name__ == "__main__":
    main()
