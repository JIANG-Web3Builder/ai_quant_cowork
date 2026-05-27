from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import pandas as pd

from asr.config.settings import AppSettings
from asr.data_sources.tushare_client import TushareClient
from asr.metadata.registry import MetadataRegistry
from asr.storage.parquet_store import ParquetStore

logger = logging.getLogger(__name__)


class HistoricalImporter:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.client = TushareClient(settings.tushare)
        self.store = ParquetStore(settings.storage.data_dir)
        self.registry = MetadataRegistry(settings.storage.duckdb_path, settings.storage.sqlite_path)

    def import_history(self, start_date: str, end_date: str) -> None:
        self._ensure_directories()
        trade_dates = self._fetch_trade_dates(start_date, end_date)
        stats: dict[str, dict[str, str | int | None]] = {
            "ashare_eod": {"min_date": None, "max_date": None, "row_count": 0},
            "adj_factor": {"min_date": None, "max_date": None, "row_count": 0},
            "daily_basic": {"min_date": None, "max_date": None, "row_count": 0},
            "daily_base": {"min_date": None, "max_date": None, "row_count": 0},
        }

        for index, trade_date in enumerate(trade_dates, start=1):
            daily = self._normalize("daily", self.client.fetch("daily", trade_date=trade_date))
            adj_factor = self._normalize("adj_factor", self.client.fetch("adj_factor", trade_date=trade_date))
            daily_basic = self._normalize("daily_basic", self.client.fetch("daily_basic", trade_date=trade_date))

            self._write_single_day("daily", trade_date, daily, stats)
            self._write_single_day("adj_factor", trade_date, adj_factor, stats)
            self._write_single_day("daily_basic", trade_date, daily_basic, stats)
            self._build_panel_for_date(trade_date, daily, adj_factor, daily_basic, stats)

            if index % 20 == 0 or index == len(trade_dates):
                logger.info("Imported %s/%s trade dates", index, len(trade_dates))

        self._register_dataset("ashare_eod", self.settings.storage.canonical_dir / "ashare_eod", stats["ashare_eod"])
        self._register_dataset("adj_factor", self.settings.storage.canonical_dir / "adj_factor", stats["adj_factor"])
        self._register_dataset("daily_basic", self.settings.storage.canonical_dir / "daily_basic", stats["daily_basic"])
        self._register_dataset("daily_base", self.settings.storage.panel_dir / "daily_base", stats["daily_base"])

    def _ensure_directories(self) -> None:
        for path in [
            self.settings.storage.raw_dir,
            self.settings.storage.canonical_dir,
            self.settings.storage.panel_dir,
            self.settings.storage.metadata_dir,
        ]:
            path.mkdir(parents=True, exist_ok=True)

    def _fetch_trade_dates(self, start_date: str, end_date: str) -> list[str]:
        calendar = self.client.fetch("trade_cal", exchange="", start_date=start_date, end_date=end_date, is_open="1")
        if calendar.empty:
            return []
        return sorted(calendar["cal_date"].astype(str).tolist())

    def _normalize(self, dataset: str, frame: pd.DataFrame) -> pd.DataFrame:
        if frame.empty:
            return frame
        normalized = frame.copy()
        if "trade_date" in normalized.columns:
            normalized["trade_date"] = normalized["trade_date"].astype(str)
        sort_columns = [column for column in ["trade_date", "ts_code"] if column in normalized.columns]
        if sort_columns:
            normalized = normalized.sort_values(sort_columns)
        return normalized

    def _write_single_day(self, dataset: str, trade_date: str, frame: pd.DataFrame, stats: dict[str, dict[str, str | int | None]]) -> None:
        if frame.empty:
            logger.warning("Dataset %s returned empty frame for trade_date=%s", dataset, trade_date)
            return

        raw_root = self.settings.storage.raw_dir / "tushare" / dataset
        canonical_name = {"daily": "ashare_eod", "adj_factor": "adj_factor", "daily_basic": "daily_basic"}[dataset]
        canonical_root = self.settings.storage.canonical_dir / canonical_name

        self.store.write_partition(raw_root, "trade_date", trade_date, frame)
        self.store.write_partition(canonical_root, "trade_date", trade_date, frame)
        self._update_stats(stats[canonical_name], trade_date, len(frame))

    def _update_stats(self, stat: dict[str, str | int | None], trade_date: str, row_count: int) -> None:
        current_min = stat["min_date"]
        current_max = stat["max_date"]
        stat["min_date"] = trade_date if current_min is None else min(str(current_min), trade_date)
        stat["max_date"] = trade_date if current_max is None else max(str(current_max), trade_date)
        stat["row_count"] = int(stat["row_count"] or 0) + row_count

    def _register_dataset(self, dataset_name: str, dataset_root: Path, stat: dict[str, str | int | None]) -> None:
        if not stat["row_count"]:
            return
        now = datetime.now().isoformat(timespec="seconds")
        self.registry.update_watermark(
            dataset_name,
            str(stat["min_date"]),
            str(stat["max_date"]),
            int(stat["row_count"] or 0),
            now,
            "ready",
        )
        glob_path = self.registry.dataset_glob_path(dataset_root)
        self.registry.register_view(dataset_name, glob_path)

    def _drop_overlapping_columns(self, base: pd.DataFrame, other: pd.DataFrame) -> pd.DataFrame:
        key_columns = {"trade_date", "ts_code"}
        overlapping = [column for column in other.columns if column in base.columns and column not in key_columns]
        if not overlapping:
            return other
        return other.drop(columns=overlapping)

    def _build_panel_for_date(
        self,
        trade_date: str,
        daily: pd.DataFrame,
        adj_factor: pd.DataFrame,
        daily_basic: pd.DataFrame,
        stats: dict[str, dict[str, str | int | None]],
    ) -> None:
        if daily.empty:
            return

        panel_root = self.settings.storage.panel_dir / "daily_base"
        panel_root.mkdir(parents=True, exist_ok=True)

        adj_factor = self._drop_overlapping_columns(daily, adj_factor)
        daily_basic = self._drop_overlapping_columns(daily, daily_basic)

        panel = daily.merge(adj_factor, on=["trade_date", "ts_code"], how="left")
        panel = panel.merge(daily_basic, on=["trade_date", "ts_code"], how="left")
        if "adj_factor" not in panel.columns:
            panel["adj_factor"] = 1.0
        panel["adj_factor"] = panel["adj_factor"].fillna(1.0)
        panel["adj_close"] = panel["close"] * panel["adj_factor"]
        panel = panel.sort_values(["trade_date", "ts_code"])

        self.store.write_partition(panel_root, "trade_date", trade_date, panel)
        self._update_stats(stats["daily_base"], trade_date, len(panel))
