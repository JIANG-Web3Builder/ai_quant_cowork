from __future__ import annotations

import numpy as np
import pandas as pd


REQUIRED_COLUMNS = {
    "ts_code",
    "trade_date",
    "adj_close",
    "turnover_rate",
    "turnover_rate_f",
    "pe_ttm",
    "pb",
    "total_mv",
}


def build_first_factor_batch(frame: pd.DataFrame) -> pd.DataFrame:
    missing = REQUIRED_COLUMNS.difference(frame.columns)
    if missing:
        raise ValueError(f"Missing required columns for factor build: {sorted(missing)}")

    data = frame.copy()
    data = data.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)

    grouped = data.groupby("ts_code", group_keys=False)

    data["ret_5"] = grouped["adj_close"].pct_change(5)
    data["ret_20"] = grouped["adj_close"].pct_change(20)
    data["ret_60"] = grouped["adj_close"].pct_change(60)
    data["reversal_5"] = -data["ret_5"]
    data["turnover_5d_avg"] = grouped["turnover_rate"].transform(lambda series: series.rolling(5).mean())
    data["turnover_20d_avg"] = grouped["turnover_rate"].transform(lambda series: series.rolling(20).mean())
    data["log_total_mv"] = data["total_mv"].where(data["total_mv"] > 0).map(lambda value: None if pd.isna(value) else float(np.log(value)))
    data["bp"] = 1 / data["pb"].where(data["pb"] != 0)
    data["ep_ttm"] = 1 / data["pe_ttm"].where(data["pe_ttm"] != 0)

    return data
