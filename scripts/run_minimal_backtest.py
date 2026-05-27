from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from asr.backtest import DailyCrossSectionalBacktestConfig, run_daily_cross_sectional_backtest
from asr.config.settings import load_settings
from asr.query.duckdb_reader import DuckDBResearchReader
from asr.utils.logging import setup_logging


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--factor-path", default=str(Path("data") / "factors" / "first_batch" / "daily_base_first_factors.parquet"))
    parser.add_argument("--signal-col", default="ret_20")
    parser.add_argument("--top-n", type=int, default=50)
    parser.add_argument("--fee-rate", type=float, default=0.001)
    parser.add_argument("--min-listed-days", type=int, default=120)
    parser.add_argument("--benchmark", default="000300.SH")
    parser.add_argument("--allow-st", action="store_true")
    parser.add_argument("--ascending", action="store_true")
    args = parser.parse_args()

    setup_logging()
    settings = load_settings(ROOT_DIR)
    factor_path = ROOT_DIR / args.factor_path
    if not factor_path.exists():
        raise FileNotFoundError(f"Factor file not found: {factor_path}")

    factor_frame = pd.read_parquet(factor_path)
    reader = DuckDBResearchReader(settings.storage.duckdb_path)
    available_tables = set(reader.list_tables())
    if "tradable_daily_base" not in available_tables:
        raise RuntimeError("tradable_daily_base is not available. Please run build_tradable_panel.py first.")

    tradable_schema = reader.sample_table("tradable_daily_base", limit=1)
    tradable_columns = [
        column
        for column in ["ts_code", "trade_date", "is_tradable", "is_suspended", "is_st", "listed_days"]
        if column in tradable_schema.columns
    ]
    tradable_frame = reader.query(
        """
        select {tradable_columns}
        from tradable_daily_base
        """.format(tradable_columns=", ".join(tradable_columns))
    )

    benchmark_frame = None
    if "index_daily" in available_tables:
        benchmark_frame = reader.query(
            f"""
            select ts_code, trade_date, close, pct_chg
            from index_daily
            where ts_code = '{args.benchmark}'
            order by trade_date asc
            """
        )

    config = DailyCrossSectionalBacktestConfig(
        signal_column=args.signal_col,
        top_n=args.top_n,
        fee_rate=args.fee_rate,
        min_listed_days=args.min_listed_days,
        exclude_st=not args.allow_st,
        ascending=args.ascending,
    )
    result = run_daily_cross_sectional_backtest(factor_frame, tradable_frame, benchmark_frame, config)

    output_dir = settings.storage.result_dir / "backtests" / f"{args.signal_col}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    output_dir.mkdir(parents=True, exist_ok=True)

    result["performance"].to_parquet(output_dir / "performance.parquet", index=False)
    result["holdings"].to_parquet(output_dir / "holdings.parquet", index=False)
    result["summary"].to_parquet(output_dir / "summary.parquet", index=False)

    print(result["summary"].to_string(index=False))
    print(result["performance"].tail(10).to_string(index=False))
    print(f"Saved backtest results to {output_dir}")


if __name__ == "__main__":
    main()
