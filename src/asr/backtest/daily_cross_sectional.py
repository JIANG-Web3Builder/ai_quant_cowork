from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(slots=True)
class DailyCrossSectionalBacktestConfig:
    signal_column: str
    top_n: int = 50
    fee_rate: float = 0.001
    min_listed_days: int = 120
    exclude_st: bool = True
    require_tradable: bool = True
    ascending: bool = False


def run_daily_cross_sectional_backtest(
    factor_frame: pd.DataFrame,
    tradable_frame: pd.DataFrame,
    benchmark_frame: pd.DataFrame | None,
    config: DailyCrossSectionalBacktestConfig,
) -> dict[str, pd.DataFrame]:
    required_factor_columns = {"ts_code", "trade_date", "adj_close", config.signal_column}
    missing_factor = required_factor_columns.difference(factor_frame.columns)
    if missing_factor:
        raise ValueError(f"Missing factor columns: {sorted(missing_factor)}")

    required_tradable_columns = {"ts_code", "trade_date"}
    missing_tradable = required_tradable_columns.difference(tradable_frame.columns)
    if missing_tradable:
        raise ValueError(f"Missing tradable columns: {sorted(missing_tradable)}")

    factor_data = factor_frame.copy()
    factor_data["ts_code"] = factor_data["ts_code"].astype(str)
    factor_data["trade_date"] = factor_data["trade_date"].astype(str)
    factor_data = factor_data.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)
    factor_data["next_return"] = factor_data.groupby("ts_code")["adj_close"].shift(-1) / factor_data["adj_close"] - 1

    tradable_columns = [
        column
        for column in ["ts_code", "trade_date", "is_tradable", "is_suspended", "is_st", "listed_days"]
        if column in tradable_frame.columns
    ]
    tradable_data = tradable_frame[tradable_columns].copy()
    tradable_data["ts_code"] = tradable_data["ts_code"].astype(str)
    tradable_data["trade_date"] = tradable_data["trade_date"].astype(str)

    merged = factor_data.merge(tradable_data, on=["ts_code", "trade_date"], how="left")
    if "is_tradable" not in merged.columns:
        merged["is_tradable"] = True
    if "is_st" not in merged.columns:
        merged["is_st"] = False
    if "listed_days" not in merged.columns:
        merged["listed_days"] = pd.NA

    benchmark_returns = _build_benchmark_returns(benchmark_frame)
    performance_rows: list[dict[str, object]] = []
    holding_rows: list[dict[str, object]] = []
    previous_weights: dict[str, float] = {}

    for trade_date, day_frame in merged.groupby("trade_date", sort=True):
        candidates = day_frame.copy()
        candidates = candidates[candidates[config.signal_column].notna()]
        candidates = candidates[candidates["next_return"].notna()]

        if config.require_tradable and "is_tradable" in candidates.columns:
            candidates = candidates[candidates["is_tradable"].fillna(False)]
        if config.exclude_st and "is_st" in candidates.columns:
            candidates = candidates[~candidates["is_st"].fillna(False)]
        if "listed_days" in candidates.columns:
            listed_days = pd.to_numeric(candidates["listed_days"], errors="coerce")
            candidates = candidates[listed_days.isna() | (listed_days >= config.min_listed_days)]

        candidates = candidates.sort_values(config.signal_column, ascending=config.ascending)
        selected = candidates.head(config.top_n).copy()

        if selected.empty:
            target_weights: dict[str, float] = {}
            gross_return = 0.0
        else:
            weight = 1.0 / len(selected)
            target_weights = {ts_code: weight for ts_code in selected["ts_code"].tolist()}
            gross_return = float(selected["next_return"].mean())
            for _, row in selected.iterrows():
                holding_rows.append(
                    {
                        "trade_date": trade_date,
                        "ts_code": row["ts_code"],
                        "signal": row[config.signal_column],
                        "next_return": row["next_return"],
                        "weight": weight,
                    }
                )

        turnover = _compute_turnover(previous_weights, target_weights)
        cost = turnover * config.fee_rate
        net_return = gross_return - cost
        benchmark_return = benchmark_returns.get(str(trade_date))

        performance_rows.append(
            {
                "trade_date": trade_date,
                "holdings_count": len(target_weights),
                "gross_return": gross_return,
                "turnover": turnover,
                "cost": cost,
                "net_return": net_return,
                "benchmark_return": benchmark_return,
                "excess_return": None if benchmark_return is None else net_return - benchmark_return,
            }
        )
        previous_weights = target_weights

    performance = pd.DataFrame(performance_rows)
    if performance.empty:
        performance["strategy_nav"] = pd.Series(dtype=float)
        performance["benchmark_nav"] = pd.Series(dtype=float)
    else:
        performance["strategy_nav"] = (1 + performance["net_return"].fillna(0.0)).cumprod()
        if "benchmark_return" in performance.columns:
            performance["benchmark_nav"] = (1 + performance["benchmark_return"].fillna(0.0)).cumprod()
        else:
            performance["benchmark_nav"] = pd.NA

    holdings = pd.DataFrame(holding_rows)
    summary = _build_summary(performance)
    return {
        "performance": performance,
        "holdings": holdings,
        "summary": summary,
    }


def _compute_turnover(previous_weights: dict[str, float], target_weights: dict[str, float]) -> float:
    all_codes = set(previous_weights).union(target_weights)
    return 0.5 * sum(abs(target_weights.get(code, 0.0) - previous_weights.get(code, 0.0)) for code in all_codes)


def _build_benchmark_returns(benchmark_frame: pd.DataFrame | None) -> dict[str, float]:
    if benchmark_frame is None or benchmark_frame.empty:
        return {}
    benchmark = benchmark_frame.copy()
    benchmark["trade_date"] = benchmark["trade_date"].astype(str)
    if "pct_chg" in benchmark.columns:
        return {row["trade_date"]: float(row["pct_chg"]) / 100.0 for _, row in benchmark.iterrows() if pd.notna(row["pct_chg"])}
    if "close" in benchmark.columns:
        benchmark = benchmark.sort_values("trade_date").reset_index(drop=True)
        benchmark["benchmark_return"] = benchmark["close"].pct_change()
        return {row["trade_date"]: float(row["benchmark_return"]) for _, row in benchmark.iterrows() if pd.notna(row["benchmark_return"])}
    return {}


def _build_summary(performance: pd.DataFrame) -> pd.DataFrame:
    if performance.empty:
        return pd.DataFrame([{"annualized_return": 0.0, "annualized_volatility": 0.0, "sharpe": 0.0, "max_drawdown": 0.0, "win_rate": 0.0, "avg_turnover": 0.0}])

    daily_returns = performance["net_return"].fillna(0.0)
    annualized_return = float((1 + daily_returns.mean()) ** 252 - 1)
    annualized_volatility = float(daily_returns.std(ddof=0) * (252 ** 0.5))
    sharpe = 0.0 if annualized_volatility == 0 else annualized_return / annualized_volatility
    strategy_nav = performance["strategy_nav"].ffill().fillna(1.0)
    rolling_peak = strategy_nav.cummax()
    drawdown = strategy_nav / rolling_peak - 1
    max_drawdown = float(drawdown.min())
    win_rate = float((daily_returns > 0).mean())
    avg_turnover = float(performance["turnover"].fillna(0.0).mean())
    return pd.DataFrame(
        [
            {
                "annualized_return": annualized_return,
                "annualized_volatility": annualized_volatility,
                "sharpe": sharpe,
                "max_drawdown": max_drawdown,
                "win_rate": win_rate,
                "avg_turnover": avg_turnover,
            }
        ]
    )
