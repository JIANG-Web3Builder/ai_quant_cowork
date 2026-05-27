from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from asr.config.settings import AppSettings
from asr.data_sources.tushare_client import TushareClient
from asr.metadata.registry import MetadataRegistry
from asr.storage.parquet_store import ParquetStore
from asr.utils.dates import today_yyyymmdd


class ETFDataImporter:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.client = TushareClient(settings.tushare)
        self.store = ParquetStore(settings.storage.data_dir)
        self.registry = MetadataRegistry(settings.storage.duckdb_path, settings.storage.sqlite_path)
        self._etf_basic_frame: pd.DataFrame | None = None
        self._exchange_traded_codes: set[str] | None = None
        self._qdii_t0_codes: set[str] | None = None

    def import_etf_basic(self) -> pd.DataFrame:
        frame = self.client.fetch("etf_basic")
        frame = self._normalize(frame, ["ts_code"])
        if frame.empty:
            return frame
        frame["ts_code"] = frame["ts_code"].astype(str)
        frame["is_exchange_traded"] = frame["ts_code"].str.endswith((".SH", ".SZ"))
        frame["is_qdii"] = frame.get("etf_type", pd.Series("", index=frame.index)).fillna("").astype(str).eq("QDII")
        frame["is_t0_qdii"] = frame["is_exchange_traded"] & frame["is_qdii"]

        raw_root = self.settings.storage.raw_dir / "tushare" / "etf_basic"
        canonical_root = self.settings.storage.canonical_dir / "etf_basic"
        self.store.write_dataset(raw_root, frame)
        self.store.write_dataset(canonical_root, frame)

        min_date, max_date = self._resolve_date_range(frame, "list_date")
        self._register_dataset("etf_basic", canonical_root, min_date, max_date, len(frame))
        self._cache_etf_universe(frame)
        return frame

    def import_etf_fund_basic(self, status: str | None = None) -> pd.DataFrame:
        universe = self._get_exchange_traded_etf_codes()
        kwargs: dict[str, Any] = {"market": "E"}
        if status:
            kwargs["status"] = status
        frame = self.client.fetch("fund_basic", **kwargs)
        frame = self._normalize(frame, ["ts_code"])
        if frame.empty:
            return frame
        frame["ts_code"] = frame["ts_code"].astype(str)
        frame = frame[frame["ts_code"].isin(universe)].reset_index(drop=True)
        frame["is_t0_qdii"] = frame["ts_code"].isin(self._get_qdii_t0_codes())

        raw_root = self.settings.storage.raw_dir / "tushare" / "etf_fund_basic"
        canonical_root = self.settings.storage.canonical_dir / "etf_fund_basic"
        self.store.write_dataset(raw_root, frame)
        self.store.write_dataset(canonical_root, frame)

        min_date, max_date = self._resolve_date_range(frame, "list_date")
        self._register_dataset("etf_fund_basic", canonical_root, min_date, max_date, len(frame))
        return frame

    def import_etf_daily(self, start_date: str = "20050101", end_date: str | None = None) -> dict[str, Any]:
        effective_end_date = end_date or today_yyyymmdd()
        return self._import_trade_date_dataset(
            endpoint="fund_daily",
            dataset_name="etf_daily",
            start_date=start_date,
            end_date=effective_end_date,
        )

    def import_etf_adj_factor(self, start_date: str = "20050101", end_date: str | None = None) -> dict[str, Any]:
        effective_end_date = end_date or today_yyyymmdd()
        return self._import_trade_date_dataset(
            endpoint="fund_adj",
            dataset_name="etf_adj_factor",
            start_date=start_date,
            end_date=effective_end_date,
        )

    def import_etf_share_size(self, start_date: str = "20050101", end_date: str | None = None) -> dict[str, Any]:
        effective_end_date = end_date or today_yyyymmdd()
        return self._import_trade_date_dataset(
            endpoint="etf_share_size",
            dataset_name="etf_share_size",
            start_date=start_date,
            end_date=effective_end_date,
        )

    def build_qdii_t0_subset(self) -> dict[str, Any]:
        qdii_codes = self._get_qdii_t0_codes()
        subset_root = self.settings.storage.canonical_dir / "etf_qdii_t0"
        subset_root.mkdir(parents=True, exist_ok=True)

        summary = {
            "qdii_t0_code_count": len(qdii_codes),
            "etf_basic": self._build_static_subset(
                source_root=self.settings.storage.canonical_dir / "etf_basic",
                target_root=subset_root / "etf_basic",
                dataset_name="etf_basic_qdii_t0",
                ts_codes=qdii_codes,
                date_column="list_date",
            ),
            "etf_fund_basic": self._build_static_subset(
                source_root=self.settings.storage.canonical_dir / "etf_fund_basic",
                target_root=subset_root / "etf_fund_basic",
                dataset_name="etf_fund_basic_qdii_t0",
                ts_codes=qdii_codes,
                date_column="list_date",
            ),
            "etf_daily": self._build_partitioned_subset(
                source_root=self.settings.storage.canonical_dir / "etf_daily",
                target_root=subset_root / "etf_daily",
                dataset_name="etf_daily_qdii_t0",
                ts_codes=qdii_codes,
            ),
            "etf_adj_factor": self._build_partitioned_subset(
                source_root=self.settings.storage.canonical_dir / "etf_adj_factor",
                target_root=subset_root / "etf_adj_factor",
                dataset_name="etf_adj_factor_qdii_t0",
                ts_codes=qdii_codes,
            ),
            "etf_share_size": self._build_partitioned_subset(
                source_root=self.settings.storage.canonical_dir / "etf_share_size",
                target_root=subset_root / "etf_share_size",
                dataset_name="etf_share_size_qdii_t0",
                ts_codes=qdii_codes,
            ),
            "subset_root": subset_root.as_posix(),
        }
        return summary

    def _import_trade_date_dataset(self, endpoint: str, dataset_name: str, start_date: str, end_date: str) -> dict[str, Any]:
        trade_dates = self._fetch_trade_dates(start_date, end_date)
        universe = self._get_exchange_traded_etf_codes()
        raw_root = self.settings.storage.raw_dir / "tushare" / dataset_name
        canonical_root = self.settings.storage.canonical_dir / dataset_name

        imported_dates = 0
        skipped_dates = 0
        total_rows = 0

        for trade_date in trade_dates:
            canonical_part = canonical_root / f"trade_date={trade_date}" / "part.parquet"
            if canonical_part.exists():
                skipped_dates += 1
                continue

            frame = self.client.fetch(endpoint, trade_date=trade_date)
            frame = self._normalize(frame, ["trade_date", "ts_code"])
            if frame.empty:
                continue

            frame["ts_code"] = frame["ts_code"].astype(str)
            frame = frame[frame["ts_code"].isin(universe)].reset_index(drop=True)
            if frame.empty:
                continue

            self.store.write_partition(raw_root, "trade_date", trade_date, frame)
            self.store.write_partition(canonical_root, "trade_date", trade_date, frame)
            imported_dates += 1
            total_rows += len(frame)

        registration = self._register_partitioned_dataset(dataset_name, canonical_root, start_date, end_date)
        registration.update(
            {
                "imported_dates": imported_dates,
                "skipped_dates": skipped_dates,
                "new_rows": total_rows,
            }
        )
        return registration

    def _build_static_subset(
        self,
        source_root: Path,
        target_root: Path,
        dataset_name: str,
        ts_codes: set[str],
        date_column: str,
    ) -> dict[str, Any]:
        if not source_root.exists():
            return {"rows": 0, "status": "source_missing"}

        source_files = sorted(source_root.glob("**/*.parquet"))
        if not source_files:
            return {"rows": 0, "status": "source_empty"}

        frame = pd.concat([pd.read_parquet(path) for path in source_files], ignore_index=True)
        if "ts_code" not in frame.columns:
            return {"rows": 0, "status": "missing_ts_code"}
        frame["ts_code"] = frame["ts_code"].astype(str)
        subset = frame[frame["ts_code"].isin(ts_codes)].reset_index(drop=True)
        if subset.empty:
            return {"rows": 0, "status": "no_match"}

        self.store.write_dataset(target_root, subset)
        min_date, max_date = self._resolve_date_range(subset, date_column)
        self._register_dataset(dataset_name, target_root, min_date, max_date, len(subset))
        return {"rows": len(subset), "status": "ready"}

    def _build_partitioned_subset(
        self,
        source_root: Path,
        target_root: Path,
        dataset_name: str,
        ts_codes: set[str],
    ) -> dict[str, Any]:
        if not source_root.exists():
            return {"partitions": 0, "rows": 0, "status": "source_missing"}

        target_root.mkdir(parents=True, exist_ok=True)
        matched_partitions = 0
        total_rows = 0

        for partition_dir in sorted(child for child in source_root.iterdir() if child.is_dir() and child.name.startswith("trade_date=")):
            trade_date = partition_dir.name.split("=", 1)[1]
            source_file = partition_dir / "part.parquet"
            if not source_file.exists():
                continue
            frame = pd.read_parquet(source_file)
            if "ts_code" not in frame.columns:
                continue
            frame["ts_code"] = frame["ts_code"].astype(str)
            subset = frame[frame["ts_code"].isin(ts_codes)].reset_index(drop=True)
            if subset.empty:
                continue
            self.store.write_partition(target_root, "trade_date", trade_date, subset)
            matched_partitions += 1
            total_rows += len(subset)

        if total_rows == 0:
            return {"partitions": 0, "rows": 0, "status": "no_match"}

        registration = self._register_partitioned_dataset(dataset_name, target_root, today_yyyymmdd(), today_yyyymmdd())
        registration.update({"partitions": matched_partitions, "rows": total_rows, "status": "ready"})
        return registration

    def _load_or_fetch_etf_basic(self) -> pd.DataFrame:
        if self._etf_basic_frame is not None:
            return self._etf_basic_frame.copy()

        canonical_root = self.settings.storage.canonical_dir / "etf_basic"
        source_file = canonical_root / "part.parquet"
        if source_file.exists():
            frame = pd.read_parquet(source_file)
            frame = self._normalize(frame, ["ts_code"])
            self._cache_etf_universe(frame)
            return frame.copy()

        frame = self.import_etf_basic()
        return frame.copy()

    def _cache_etf_universe(self, frame: pd.DataFrame) -> None:
        cached = frame.copy()
        cached["ts_code"] = cached["ts_code"].astype(str)
        if "is_exchange_traded" not in cached.columns:
            cached["is_exchange_traded"] = cached["ts_code"].str.endswith((".SH", ".SZ"))
        if "is_t0_qdii" not in cached.columns:
            cached["is_qdii"] = cached.get("etf_type", pd.Series("", index=cached.index)).fillna("").astype(str).eq("QDII")
            cached["is_t0_qdii"] = cached["is_exchange_traded"] & cached["is_qdii"]
        self._etf_basic_frame = cached
        self._exchange_traded_codes = set(cached.loc[cached["is_exchange_traded"], "ts_code"].astype(str).tolist())
        self._qdii_t0_codes = set(cached.loc[cached["is_t0_qdii"], "ts_code"].astype(str).tolist())

    def _get_exchange_traded_etf_codes(self) -> set[str]:
        if self._exchange_traded_codes is None:
            self._load_or_fetch_etf_basic()
        return set(self._exchange_traded_codes or set())

    def _get_qdii_t0_codes(self) -> set[str]:
        if self._qdii_t0_codes is None:
            self._load_or_fetch_etf_basic()
        return set(self._qdii_t0_codes or set())

    def _fetch_trade_dates(self, start_date: str, end_date: str) -> list[str]:
        calendar = self.client.fetch("trade_cal", exchange="", start_date=start_date, end_date=end_date, is_open="1")
        if calendar.empty:
            return []
        return sorted(calendar["cal_date"].astype(str).tolist())

    def _normalize(self, frame: pd.DataFrame, sort_columns: list[str]) -> pd.DataFrame:
        if frame.empty:
            return frame
        normalized = frame.copy()
        for column in [
            "ts_code",
            "list_date",
            "delist_date",
            "trade_date",
            "cal_date",
            "pretrade_date",
            "index_code",
            "index_name",
            "exchange",
            "etf_type",
        ]:
            if column in normalized.columns:
                normalized[column] = normalized[column].fillna("").astype(str)
        existing_sort_columns = [column for column in sort_columns if column in normalized.columns]
        if existing_sort_columns:
            normalized = normalized.sort_values(existing_sort_columns).reset_index(drop=True)
        return normalized

    def _resolve_date_range(self, frame: pd.DataFrame, date_column: str) -> tuple[str, str]:
        if frame.empty or date_column not in frame.columns:
            today = today_yyyymmdd()
            return today, today
        values = frame[date_column].astype(str)
        values = values[values != ""]
        if values.empty:
            today = today_yyyymmdd()
            return today, today
        return str(values.min()), str(values.max())

    def _register_dataset(self, dataset_name: str, dataset_root: Path, min_date: str, max_date: str, row_count: int) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        self.registry.update_watermark(dataset_name, min_date, max_date, row_count, now, "ready")
        glob_path = self.registry.dataset_glob_path(dataset_root)
        self.registry.register_view(dataset_name, glob_path)

    def _register_partitioned_dataset(self, dataset_name: str, dataset_root: Path, fallback_min: str, fallback_max: str) -> dict[str, Any]:
        glob_path = self.registry.dataset_glob_path(dataset_root)
        min_date = fallback_min
        max_date = fallback_max
        row_count = 0
        try:
            with duckdb.connect() as conn:
                stats = conn.execute(
                    f"""
                    select
                        min(cast(trade_date as varchar)) as min_date,
                        max(cast(trade_date as varchar)) as max_date,
                        count(*) as row_count
                    from read_parquet('{glob_path}', hive_partitioning=true, union_by_name=true)
                    """
                ).fetchone()
            if stats is not None:
                min_date = str(stats[0] or fallback_min)
                max_date = str(stats[1] or fallback_max)
                row_count = int(stats[2] or 0)
        except Exception:
            min_date = fallback_min
            max_date = fallback_max
            row_count = 0

        now = datetime.now().isoformat(timespec="seconds")
        self.registry.update_watermark(dataset_name, min_date, max_date, row_count, now, "ready")
        if row_count > 0:
            self.registry.register_view(dataset_name, glob_path)
        return {"min_date": min_date, "max_date": max_date, "row_count": row_count}
