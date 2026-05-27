from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


class ParquetStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def write_partition(self, dataset_root: Path, partition_key: str, partition_value: str, frame: pd.DataFrame) -> Path:
        target_dir = dataset_root / f"{partition_key}={partition_value}"
        target_dir.mkdir(parents=True, exist_ok=True)
        target_file = target_dir / "part.parquet"
        table = pa.Table.from_pandas(frame, preserve_index=False)
        pq.write_table(table, target_file)
        return target_file

    def write_dataset(self, dataset_root: Path, frame: pd.DataFrame, filename: str = "part.parquet") -> Path:
        dataset_root.mkdir(parents=True, exist_ok=True)
        target_file = dataset_root / filename
        table = pa.Table.from_pandas(frame, preserve_index=False)
        pq.write_table(table, target_file)
        return target_file

    def write_file(self, dataset_root: Path, filename: str, frame: pd.DataFrame) -> Path:
        dataset_root.mkdir(parents=True, exist_ok=True)
        target_file = dataset_root / filename
        table = pa.Table.from_pandas(frame, preserve_index=False)
        pq.write_table(table, target_file)
        return target_file
