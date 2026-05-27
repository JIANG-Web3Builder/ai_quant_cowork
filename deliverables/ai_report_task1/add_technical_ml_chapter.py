from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from shutil import copy2

import duckdb
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np
import pandas as pd
from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor


ROOT_DIR = Path(__file__).resolve().parents[2]
WORK_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = WORK_DIR / "outputs_enhanced"
REPORT_DIR = OUTPUT_DIR / "report"
TECH_DIR = OUTPUT_DIR / "technical_ml"
TABLE_DIR = TECH_DIR / "tables"
FIGURE_DIR = TECH_DIR / "figures"
DUCKDB_PATH = ROOT_DIR / "data" / "metadata" / "research.duckdb"

START_DATE = "20230101"
MODEL_TRAIN_END_DATE = "20241129"
TEST_START_DATE = "20250101"
BENCHMARK_CODE = "000300.SH"
DEFAULT_FEE_RATE = 0.001
FONT = "Microsoft YaHei"
BLUE = RGBColor(31, 78, 121)
CHAPTER_TITLE = "十一、技术因子扩展与机器学习模型增强"

FUNDAMENTAL_FEATURES = [
    "bp",
    "ep_ttm",
    "dividend_yield",
    "neg_log_total_mv",
    "quality_roe",
    "quality_roa",
    "cashflow_ocfps",
    "growth_sales_yoy",
    "growth_profit_yoy",
    "low_leverage",
]

TECHNICAL_FACTORS = [
    "reversal_1",
    "reversal_5",
    "reversal_20",
    "momentum_20",
    "momentum_60",
    "momentum_120",
    "momentum_120_20",
    "relative_ret_20",
    "relative_ret_60",
    "neg_volatility_20",
    "neg_volatility_60",
    "neg_turnover_20d_avg",
    "turnover_5_20",
    "amount_5_20",
    "bias_5",
    "bias_20",
    "bias_60",
    "ma5_ma20",
    "ma20_ma60",
    "range_position_20",
    "breakout_20",
    "boll_pos_20",
    "rsi_14",
    "neg_atr_14_pct",
    "neg_amihud_20",
]

ML_FEATURES = FUNDAMENTAL_FEATURES + TECHNICAL_FACTORS

TARGET_LABELS = {
    "next_5d_return": "未来5日收益",
    "next_20d_return": "未来20日收益",
}

FACTOR_LABELS = {
    "bp": "估值BP",
    "ep_ttm": "估值EP(TTM)",
    "dividend_yield": "股息率",
    "neg_log_total_mv": "小市值暴露",
    "quality_roe": "ROE质量",
    "quality_roa": "ROA质量",
    "cashflow_ocfps": "经营现金流",
    "growth_sales_yoy": "收入成长",
    "growth_profit_yoy": "利润成长",
    "low_leverage": "低杠杆",
    "reversal_1": "1日反转",
    "reversal_5": "5日反转",
    "reversal_20": "20日反转",
    "momentum_20": "20日动量",
    "momentum_60": "60日动量",
    "momentum_120": "120日动量",
    "momentum_120_20": "中长期动量剔除近端",
    "relative_ret_20": "相对沪深300强度20日",
    "relative_ret_60": "相对沪深300强度60日",
    "neg_volatility_20": "20日低波动",
    "neg_volatility_60": "60日低波动",
    "neg_turnover_20d_avg": "20日低换手",
    "turnover_5_20": "短期换手放大",
    "amount_5_20": "短期成交额放大",
    "bias_5": "5日乖离率",
    "bias_20": "20日乖离率",
    "bias_60": "60日乖离率",
    "ma5_ma20": "均线斜率5/20",
    "ma20_ma60": "均线斜率20/60",
    "range_position_20": "20日价格区间位置",
    "breakout_20": "20日突破强度",
    "boll_pos_20": "布林带位置",
    "rsi_14": "RSI14",
    "neg_atr_14_pct": "低ATR波动",
    "neg_amihud_20": "低冲击成本",
}


@dataclass(frozen=True)
class BacktestResult:
    performance: pd.DataFrame
    summary: pd.DataFrame


def winsorized_zscore(series: pd.Series, lower: float = 0.01, upper: float = 0.99) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan)
    if values.notna().sum() < 3:
        return pd.Series(np.zeros(len(series)), index=series.index, dtype=float)
    clipped = values.clip(values.quantile(lower), values.quantile(upper))
    std = clipped.std(ddof=0)
    if pd.isna(std) or std == 0:
        return pd.Series(np.zeros(len(series)), index=series.index, dtype=float)
    return ((clipped - clipped.mean()) / std).fillna(0.0)


def compute_rsi(close: pd.Series, window: int = 14) -> pd.Series:
    prices = pd.to_numeric(close, errors="coerce")
    delta = prices.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.rolling(window, min_periods=max(3, window // 2)).mean()
    avg_loss = loss.rolling(window, min_periods=max(3, window // 2)).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100.0 - 100.0 / (1.0 + rs)
    return ((rsi - 50.0) / 50.0).replace([np.inf, -np.inf], np.nan)


def fit_ridge(x: np.ndarray, y: np.ndarray, alpha: float = 10.0) -> np.ndarray:
    x_arr = np.asarray(x, dtype=float)
    y_arr = np.asarray(y, dtype=float)
    mask = np.isfinite(y_arr) & np.isfinite(x_arr).all(axis=1)
    x_arr = x_arr[mask]
    y_arr = y_arr[mask]
    if x_arr.ndim != 2 or x_arr.shape[0] == 0:
        raise ValueError("x must contain at least one valid two-dimensional observation")
    xtx = x_arr.T @ x_arr
    ridge = np.eye(x_arr.shape[1], dtype=float) * float(alpha)
    xty = x_arr.T @ y_arr
    return np.linalg.solve(xtx + ridge, xty)


def select_best_model(table: pd.DataFrame) -> pd.Series:
    if table.empty:
        raise ValueError("model selection table is empty")
    frame = table.copy()
    for column in ["train_objective", "train_sharpe", "train_excess_annualized_return"]:
        if column not in frame.columns:
            frame[column] = 0.0
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0.0)
    return frame.sort_values(
        ["train_objective", "train_sharpe", "train_excess_annualized_return"],
        ascending=False,
    ).iloc[0]


def configure_plot_font() -> None:
    for font_path in [
        Path(r"C:\Windows\Fonts\msyh.ttc"),
        Path(r"C:\Windows\Fonts\msyhbd.ttc"),
        Path(r"C:\Windows\Fonts\simhei.ttf"),
        Path(r"C:\Windows\Fonts\simsun.ttc"),
    ]:
        if font_path.exists():
            font_manager.fontManager.addfont(str(font_path))
            font_name = font_manager.FontProperties(fname=str(font_path)).get_name()
            plt.rcParams["font.family"] = [font_name]
            plt.rcParams["font.sans-serif"] = [font_name, "DejaVu Sans"]
            plt.rcParams["axes.unicode_minus"] = False
            return
    plt.rcParams["font.sans-serif"] = ["DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False


def ensure_directories() -> None:
    for path in [TECH_DIR, TABLE_DIR, FIGURE_DIR]:
        path.mkdir(parents=True, exist_ok=True)


def connect_duckdb() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(DUCKDB_PATH), read_only=True)


def load_daily_frame(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    sql = f"""
    select
        f.ts_code,
        cast(f.trade_date as varchar) as trade_date,
        f.open,
        f.high,
        f.low,
        f.close,
        f.pre_close,
        f.pct_chg,
        f.amount,
        f.adj_close,
        f.turnover_rate,
        f.turnover_rate_f,
        f.volume_ratio,
        f.pe_ttm,
        f.pb,
        f.dv_ttm,
        f.total_mv,
        f.circ_mv,
        f.roe,
        f.roa,
        f.debt_to_assets,
        f.ocfps,
        f.q_sales_yoy,
        f.netprofit_yoy,
        t.name,
        t.market,
        t.is_tradable,
        t.can_buy,
        t.can_sell,
        t.listed_days,
        s.industry
    from daily_fundamental_base f
    left join tradable_daily_base t
      on f.ts_code = t.ts_code and f.trade_date = t.trade_date
    left join stock_basic s
      on f.ts_code = s.ts_code
    where f.trade_date >= '{START_DATE}'
    order by f.ts_code, f.trade_date
    """
    data = con.execute(sql).fetchdf()
    data["trade_date"] = data["trade_date"].astype(str)
    return data


def load_benchmark(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    benchmark = con.execute(
        f"""
        select cast(trade_date as varchar) as trade_date, close, pct_chg, amount
        from index_daily
        where ts_code = '{BENCHMARK_CODE}' and trade_date >= '{START_DATE}'
        order by trade_date
        """
    ).fetchdf()
    benchmark["trade_date"] = benchmark["trade_date"].astype(str)
    benchmark["close"] = pd.to_numeric(benchmark["close"], errors="coerce")
    benchmark["benchmark_return"] = benchmark["close"].pct_change().shift(-1)
    benchmark["index_ret_20"] = benchmark["close"].pct_change(20)
    benchmark["index_ret_60"] = benchmark["close"].pct_change(60)
    return benchmark


def add_fundamental_factors(data: pd.DataFrame) -> None:
    data["bp"] = np.where(data["pb"] > 0, 1.0 / data["pb"], np.nan)
    data["ep_ttm"] = np.where((data["pe_ttm"] > 0) & (data["pe_ttm"] < 300), 1.0 / data["pe_ttm"], np.nan)
    data["dividend_yield"] = data["dv_ttm"] / 100.0
    data["log_total_mv"] = np.where(data["total_mv"] > 0, np.log(data["total_mv"]), np.nan)
    data["neg_log_total_mv"] = -data["log_total_mv"]
    data["quality_roe"] = data["roe"]
    data["quality_roa"] = data["roa"]
    data["cashflow_ocfps"] = data["ocfps"]
    data["growth_sales_yoy"] = data["q_sales_yoy"]
    data["growth_profit_yoy"] = data["netprofit_yoy"]
    data["low_leverage"] = -data["debt_to_assets"]


def build_factor_frame(raw: pd.DataFrame, benchmark: pd.DataFrame) -> pd.DataFrame:
    data = raw.copy()
    data["ts_code"] = data["ts_code"].astype(str)
    data["trade_date"] = data["trade_date"].astype(str)
    data = data.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)

    numeric_columns = [
        "open",
        "high",
        "low",
        "close",
        "pre_close",
        "pct_chg",
        "amount",
        "adj_close",
        "turnover_rate",
        "turnover_rate_f",
        "volume_ratio",
        "pe_ttm",
        "pb",
        "dv_ttm",
        "total_mv",
        "circ_mv",
        "roe",
        "roa",
        "debt_to_assets",
        "ocfps",
        "q_sales_yoy",
        "netprofit_yoy",
        "listed_days",
    ]
    for column in numeric_columns:
        data[column] = pd.to_numeric(data[column], errors="coerce")

    grouped = data.groupby("ts_code", group_keys=False)
    data["ret_1"] = grouped["adj_close"].pct_change()
    data["ret_5"] = grouped["adj_close"].pct_change(5)
    data["ret_20"] = grouped["adj_close"].pct_change(20)
    data["ret_60"] = grouped["adj_close"].pct_change(60)
    data["ret_120"] = grouped["adj_close"].pct_change(120)
    data["next_return"] = grouped["adj_close"].shift(-1) / data["adj_close"] - 1
    data["next_5d_return"] = grouped["adj_close"].shift(-5) / data["adj_close"] - 1
    data["next_20d_return"] = grouped["adj_close"].shift(-20) / data["adj_close"] - 1

    data["reversal_1"] = -data["ret_1"]
    data["reversal_5"] = -data["ret_5"]
    data["reversal_20"] = -data["ret_20"]
    data["momentum_20"] = data["ret_20"]
    data["momentum_60"] = data["ret_60"]
    data["momentum_120"] = data["ret_120"]
    data["momentum_120_20"] = data["ret_120"] - data["ret_20"]

    for window in [5, 10, 20, 60]:
        data[f"ma{window}"] = grouped["adj_close"].transform(lambda s, w=window: s.rolling(w, min_periods=max(3, w // 2)).mean())
    data["bias_5"] = data["adj_close"] / data["ma5"] - 1
    data["bias_20"] = data["adj_close"] / data["ma20"] - 1
    data["bias_60"] = data["adj_close"] / data["ma60"] - 1
    data["ma5_ma20"] = data["ma5"] / data["ma20"] - 1
    data["ma20_ma60"] = data["ma20"] / data["ma60"] - 1

    data["volatility_20"] = grouped["ret_1"].transform(lambda s: s.rolling(20, min_periods=10).std())
    data["volatility_60"] = grouped["ret_1"].transform(lambda s: s.rolling(60, min_periods=20).std())
    data["neg_volatility_20"] = -data["volatility_20"]
    data["neg_volatility_60"] = -data["volatility_60"]

    data["turnover_5d_avg"] = grouped["turnover_rate"].transform(lambda s: s.rolling(5, min_periods=3).mean())
    data["turnover_20d_avg"] = grouped["turnover_rate"].transform(lambda s: s.rolling(20, min_periods=10).mean())
    data["turnover_60d_avg"] = grouped["turnover_rate"].transform(lambda s: s.rolling(60, min_periods=20).mean())
    data["neg_turnover_20d_avg"] = -data["turnover_20d_avg"]
    data["turnover_5_20"] = data["turnover_5d_avg"] / data["turnover_20d_avg"] - 1

    data["amount_5d_avg"] = grouped["amount"].transform(lambda s: s.rolling(5, min_periods=3).mean())
    data["amount_20d_avg"] = grouped["amount"].transform(lambda s: s.rolling(20, min_periods=10).mean())
    data["amount_5_20"] = data["amount_5d_avg"] / data["amount_20d_avg"] - 1

    data["high_20"] = grouped["adj_close"].transform(lambda s: s.rolling(20, min_periods=10).max())
    data["low_20"] = grouped["adj_close"].transform(lambda s: s.rolling(20, min_periods=10).min())
    data["range_position_20"] = (data["adj_close"] - data["low_20"]) / (data["high_20"] - data["low_20"])
    data["breakout_20"] = data["adj_close"] / data["high_20"] - 1
    data["std_20"] = grouped["adj_close"].transform(lambda s: s.rolling(20, min_periods=10).std())
    data["boll_pos_20"] = (data["adj_close"] - data["ma20"]) / (2.0 * data["std_20"])

    data["rsi_14"] = grouped["adj_close"].transform(lambda s: compute_rsi(s, 14))
    true_range = pd.concat(
        [
            data["high"] - data["low"],
            (data["high"] - data["pre_close"]).abs(),
            (data["low"] - data["pre_close"]).abs(),
        ],
        axis=1,
    ).max(axis=1)
    data["true_range_pct"] = true_range / data["close"].replace(0, np.nan)
    data["atr_14_pct"] = grouped["true_range_pct"].transform(lambda s: s.rolling(14, min_periods=7).mean())
    data["neg_atr_14_pct"] = -data["atr_14_pct"]

    abs_ret = (data["pct_chg"].abs() / 100.0).replace([np.inf, -np.inf], np.nan)
    data["amihud_raw"] = abs_ret / (data["amount"].abs() + 1.0)
    data["amihud_20"] = grouped["amihud_raw"].transform(lambda s: s.rolling(20, min_periods=10).mean())
    data["neg_amihud_20"] = -data["amihud_20"]

    add_fundamental_factors(data)
    relative = benchmark[["trade_date", "index_ret_20", "index_ret_60"]].copy()
    data = data.merge(relative, on="trade_date", how="left")
    data["relative_ret_20"] = data["ret_20"] - data["index_ret_20"]
    data["relative_ret_60"] = data["ret_60"] - data["index_ret_60"]

    name_text = data["name"].fillna("").astype(str)
    data["is_st"] = name_text.str.contains("ST", case=False, regex=False)
    data["research_universe"] = (
        data["is_tradable"].fillna(False).astype(bool)
        & data["can_buy"].fillna(True).astype(bool)
        & data["can_sell"].fillna(True).astype(bool)
        & (data["listed_days"] >= 120)
        & (~data["is_st"])
    )

    z_columns = {
        f"z_{factor}": data.groupby("trade_date")[factor].transform(winsorized_zscore)
        for factor in ML_FEATURES
    }
    return pd.concat([data, pd.DataFrame(z_columns, index=data.index)], axis=1)


def daily_rank_ic(frame: pd.DataFrame, factor: str, target: str) -> float | None:
    subset = frame[[factor, target]].replace([np.inf, -np.inf], np.nan).dropna()
    if len(subset) < 50:
        return None
    if subset[factor].nunique(dropna=True) <= 1 or subset[target].nunique(dropna=True) <= 1:
        return None
    return float(subset[factor].rank().corr(subset[target].rank()))


def build_ic_summary(
    data: pd.DataFrame,
    factors: list[str],
    target: str = "next_5d_return",
    start_date: str | None = None,
    end_date: str | None = None,
) -> pd.DataFrame:
    mask = data["research_universe"].fillna(False).astype(bool)
    if start_date:
        mask &= data["trade_date"] >= start_date
    if end_date:
        mask &= data["trade_date"] <= end_date
    rows: list[dict[str, object]] = []
    for factor in factors:
        z_factor = f"z_{factor}"
        panel = data.loc[mask, ["trade_date", z_factor, target]]
        values: list[float] = []
        for _, day in panel.groupby("trade_date"):
            ic = daily_rank_ic(day, z_factor, target)
            if ic is not None and np.isfinite(ic):
                values.append(ic)
        if not values:
            continue
        daily_ic = pd.Series(values, dtype=float)
        std = daily_ic.std(ddof=0)
        rows.append(
            {
                "factor": factor,
                "factor_name": FACTOR_LABELS.get(factor, factor),
                "mean_ic": float(daily_ic.mean()),
                "ic_ir": float(daily_ic.mean() / std) if std and not pd.isna(std) else 0.0,
                "positive_ratio": float((daily_ic > 0).mean()),
                "observations": int(len(daily_ic)),
            }
        )
    return pd.DataFrame(rows).sort_values("mean_ic", ascending=False).reset_index(drop=True)


def build_factor_weights(ic_summary: pd.DataFrame, max_factors: int = 10) -> dict[str, float]:
    frame = ic_summary.copy()
    if frame.empty:
        return {}
    frame["mean_ic"] = pd.to_numeric(frame["mean_ic"], errors="coerce")
    frame["ic_ir"] = pd.to_numeric(frame["ic_ir"], errors="coerce")
    frame["positive_ratio"] = pd.to_numeric(frame["positive_ratio"], errors="coerce")
    usable = frame[(frame["mean_ic"] > 0) & (frame["positive_ratio"] >= 0.52)].copy()
    if usable.empty:
        usable = frame[frame["mean_ic"] > 0].copy()
    if usable.empty:
        return {}
    usable["weight_score"] = (
        usable["mean_ic"].clip(lower=0)
        * (1.0 + usable["ic_ir"].clip(lower=0).fillna(0.0))
        * (usable["positive_ratio"].fillna(0.5) - 0.49).clip(lower=0.01)
    )
    usable = usable.sort_values("weight_score", ascending=False).head(max_factors)
    total = usable["weight_score"].sum()
    if not np.isfinite(total) or total <= 0:
        return {str(row.factor): 1.0 / len(usable) for row in usable.itertuples()}
    return {str(row.factor): float(row.weight_score / total) for row in usable.itertuples()}


def apply_weighted_score(data: pd.DataFrame, weights: dict[str, float], score_col: str) -> None:
    if not weights:
        weights = {"reversal_5": 0.25, "momentum_60": 0.25, "neg_volatility_20": 0.25, "relative_ret_20": 0.25}
    score = pd.Series(np.zeros(len(data), dtype=float), index=data.index)
    for factor, weight in weights.items():
        score = score + data[f"z_{factor}"].fillna(0.0) * float(weight)
    data[score_col] = score
    data[f"z_{score_col}"] = data.groupby("trade_date")[score_col].transform(winsorized_zscore)


def run_top_portfolio_backtest(
    data: pd.DataFrame,
    benchmark: pd.DataFrame,
    score_col: str,
    start_date: str,
    top_n: int,
    end_date: str | None = None,
    fee_rate: float = DEFAULT_FEE_RATE,
    output_prefix: str | None = None,
) -> BacktestResult:
    required = ["ts_code", "trade_date", "research_universe", score_col, "next_return"]
    panel = data.loc[(data["research_universe"]) & (data["trade_date"] >= start_date), required].dropna(subset=[score_col, "next_return"]).copy()
    if end_date:
        panel = panel[panel["trade_date"] <= end_date]
    benchmark_map = benchmark.set_index("trade_date")["benchmark_return"].to_dict()
    rows: list[dict[str, object]] = []
    previous_holdings: set[str] = set()
    for trade_date, day in panel.groupby("trade_date"):
        selected = day.sort_values(score_col, ascending=False).head(top_n)
        if len(selected) < max(20, top_n // 2):
            continue
        holdings = set(selected["ts_code"].astype(str))
        overlap = len(holdings & previous_holdings) if previous_holdings else 0
        turnover = 1.0 if not previous_holdings else 1.0 - overlap / max(len(holdings), 1)
        gross_return = float(selected["next_return"].mean())
        rows.append(
            {
                "trade_date": trade_date,
                "strategy_return": gross_return - turnover * fee_rate,
                "gross_return": gross_return,
                "benchmark_return": benchmark_map.get(trade_date, np.nan),
                "turnover": turnover,
                "holding_count": len(selected),
            }
        )
        previous_holdings = holdings
    performance = pd.DataFrame(rows).sort_values("trade_date").reset_index(drop=True)
    if performance.empty:
        return BacktestResult(performance, pd.DataFrame())
    performance["strategy_nav"] = (1 + performance["strategy_return"].fillna(0.0)).cumprod()
    performance["benchmark_nav"] = (1 + performance["benchmark_return"].fillna(0.0)).cumprod()
    performance["excess_return"] = performance["strategy_return"] - performance["benchmark_return"].fillna(0.0)
    performance["excess_nav"] = (1 + performance["excess_return"].fillna(0.0)).cumprod()
    summary = pd.DataFrame([performance_summary(performance)])
    if output_prefix:
        performance.to_csv(TABLE_DIR / f"{output_prefix}_daily.csv", index=False, encoding="utf-8-sig")
        summary.to_csv(TABLE_DIR / f"{output_prefix}_summary.csv", index=False, encoding="utf-8-sig")
    return BacktestResult(performance, summary)


def performance_summary(performance: pd.DataFrame) -> dict[str, float | int]:
    trading_days = max(len(performance), 1)
    strategy_return = pd.to_numeric(performance["strategy_return"], errors="coerce").fillna(0.0)
    benchmark_return = pd.to_numeric(performance["benchmark_return"], errors="coerce").fillna(0.0)
    excess_return = strategy_return - benchmark_return
    nav = (1 + strategy_return).cumprod()
    benchmark_nav = (1 + benchmark_return).cumprod()
    excess_nav = (1 + excess_return).cumprod()
    drawdown = nav / nav.cummax() - 1
    excess_drawdown = excess_nav / excess_nav.cummax() - 1
    annualized_return = float(nav.iloc[-1] ** (252 / trading_days) - 1)
    benchmark_annualized_return = float(benchmark_nav.iloc[-1] ** (252 / trading_days) - 1)
    annualized_volatility = float(strategy_return.std(ddof=0) * math.sqrt(252))
    excess_annualized_return = float(excess_nav.iloc[-1] ** (252 / trading_days) - 1)
    return {
        "trading_days": int(trading_days),
        "annualized_return": annualized_return,
        "benchmark_annualized_return": benchmark_annualized_return,
        "excess_annualized_return": excess_annualized_return,
        "annualized_volatility": annualized_volatility,
        "sharpe": float(annualized_return / annualized_volatility) if annualized_volatility > 0 else 0.0,
        "max_drawdown": float(drawdown.min()),
        "excess_max_drawdown": float(excess_drawdown.min()),
        "win_rate": float((strategy_return > 0).mean()),
        "avg_turnover": float(pd.to_numeric(performance["turnover"], errors="coerce").mean()),
    }


def model_objective(summary_row: pd.Series) -> float:
    return (
        float(summary_row.get("annualized_return", 0.0))
        + 0.5 * float(summary_row.get("excess_annualized_return", 0.0))
        - 0.35 * abs(float(summary_row.get("max_drawdown", 0.0)))
        - 0.05 * float(summary_row.get("avg_turnover", 0.0))
    )


def build_ridge_model_score(data: pd.DataFrame, target: str, score_col: str, features: list[str]) -> pd.DataFrame:
    z_features = [f"z_{factor}" for factor in features]
    train_mask = (data["research_universe"]) & (data["trade_date"] <= MODEL_TRAIN_END_DATE)
    train = data.loc[train_mask, ["trade_date", target] + z_features].replace([np.inf, -np.inf], np.nan).dropna(subset=[target]).copy()
    train["target_z"] = train.groupby("trade_date")[target].transform(winsorized_zscore)
    train = train.dropna(subset=z_features + ["target_z"])
    if len(train) > 800_000:
        train = train.sample(800_000, random_state=7)
    x_train = train[z_features].to_numpy(dtype=np.float32)
    y_train = train["target_z"].to_numpy(dtype=np.float32)
    coefficients = fit_ridge(x_train, y_train, alpha=25.0)

    x_all = data[z_features].replace([np.inf, -np.inf], np.nan).fillna(0.0).to_numpy(dtype=np.float32)
    data[score_col] = x_all @ coefficients.astype(np.float32)
    data[f"z_{score_col}"] = data.groupby("trade_date")[score_col].transform(winsorized_zscore)

    coefficient_table = pd.DataFrame(
        {
            "feature": features,
            "feature_name": [FACTOR_LABELS.get(feature, feature) for feature in features],
            "coefficient": coefficients,
            "target": target,
            "score_col": score_col,
        }
    ).sort_values("coefficient", ascending=False)
    coefficient_table.to_csv(TABLE_DIR / f"{score_col}_coefficients.csv", index=False, encoding="utf-8-sig")
    return coefficient_table


def build_models(data: pd.DataFrame, benchmark: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, BacktestResult]:
    model_rows: list[dict[str, object]] = []
    coefficient_frames: list[pd.DataFrame] = []

    for target, target_label in TARGET_LABELS.items():
        train_ic = build_ic_summary(data, TECHNICAL_FACTORS, target=target, start_date=START_DATE, end_date=MODEL_TRAIN_END_DATE)
        weights = build_factor_weights(train_ic, max_factors=10)
        score_col = f"technical_ensemble_{target}"
        apply_weighted_score(data, weights, score_col)
        pd.DataFrame(
            [
                {
                    "target": target,
                    "factor": factor,
                    "factor_name": FACTOR_LABELS.get(factor, factor),
                    "weight": weight,
                }
                for factor, weight in weights.items()
            ]
        ).to_csv(TABLE_DIR / f"{score_col}_weights.csv", index=False, encoding="utf-8-sig")

        ridge_col = f"ridge_ml_{target}"
        coefficient_frames.append(build_ridge_model_score(data, target, ridge_col, ML_FEATURES))

        for model_type, model_score_col in [("技术因子IC加权", score_col), ("Ridge横截面机器学习", ridge_col)]:
            for top_n in [50, 100, 200, 300]:
                train_result = run_top_portfolio_backtest(
                    data,
                    benchmark,
                    score_col=model_score_col,
                    start_date=START_DATE,
                    end_date=MODEL_TRAIN_END_DATE,
                    top_n=top_n,
                )
                if train_result.summary.empty:
                    continue
                train_row = train_result.summary.iloc[0]
                oos_result = run_top_portfolio_backtest(
                    data,
                    benchmark,
                    score_col=model_score_col,
                    start_date=TEST_START_DATE,
                    top_n=top_n,
                )
                oos_row = oos_result.summary.iloc[0] if not oos_result.summary.empty else pd.Series(dtype=float)
                model_rows.append(
                    {
                        "model_id": f"{model_score_col}_top{top_n}",
                        "model_type": model_type,
                        "target": target,
                        "target_label": target_label,
                        "score_col": model_score_col,
                        "top_n": top_n,
                        "train_objective": model_objective(train_row),
                        "train_annualized_return": train_row.get("annualized_return", np.nan),
                        "train_excess_annualized_return": train_row.get("excess_annualized_return", np.nan),
                        "train_sharpe": train_row.get("sharpe", np.nan),
                        "train_max_drawdown": train_row.get("max_drawdown", np.nan),
                        "train_avg_turnover": train_row.get("avg_turnover", np.nan),
                        "oos_annualized_return": oos_row.get("annualized_return", np.nan),
                        "oos_benchmark_annualized_return": oos_row.get("benchmark_annualized_return", np.nan),
                        "oos_excess_annualized_return": oos_row.get("excess_annualized_return", np.nan),
                        "oos_sharpe": oos_row.get("sharpe", np.nan),
                        "oos_max_drawdown": oos_row.get("max_drawdown", np.nan),
                        "oos_avg_turnover": oos_row.get("avg_turnover", np.nan),
                    }
                )

    model_table = pd.DataFrame(model_rows).sort_values("train_objective", ascending=False).reset_index(drop=True)
    model_table.to_csv(TABLE_DIR / "technical_ml_model_selection.csv", index=False, encoding="utf-8-sig")
    coefficients = pd.concat(coefficient_frames, ignore_index=True) if coefficient_frames else pd.DataFrame()
    coefficients.to_csv(TABLE_DIR / "technical_ml_ridge_coefficients.csv", index=False, encoding="utf-8-sig")
    selected = select_best_model(model_table)
    selected.to_frame().T.to_csv(TABLE_DIR / "technical_ml_selected_model.csv", index=False, encoding="utf-8-sig")
    selected_oos = run_top_portfolio_backtest(
        data,
        benchmark,
        score_col=str(selected["score_col"]),
        start_date=TEST_START_DATE,
        top_n=int(selected["top_n"]),
        output_prefix="technical_ml_selected_oos",
    )
    return model_table, selected.to_frame().T, coefficients, selected_oos


def plot_ic_bar(ic_summary: pd.DataFrame) -> Path:
    top = ic_summary.sort_values("mean_ic", ascending=True).tail(12)
    path = FIGURE_DIR / "technical_factor_oos_ic_bar.png"
    fig, ax = plt.subplots(figsize=(8, 4.8))
    ax.barh(top["factor_name"], top["mean_ic"], color="#2F5597")
    ax.axvline(0, color="#666666", linewidth=0.8)
    ax.set_title("技术因子样本外Rank IC（未来5日收益）")
    ax.set_xlabel("平均Rank IC")
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)
    return path


def plot_selected_nav(backtest: BacktestResult) -> Path | None:
    if backtest.performance.empty:
        return None
    path = FIGURE_DIR / "technical_ml_selected_nav.png"
    performance = backtest.performance.copy()
    fig, ax = plt.subplots(figsize=(8, 4.8))
    ax.plot(pd.to_datetime(performance["trade_date"]), performance["strategy_nav"], label="技术/ML模型组合", linewidth=1.8)
    ax.plot(pd.to_datetime(performance["trade_date"]), performance["benchmark_nav"], label="沪深300", linewidth=1.4)
    ax.set_title("技术因子与机器学习增强模型样本外净值")
    ax.set_ylabel("净值")
    ax.legend()
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)
    return path


def fmt_pct(value: object) -> str:
    number = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(number):
        return "-"
    return f"{number:.2%}"


def fmt_num(value: object, digits: int = 3) -> str:
    number = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(number):
        return "-"
    return f"{number:.{digits}f}"


def find_report() -> Path:
    candidates = [
        path
        for path in REPORT_DIR.glob("*.docx")
        if "ai" in path.name.lower()
        and "before-methodology" not in path.name.lower()
        and "before-technical-ml" not in path.name.lower()
        and not path.name.startswith("~$")
    ]
    if not candidates:
        raise FileNotFoundError(f"No AI report docx found in {REPORT_DIR}")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def set_font(run, size: float = 10.5, bold: bool = False, color: RGBColor | None = None) -> None:
    run.font.name = FONT
    run._element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
    run.font.size = Pt(size)
    run.bold = bold
    if color is not None:
        run.font.color.rgb = color


def add_heading(document: Document, text: str, level: int = 1) -> None:
    paragraph = document.add_paragraph()
    paragraph.paragraph_format.space_before = Pt(8 if level == 1 else 5)
    paragraph.paragraph_format.space_after = Pt(4)
    run = paragraph.add_run(text)
    set_font(run, 14 if level == 1 else 12, True, BLUE)


def add_body(document: Document, text: str) -> None:
    paragraph = document.add_paragraph()
    paragraph.paragraph_format.first_line_indent = Pt(21)
    paragraph.paragraph_format.line_spacing = 1.25
    paragraph.paragraph_format.space_after = Pt(3)
    run = paragraph.add_run(text)
    set_font(run, 10.5)


def shade_cell(cell, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shading = OxmlElement("w:shd")
    shading.set(qn("w:fill"), fill)
    tc_pr.append(shading)


def style_cell(cell, bold: bool = False, size: float = 8.5, align_center: bool = False) -> None:
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    for paragraph in cell.paragraphs:
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER if align_center else WD_ALIGN_PARAGRAPH.LEFT
        for run in paragraph.runs:
            set_font(run, size, bold)


def add_table(document: Document, title: str, headers: list[str], rows: list[list[str]]) -> None:
    caption = document.add_paragraph()
    caption.paragraph_format.space_before = Pt(4)
    caption.paragraph_format.space_after = Pt(2)
    run = caption.add_run(title)
    set_font(run, 10, True)
    table = document.add_table(rows=1, cols=len(headers))
    try:
        table.style = "Table Grid"
    except KeyError:
        pass
    for idx, header in enumerate(headers):
        table.rows[0].cells[idx].text = header
        shade_cell(table.rows[0].cells[idx], "D9EAF7")
        style_cell(table.rows[0].cells[idx], bold=True, align_center=True)
    for row in rows:
        cells = table.add_row().cells
        for idx, value in enumerate(row):
            cells[idx].text = value
            style_cell(cells[idx], size=8.0)
    table.autofit = True


def add_picture_if_exists(document: Document, path: Path | None, width: float = 6.1) -> None:
    if path is None or not path.exists():
        return
    paragraph = document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run()
    run.add_picture(str(path), width=Inches(width))


def append_chapter(
    document: Document,
    train_ic: pd.DataFrame,
    oos_ic: pd.DataFrame,
    model_table: pd.DataFrame,
    selected_table: pd.DataFrame,
    coefficients: pd.DataFrame,
    selected_oos: BacktestResult,
    ic_figure: Path | None,
    nav_figure: Path | None,
) -> None:
    document.add_page_break()
    add_heading(document, CHAPTER_TITLE, 1)
    add_body(
        document,
        "在前述基本面、估值和规模因子基础上，本章进一步补充A股量化研究中常用的技术面因子，并引入可在当前本地环境直接复现的横截面机器学习模型。该扩展的目标不是简单堆叠更多指标，而是把趋势、反转、低波动、量价配合、价格位置、流动性冲击成本等可交易信号纳入同一套训练期验证框架，再用样本外回测检验其增量价值。",
    )

    add_heading(document, "（一）A股技术因子扩展", 2)
    add_body(
        document,
        "本轮新增技术因子覆盖五类信号：第一类为反转与动量，刻画短期过度反应和中期趋势延续；第二类为均线与价格位置，刻画价格相对历史区间、均线斜率和突破状态；第三类为波动率与ATR，刻画风险暴露和振幅结构；第四类为换手率、成交额和Amihud冲击成本，刻画流动性拥挤与交易摩擦；第五类为相对沪深300强度，用于区分个股自身强弱与市场整体 beta 推动。",
    )
    add_table(
        document,
        "表11-1：新增技术因子分组与计算口径",
        ["因子类别", "代表因子", "计算口径", "预期用途"],
        [
            ["反转/动量", "1日反转、5日反转、20/60/120日动量", "基于复权收盘价历史收益率计算，不使用未来收益", "识别短期均值回复与中期趋势延续"],
            ["价格位置", "均线乖离、20日区间位置、20日突破、布林带位置", "使用当日及以前滚动均线、高低点和标准差", "刻画趋势斜率、突破强度和价格拥挤程度"],
            ["风险结构", "20/60日低波、低ATR波动", "使用历史日收益波动和真实波幅滚动均值", "控制高波动回撤风险，识别稳健趋势"],
            ["量价流动性", "短期换手放大、成交额放大、低冲击成本", "使用历史换手、成交额和Amihud指标", "识别资金参与度和潜在交易摩擦"],
            ["相对强度", "相对沪深300强度20/60日", "个股历史收益减同期沪深300历史收益", "剥离市场整体涨跌后的个股强弱"],
        ],
    )

    add_heading(document, "（二）技术因子有效性检验", 2)
    add_body(
        document,
        f"技术因子的有效性仍采用训练期和样本外分离口径。训练期截至{MODEL_TRAIN_END_DATE}，样本外从{TEST_START_DATE}开始；因子标准化仅在同一交易日横截面内完成，滚动窗口仅使用当日及以前历史数据，未来5日和未来20日收益只作为训练标签和回测评价，不进入当日信号计算。",
    )
    top_ic_rows = []
    for row in oos_ic.head(8).itertuples():
        top_ic_rows.append(
            [
                str(row.factor_name),
                fmt_num(row.mean_ic, 4),
                fmt_num(row.ic_ir, 3),
                fmt_pct(row.positive_ratio),
                str(row.observations),
            ]
        )
    add_table(
        document,
        "表11-2：样本外技术因子Rank IC表现（未来5日收益）",
        ["因子", "平均IC", "IC_IR", "正IC占比", "观测交易日"],
        top_ic_rows,
    )
    add_picture_if_exists(document, ic_figure)

    add_heading(document, "（三）机器学习模型选择与环境约束", 2)
    add_body(
        document,
        "在模型层面，本轮把技术因子IC加权组合与横截面Ridge机器学习模型放入同一训练期选模框架。Ridge模型以基本面因子和新增技术因子的横截面标准化值作为输入，以未来5日或未来20日收益的横截面标准化标签作为训练目标，通过L2正则控制多因子共线性和过拟合风险。当前本地环境未安装LightGBM、XGBoost、PyTorch或TensorFlow等外部训练包，因此本章只呈现可以在现有环境完整复现的模型结果；LightGBM适合在下一阶段作为非线性树模型扩展，LSTM更适合分钟序列或更长时序样本任务，不写入本轮已验证结果。",
    )
    coef_rows = []
    if not coefficients.empty:
        selected_score = str(selected_table.iloc[0]["score_col"])
        coef_view = coefficients[coefficients["score_col"] == selected_score].copy()
        coef_view["abs_coef"] = coef_view["coefficient"].abs()
        for row in coef_view.sort_values("abs_coef", ascending=False).head(10).itertuples():
            coef_rows.append([str(row.feature_name), fmt_num(row.coefficient, 4), str(row.target)])
    add_table(
        document,
        "表11-3：选定Ridge模型主要特征系数（按绝对值排序）",
        ["特征", "系数", "训练目标"],
        coef_rows if coef_rows else [["-", "-", "-"]],
    )

    add_heading(document, "（四）技术因子/机器学习模型回测对比", 2)
    selected = selected_table.iloc[0]
    summary = selected_oos.summary.iloc[0] if not selected_oos.summary.empty else pd.Series(dtype=float)
    add_body(
        document,
        f"选模仍只依据训练期目标函数完成，目标函数综合考虑年化收益、超额收益、夏普、回撤和换手成本，样本外结果不参与模型选择。按照该口径，本轮技术扩展选定模型为“{selected['model_type']} / {selected['target_label']} / Top{int(selected['top_n'])}”，样本外年化收益为{fmt_pct(summary.get('annualized_return'))}，同期沪深300年化收益为{fmt_pct(summary.get('benchmark_annualized_return'))}，年化超额收益为{fmt_pct(summary.get('excess_annualized_return'))}，最大回撤为{fmt_pct(summary.get('max_drawdown'))}，平均换手率为{fmt_pct(summary.get('avg_turnover'))}。交易成本按单边0.10%计入。",
    )
    comparison_rows = []
    for row in model_table.head(8).itertuples():
        comparison_rows.append(
            [
                str(row.model_type),
                str(row.target_label),
                f"Top{int(row.top_n)}",
                fmt_num(row.train_objective, 3),
                fmt_pct(row.oos_annualized_return),
                fmt_pct(row.oos_excess_annualized_return),
                fmt_pct(row.oos_max_drawdown),
                fmt_pct(row.oos_avg_turnover),
            ]
        )
    add_table(
        document,
        "表11-4：技术因子与机器学习候选模型对比（按训练期目标函数排序）",
        ["模型类型", "训练目标", "组合", "训练目标函数", "样本外年化", "样本外超额", "样本外回撤", "平均换手"],
        comparison_rows,
    )
    add_picture_if_exists(document, nav_figure)

    add_heading(document, "（五）研究结论与AI优化落地方式", 2)
    add_body(
        document,
        "技术因子扩展后，研究流程从单一基本面因子验证升级为“基本面 + 技术面 + 流动性 + 横截面机器学习”的组合验证框架。AI在其中承担三类落地功能：一是快速把A股常用量化假设转化为可计算因子并形成字段口径；二是基于训练期IC、稳定性、相关性和回测表现自动归纳因子组合；三是把模型结果转化为报告中的因子解释、选模依据和样本外表现对比。该过程保留了量化研究的可复现性，同时提升了因子迭代、模型复盘和报告汇总效率。",
    )
    add_body(
        document,
        "从本轮结果看，技术因子和机器学习模型并非无条件替代原组合，而是为选股模型提供了更完整的信号池和更严格的比较基准。报告后续可继续沿用本章框架，引入LightGBM等非线性模型、行业/市值中性化处理、月度换仓约束和分钟级序列特征，在统一的训练期选模和样本外验证框架下持续迭代。",
    )


def write_report_chapter(
    train_ic: pd.DataFrame,
    oos_ic: pd.DataFrame,
    model_table: pd.DataFrame,
    selected_table: pd.DataFrame,
    coefficients: pd.DataFrame,
    selected_oos: BacktestResult,
    ic_figure: Path | None,
    nav_figure: Path | None,
) -> Path:
    report_path = find_report()
    backup_path = report_path.with_name(report_path.stem + "-before-technical-ml-addition.docx")
    if not backup_path.exists():
        copy2(report_path, backup_path)
    document = Document(report_path)
    text = "\n".join(paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text.strip())
    if CHAPTER_TITLE not in text:
        append_chapter(document, train_ic, oos_ic, model_table, selected_table, coefficients, selected_oos, ic_figure, nav_figure)
        document.save(report_path)
    return report_path


def main() -> None:
    ensure_directories()
    configure_plot_font()
    con = connect_duckdb()
    try:
        benchmark = load_benchmark(con)
        raw = load_daily_frame(con)
    finally:
        con.close()

    factor_frame = build_factor_frame(raw, benchmark)
    train_ic = build_ic_summary(factor_frame, TECHNICAL_FACTORS, target="next_5d_return", start_date=START_DATE, end_date=MODEL_TRAIN_END_DATE)
    oos_ic = build_ic_summary(factor_frame, TECHNICAL_FACTORS, target="next_5d_return", start_date=TEST_START_DATE)
    train_ic.to_csv(TABLE_DIR / "technical_factor_ic_train.csv", index=False, encoding="utf-8-sig")
    oos_ic.to_csv(TABLE_DIR / "technical_factor_ic_oos.csv", index=False, encoding="utf-8-sig")
    model_table, selected_table, coefficients, selected_oos = build_models(factor_frame, benchmark)
    plot_ic_bar(oos_ic)
    plot_selected_nav(selected_oos)
    report_path = find_report()

    print(f"report={report_path}")
    print(f"technical_outputs={TECH_DIR}")
    print(f"selected_model={selected_table.iloc[0]['model_id']}")
    if not selected_oos.summary.empty:
        print(selected_oos.summary.to_string(index=False))


if __name__ == "__main__":
    main()
