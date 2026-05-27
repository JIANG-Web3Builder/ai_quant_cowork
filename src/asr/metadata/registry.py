from __future__ import annotations

import sqlite3
from pathlib import Path

import duckdb


class MetadataRegistry:
    def __init__(self, duckdb_path: Path, sqlite_path: Path) -> None:
        duckdb_path.parent.mkdir(parents=True, exist_ok=True)
        sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self.duckdb_path = duckdb_path
        self.sqlite_path = sqlite_path
        self._init_sqlite()

    def _init_sqlite(self) -> None:
        with sqlite3.connect(self.sqlite_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS dataset_watermark (
                    dataset_name TEXT PRIMARY KEY,
                    min_date TEXT,
                    max_date TEXT,
                    row_count INTEGER,
                    last_update_time TEXT,
                    status TEXT
                )
                """
            )

    def update_watermark(self, dataset_name: str, min_date: str, max_date: str, row_count: int, last_update_time: str, status: str) -> None:
        with sqlite3.connect(self.sqlite_path) as conn:
            conn.execute(
                """
                INSERT INTO dataset_watermark (dataset_name, min_date, max_date, row_count, last_update_time, status)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(dataset_name) DO UPDATE SET
                    min_date=excluded.min_date,
                    max_date=excluded.max_date,
                    row_count=excluded.row_count,
                    last_update_time=excluded.last_update_time,
                    status=excluded.status
                """,
                (dataset_name, min_date, max_date, row_count, last_update_time, status),
            )

    def dataset_glob_path(self, dataset_root: Path) -> str:
        if dataset_root.exists():
            partition_dirs = [child for child in dataset_root.iterdir() if child.is_dir() and "=" in child.name]
            if partition_dirs:
                return dataset_root.as_posix() + "/*/*.parquet"
        return dataset_root.as_posix() + "/**/*.parquet"

    def register_view(self, view_name: str, glob_path: str) -> None:
        with duckdb.connect(str(self.duckdb_path)) as conn:
            conn.execute(
                f"CREATE OR REPLACE VIEW {view_name} AS SELECT * FROM read_parquet('{glob_path}', hive_partitioning=true, union_by_name=true)"
            )
