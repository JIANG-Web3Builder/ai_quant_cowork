from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from asr.config.settings import load_settings
from asr.ingestion.financial_importer import FinancialDataImporter
from asr.query.duckdb_reader import DuckDBResearchReader
from asr.utils.logging import setup_logging


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date", default="20220101")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument(
        "--dataset",
        default="fina_indicator",
        choices=["fina_indicator", "income", "balancesheet", "cashflow"],
    )
    args = parser.parse_args()

    setup_logging()
    settings = load_settings(ROOT_DIR)
    reader = DuckDBResearchReader(settings.storage.duckdb_path)

    if "stock_basic" not in reader.list_tables():
        raise RuntimeError("stock_basic view is not available. Please run bootstrap_reference_data.py first.")

    stock_basic = reader.query(
        f"""
        select ts_code
        from stock_basic
        order by ts_code asc
        limit {int(args.limit)}
        """
    )
    ts_codes = stock_basic["ts_code"].astype(str).tolist()

    importer = FinancialDataImporter(settings)
    handler = {
        "fina_indicator": importer.import_fina_indicator,
        "income": importer.import_income,
        "balancesheet": importer.import_balancesheet,
        "cashflow": importer.import_cashflow,
    }[args.dataset]
    summary = handler(ts_codes=ts_codes, start_date=args.start_date)
    print(summary)


if __name__ == "__main__":
    main()
