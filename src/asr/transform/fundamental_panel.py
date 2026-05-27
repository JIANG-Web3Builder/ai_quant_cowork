from __future__ import annotations

import pandas as pd


DEFAULT_FUNDAMENTAL_COLUMNS = [
    "ts_code",
    "ann_date",
    "end_date",
    "roe",
    "roe_dt",
    "roa",
    "gross_margin",
    "current_ratio",
    "quick_ratio",
    "debt_to_assets",
    "ocfps",
    "bps",
    "q_roe",
    "q_sales_yoy",
    "q_op_qoq",
    "netprofit_yoy",
    "dt_netprofit_yoy",
    "ocf_yoy",
    "or_yoy",
]


def build_daily_fundamental_base(
    daily_base: pd.DataFrame,
    fina_indicator: pd.DataFrame,
    fundamental_columns: list[str] | None = None,
) -> pd.DataFrame:
    if daily_base.empty:
        return daily_base.copy()
    if fina_indicator.empty:
        return daily_base.copy()

    selected_columns = fundamental_columns or DEFAULT_FUNDAMENTAL_COLUMNS
    available_columns = [column for column in selected_columns if column in fina_indicator.columns]
    if "ts_code" not in available_columns:
        available_columns.insert(0, "ts_code")
    if "ann_date" not in available_columns:
        available_columns.insert(1, "ann_date")
    if "end_date" not in available_columns and "end_date" in fina_indicator.columns:
        available_columns.insert(2, "end_date")

    market = daily_base.copy()
    market["ts_code"] = market["ts_code"].astype(str)
    market["trade_date"] = market["trade_date"].astype(str)
    market["trade_dt"] = pd.to_datetime(market["trade_date"], format="%Y%m%d", errors="coerce")

    funda = fina_indicator[available_columns].copy()
    funda["ts_code"] = funda["ts_code"].astype(str)
    funda["ann_date"] = funda["ann_date"].astype(str)
    funda = funda[funda["ann_date"] != ""]
    funda["ann_dt"] = pd.to_datetime(funda["ann_date"], format="%Y%m%d", errors="coerce")
    funda = funda.dropna(subset=["ann_dt"])

    merged_parts: list[pd.DataFrame] = []
    for ts_code, market_part in market.groupby("ts_code", sort=False):
        funda_part = funda[funda["ts_code"] == ts_code].sort_values("ann_dt")
        market_part = market_part.sort_values("trade_dt")
        if funda_part.empty:
            merged_parts.append(market_part)
            continue
        merged = pd.merge_asof(
            market_part,
            funda_part,
            left_on="trade_dt",
            right_on="ann_dt",
            direction="backward",
        )
        if "ts_code_x" in merged.columns:
            merged = merged.rename(columns={"ts_code_x": "ts_code"})
        if "ts_code_y" in merged.columns:
            merged = merged.drop(columns=["ts_code_y"])
        merged_parts.append(merged)

    panel = pd.concat(merged_parts, ignore_index=True)
    drop_columns = [column for column in ["trade_dt", "ann_dt"] if column in panel.columns]
    if drop_columns:
        panel = panel.drop(columns=drop_columns)
    return panel.sort_values(["trade_date", "ts_code"]).reset_index(drop=True)
