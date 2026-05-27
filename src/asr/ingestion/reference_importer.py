from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from asr.config.settings import AppSettings
from asr.data_sources.tushare_client import TushareClient
from asr.metadata.registry import MetadataRegistry
from asr.storage.parquet_store import ParquetStore
from asr.utils.dates import today_yyyymmdd


DEFAULT_BENCHMARK_INDEXES = [
    "000001.SH",
    "399001.SZ",
    "399006.SZ",
    "000300.SH",
    "000905.SH",
    "000852.SH",
]


class ReferenceDataImporter:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.client = TushareClient(settings.tushare)
        self.store = ParquetStore(settings.storage.data_dir)
        self.registry = MetadataRegistry(settings.storage.duckdb_path, settings.storage.sqlite_path)

    def import_stock_basic(self, list_status: str = "L") -> pd.DataFrame:
        frame = self.client.fetch("stock_basic", list_status=list_status)
        frame = self._normalize(frame, ["ts_code"])

        raw_root = self.settings.storage.raw_dir / "tushare" / "stock_basic"
        canonical_root = self.settings.storage.canonical_dir / "stock_basic"
        self.store.write_dataset(raw_root, frame)
        self.store.write_dataset(canonical_root, frame)

        min_date, max_date = self._resolve_date_range(frame, "list_date")
        self._register_dataset("stock_basic", canonical_root, min_date, max_date, len(frame))
        return frame

    def import_trade_calendar(self, start_date: str = "20220101", end_date: str | None = None, exchange: str = "") -> pd.DataFrame:
        effective_end_date = end_date or today_yyyymmdd()
        frame = self.client.fetch("trade_cal", exchange=exchange, start_date=start_date, end_date=effective_end_date)
        frame = self._normalize(frame, ["cal_date", "exchange"])

        raw_root = self.settings.storage.raw_dir / "tushare" / "trade_cal"
        canonical_root = self.settings.storage.canonical_dir / "trade_cal"
        filename = f"trade_cal_{start_date}_{effective_end_date}.parquet"
        self.store.write_file(raw_root, filename, frame)
        self.store.write_file(canonical_root, filename, frame)

        min_date, max_date = self._resolve_date_range(frame, "cal_date")
        self._register_dataset("trade_cal", canonical_root, min_date, max_date, len(frame))
        return frame

    def import_suspend_d(self, start_date: str = "20220101", end_date: str | None = None) -> pd.DataFrame:
        effective_end_date = end_date or today_yyyymmdd()
        return self._import_daily_range_dataset(
            endpoint="suspend_d",
            dataset_name="suspend_d",
            start_date=start_date,
            end_date=effective_end_date,
        )

    def import_stk_limit(self, start_date: str = "20220101", end_date: str | None = None) -> pd.DataFrame:
        effective_end_date = end_date or today_yyyymmdd()
        return self._import_daily_range_dataset(
            endpoint="stk_limit",
            dataset_name="stk_limit",
            start_date=start_date,
            end_date=effective_end_date,
        )

    def import_stock_st(self, start_date: str = "20220101", end_date: str | None = None) -> pd.DataFrame:
        effective_end_date = end_date or today_yyyymmdd()
        return self._import_daily_range_dataset(
            endpoint="stock_st",
            dataset_name="stock_st",
            start_date=start_date,
            end_date=effective_end_date,
        )

    def import_index_classify(self, source: str = "SW2021") -> pd.DataFrame:
        dataset_name = f"index_classify_{source.lower()}"
        frame = self.client.fetch("index_classify", src=source)
        frame = self._normalize(frame, ["level", "industry_code", "index_code"])
        return self._import_static_dataset(frame, dataset_name=dataset_name, date_column="index_code")

    def import_index_member(
        self,
        source: str = "SW2021",
        is_new: str = "N",
        index_codes: list[str] | None = None,
    ) -> dict[str, int]:
        dataset_name = f"index_member_{source.lower()}"
        raw_root = self.settings.storage.raw_dir / "tushare" / dataset_name
        canonical_root = self.settings.storage.canonical_dir / dataset_name

        if index_codes is None:
            classify = self.client.fetch("index_classify", src=source)
            candidate_column = "index_code" if "index_code" in classify.columns else "industry_code"
            index_codes = sorted(classify[candidate_column].dropna().astype(str).unique().tolist())

        total_rows = 0
        imported_codes = 0
        min_date: str | None = None
        max_date: str | None = None

        for index_code in index_codes:
            frame = self.client.fetch("index_member", index_code=index_code, is_new=is_new)
            frame = self._normalize(frame, ["index_code", "con_code", "in_date", "out_date"])
            if frame.empty:
                continue
            filename = f"{index_code.replace('.', '_')}.parquet"
            self.store.write_file(raw_root, filename, frame)
            self.store.write_file(canonical_root, filename, frame)
            imported_codes += 1
            total_rows += len(frame)
            code_min, code_max = self._resolve_multi_date_range(frame, ["in_date", "out_date"])
            min_date = code_min if min_date is None else min(min_date, code_min)
            max_date = code_max if max_date is None else max(max_date, code_max)

        if total_rows > 0 and min_date is not None and max_date is not None:
            self._register_dataset(dataset_name, canonical_root, min_date, max_date, total_rows)

        return {
            "imported_codes": imported_codes,
            "total_rows": total_rows,
            "min_date": min_date or today_yyyymmdd(),
            "max_date": max_date or today_yyyymmdd(),
        }

    def import_index_daily(
        self,
        start_date: str = "20220101",
        end_date: str | None = None,
        ts_codes: list[str] | None = None,
    ) -> dict[str, int]:
        effective_end_date = end_date or today_yyyymmdd()
        codes = ts_codes or DEFAULT_BENCHMARK_INDEXES
        raw_root = self.settings.storage.raw_dir / "tushare" / "index_daily"
        canonical_root = self.settings.storage.canonical_dir / "index_daily"

        total_rows = 0
        min_date: str | None = None
        max_date: str | None = None
        imported_codes = 0

        for ts_code in codes:
            frame = self.client.fetch("index_daily", ts_code=ts_code, start_date=start_date, end_date=effective_end_date)
            frame = self._normalize(frame, ["trade_date", "ts_code"])
            if frame.empty:
                continue

            filename = f"{ts_code.replace('.', '_')}.parquet"
            self.store.write_file(raw_root, filename, frame)
            self.store.write_file(canonical_root, filename, frame)

            imported_codes += 1
            total_rows += len(frame)
            code_min, code_max = self._resolve_date_range(frame, "trade_date")
            min_date = code_min if min_date is None else min(min_date, code_min)
            max_date = code_max if max_date is None else max(max_date, code_max)

        if total_rows > 0 and min_date is not None and max_date is not None:
            self._register_dataset("index_daily", canonical_root, min_date, max_date, total_rows)

        return {
            "imported_codes": imported_codes,
            "total_rows": total_rows,
            "min_date": min_date or start_date,
            "max_date": max_date or effective_end_date,
        }

    def _import_range_dataset(
        self,
        endpoint: str,
        dataset_name: str,
        start_date: str,
        end_date: str,
        date_column: str,
        sort_columns: list[str],
    ) -> pd.DataFrame:
        frame = self.client.fetch(endpoint, start_date=start_date, end_date=end_date)
        frame = self._normalize(frame, sort_columns)

        raw_root = self.settings.storage.raw_dir / "tushare" / dataset_name
        canonical_root = self.settings.storage.canonical_dir / dataset_name
        filename = f"{dataset_name}_{start_date}_{end_date}.parquet"
        self.store.write_file(raw_root, filename, frame)
        self.store.write_file(canonical_root, filename, frame)

        min_date, max_date = self._resolve_date_range(frame, date_column)
        self._register_dataset(dataset_name, canonical_root, min_date, max_date, len(frame))
        return frame

    def _import_daily_range_dataset(self, endpoint: str, dataset_name: str, start_date: str, end_date: str) -> pd.DataFrame:
        trade_dates = self._fetch_trade_dates(start_date, end_date)
        raw_root = self.settings.storage.raw_dir / "tushare" / dataset_name
        canonical_root = self.settings.storage.canonical_dir / dataset_name

        frames: list[pd.DataFrame] = []
        for trade_date in trade_dates:
            frame = self.client.fetch(endpoint, trade_date=trade_date)
            frame = self._normalize(frame, ["trade_date", "ts_code"])
            if frame.empty:
                continue
            self.store.write_partition(raw_root, "trade_date", trade_date, frame)
            self.store.write_partition(canonical_root, "trade_date", trade_date, frame)
            frames.append(frame)

        if not frames:
            empty = pd.DataFrame()
            self._register_dataset(dataset_name, canonical_root, start_date, end_date, 0)
            return empty

        full_frame = pd.concat(frames, ignore_index=True)
        min_date, max_date = self._resolve_date_range(full_frame, "trade_date")
        self._register_dataset(dataset_name, canonical_root, min_date, max_date, len(full_frame))
        return full_frame

    def _import_static_dataset(self, frame: pd.DataFrame, dataset_name: str, date_column: str) -> pd.DataFrame:
        raw_root = self.settings.storage.raw_dir / "tushare" / dataset_name
        canonical_root = self.settings.storage.canonical_dir / dataset_name
        self.store.write_dataset(raw_root, frame)
        self.store.write_dataset(canonical_root, frame)
        min_date, max_date = self._resolve_date_range(frame, date_column)
        self._register_dataset(dataset_name, canonical_root, min_date, max_date, len(frame))
        return frame

    def _fetch_trade_dates(self, start_date: str, end_date: str) -> list[str]:
        calendar = self.client.fetch("trade_cal", exchange="", start_date=start_date, end_date=end_date, is_open="1")
        if calendar.empty:
            return []
        return sorted(calendar["cal_date"].astype(str).tolist())

    def _normalize(self, frame: pd.DataFrame, sort_columns: list[str]) -> pd.DataFrame:
        if frame.empty:
            return frame
        normalized = frame.copy()
        for column in ["list_date", "delist_date", "cal_date", "pretrade_date", "trade_date", "in_date", "out_date", "index_code", "industry_code"]:
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

    def _resolve_multi_date_range(self, frame: pd.DataFrame, date_columns: list[str]) -> tuple[str, str]:
        candidates: list[str] = []
        for column in date_columns:
            if column not in frame.columns:
                continue
            values = frame[column].astype(str)
            values = values[values != ""]
            if not values.empty:
                candidates.extend(values.tolist())
        if not candidates:
            today = today_yyyymmdd()
            return today, today
        return min(candidates), max(candidates)

    def _register_dataset(self, dataset_name: str, dataset_root: Path, min_date: str, max_date: str, row_count: int) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        self.registry.update_watermark(dataset_name, min_date, max_date, row_count, now, "ready")
        glob_path = self.registry.dataset_glob_path(dataset_root)
        self.registry.register_view(dataset_name, glob_path)
