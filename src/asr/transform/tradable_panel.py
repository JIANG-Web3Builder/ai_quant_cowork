from __future__ import annotations

import pandas as pd


EPSILON = 1e-8


def build_tradable_daily_base(
    daily_base: pd.DataFrame,
    stock_basic: pd.DataFrame,
    suspend_d: pd.DataFrame,
    stk_limit: pd.DataFrame,
    stock_st: pd.DataFrame | None = None,
) -> pd.DataFrame:
    panel = daily_base.copy()
    panel["ts_code"] = panel["ts_code"].astype(str)
    panel["trade_date"] = panel["trade_date"].astype(str)

    stock_columns = [column for column in ["ts_code", "name", "market", "list_status", "list_date", "delist_date"] if column in stock_basic.columns]
    if stock_columns:
        stock_info = stock_basic[stock_columns].drop_duplicates(subset=["ts_code"])
        stock_info["ts_code"] = stock_info["ts_code"].astype(str)
        panel = panel.merge(stock_info, on="ts_code", how="left")

    if not suspend_d.empty:
        suspend_info = suspend_d.copy()
        if "ts_code" in suspend_info.columns:
            suspend_info["ts_code"] = suspend_info["ts_code"].astype(str)
        if "trade_date" in suspend_info.columns:
            suspend_info["trade_date"] = suspend_info["trade_date"].astype(str)
        keep_columns = [column for column in ["ts_code", "trade_date", "suspend_type"] if column in suspend_info.columns]
        suspend_info = suspend_info[keep_columns].drop_duplicates(subset=["ts_code", "trade_date"])
        suspend_info["is_suspended"] = suspend_info.get("suspend_type", "") == "S"
        panel = panel.merge(suspend_info[["ts_code", "trade_date", "is_suspended"]], on=["ts_code", "trade_date"], how="left")
    else:
        panel["is_suspended"] = False

    if "is_suspended" not in panel.columns:
        panel["is_suspended"] = False
    panel["is_suspended"] = panel["is_suspended"].fillna(False).astype(bool)

    stock_st = pd.DataFrame() if stock_st is None else stock_st
    if not stock_st.empty:
        st_info = stock_st.copy()
        if "ts_code" in st_info.columns:
            st_info["ts_code"] = st_info["ts_code"].astype(str)
        if "trade_date" in st_info.columns:
            st_info["trade_date"] = st_info["trade_date"].astype(str)
        keep_columns = [column for column in ["ts_code", "trade_date", "type", "type_name"] if column in st_info.columns]
        st_info = st_info[keep_columns].drop_duplicates(subset=["ts_code", "trade_date"])
        st_info["is_st"] = True
        panel = panel.merge(st_info[["ts_code", "trade_date", "is_st"]], on=["ts_code", "trade_date"], how="left")

    if "is_st" not in panel.columns:
        panel["is_st"] = False
    panel["is_st"] = panel["is_st"].fillna(False).astype(bool)

    if not stk_limit.empty:
        stk_limit = stk_limit.copy()
        if "ts_code" in stk_limit.columns:
            stk_limit["ts_code"] = stk_limit["ts_code"].astype(str)
        if "trade_date" in stk_limit.columns:
            stk_limit["trade_date"] = stk_limit["trade_date"].astype(str)
        limit_columns = [column for column in ["ts_code", "trade_date", "up_limit", "down_limit"] if column in stk_limit.columns]
        limit_info = stk_limit[limit_columns].drop_duplicates(subset=["ts_code", "trade_date"])
        panel = panel.merge(limit_info, on=["ts_code", "trade_date"], how="left")

    if "up_limit" not in panel.columns:
        panel["up_limit"] = pd.NA
    if "down_limit" not in panel.columns:
        panel["down_limit"] = pd.NA

    panel["hit_up_limit"] = panel["up_limit"].notna() & (panel["close"] >= panel["up_limit"] - EPSILON)
    panel["hit_down_limit"] = panel["down_limit"].notna() & (panel["close"] <= panel["down_limit"] + EPSILON)
    panel["can_buy"] = (~panel["is_suspended"]) & (~panel["hit_up_limit"])
    panel["can_sell"] = (~panel["is_suspended"]) & (~panel["hit_down_limit"])
    panel["is_tradable"] = panel["can_buy"] & panel["can_sell"]

    if "list_date" in panel.columns:
        trade_dt = pd.to_datetime(panel["trade_date"], format="%Y%m%d", errors="coerce")
        list_dt = pd.to_datetime(panel["list_date"], format="%Y%m%d", errors="coerce")
        panel["listed_days"] = (trade_dt - list_dt).dt.days
    else:
        panel["listed_days"] = pd.NA

    return panel.sort_values(["trade_date", "ts_code"]).reset_index(drop=True)
