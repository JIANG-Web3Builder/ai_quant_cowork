from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml
from dotenv import load_dotenv


@dataclass(slots=True)
class TushareSettings:
    token: str
    pause_seconds: float
    max_retries: int


@dataclass(slots=True)
class StorageSettings:
    root_dir: Path
    data_dir: Path
    raw_dir: Path
    canonical_dir: Path
    panel_dir: Path
    dataset_dir: Path
    factors_dir: Path
    cache_dir: Path
    result_dir: Path
    metadata_dir: Path
    duckdb_path: Path
    sqlite_path: Path


@dataclass(slots=True)
class AppSettings:
    root_dir: Path
    tushare: TushareSettings
    storage: StorageSettings


def _read_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file) or {}


def load_settings(root_dir: Path | None = None) -> AppSettings:
    base_dir = root_dir or Path(__file__).resolve().parents[3]
    load_dotenv(base_dir / ".env")

    data_source_config = _read_yaml(base_dir / "configs" / "data_sources.yaml")
    storage_config = _read_yaml(base_dir / "configs" / "storage.yaml").get("storage", {})

    token = os.getenv("TUSHARE_TOKEN", "").strip()
    if not token:
        raise ValueError("TUSHARE_TOKEN is not set. Please create a .env file or set an environment variable.")

    data_dir = base_dir / storage_config.get("data_dir", "data")
    metadata_dir = data_dir / storage_config.get("metadata_dir", "metadata")

    storage = StorageSettings(
        root_dir=base_dir,
        data_dir=data_dir,
        raw_dir=data_dir / storage_config.get("raw_dir", "raw"),
        canonical_dir=data_dir / storage_config.get("canonical_dir", "canonical"),
        panel_dir=data_dir / storage_config.get("panel_dir", "panel"),
        dataset_dir=data_dir / storage_config.get("dataset_dir", "dataset"),
        factors_dir=data_dir / storage_config.get("factors_dir", "factors"),
        cache_dir=data_dir / storage_config.get("cache_dir", "cache"),
        result_dir=data_dir / storage_config.get("result_dir", "result"),
        metadata_dir=metadata_dir,
        duckdb_path=metadata_dir / storage_config.get("duckdb_name", "research.duckdb"),
        sqlite_path=metadata_dir / storage_config.get("sqlite_name", "metadata.sqlite"),
    )

    tushare_config = data_source_config.get("tushare", {})
    tushare_settings = TushareSettings(
        token=token,
        pause_seconds=float(tushare_config.get("pause_seconds", 0.2)),
        max_retries=int(tushare_config.get("max_retries", 3)),
    )

    return AppSettings(root_dir=base_dir, tushare=tushare_settings, storage=storage)
