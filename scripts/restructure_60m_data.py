from __future__ import annotations

import shutil
from pathlib import Path

import pandas as pd

ROOT = Path(r"D:\a_stock_research")
MIN60_SOURCE = ROOT / "60m" / "60分钟" / "60分钟"
MIN60_TARGET = ROOT / "60m" / "stock_data"
MIN60_PARQUET_TARGET = ROOT / "60m" / "stock_data_parquet"
ADJ_SOURCE = ROOT / "复权因子(同花顺)_20260520_102229" / "复权因子(同花顺)"
ADJ_TARGET = ROOT / "60m" / "ths_adj_factor"


def move_minute_files() -> tuple[int, int]:
    MIN60_TARGET.mkdir(parents=True, exist_ok=True)
    moved = 0
    skipped = 0
    for source_file in sorted(MIN60_SOURCE.glob("*.csv")):
        target_file = MIN60_TARGET / source_file.name
        if target_file.exists():
            skipped += 1
            continue
        shutil.move(str(source_file), str(target_file))
        moved += 1
    return moved, skipped


def convert_minute_files_to_parquet() -> tuple[int, int]:
    MIN60_PARQUET_TARGET.mkdir(parents=True, exist_ok=True)
    converted = 0
    skipped = 0
    for source_file in sorted(MIN60_TARGET.glob("*.csv")):
        ts_code = source_file.stem
        target_file = MIN60_PARQUET_TARGET / f"{ts_code}.parquet"
        if target_file.exists():
            skipped += 1
            continue
        frame = pd.read_csv(source_file)
        rename_map = {
            "日期": "trade_date",
            "时间": "trade_time",
            "开盘": "open",
            "最高": "high",
            "最低": "low",
            "收盘": "close",
            "成交量": "volume",
            "成交额": "amount",
        }
        frame = frame.rename(columns=rename_map)
        frame = frame[["trade_date", "trade_time", "open", "high", "low", "close", "volume", "amount"]]
        raw_trade_time = frame["trade_time"].copy()
        frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce").dt.strftime("%Y%m%d")
        frame["trade_time"] = pd.to_datetime(frame["trade_time"], format="%H:%M", errors="coerce").dt.strftime("%H:%M:%S")
        missing_time = frame["trade_time"].isna()
        if missing_time.any():
            frame.loc[missing_time, "trade_time"] = pd.to_datetime(
                raw_trade_time.loc[missing_time], errors="coerce"
            ).dt.strftime("%H:%M:%S")
        frame.insert(0, "ts_code", ts_code)
        frame["trade_datetime"] = pd.to_datetime(
            frame["trade_date"].fillna("") + " " + frame["trade_time"].fillna(""),
            format="%Y%m%d %H:%M:%S",
            errors="coerce",
        )
        frame = frame.dropna(subset=["trade_date", "trade_time", "trade_datetime"])
        frame = frame[["ts_code", "trade_date", "trade_time", "trade_datetime", "open", "high", "low", "close", "volume", "amount"]]
        frame = frame.sort_values(["trade_date", "trade_time"]).reset_index(drop=True)
        frame.to_parquet(target_file, index=False)
        converted += 1
    return converted, skipped


def convert_adjustment_factors() -> tuple[int, int]:
    ADJ_TARGET.mkdir(parents=True, exist_ok=True)
    converted = 0
    skipped = 0
    for source_file in sorted(ADJ_SOURCE.glob("*.csv")):
        ts_code = source_file.stem
        target_file = ADJ_TARGET / f"{ts_code}.parquet"
        if target_file.exists():
            skipped += 1
            continue
        frame = pd.read_csv(source_file)
        rename_map = {
            "日期": "trade_date",
            "前复权因子": "qfq_factor",
            "后复权因子": "hfq_factor",
        }
        frame = frame.rename(columns=rename_map)
        frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce").dt.strftime("%Y%m%d")
        frame.insert(0, "ts_code", ts_code)
        frame = frame[["ts_code", "trade_date", "qfq_factor", "hfq_factor"]]
        frame = frame.dropna(subset=["trade_date"]).sort_values("trade_date").reset_index(drop=True)
        frame.to_parquet(target_file, index=False)
        converted += 1
    return converted, skipped


def main() -> None:
    if not MIN60_SOURCE.exists() and not MIN60_TARGET.exists():
        raise FileNotFoundError(f"60分钟目录不存在: {MIN60_SOURCE} / {MIN60_TARGET}")
    if not ADJ_SOURCE.exists() and not ADJ_TARGET.exists():
        raise FileNotFoundError(f"复权因子目录不存在: {ADJ_SOURCE} / {ADJ_TARGET}")

    if MIN60_SOURCE.exists():
        moved, minute_skipped = move_minute_files()
    else:
        moved, minute_skipped = 0, 0

    minute_parquet_converted, minute_parquet_skipped = convert_minute_files_to_parquet()

    if ADJ_SOURCE.exists():
        converted, adj_skipped = convert_adjustment_factors()
    else:
        converted, adj_skipped = 0, len(list(ADJ_TARGET.glob("*.parquet")))

    print(f"minute_files_moved={moved}")
    print(f"minute_files_skipped={minute_skipped}")
    print(f"minute_parquet_files_converted={minute_parquet_converted}")
    print(f"minute_parquet_files_skipped={minute_parquet_skipped}")
    print(f"adj_factor_files_converted={converted}")
    print(f"adj_factor_files_skipped={adj_skipped}")
    print(f"minute_target={MIN60_TARGET}")
    print(f"minute_parquet_target={MIN60_PARQUET_TARGET}")
    print(f"adj_target={ADJ_TARGET}")


if __name__ == "__main__":
    main()
