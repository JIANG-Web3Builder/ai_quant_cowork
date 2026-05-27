from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from asr.config.settings import load_settings
from asr.metadata.registry import MetadataRegistry
from asr.utils.logging import setup_logging


def main() -> None:
    setup_logging()
    settings = load_settings(ROOT_DIR)
    registry = MetadataRegistry(settings.storage.duckdb_path, settings.storage.sqlite_path)

    with sqlite3.connect(settings.storage.sqlite_path) as conn:
        dataset_names = [row[0] for row in conn.execute("select dataset_name from dataset_watermark order by dataset_name").fetchall()]

    for dataset_name in dataset_names:
        canonical_root = settings.storage.canonical_dir / dataset_name
        panel_root = settings.storage.panel_dir / dataset_name
        dataset_root = canonical_root if canonical_root.exists() else panel_root
        if not dataset_root.exists():
            continue
        registry.register_view(dataset_name, registry.dataset_glob_path(dataset_root))
        print(f"Refreshed view: {dataset_name}")


if __name__ == "__main__":
    main()
