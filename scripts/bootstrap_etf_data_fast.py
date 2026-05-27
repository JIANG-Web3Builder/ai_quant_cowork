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
from asr.data_sources.tushare_client import TushareClient
from asr.metadata.registry import MetadataRegistry
from asr.storage.parquet_store import ParquetStore
from asr.utils.dates import today_yyyymmdd
from asr.utils.logging import setup_logging


def normalize(frame: pd.DataFrame, sort_columns: list[str]) -> pd.DataFrame:
    if frame.empty:
        return frame
    normalized = frame.copy()
    for column in [
        "ts_code",
        "trade_date",
        "list_date",
        "delist_date",
        "etf_type",
        "exchange",
        "index_code",
        "index_name",
    ]:
        if column in normalized.columns:
            normalized[column] = normalized[column].fillna("").astype(str)
    existing_sort_columns = [column for column in sort_columns if column in normalized.columns]
    if existing_sort_columns:
        normalized = normalized.sort_values(existing_sort_columns).reset_index(drop=True)
    return normalized


def resolve_date_range(frame: pd.DataFrame, date_column: str) -> tuple[str, str]:
    if frame.empty or date_column not in frame.columns:
        today = today_yyyymmdd()
        return today, today
    values = frame[date_column].astype(str)
    values = values[values != ""]
    if values.empty:
        today = today_yyyymmdd()
        return today, today
    return str(values.min()), str(values.max())


def update_dataset_view(registry: MetadataRegistry, dataset_name: str, dataset_root: Path, min_date: str, max_date: str, row_count: int) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    registry.update_watermark(dataset_name, min_date, max_date, row_count, now, "ready")
    registry.register_view(dataset_name, registry.dataset_glob_path(dataset_root))


def seed_or_load_etf_basic(store: ParquetStore, registry: MetadataRegistry, etf_basic_path: Path | None) -> pd.DataFrame:
    canonical_root = ROOT_DIR / "data" / "canonical" / "etf_basic"
    canonical_file = canonical_root / "part.parquet"
    if canonical_file.exists():
        return normalize(pd.read_parquet(canonical_file), ["ts_code"])

    if etf_basic_path is None:
        raise RuntimeError("etf_basic parquet is missing and no --etf-basic-json path was provided.")

    records = json.loads(etf_basic_path.read_text(encoding="utf-8"))
    frame = pd.DataFrame(records)
    frame = normalize(frame, ["ts_code"])
    frame["is_exchange_traded"] = frame["ts_code"].str.endswith((".SH", ".SZ"))
    frame["is_qdii"] = frame.get("etf_type", pd.Series("", index=frame.index)).fillna("").astype(str).eq("QDII")
    frame["is_t0_qdii"] = frame["is_exchange_traded"] & frame["is_qdii"]

    raw_root = ROOT_DIR / "data" / "raw" / "tushare" / "etf_basic"
    store.write_dataset(raw_root, frame)
    store.write_dataset(canonical_root, frame)
    min_date, max_date = resolve_date_range(frame, "list_date")
    update_dataset_view(registry, "etf_basic", canonical_root, min_date, max_date, len(frame))
    return frame


def write_static_dataset(store: ParquetStore, registry: MetadataRegistry, dataset_name: str, frame: pd.DataFrame, date_column: str) -> None:
    raw_root = ROOT_DIR / "data" / "raw" / "tushare" / dataset_name
    canonical_root = ROOT_DIR / "data" / "canonical" / dataset_name
    store.write_dataset(raw_root, frame)
    store.write_dataset(canonical_root, frame)
    min_date, max_date = resolve_date_range(frame, date_column)
    update_dataset_view(registry, dataset_name, canonical_root, min_date, max_date, len(frame))


def fetch_by_code_dataset(
    client: TushareClient,
    store: ParquetStore,
    registry: MetadataRegistry,
    dataset_name: str,
    endpoint: str,
    ts_codes: list[str],
    start_date: str,
    end_date: str,
    sort_columns: list[str],
) -> dict[str, int | str]:
    raw_root = ROOT_DIR / "data" / "raw" / "tushare" / dataset_name
    canonical_root = ROOT_DIR / "data" / "canonical" / dataset_name
    raw_root.mkdir(parents=True, exist_ok=True)
    canonical_root.mkdir(parents=True, exist_ok=True)

    imported_codes = 0
    skipped_codes = 0
    total_rows = 0
    min_date: str | None = None
    max_date: str | None = None

    for ts_code in ts_codes:
        filename = f"{ts_code.replace('.', '_')}.parquet"
        canonical_file = canonical_root / filename
        if canonical_file.exists():
            skipped_codes += 1
            continue

        frame = client.fetch(endpoint, ts_code=ts_code, start_date=start_date, end_date=end_date)
        frame = normalize(frame, sort_columns)
        if frame.empty:
            continue

        store.write_file(raw_root, filename, frame)
        store.write_file(canonical_root, filename, frame)
        imported_codes += 1
        total_rows += len(frame)
        code_min, code_max = resolve_date_range(frame, "trade_date")
        min_date = code_min if min_date is None else min(min_date, code_min)
        max_date = code_max if max_date is None else max(max_date, code_max)

    existing_files = sorted(canonical_root.glob("*.parquet"))
    if existing_files:
        if min_date is None or max_date is None:
            sample = pd.concat([pd.read_parquet(path, columns=["trade_date"]) for path in existing_files if path.exists()], ignore_index=True)
            if not sample.empty:
                min_date, max_date = resolve_date_range(sample, "trade_date")
        row_count = total_rows
        if row_count == 0:
            row_count = sum(len(pd.read_parquet(path, columns=["trade_date"])) for path in existing_files)
        update_dataset_view(
            registry,
            dataset_name,
            canonical_root,
            min_date or start_date,
            max_date or end_date,
            row_count,
        )

    return {
        "imported_codes": imported_codes,
        "skipped_codes": skipped_codes,
        "row_count": total_rows,
        "min_date": min_date or start_date,
        "max_date": max_date or end_date,
    }


def build_qdii_t0_subsets(store: ParquetStore, registry: MetadataRegistry, qdii_codes: set[str]) -> dict[str, dict[str, int | str]]:
    subset_root = ROOT_DIR / "data" / "canonical" / "etf_qdii_t0"
    subset_root.mkdir(parents=True, exist_ok=True)
    summary: dict[str, dict[str, int | str]] = {}

    static_datasets = {
        "etf_basic": "list_date",
        "etf_fund_basic": "list_date",
    }
    for dataset_name, date_column in static_datasets.items():
        source_file = ROOT_DIR / "data" / "canonical" / dataset_name / "part.parquet"
        if not source_file.exists():
            summary[dataset_name] = {"rows": 0, "status": "source_missing"}
            continue
        frame = pd.read_parquet(source_file)
        frame["ts_code"] = frame["ts_code"].astype(str)
        subset = frame[frame["ts_code"].isin(qdii_codes)].reset_index(drop=True)
        if subset.empty:
            summary[dataset_name] = {"rows": 0, "status": "no_match"}
            continue
        target_root = subset_root / dataset_name
        store.write_dataset(target_root, subset)
        min_date, max_date = resolve_date_range(subset, date_column)
        update_dataset_view(registry, f"{dataset_name}_qdii_t0", target_root, min_date, max_date, len(subset))
        summary[dataset_name] = {"rows": len(subset), "status": "ready"}

    code_datasets = ["etf_daily", "etf_adj_factor", "etf_share_size"]
    for dataset_name in code_datasets:
        source_root = ROOT_DIR / "data" / "canonical" / dataset_name
        target_root = subset_root / dataset_name
        target_root.mkdir(parents=True, exist_ok=True)
        copied_files = 0
        total_rows = 0
        min_date: str | None = None
        max_date: str | None = None
        for ts_code in sorted(qdii_codes):
            source_file = source_root / f"{ts_code.replace('.', '_')}.parquet"
            if not source_file.exists():
                continue
            frame = pd.read_parquet(source_file)
            if frame.empty:
                continue
            store.write_file(target_root, source_file.name, frame)
            copied_files += 1
            total_rows += len(frame)
            code_min, code_max = resolve_date_range(frame, "trade_date")
            min_date = code_min if min_date is None else min(min_date, code_min)
            max_date = code_max if max_date is None else max(max_date, code_max)
        if copied_files == 0:
            summary[dataset_name] = {"files": 0, "rows": 0, "status": "no_match"}
            continue
        update_dataset_view(registry, f"{dataset_name}_qdii_t0", target_root, min_date or today_yyyymmdd(), max_date or today_yyyymmdd(), total_rows)
        summary[dataset_name] = {"files": copied_files, "rows": total_rows, "status": "ready"}

    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date", default="20050101")
    parser.add_argument("--end-date", default=today_yyyymmdd())
    parser.add_argument("--status", default="L")
    parser.add_argument("--etf-basic-json", default="")
    args = parser.parse_args()

    setup_logging()
    settings = load_settings(ROOT_DIR)
    client = TushareClient(settings.tushare)
    store = ParquetStore(settings.storage.data_dir)
    registry = MetadataRegistry(settings.storage.duckdb_path, settings.storage.sqlite_path)

    etf_basic_path = Path(args.etf_basic_json) if args.etf_basic_json else None
    etf_basic = seed_or_load_etf_basic(store, registry, etf_basic_path)
    exchange_codes = sorted(etf_basic.loc[etf_basic["ts_code"].str.endswith((".SH", ".SZ")), "ts_code"].astype(str).unique().tolist())
    qdii_codes = set(
        etf_basic.loc[
            etf_basic["ts_code"].str.endswith((".SH", ".SZ")) & etf_basic.get("etf_type", pd.Series("", index=etf_basic.index)).fillna("").astype(str).eq("QDII"),
            "ts_code",
        ].astype(str).tolist()
    )

    fund_basic = client.fetch("fund_basic", market="E", status=args.status)
    fund_basic = normalize(fund_basic, ["ts_code"])
    fund_basic = fund_basic[fund_basic["ts_code"].astype(str).isin(exchange_codes)].reset_index(drop=True)
    fund_basic["is_t0_qdii"] = fund_basic["ts_code"].astype(str).isin(qdii_codes)
    write_static_dataset(store, registry, "etf_fund_basic", fund_basic, "list_date")

    etf_daily_summary = fetch_by_code_dataset(
        client=client,
        store=store,
        registry=registry,
        dataset_name="etf_daily",
        endpoint="fund_daily",
        ts_codes=exchange_codes,
        start_date=args.start_date,
        end_date=args.end_date,
        sort_columns=["ts_code", "trade_date"],
    )
    etf_adj_summary = fetch_by_code_dataset(
        client=client,
        store=store,
        registry=registry,
        dataset_name="etf_adj_factor",
        endpoint="fund_adj",
        ts_codes=exchange_codes,
        start_date=args.start_date,
        end_date=args.end_date,
        sort_columns=["ts_code", "trade_date"],
    )
    etf_share_size_summary = fetch_by_code_dataset(
        client=client,
        store=store,
        registry=registry,
        dataset_name="etf_share_size",
        endpoint="etf_share_size",
        ts_codes=exchange_codes,
        start_date=args.start_date,
        end_date=args.end_date,
        sort_columns=["ts_code", "trade_date"],
    )
    qdii_summary = build_qdii_t0_subsets(store, registry, qdii_codes)

    print(f"Imported etf_basic rows={len(etf_basic)}")
    print(f"Imported etf_fund_basic rows={len(fund_basic)}")
    print(f"Imported etf_daily summary={etf_daily_summary}")
    print(f"Imported etf_adj_factor summary={etf_adj_summary}")
    print(f"Imported etf_share_size summary={etf_share_size_summary}")
    print(f"Built qdii_t0 subset summary={qdii_summary}")


if __name__ == "__main__":
    main()
