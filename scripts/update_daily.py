from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from asr.config.settings import load_settings
from asr.ingestion.historical_importer import HistoricalImporter
from asr.utils.dates import today_yyyymmdd
from asr.utils.logging import setup_logging


if __name__ == "__main__":
    setup_logging()
    today = today_yyyymmdd()
    settings = load_settings(ROOT_DIR)
    importer = HistoricalImporter(settings)
    importer.import_history(start_date=today, end_date=today)
