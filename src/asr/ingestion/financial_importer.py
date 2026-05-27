from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from asr.config.settings import AppSettings
from asr.data_sources.tushare_client import TushareClient
from asr.metadata.registry import MetadataRegistry
from asr.storage.parquet_store import ParquetStore
from asr.utils.dates import today_yyyymmdd


class FinancialDataImporter:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.client = TushareClient(settings.tushare)
        self.store = ParquetStore(settings.storage.data_dir)
        self.registry = MetadataRegistry(settings.storage.duckdb_path, settings.storage.sqlite_path)

    def import_fina_indicator(self, ts_codes: list[str], start_date: str = "20220101") -> dict[str, int]:
        return self._import_statement_dataset("fina_indicator", ts_codes=ts_codes, start_date=start_date)

    def import_income(self, ts_codes: list[str], start_date: str = "20220101") -> dict[str, int]:
        return self._import_statement_dataset("income", ts_codes=ts_codes, start_date=start_date)

    def import_balancesheet(self, ts_codes: list[str], start_date: str = "20220101") -> dict[str, int]:
        return self._import_statement_dataset("balancesheet", ts_codes=ts_codes, start_date=start_date)

    def import_cashflow(self, ts_codes: list[str], start_date: str = "20220101") -> dict[str, int]:
        return self._import_statement_dataset("cashflow", ts_codes=ts_codes, start_date=start_date)

    def _import_statement_dataset(self, dataset_name: str, ts_codes: list[str], start_date: str = "20220101") -> dict[str, int]:
        raw_root = self.settings.storage.raw_dir / "tushare" / "fina_indicator"
        canonical_root = self.settings.storage.canonical_dir / "fina_indicator"

        if dataset_name != "fina_indicator":
            raw_root = self.settings.storage.raw_dir / "tushare" / dataset_name
            canonical_root = self.settings.storage.canonical_dir / dataset_name

        total_rows = 0
        min_date: str | None = None
        max_date: str | None = None
        imported_codes = 0

        for ts_code in ts_codes:
            frame = self.client.fetch(dataset_name, ts_code=ts_code, start_date=start_date)
            frame = self._normalize(frame)
            if frame.empty:
                continue

            filename = f"{ts_code.replace('.', '_')}.parquet"
            self.store.write_file(raw_root, filename, frame)
            self.store.write_file(canonical_root, filename, frame)

            imported_codes += 1
            total_rows += len(frame)
            code_min, code_max = self._resolve_date_range(frame)
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

    def _normalize(self, frame: pd.DataFrame) -> pd.DataFrame:
        if frame.empty:
            return frame
        normalized = frame.copy()
        for column in ["ann_date", "end_date"]:
            if column in normalized.columns:
                normalized[column] = normalized[column].fillna("").astype(str)
        sort_columns = [column for column in ["ts_code", "end_date", "ann_date"] if column in normalized.columns]
        if sort_columns:
            normalized = normalized.sort_values(sort_columns).reset_index(drop=True)
        return normalized

    def _resolve_date_range(self, frame: pd.DataFrame) -> tuple[str, str]:
        for column in ["end_date", "ann_date"]:
            if column in frame.columns:
                values = frame[column].astype(str)
                values = values[values != ""]
                if not values.empty:
                    return str(values.min()), str(values.max())
        today = today_yyyymmdd()
        return today, today

    def _register_dataset(self, dataset_name: str, dataset_root: Path, min_date: str, max_date: str, row_count: int) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        self.registry.update_watermark(dataset_name, min_date, max_date, row_count, now, "ready")
        glob_path = self.registry.dataset_glob_path(dataset_root)
        self.registry.register_view(dataset_name, glob_path)
