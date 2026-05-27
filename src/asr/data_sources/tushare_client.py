from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

import pandas as pd
import tushare as ts

from asr.config.settings import TushareSettings

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class TushareClient:
    settings: TushareSettings
    pro: Any = field(init=False)

    def __post_init__(self) -> None:
        ts.set_token(self.settings.token)
        self.pro = ts.pro_api()

    def fetch(self, endpoint: str, **kwargs: Any) -> pd.DataFrame:
        last_error: Exception | None = None
        for attempt in range(1, self.settings.max_retries + 1):
            try:
                logger.info("Fetching Tushare endpoint=%s params=%s", endpoint, kwargs)
                frame = getattr(self.pro, endpoint)(**kwargs)
                time.sleep(self.settings.pause_seconds)
                if frame is None:
                    return pd.DataFrame()
                return frame
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                logger.warning("Tushare fetch failed endpoint=%s attempt=%s error=%s", endpoint, attempt, exc)
                time.sleep(self.settings.pause_seconds * attempt)
        raise RuntimeError(f"Failed to fetch endpoint={endpoint}") from last_error
