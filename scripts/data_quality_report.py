from __future__ import annotations

import json
import sys
from pathlib import Path

import duckdb
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from asr.config.settings import load_settings
from asr.utils.logging import setup_logging


def main() -> None:
    setup_logging()
    settings = load_settings(ROOT_DIR)
    output_dir = settings.storage.result_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    with duckdb.connect(str(settings.storage.duckdb_path), read_only=True) as conn:
        coverage = conn.execute(
            """
            select
                min(trade_date) as min_trade_date,
                max(trade_date) as max_trade_date,
                count(distinct trade_date) as trade_date_count,
                count(distinct ts_code) as stock_count,
                count(*) as row_count
            from daily_base
            """
        ).fetchdf()

        null_summary = conn.execute(
            """
            select
                sum(case when adj_close is null then 1 else 0 end) as adj_close_nulls,
                sum(case when pe_ttm is null then 1 else 0 end) as pe_ttm_nulls,
                sum(case when pb is null then 1 else 0 end) as pb_nulls,
                sum(case when turnover_rate is null then 1 else 0 end) as turnover_rate_nulls,
                sum(case when total_mv is null then 1 else 0 end) as total_mv_nulls
            from daily_base
            """
        ).fetchdf()

        duplicate_summary = conn.execute(
            """
            select count(*) as duplicate_rows
            from (
                select trade_date, ts_code, count(*) as cnt
                from daily_base
                group by trade_date, ts_code
                having count(*) > 1
            )
            """
        ).fetchdf()

        latest_dates = conn.execute(
            """
            select trade_date, count(*) as stock_count
            from daily_base
            group by trade_date
            order by trade_date desc
            limit 10
            """
        ).fetchdf()

    report = {
        "coverage": coverage.iloc[0].to_dict(),
        "null_summary": null_summary.iloc[0].to_dict(),
        "duplicate_summary": duplicate_summary.iloc[0].to_dict(),
        "latest_trade_dates": latest_dates.to_dict(orient="records"),
    }

    json_path = output_dir / "data_quality_report.json"
    md_path = output_dir / "data_quality_report.md"

    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    md_lines = [
        "# Data Quality Report",
        "",
        "## Coverage",
        "",
        f"- min_trade_date: {report['coverage']['min_trade_date']}",
        f"- max_trade_date: {report['coverage']['max_trade_date']}",
        f"- trade_date_count: {report['coverage']['trade_date_count']}",
        f"- stock_count: {report['coverage']['stock_count']}",
        f"- row_count: {report['coverage']['row_count']}",
        "",
        "## Null Summary",
        "",
        f"- adj_close_nulls: {report['null_summary']['adj_close_nulls']}",
        f"- pe_ttm_nulls: {report['null_summary']['pe_ttm_nulls']}",
        f"- pb_nulls: {report['null_summary']['pb_nulls']}",
        f"- turnover_rate_nulls: {report['null_summary']['turnover_rate_nulls']}",
        f"- total_mv_nulls: {report['null_summary']['total_mv_nulls']}",
        "",
        "## Duplicate Summary",
        "",
        f"- duplicate_rows: {report['duplicate_summary']['duplicate_rows']}",
        "",
        "## Latest Trade Dates",
        "",
    ]

    for row in report["latest_trade_dates"]:
        md_lines.append(f"- {row['trade_date']}: {row['stock_count']} rows")

    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    print(f"Saved report to {md_path}")


if __name__ == "__main__":
    main()
