from __future__ import annotations

import math
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

import duckdb
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np
import pandas as pd
from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor


ROOT_DIR = Path(__file__).resolve().parents[2]
WORK_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = WORK_DIR / "outputs_enhanced"
TABLE_DIR = OUTPUT_DIR / "tables"
FIGURE_DIR = OUTPUT_DIR / "figures"
REPORT_DIR = OUTPUT_DIR / "report"
DOC_SOURCE = ROOT_DIR / "选股与择时中AI可应用部分因子总结方案-提交版.docx"
DOC_TARGET = REPORT_DIR / "选股与择时中AI可应用部分因子总结方案-增强数据支撑版.docx"

DUCKDB_PATH = ROOT_DIR / "data" / "metadata" / "research.duckdb"
MINUTE_DIR = ROOT_DIR / "60m" / "stock_data_parquet"

START_DATE = "20230101"
TRAIN_END_DATE = "20241231"
MODEL_TRAIN_END_DATE = "20241129"
TEST_START_DATE = "20250101"
BENCHMARK_CODE = "000300.SH"
DEFAULT_FEE_RATE = 0.001
SELECTED_NAV_FIGURE = "optimized_selected_nav.png"
REPORT_LANDING_SECTION_TITLE = "（九）落地实施方案"
PRIMARY_COLOR = "#1F4E79"
SECONDARY_COLOR = "#2F6B5F"
ACCENT_COLOR = "#B07A24"
NEGATIVE_COLOR = "#8C3F3F"
GRID_COLOR = "#D9E2F0"
REPORT_LANDING_PARAGRAPH = (
    "AI能力落地划分为四个可审计模块：第一，因子研究助手，负责自动生成IC、相关性、分层和动作归类；"
    "第二，模型复盘助手，负责读取回测曲线、换手、回撤和风格暴露并输出问题清单；"
    "第三，分钟结构标签助手，负责把60分钟量价结构转成日频可用标签；"
    "第四，择时状态解释助手，负责把趋势、宽度、量能和波动状态转成仓位与风险提示。"
    "该实施框架保留量化研究的可复现性，同时发挥AI在归纳、解释和迭代效率上的优势。"
)

TARGET_LABELS = {
    "next_5d_return": "未来5日收益",
    "next_20d_return": "未来20日收益",
}

FUNDAMENTAL_FACTOR_COLUMNS = [
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

TECHNICAL_FACTOR_COLUMNS = [
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

DAILY_FACTOR_COLUMNS = FUNDAMENTAL_FACTOR_COLUMNS + TECHNICAL_FACTOR_COLUMNS

FACTOR_LABELS = {
    "bp": "估值-BP",
    "ep_ttm": "估值-EP(TTM)",
    "dividend_yield": "股息率",
    "neg_log_total_mv": "小市值暴露",
    "reversal_1": "1日反转",
    "reversal_5": "短期反转",
    "reversal_20": "20日反转",
    "momentum_20": "20日动量",
    "momentum_60": "中期动量",
    "momentum_120": "120日动量",
    "momentum_120_20": "中长期动量剔除近端",
    "relative_ret_20": "相对沪深300强度20日",
    "relative_ret_60": "相对沪深300强度60日",
    "neg_volatility_20": "低波动",
    "neg_volatility_60": "60日低波动",
    "neg_turnover_20d_avg": "低换手",
    "turnover_5_20": "短期换手放大",
    "amount_5_20": "短期成交额放大",
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
    "quality_roe": "ROE质量",
    "quality_roa": "ROA质量",
    "cashflow_ocfps": "经营现金流",
    "growth_sales_yoy": "收入成长",
    "growth_profit_yoy": "利润成长",
    "low_leverage": "低杠杆",
    "optimized_score": "AI辅助优化综合分",
}

FACTOR_GROUP_MAP = {
    "bp": "估值与质量",
    "ep_ttm": "估值与质量",
    "dividend_yield": "估值与质量",
    "neg_log_total_mv": "规模与风险补偿",
    "quality_roe": "估值与质量",
    "quality_roa": "估值与质量",
    "cashflow_ocfps": "现金流与成长",
    "growth_sales_yoy": "现金流与成长",
    "growth_profit_yoy": "现金流与成长",
    "low_leverage": "资本结构",
    "reversal_1": "反转与趋势",
    "reversal_5": "反转与趋势",
    "reversal_20": "反转与趋势",
    "momentum_20": "反转与趋势",
    "momentum_60": "反转与趋势",
    "momentum_120": "反转与趋势",
    "momentum_120_20": "反转与趋势",
    "relative_ret_20": "相对强弱",
    "relative_ret_60": "相对强弱",
    "neg_volatility_20": "波动与防御",
    "neg_volatility_60": "波动与防御",
    "neg_turnover_20d_avg": "流动性与拥挤",
    "turnover_5_20": "流动性与拥挤",
    "amount_5_20": "流动性与拥挤",
    "bias_20": "价格位置",
    "bias_60": "价格位置",
    "ma5_ma20": "价格位置",
    "ma20_ma60": "价格位置",
    "range_position_20": "价格位置",
    "breakout_20": "价格位置",
    "boll_pos_20": "价格位置",
    "rsi_14": "价格位置",
    "neg_atr_14_pct": "波动与防御",
    "neg_amihud_20": "流动性与拥挤",
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


def fit_ridge(x: np.ndarray, y: np.ndarray, alpha: float = 25.0) -> np.ndarray:
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


def model_objective(summary_row: pd.Series) -> float:
    return (
        float(summary_row.get("annualized_return", 0.0))
        + 0.5 * float(summary_row.get("excess_annualized_return", 0.0))
        - 0.35 * abs(float(summary_row.get("max_drawdown", 0.0)))
        - 0.05 * float(summary_row.get("avg_turnover", 0.0))
    )


def build_factor_weights(ic_summary: pd.DataFrame, max_factors: int = 6) -> dict[str, float]:
    if ic_summary.empty:
        return {}
    frame = ic_summary.copy()
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
        equal = 1.0 / len(usable)
        return {str(row.factor): equal for row in usable.itertuples()}
    return {str(row.factor): float(row.weight_score / total) for row in usable.itertuples()}


def describe_ai_factor_actions(ic_summary: pd.DataFrame) -> pd.DataFrame:
    frame = ic_summary.copy()

    def action(row: pd.Series) -> str:
        mean_ic = float(row.get("mean_ic", 0.0) or 0.0)
        ic_ir = float(row.get("ic_ir", 0.0) or 0.0)
        positive_ratio = float(row.get("positive_ratio", 0.0) or 0.0)
        if mean_ic >= 0.02 and ic_ir > 0 and positive_ratio >= 0.55:
            return "核心加权"
        if mean_ic < 0 or positive_ratio < 0.45:
            return "反向验证或降权"
        if mean_ic >= 0.01 and positive_ratio >= 0.52:
            return "辅助过滤"
        return "观察保留"

    def reason(row: pd.Series) -> str:
        mean_ic = float(row.get("mean_ic", 0.0) or 0.0)
        positive_ratio = float(row.get("positive_ratio", 0.0) or 0.0)
        if mean_ic >= 0.02 and positive_ratio >= 0.55:
            return "方向稳定，可作为组合主输入"
        if mean_ic < 0:
            return "历史方向为负，需检查是否应反向使用"
        if positive_ratio < 0.45:
            return "正IC占比较低，阶段稳定性不足"
        if mean_ic >= 0.01:
            return "有一定信息量，适合作为条件或过滤项"
        return "信号较弱，保留观察不直接加权"

    frame["factor_name"] = frame["factor"].map(FACTOR_LABELS).fillna(frame["factor"])
    frame["ai_action"] = frame.apply(action, axis=1)
    frame["ai_reason"] = frame.apply(reason, axis=1)
    return frame


def configure_plot_font() -> str:
    candidate_paths = [
        Path(r"C:\Windows\Fonts\msyh.ttc"),
        Path(r"C:\Windows\Fonts\msyhbd.ttc"),
        Path(r"C:\Windows\Fonts\simhei.ttf"),
        Path(r"C:\Windows\Fonts\simsun.ttc"),
    ]
    for font_path in candidate_paths:
        if font_path.exists():
            font_manager.fontManager.addfont(str(font_path))
            font_name = font_manager.FontProperties(fname=str(font_path)).get_name()
            plt.rcParams["font.family"] = [font_name]
            plt.rcParams["font.sans-serif"] = [font_name, "DejaVu Sans"]
            plt.rcParams["axes.unicode_minus"] = False
            return font_name
    plt.rcParams["font.sans-serif"] = ["DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    return "DejaVu Sans"


def ensure_directories() -> None:
    for path in [OUTPUT_DIR, TABLE_DIR, FIGURE_DIR, REPORT_DIR]:
        path.mkdir(parents=True, exist_ok=True)


def resolve_report_source() -> Path | None:
    candidates = [DOC_SOURCE]
    candidates.extend((WORK_DIR / "outputs" / "report").glob("*数据支撑版.docx"))
    candidates.extend(ROOT_DIR.glob("*提交版.docx"))
    for candidate in candidates:
        if candidate.exists() and candidate.resolve() != DOC_TARGET.resolve():
            return candidate
    return None


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
        f.pct_chg,
        f.amount,
        f.adj_close,
        f.turnover_rate,
        f.turnover_rate_f,
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


def build_factor_frame(frame: pd.DataFrame, benchmark: pd.DataFrame) -> pd.DataFrame:
    data = frame.copy()
    data["ts_code"] = data["ts_code"].astype(str)
    data["trade_date"] = data["trade_date"].astype(str)
    data = data.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)

    numeric_columns = [
        "open",
        "high",
        "low",
        "close",
        "pct_chg",
        "amount",
        "adj_close",
        "turnover_rate",
        "turnover_rate_f",
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
        if column in data.columns:
            data[column] = pd.to_numeric(data[column], errors="coerce")

    grouped = data.groupby("ts_code", group_keys=False)
    daily_return = grouped["adj_close"].pct_change()
    data["next_return"] = grouped["adj_close"].shift(-1) / data["adj_close"] - 1
    data["next_5d_return"] = grouped["adj_close"].shift(-5) / data["adj_close"] - 1
    data["next_20d_return"] = grouped["adj_close"].shift(-20) / data["adj_close"] - 1
    data["ret_1"] = daily_return
    data["ret_5"] = grouped["adj_close"].pct_change(5)
    data["ret_20"] = grouped["adj_close"].pct_change(20)
    data["ret_60"] = grouped["adj_close"].pct_change(60)
    data["ret_120"] = grouped["adj_close"].pct_change(120)

    data["reversal_1"] = -data["ret_1"]
    data["reversal_5"] = -data["ret_5"]
    data["reversal_20"] = -data["ret_20"]
    data["momentum_20"] = data["ret_20"]
    data["momentum_60"] = data["ret_60"]
    data["momentum_120"] = data["ret_120"]
    data["momentum_120_20"] = data["ret_120"] - data["ret_20"]

    for window in [5, 10, 20, 60]:
        data[f"ma{window}"] = grouped["adj_close"].transform(lambda s, w=window: s.rolling(w, min_periods=max(3, w // 2)).mean())
    data["bias_20"] = data["adj_close"] / data["ma20"] - 1
    data["bias_60"] = data["adj_close"] / data["ma60"] - 1
    data["ma5_ma20"] = data["ma5"] / data["ma20"] - 1
    data["ma20_ma60"] = data["ma20"] / data["ma60"] - 1

    data["volatility_20"] = grouped["ret_1"].transform(lambda s: s.rolling(20, min_periods=10).std())
    data["volatility_60"] = grouped["ret_1"].transform(lambda s: s.rolling(60, min_periods=20).std())
    data["bp"] = np.where(data["pb"] > 0, 1.0 / data["pb"], np.nan)
    data["ep_ttm"] = np.where((data["pe_ttm"] > 0) & (data["pe_ttm"] < 300), 1.0 / data["pe_ttm"], np.nan)
    data["dividend_yield"] = data["dv_ttm"] / 100.0
    data["log_total_mv"] = np.where(data["total_mv"] > 0, np.log(data["total_mv"]), np.nan)
    data["neg_log_total_mv"] = -data["log_total_mv"]
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
    prev_close = grouped["close"].shift(1)
    true_range = pd.concat(
        [
            data["high"] - data["low"],
            (data["high"] - prev_close).abs(),
            (data["low"] - prev_close).abs(),
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

    data["quality_roe"] = data["roe"]
    data["quality_roa"] = data["roa"]
    data["cashflow_ocfps"] = data["ocfps"]
    data["growth_sales_yoy"] = data["q_sales_yoy"]
    data["growth_profit_yoy"] = data["netprofit_yoy"]
    data["low_leverage"] = -data["debt_to_assets"]

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
        for factor in DAILY_FACTOR_COLUMNS
    }
    result = pd.concat([data, pd.DataFrame(z_columns, index=data.index)], axis=1)
    keep_columns = [
        "ts_code",
        "trade_date",
        "amount",
        "research_universe",
        "next_return",
        "next_5d_return",
        "next_20d_return",
    ] + DAILY_FACTOR_COLUMNS + list(z_columns.keys())
    return result[keep_columns].copy()


def build_coverage_summary(con: duckdb.DuckDBPyConnection, factor_frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for table_name in [
        "daily_base",
        "tradable_daily_base",
        "daily_fundamental_base",
        "index_daily",
        "stock_basic",
    ]:
        rows.append(
            {
                "dataset": table_name,
                "row_count": int(con.execute(f"select count(*) as cnt from {table_name}").fetchone()[0]),
                "note": "DuckDB研究底座",
            }
        )
    rows.append(
        {
            "dataset": "60m_stock_data_parquet",
            "row_count": len(list(MINUTE_DIR.glob("*.parquet"))),
            "note": "同花顺60分钟价量数据文件数",
        }
    )
    rows.append(
        {
            "dataset": "analysis_universe_days",
            "row_count": int(factor_frame["research_universe"].sum()),
            "note": f"{START_DATE}以来可交易股票-日期样本",
        }
    )
    summary = pd.DataFrame(rows)
    summary.to_csv(TABLE_DIR / "coverage_summary_enhanced.csv", index=False, encoding="utf-8-sig")
    return summary


def daily_rank_ic(frame: pd.DataFrame, factor: str, target: str) -> float | None:
    subset = frame[[factor, target]].replace([np.inf, -np.inf], np.nan).dropna()
    if len(subset) < 50:
        return None
    if subset[factor].nunique(dropna=True) <= 1 or subset[target].nunique(dropna=True) <= 1:
        return None
    return float(subset[factor].rank().corr(subset[target].rank()))


def build_ic_summary(data: pd.DataFrame, target: str = "next_5d_return", start_date: str | None = None, end_date: str | None = None) -> pd.DataFrame:
    mask = data["research_universe"].fillna(False)
    if start_date:
        mask = mask & (data["trade_date"] >= start_date)
    if end_date:
        mask = mask & (data["trade_date"] <= end_date)

    rows: list[dict[str, object]] = []
    for factor in DAILY_FACTOR_COLUMNS:
        z_factor = f"z_{factor}"
        factor_panel = data.loc[mask, ["trade_date", z_factor, target]].replace([np.inf, -np.inf], np.nan).dropna()
        if factor_panel.empty:
            continue
        daily_ic = factor_panel.groupby("trade_date").apply(lambda x: daily_rank_ic(x, z_factor, target), include_groups=False)
        daily_ic = pd.to_numeric(daily_ic, errors="coerce").dropna()
        if daily_ic.empty:
            continue
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
    summary = pd.DataFrame(rows).sort_values("mean_ic", ascending=False).reset_index(drop=True)
    return summary


def apply_optimized_score(data: pd.DataFrame, weights: dict[str, float], score_col: str = "optimized_score") -> pd.DataFrame:
    result = data
    result[score_col] = compute_weighted_score_series(result, weights)
    result[f"z_{score_col}"] = result.groupby("trade_date")[score_col].transform(winsorized_zscore)
    return result


def compute_weighted_score_series(data: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
    if not weights:
        positive_defaults = ["bp", "reversal_5", "ep_ttm", "neg_volatility_20"]
        weights = {factor: 1.0 / len(positive_defaults) for factor in positive_defaults}
    score = pd.Series(np.zeros(len(data)), index=data.index, dtype=float)
    for factor, weight in weights.items():
        score = score + data[f"z_{factor}"].fillna(0.0) * weight
    return score


def fit_ridge_coefficients(
    data: pd.DataFrame,
    target: str,
    features: list[str],
    train_end_date: str,
    alpha: float = 25.0,
) -> np.ndarray:
    z_features = [f"z_{factor}" for factor in features]
    train_mask = (data["research_universe"]) & (data["trade_date"] <= train_end_date)
    train = data.loc[train_mask, ["trade_date", target] + z_features].replace([np.inf, -np.inf], np.nan).dropna(subset=[target]).copy()
    train["target_z"] = train.groupby("trade_date")[target].transform(winsorized_zscore)
    train = train.dropna(subset=z_features + ["target_z"])
    if len(train) > 800_000:
        train = train.sample(800_000, random_state=7)
    x_train = train[z_features].to_numpy(dtype=np.float32)
    y_train = train["target_z"].to_numpy(dtype=np.float32)
    return fit_ridge(x_train, y_train, alpha=alpha)


def compute_ridge_score_series(data: pd.DataFrame, features: list[str], coefficients: np.ndarray) -> pd.Series:
    z_features = [f"z_{factor}" for factor in features]
    x_all = data[z_features].replace([np.inf, -np.inf], np.nan).fillna(0.0).to_numpy(dtype=np.float32)
    return pd.Series(x_all @ coefficients.astype(np.float32), index=data.index, dtype=float)


def build_factor_weight_table(weights: dict[str, float], ic_summary: pd.DataFrame, output_name: str = "factor_weights.csv") -> pd.DataFrame:
    rows = [{"factor": factor, "factor_name": FACTOR_LABELS.get(factor, factor), "weight": weight} for factor, weight in weights.items()]
    table = pd.DataFrame(rows).sort_values("weight", ascending=False).reset_index(drop=True)
    if not table.empty:
        table = table.merge(ic_summary[["factor", "mean_ic", "ic_ir", "positive_ratio"]], on="factor", how="left")
    table.to_csv(TABLE_DIR / output_name, index=False, encoding="utf-8-sig")
    return table


def build_factor_group_summary(train_ic: pd.DataFrame, oos_ic: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for group_name in sorted(set(FACTOR_GROUP_MAP.values())):
        group_factors = [factor for factor, group in FACTOR_GROUP_MAP.items() if group == group_name]
        train_view = train_ic[train_ic["factor"].isin(group_factors)].copy()
        oos_view = oos_ic[oos_ic["factor"].isin(group_factors)].copy()
        rows.append(
            {
                "factor_group": group_name,
                "factor_count": int(len(group_factors)),
                "train_mean_ic": float(train_view["mean_ic"].mean()) if not train_view.empty else np.nan,
                "train_positive_ratio": float(train_view["positive_ratio"].mean()) if not train_view.empty else np.nan,
                "oos_mean_ic": float(oos_view["mean_ic"].mean()) if not oos_view.empty else np.nan,
                "oos_positive_ratio": float(oos_view["positive_ratio"].mean()) if not oos_view.empty else np.nan,
            }
        )
    result = pd.DataFrame(rows).sort_values("oos_mean_ic", ascending=False).reset_index(drop=True)
    result.to_csv(TABLE_DIR / "factor_group_summary.csv", index=False, encoding="utf-8-sig")
    return result


def build_factor_correlation(data: pd.DataFrame, start_date: str = TEST_START_DATE) -> pd.DataFrame:
    columns = [f"z_{factor}" for factor in DAILY_FACTOR_COLUMNS]
    sample = data[(data["research_universe"]) & (data["trade_date"] >= start_date)][columns].replace([np.inf, -np.inf], np.nan)
    if len(sample) > 120_000:
        sample = sample.sample(120_000, random_state=7)
    corr = sample.corr(method="spearman")
    corr.index = [FACTOR_LABELS.get(c.replace("z_", ""), c) for c in corr.index]
    corr.columns = [FACTOR_LABELS.get(c.replace("z_", ""), c) for c in corr.columns]
    corr.to_csv(TABLE_DIR / "factor_correlation.csv", encoding="utf-8-sig")
    return corr


def build_ai_actions(ic_summary: pd.DataFrame) -> pd.DataFrame:
    actions = describe_ai_factor_actions(ic_summary)
    columns = ["factor", "factor_name", "mean_ic", "ic_ir", "positive_ratio", "ai_action", "ai_reason"]
    actions[columns].to_csv(TABLE_DIR / "ai_factor_actions.csv", index=False, encoding="utf-8-sig")
    return actions[columns]


def build_sample_commonality(data: pd.DataFrame, start_date: str = TEST_START_DATE) -> pd.DataFrame:
    panel = data[(data["research_universe"]) & (data["trade_date"] >= start_date)].dropna(subset=["next_20d_return"]).copy()
    if panel.empty:
        panel = data[data["research_universe"]].dropna(subset=["next_20d_return"]).copy()
    panel["strong_sample"] = panel.groupby("trade_date")["next_20d_return"].transform(
        lambda s: s >= s.quantile(0.9) if len(s) >= 80 else False
    )
    rows: list[dict[str, object]] = []
    for factor in DAILY_FACTOR_COLUMNS:
        z_col = f"z_{factor}"
        strong = pd.to_numeric(panel.loc[panel["strong_sample"], z_col], errors="coerce")
        universe = pd.to_numeric(panel[z_col], errors="coerce")
        diff = float(strong.median() - universe.median()) if strong.notna().any() and universe.notna().any() else np.nan
        rows.append(
            {
                "factor": factor,
                "factor_name": FACTOR_LABELS.get(factor, factor),
                "strong_sample_median_z": float(strong.median()) if strong.notna().any() else np.nan,
                "universe_median_z": float(universe.median()) if universe.notna().any() else np.nan,
                "median_diff_z": diff,
                "ai_commonality": "强势样本显著偏高" if diff >= 0.15 else ("强势样本显著偏低" if diff <= -0.15 else "差异不显著"),
            }
        )
    result = pd.DataFrame(rows).sort_values("median_diff_z", ascending=False).reset_index(drop=True)
    result.to_csv(TABLE_DIR / "strong_sample_commonality.csv", index=False, encoding="utf-8-sig")
    return result


def build_quantile_returns(data: pd.DataFrame, score_col: str = "optimized_score", start_date: str = TEST_START_DATE) -> pd.DataFrame:
    panel = data[(data["research_universe"]) & (data["trade_date"] >= start_date)].dropna(subset=[score_col, "next_return"]).copy()
    if panel.empty:
        panel = data[data["research_universe"]].dropna(subset=[score_col, "next_return"]).copy()
    rows: list[dict[str, object]] = []
    for trade_date, day in panel.groupby("trade_date"):
        if len(day) < 100:
            continue
        ranked = day[[score_col, "next_return"]].copy()
        ranked["bucket"] = pd.qcut(ranked[score_col].rank(method="first"), 5, labels=[1, 2, 3, 4, 5])
        ret = ranked.groupby("bucket", observed=False)["next_return"].mean()
        rows.append(
            {
                "trade_date": trade_date,
                "q1": ret.get(1, np.nan),
                "q2": ret.get(2, np.nan),
                "q3": ret.get(3, np.nan),
                "q4": ret.get(4, np.nan),
                "q5": ret.get(5, np.nan),
                "long_short": ret.get(5, np.nan) - ret.get(1, np.nan),
            }
        )
    result = pd.DataFrame(rows).sort_values("trade_date").reset_index(drop=True)
    if not result.empty:
        result["long_short_nav"] = (1 + result["long_short"].fillna(0.0)).cumprod()
    result.to_csv(TABLE_DIR / "optimized_quantile_returns.csv", index=False, encoding="utf-8-sig")
    return result


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


def run_top_portfolio_backtest(
    data: pd.DataFrame,
    benchmark: pd.DataFrame,
    score_col: str = "optimized_score",
    start_date: str = TEST_START_DATE,
    end_date: str | None = None,
    top_n: int = 50,
    fee_rate: float = DEFAULT_FEE_RATE,
    output_prefix: str | None = "optimized_selected",
) -> BacktestResult:
    required_columns = ["ts_code", "trade_date", "research_universe", score_col, "next_return"]
    panel = data.loc[(data["research_universe"]) & (data["trade_date"] >= start_date), required_columns].dropna(subset=[score_col, "next_return"]).copy()
    if end_date:
        panel = panel[panel["trade_date"] <= end_date]
    if panel.empty:
        panel = data.loc[data["research_universe"], required_columns].dropna(subset=[score_col, "next_return"]).copy()
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
        strategy_return = gross_return - turnover * fee_rate
        rows.append(
            {
                "trade_date": trade_date,
                "strategy_return": strategy_return,
                "gross_return": gross_return,
                "benchmark_return": benchmark_map.get(trade_date, np.nan),
                "turnover": turnover,
                "holding_count": len(selected),
            }
        )
        previous_holdings = holdings
    performance = pd.DataFrame(rows).sort_values("trade_date").reset_index(drop=True)
    if performance.empty:
        summary = pd.DataFrame()
        return BacktestResult(performance, summary)
    performance["strategy_nav"] = (1 + performance["strategy_return"].fillna(0.0)).cumprod()
    performance["benchmark_nav"] = (1 + performance["benchmark_return"].fillna(0.0)).cumprod()
    performance["excess_return"] = performance["strategy_return"] - performance["benchmark_return"].fillna(0.0)
    performance["excess_nav"] = (1 + performance["excess_return"].fillna(0.0)).cumprod()

    summary = pd.DataFrame([_performance_summary(performance)])
    if output_prefix:
        performance.to_csv(TABLE_DIR / f"{output_prefix}_backtest_daily.csv", index=False, encoding="utf-8-sig")
        summary.to_csv(TABLE_DIR / f"{output_prefix}_backtest_summary.csv", index=False, encoding="utf-8-sig")
    return BacktestResult(performance, summary)


def _performance_summary(performance: pd.DataFrame) -> dict[str, float | int]:
    trading_days = max(len(performance), 1)
    strategy_return = pd.to_numeric(performance["strategy_return"], errors="coerce").fillna(0.0)
    benchmark_return = pd.to_numeric(performance["benchmark_return"], errors="coerce").fillna(0.0)
    excess_return = strategy_return - benchmark_return
    nav = (1 + strategy_return).cumprod()
    benchmark_nav = (1 + benchmark_return).cumprod()
    drawdown = nav / nav.cummax() - 1
    excess_nav = (1 + excess_return).cumprod()
    excess_drawdown = excess_nav / excess_nav.cummax() - 1
    annualized_return = float(nav.iloc[-1] ** (252 / trading_days) - 1)
    benchmark_annualized_return = float(benchmark_nav.iloc[-1] ** (252 / trading_days) - 1)
    annualized_vol = float(strategy_return.std(ddof=0) * math.sqrt(252))
    excess_annualized_return = float(excess_nav.iloc[-1] ** (252 / trading_days) - 1)
    return {
        "trading_days": int(trading_days),
        "annualized_return": annualized_return,
        "benchmark_annualized_return": benchmark_annualized_return,
        "excess_annualized_return": excess_annualized_return,
        "annualized_volatility": annualized_vol,
        "sharpe": float(annualized_return / annualized_vol) if annualized_vol > 0 else 0.0,
        "max_drawdown": float(drawdown.min()),
        "excess_max_drawdown": float(excess_drawdown.min()),
        "win_rate": float((strategy_return > 0).mean()),
        "avg_turnover": float(pd.to_numeric(performance["turnover"], errors="coerce").mean()),
    }


def build_validation_windows(
    data: pd.DataFrame,
    min_train_days: int = 252,
    validation_days: int = 60,
    max_windows: int = 4,
) -> list[dict[str, str]]:
    train_dates = sorted(
        data.loc[
            (data["research_universe"])
            & (data["trade_date"] >= START_DATE)
            & (data["trade_date"] <= MODEL_TRAIN_END_DATE),
            "trade_date",
        ].astype(str).unique().tolist()
    )
    if len(train_dates) < min_train_days + validation_days:
        return []
    possible_windows = max((len(train_dates) - min_train_days) // validation_days, 1)
    window_count = min(max_windows, possible_windows)
    start_idx = len(train_dates) - window_count * validation_days
    windows: list[dict[str, str]] = []
    for idx in range(window_count):
        val_start_idx = start_idx + idx * validation_days
        train_end_idx = val_start_idx - 1
        val_end_idx = min(val_start_idx + validation_days - 1, len(train_dates) - 1)
        if train_end_idx < min_train_days - 1:
            continue
        windows.append(
            {
                "window_id": f"window_{idx + 1}",
                "train_end": train_dates[train_end_idx],
                "validation_start": train_dates[val_start_idx],
                "validation_end": train_dates[val_end_idx],
            }
        )
    return windows


def build_ridge_model_score(
    data: pd.DataFrame,
    target: str,
    score_col: str,
    features: list[str],
    train_end_date: str,
) -> pd.DataFrame:
    coefficients = fit_ridge_coefficients(data, target, features, train_end_date, alpha=25.0)
    data[score_col] = compute_ridge_score_series(data, features, coefficients)
    data[f"z_{score_col}"] = data.groupby("trade_date")[score_col].transform(winsorized_zscore)

    coefficient_table = pd.DataFrame(
        {
            "feature": features,
            "factor_group": [FACTOR_GROUP_MAP.get(feature, "其他") for feature in features],
            "feature_name": [FACTOR_LABELS.get(feature, feature) for feature in features],
            "coefficient": coefficients,
            "target": target,
            "score_col": score_col,
        }
    ).sort_values("coefficient", ascending=False)
    return coefficient_table


def select_best_model_config(configs: pd.DataFrame) -> pd.Series:
    if configs.empty:
        raise ValueError("model config table is empty")
    normalized = configs.copy()
    for column in [
        "validation_objective_mean",
        "validation_objective_std",
        "train_objective",
        "train_sharpe",
        "train_excess_annualized_return",
    ]:
        if column not in normalized.columns:
            normalized[column] = 0.0
    ranked = normalized.sort_values(
        ["validation_objective_mean", "validation_objective_std", "train_objective", "train_sharpe", "train_excess_annualized_return"],
        ascending=[False, True, False, False, False],
    ).reset_index(drop=True)
    return ranked.iloc[0]


def build_model_scores_and_select(
    data: pd.DataFrame,
    benchmark: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, float], pd.DataFrame, pd.DataFrame, BacktestResult, pd.DataFrame, pd.DataFrame]:
    scored = data.copy()
    model_rows: list[dict[str, object]] = []
    model_weights: dict[str, dict[str, float]] = {}
    model_ic: dict[str, pd.DataFrame] = {}
    ridge_coefficients: dict[str, pd.DataFrame] = {}
    validation_windows = pd.DataFrame(build_validation_windows(scored))
    base_validation_panel = scored[["ts_code", "trade_date", "research_universe", "next_return"]].copy()

    for target in TARGET_LABELS:
        ic_summary = build_ic_summary(scored, target=target, start_date=START_DATE, end_date=MODEL_TRAIN_END_DATE)
        weights = build_factor_weights(ic_summary, max_factors=10)
        ensemble_col = f"ensemble_{target}"
        scored = apply_optimized_score(scored, weights, score_col=ensemble_col)
        model_weights[ensemble_col] = weights
        model_ic[ensemble_col] = ic_summary

        ridge_col = f"ridge_{target}"
        ridge_coefficients[ridge_col] = build_ridge_model_score(scored, target, ridge_col, DAILY_FACTOR_COLUMNS, MODEL_TRAIN_END_DATE)
        model_weights[ridge_col] = {}
        model_ic[ridge_col] = ic_summary

        for model_type, score_col in [("多因子IC加权", ensemble_col), ("Ridge横截面机器学习", ridge_col)]:
            validation_panels: list[pd.DataFrame] = []
            for window in validation_windows.to_dict("records"):
                if model_type == "多因子IC加权":
                    window_ic = build_ic_summary(scored, target=target, start_date=START_DATE, end_date=str(window["train_end"]))
                    window_weights = build_factor_weights(window_ic, max_factors=10)
                    window_score = compute_weighted_score_series(scored, window_weights)
                else:
                    window_coefficients = fit_ridge_coefficients(scored, target, DAILY_FACTOR_COLUMNS, str(window["train_end"]), alpha=25.0)
                    window_score = compute_ridge_score_series(scored, DAILY_FACTOR_COLUMNS, window_coefficients)
                validation_panels.append(
                    pd.DataFrame(
                        {
                            "ts_code": base_validation_panel["ts_code"],
                            "trade_date": base_validation_panel["trade_date"],
                            "research_universe": base_validation_panel["research_universe"],
                            "next_return": base_validation_panel["next_return"],
                            "window_score": window_score,
                            "validation_start": str(window["validation_start"]),
                            "validation_end": str(window["validation_end"]),
                        }
                    )
                )
            for top_n in [50, 100, 200, 300]:
                validation_rows: list[pd.Series] = []
                for window_data in validation_panels:
                    validation_result = run_top_portfolio_backtest(
                        window_data,
                        benchmark,
                        score_col="window_score",
                        start_date=str(window_data["validation_start"].iloc[0]),
                        end_date=str(window_data["validation_end"].iloc[0]),
                        top_n=top_n,
                        output_prefix=None,
                    )
                    if validation_result.summary.empty:
                        continue
                    validation_rows.append(validation_result.summary.iloc[0])

                if validation_rows:
                    validation_frame = pd.DataFrame(validation_rows)
                    validation_objective_mean = float(validation_frame.apply(model_objective, axis=1).mean())
                    validation_objective_std = float(validation_frame.apply(model_objective, axis=1).std(ddof=0)) if len(validation_frame) > 1 else 0.0
                    validation_excess_mean = float(validation_frame["excess_annualized_return"].mean())
                    validation_drawdown_mean = float(validation_frame["max_drawdown"].mean())
                    validation_turnover_mean = float(validation_frame["avg_turnover"].mean())
                else:
                    validation_objective_mean = np.nan
                    validation_objective_std = np.nan
                    validation_excess_mean = np.nan
                    validation_drawdown_mean = np.nan
                    validation_turnover_mean = np.nan

                train_result = run_top_portfolio_backtest(
                    scored,
                    benchmark,
                    score_col=score_col,
                    start_date=START_DATE,
                    end_date=MODEL_TRAIN_END_DATE,
                    top_n=top_n,
                    output_prefix=None,
                )
                if train_result.summary.empty:
                    continue
                row = train_result.summary.iloc[0].to_dict()
                objective = model_objective(pd.Series(row))
                model_rows.append(
                    {
                        "model_id": f"{score_col}_top{top_n}",
                        "model_type": model_type,
                        "target": target,
                        "target_label": TARGET_LABELS[target],
                        "score_col": score_col,
                        "top_n": top_n,
                        "validation_window_count": int(len(validation_rows)),
                        "validation_objective_mean": validation_objective_mean,
                        "validation_objective_std": validation_objective_std,
                        "validation_excess_annualized_return": validation_excess_mean,
                        "validation_max_drawdown": validation_drawdown_mean,
                        "validation_avg_turnover": validation_turnover_mean,
                        "train_objective": objective,
                        "train_annualized_return": row["annualized_return"],
                        "train_benchmark_annualized_return": row["benchmark_annualized_return"],
                        "train_excess_annualized_return": row["excess_annualized_return"],
                        "train_sharpe": row["sharpe"],
                        "train_max_drawdown": row["max_drawdown"],
                        "train_avg_turnover": row["avg_turnover"],
                    }
                )
    config_table = pd.DataFrame(model_rows).sort_values(
        ["validation_objective_mean", "train_objective"],
        ascending=False,
    ).reset_index(drop=True)
    config_table.to_csv(TABLE_DIR / "model_selection_train.csv", index=False, encoding="utf-8-sig")
    selected = select_best_model_config(config_table)
    selected_score_col = str(selected["score_col"])
    selected_weights = model_weights[selected_score_col]
    selected_ic = model_ic[selected_score_col]
    coefficients = pd.concat(ridge_coefficients.values(), ignore_index=True) if ridge_coefficients else pd.DataFrame()
    coefficients.to_csv(TABLE_DIR / "ridge_model_coefficients.csv", index=False, encoding="utf-8-sig")
    if selected_weights:
        selected_weight_table = build_factor_weight_table(selected_weights, selected_ic, output_name="factor_weights.csv")
    else:
        selected_target_coefficients = coefficients[coefficients["score_col"] == selected_score_col].copy()
        selected_target_coefficients["weight"] = selected_target_coefficients["coefficient"].abs()
        total_weight = float(selected_target_coefficients["weight"].sum()) if not selected_target_coefficients.empty else 0.0
        if total_weight > 0:
            selected_target_coefficients["weight"] = selected_target_coefficients["weight"] / total_weight
        selected_weight_table = selected_target_coefficients.rename(columns={"feature": "factor", "feature_name": "factor_name"})[
            ["factor", "factor_name", "weight"]
        ]
        selected_weight_table = selected_weight_table.merge(
            selected_ic[["factor", "mean_ic", "positive_ratio"]],
            on="factor",
            how="left",
        ).sort_values("weight", ascending=False).reset_index(drop=True)
        selected_weight_table.to_csv(TABLE_DIR / "factor_weights.csv", index=False, encoding="utf-8-sig")
    oos_result = run_top_portfolio_backtest(
        scored,
        benchmark,
        score_col=selected_score_col,
        start_date=TEST_START_DATE,
        top_n=int(selected["top_n"]),
        output_prefix="optimized_selected",
    )
    selected.to_frame().T.to_csv(TABLE_DIR / "model_selection_selected.csv", index=False, encoding="utf-8-sig")
    validation_windows.to_csv(TABLE_DIR / "rolling_validation_windows.csv", index=False, encoding="utf-8-sig")
    return scored.rename(columns={selected_score_col: "optimized_score"}), selected_weights, selected_weight_table, config_table, oos_result, coefficients, validation_windows


def build_timing_regime(con: duckdb.DuckDBPyConnection) -> tuple[pd.DataFrame, pd.DataFrame]:
    benchmark = load_benchmark(con)[["trade_date", "close", "pct_chg", "amount"]].copy()
    breadth = con.execute(
        f"""
        select
            cast(trade_date as varchar) as trade_date,
            avg(case when pct_chg > 0 then 1.0 else 0.0 end) as adv_ratio,
            sum(amount) as market_amount
        from daily_base
        where trade_date >= '{START_DATE}'
        group by trade_date
        order by trade_date
        """
    ).fetchdf()
    merged = benchmark.merge(breadth, on="trade_date", how="left").sort_values("trade_date").reset_index(drop=True)
    merged["close"] = pd.to_numeric(merged["close"], errors="coerce")
    merged["ma20"] = merged["close"].rolling(20).mean()
    merged["ma60"] = merged["close"].rolling(60).mean()
    merged["return_20"] = merged["close"].pct_change(20)
    merged["volatility_20"] = merged["close"].pct_change().rolling(20).std()
    merged["amount_z20"] = winsorized_zscore(merged["market_amount"].rolling(20).mean())
    merged["next_5d_return"] = merged["close"].shift(-5) / merged["close"] - 1
    merged["regime"] = "中性震荡"
    merged.loc[(merged["close"] > merged["ma20"]) & (merged["ma20"] > merged["ma60"]) & (merged["adv_ratio"] >= 0.55), "regime"] = "趋势上行"
    merged.loc[(merged["close"] < merged["ma20"]) & (merged["ma20"] < merged["ma60"]) & (merged["adv_ratio"] <= 0.45), "regime"] = "风险收缩"
    merged.loc[(merged["close"] > merged["ma20"]) & (merged["adv_ratio"] >= 0.60) & (merged["return_20"] < 0.04), "regime"] = "修复反弹"
    merged.loc[(merged["volatility_20"] >= merged["volatility_20"].quantile(0.75)) & (merged["adv_ratio"] < 0.50), "regime"] = "高波动分化"
    merged["ai_timing_read"] = merged["regime"].map(
        {
            "趋势上行": "趋势和宽度共振，适合提高权益暴露并强化动量类信号",
            "修复反弹": "宽度改善但趋势仍需确认，适合结合反转与低估值修复",
            "风险收缩": "趋势与宽度同步走弱，适合降低仓位或提高防御过滤",
            "高波动分化": "波动抬升且赚钱效应不足，适合降低换手并控制回撤",
            "中性震荡": "趋势信号不充分，适合等待宽度或量能确认",
        }
    )
    summary = (
        merged.dropna(subset=["next_5d_return"])
        .groupby("regime", as_index=False)
        .agg(
            observations=("trade_date", "count"),
            avg_next_5d_return=("next_5d_return", "mean"),
            win_rate=("next_5d_return", lambda s: float((s > 0).mean())),
            avg_adv_ratio=("adv_ratio", "mean"),
        )
        .sort_values("avg_next_5d_return", ascending=False)
        .reset_index(drop=True)
    )
    summary["ai_timing_read"] = summary["regime"].map(merged.drop_duplicates("regime").set_index("regime")["ai_timing_read"])
    merged.to_csv(TABLE_DIR / "timing_regime_daily_enhanced.csv", index=False, encoding="utf-8-sig")
    summary.to_csv(TABLE_DIR / "timing_regime_summary_enhanced.csv", index=False, encoding="utf-8-sig")
    return merged, summary


def stock_code_from_minute_name(path: Path) -> str:
    stem = path.stem.lower()
    if stem.startswith("sh"):
        return f"{stem[2:]}.SH"
    if stem.startswith("sz"):
        return f"{stem[2:]}.SZ"
    if stem.startswith("bj"):
        return f"{stem[2:]}.BJ"
    return stem.upper()


def load_intraday_features(daily_data: pd.DataFrame, max_files: int = 600) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not MINUTE_DIR.exists():
        empty = pd.DataFrame()
        return empty, empty
    recent_liquid = (
        daily_data[
            (daily_data["research_universe"])
            & (daily_data["trade_date"] >= START_DATE)
            & (daily_data["trade_date"] <= MODEL_TRAIN_END_DATE)
        ]
        .groupby("ts_code", as_index=False)["amount"]
        .median()
        .sort_values("amount", ascending=False)
        .head(max_files)
    )
    target_codes = set(recent_liquid["ts_code"].astype(str))
    paths = [path for path in MINUTE_DIR.glob("*.parquet") if stock_code_from_minute_name(path) in target_codes]
    rows: list[pd.DataFrame] = []
    for path in paths[:max_files]:
        ts_code = stock_code_from_minute_name(path)
        try:
            minute = pd.read_parquet(path, columns=["trade_date", "trade_time", "open", "high", "low", "close", "amount"])
        except Exception:
            continue
        minute["trade_date"] = minute["trade_date"].astype(str)
        minute = minute[minute["trade_date"] >= TEST_START_DATE].copy()
        if minute.empty:
            continue
        for col in ["open", "high", "low", "close", "amount"]:
            minute[col] = pd.to_numeric(minute[col], errors="coerce")
        minute["bar_return"] = minute.groupby("trade_date")["close"].pct_change()
        daily = (
            minute.groupby("trade_date")
            .agg(
                first_open=("open", "first"),
                first_close=("close", "first"),
                last_close=("close", "last"),
                high=("high", "max"),
                low=("low", "min"),
                total_amount=("amount", "sum"),
                last_bar_amount=("amount", "last"),
                intraday_volatility=("bar_return", "std"),
            )
            .reset_index()
        )
        daily["ts_code"] = ts_code
        daily["intraday_return"] = daily["last_close"] / daily["first_open"] - 1
        daily["first_bar_return"] = daily["first_close"] / daily["first_open"] - 1
        daily["tail_bar_amount_ratio"] = daily["last_bar_amount"] / daily["total_amount"].replace(0, np.nan)
        daily["intraday_amplitude"] = daily["high"] / daily["low"].replace(0, np.nan) - 1
        rows.append(daily)
    if not rows:
        empty = pd.DataFrame()
        return empty, empty
    features = pd.concat(rows, ignore_index=True)
    merged = features.merge(
        daily_data[["ts_code", "trade_date", "next_5d_return", "next_20d_return"]],
        on=["ts_code", "trade_date"],
        how="inner",
    )
    intraday_factors = ["intraday_return", "first_bar_return", "tail_bar_amount_ratio", "intraday_amplitude", "intraday_volatility"]
    ic_rows: list[dict[str, object]] = []
    for factor in intraday_factors:
        daily_ic = merged.groupby("trade_date").apply(lambda x: daily_rank_ic(x, factor, "next_5d_return"), include_groups=False)
        daily_ic = pd.to_numeric(daily_ic, errors="coerce").dropna()
        if daily_ic.empty:
            continue
        std = daily_ic.std(ddof=0)
        ic_rows.append(
            {
                "factor": factor,
                "factor_name": {
                    "intraday_return": "日内收益",
                    "first_bar_return": "首小时强弱",
                    "tail_bar_amount_ratio": "尾盘成交占比",
                    "intraday_amplitude": "日内振幅",
                    "intraday_volatility": "日内波动",
                }[factor],
                "mean_ic": float(daily_ic.mean()),
                "ic_ir": float(daily_ic.mean() / std) if std and not pd.isna(std) else 0.0,
                "positive_ratio": float((daily_ic > 0).mean()),
                "observations": int(len(daily_ic)),
            }
        )
    ic_summary = pd.DataFrame(ic_rows).sort_values("mean_ic", ascending=False).reset_index(drop=True)
    features.to_csv(TABLE_DIR / "intraday_60m_features_sample.csv", index=False, encoding="utf-8-sig")
    ic_summary.to_csv(TABLE_DIR / "intraday_60m_ic_summary.csv", index=False, encoding="utf-8-sig")
    return features, ic_summary


def save_figures(
    train_ic: pd.DataFrame,
    oos_ic: pd.DataFrame,
    factor_corr: pd.DataFrame,
    quantile: pd.DataFrame,
    backtest: BacktestResult,
    timing_summary: pd.DataFrame,
    intraday_ic: pd.DataFrame,
) -> None:
    plt.style.use("seaborn-v0_8-whitegrid")
    plt.rcParams["font.family"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    plt.figure(figsize=(10.5, 5.2))
    plot_ic = oos_ic.head(10).sort_values("mean_ic")
    plt.barh(plot_ic["factor_name"], plot_ic["mean_ic"], color=SECONDARY_COLOR, alpha=0.92)
    plt.axvline(0, color="#666666", linewidth=0.9)
    plt.title("样本外候选因子Rank IC（未来5日）")
    plt.xlabel("平均Rank IC")
    plt.grid(axis="x", color=GRID_COLOR, linewidth=0.8)
    plt.tight_layout()
    plt.savefig(FIGURE_DIR / "oos_factor_ic_bar.png", dpi=180)
    plt.close()

    if not factor_corr.empty:
        plt.figure(figsize=(9.5, 7.2))
        plt.imshow(factor_corr.fillna(0.0), cmap="RdYlGn", vmin=-1, vmax=1)
        plt.colorbar(fraction=0.046, pad=0.04)
        plt.xticks(range(len(factor_corr.columns)), factor_corr.columns, rotation=60, ha="right", fontsize=8)
        plt.yticks(range(len(factor_corr.index)), factor_corr.index, fontsize=8)
        plt.title("候选因子相关性热力图（用于识别冗余）")
        plt.tight_layout()
        plt.savefig(FIGURE_DIR / "factor_correlation_heatmap.png", dpi=180)
        plt.close()

    if not quantile.empty:
        plt.figure(figsize=(10.5, 5.2))
        x = pd.to_datetime(quantile["trade_date"])
        y = quantile["long_short_nav"]
        plt.plot(x, y, color=NEGATIVE_COLOR, linewidth=1.8)
        plt.fill_between(x, y, 1.0, color=NEGATIVE_COLOR, alpha=0.10)
        plt.title("AI辅助优化综合分：Q5-Q1多空净值")
        plt.ylabel("多空净值")
        plt.tight_layout()
        plt.savefig(FIGURE_DIR / "optimized_long_short_nav.png", dpi=180)
        plt.close()

    if not backtest.performance.empty:
        perf = backtest.performance
        drawdown = perf["strategy_nav"] / perf["strategy_nav"].cummax() - 1
        fig, axes = plt.subplots(2, 1, figsize=(10.8, 7.2), sharex=True, gridspec_kw={"height_ratios": [3.3, 1.2]})
        x = pd.to_datetime(perf["trade_date"])
        axes[0].plot(x, perf["strategy_nav"], label="选定组合", color=SECONDARY_COLOR, linewidth=2.0)
        axes[0].plot(x, perf["benchmark_nav"], label="沪深300", color=ACCENT_COLOR, linewidth=1.6)
        axes[0].plot(x, perf["excess_nav"], label="超额净值", color=PRIMARY_COLOR, linewidth=1.6)
        axes[0].set_title("AI辅助优化综合分选定组合回测")
        axes[0].set_ylabel("净值")
        axes[0].legend(loc="upper left", ncol=3, frameon=False)
        axes[0].grid(color=GRID_COLOR, linewidth=0.8)

        axes[1].fill_between(x, drawdown, 0.0, color=NEGATIVE_COLOR, alpha=0.18)
        axes[1].plot(x, drawdown, color=NEGATIVE_COLOR, linewidth=1.1)
        axes[1].axhline(0, color="#666666", linewidth=0.8)
        axes[1].set_ylabel("回撤")
        axes[1].grid(color=GRID_COLOR, linewidth=0.8)

        fig.tight_layout()
        fig.savefig(FIGURE_DIR / SELECTED_NAV_FIGURE, dpi=180)
        plt.close(fig)

    if not timing_summary.empty:
        plt.figure(figsize=(9.4, 5.0))
        plt.bar(timing_summary["regime"], timing_summary["avg_next_5d_return"], color=PRIMARY_COLOR, alpha=0.88)
        plt.axhline(0, color="#666666", linewidth=0.8)
        plt.title("不同市场状态下沪深300未来5日平均收益")
        plt.ylabel("未来5日平均收益")
        plt.tight_layout()
        plt.savefig(FIGURE_DIR / "timing_regime_enhanced.png", dpi=180)
        plt.close()

    if not intraday_ic.empty:
        plt.figure(figsize=(8.8, 4.8))
        plot_intraday = intraday_ic.sort_values("mean_ic")
        plt.barh(plot_intraday["factor_name"], plot_intraday["mean_ic"], color=ACCENT_COLOR, alpha=0.9)
        plt.axvline(0, color="#666666", linewidth=0.8)
        plt.title("60分钟日内结构特征Rank IC（样本股票）")
        plt.xlabel("平均Rank IC")
        plt.tight_layout()
        plt.savefig(FIGURE_DIR / "intraday_60m_ic_bar.png", dpi=180)
        plt.close()


def add_heading(document: Document, text: str, level: int = 1) -> None:
    paragraph = document.add_paragraph(style=find_heading_style(document, level))
    run = paragraph.add_run(text)
    run.bold = True
    run.font.name = "Microsoft YaHei"
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
    run.font.size = Pt(14 if level == 1 else 12)


def find_heading_style(document: Document, level: int) -> str | None:
    candidates = [f"Heading {min(level, 3)}", f"标题 {min(level, 3)}", f"{min(level, 3)}"]
    available = {style.name for style in document.styles}
    for candidate in candidates:
        if candidate in available:
            return candidate
    return None


def apply_report_styles(document: Document) -> None:
    section = document.sections[-1]
    section.top_margin = Inches(0.8)
    section.bottom_margin = Inches(0.8)
    section.left_margin = Inches(0.85)
    section.right_margin = Inches(0.85)
    normal = document.styles["Normal"]
    normal.font.name = "Microsoft YaHei"
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
    normal.font.size = Pt(10.5)
    for style_name in ["Heading 1", "Heading 2", "Heading 3", "标题 1", "标题 2", "标题 3"]:
        if style_name not in {style.name for style in document.styles}:
            continue
        style = document.styles[style_name]
        style.font.name = "Microsoft YaHei"
        style._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
        style.font.bold = True
        style.font.color.rgb = RGBColor(31, 78, 121)


def set_cell_shading(cell, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shading = OxmlElement("w:shd")
    shading.set(qn("w:fill"), fill)
    tc_pr.append(shading)


def set_cell_text_style(cell, bold: bool = False, size: float = 8.5) -> None:
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    for paragraph in cell.paragraphs:
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER if bold else WD_ALIGN_PARAGRAPH.LEFT
        for run in paragraph.runs:
            run.font.name = "Microsoft YaHei"
            run._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
            run.font.size = Pt(size)
            run.bold = bold


def add_table(document: Document, title: str, frame: pd.DataFrame, max_rows: int = 8) -> None:
    caption = document.add_paragraph()
    caption_run = caption.add_run(title)
    caption_run.bold = True
    caption_run.font.name = "Microsoft YaHei"
    caption_run._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
    caption_run.font.size = Pt(10)
    display = frame.head(max_rows).copy()
    if display.empty:
        document.add_paragraph("暂无可展示数据。")
        return
    table = document.add_table(rows=1, cols=len(display.columns))
    try:
        table.style = "Table Grid"
    except KeyError:
        pass
    for idx, column in enumerate(display.columns):
        table.rows[0].cells[idx].text = str(column)
        set_cell_shading(table.rows[0].cells[idx], "D9EAF7")
        set_cell_text_style(table.rows[0].cells[idx], bold=True, size=8.5)
    for _, row in display.iterrows():
        cells = table.add_row().cells
        for idx, value in enumerate(row.tolist()):
            cells[idx].text = format_cell_value(value)
            set_cell_text_style(cells[idx], size=8.0)
    table.autofit = True


def format_cell_value(value: object) -> str:
    if isinstance(value, (float, np.floating)):
        if pd.isna(value):
            return ""
        if abs(float(value)) < 1:
            return f"{float(value):.4f}"
        return f"{float(value):.2f}"
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    return str(value)


def format_fee_rate(fee_rate: float) -> str:
    return f"{fee_rate:.2%}"


def add_picture_if_exists(document: Document, path: Path, width: float = 6.2) -> None:
    if path.exists() and path.stat().st_size > 0:
        document.add_picture(str(path), width=Inches(width))


def localized_ic_table(frame: pd.DataFrame) -> pd.DataFrame:
    columns = ["factor_name", "mean_ic", "ic_ir", "positive_ratio", "observations"]
    result = frame[columns].copy()
    return result.rename(
        columns={
            "factor_name": "因子",
            "mean_ic": "平均IC",
            "ic_ir": "IC_IR",
            "positive_ratio": "正IC占比",
            "observations": "观测日数",
        }
    )


def localized_factor_group_table(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    return frame.rename(
        columns={
            "factor_group": "因子组",
            "factor_count": "因子数量",
            "train_mean_ic": "训练期平均IC",
            "train_positive_ratio": "训练期正IC占比",
            "oos_mean_ic": "样本外平均IC",
            "oos_positive_ratio": "样本外正IC占比",
        }
    )


def localized_weight_table(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    return frame[["factor_name", "weight", "mean_ic", "positive_ratio"]].rename(
        columns={
            "factor_name": "因子",
            "weight": "权重",
            "mean_ic": "训练期平均IC",
            "positive_ratio": "训练期正IC占比",
        }
    )


def localized_coefficient_table(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    return frame[["feature_name", "factor_group", "coefficient", "target"]].rename(
        columns={
            "feature_name": "特征",
            "factor_group": "因子组",
            "coefficient": "系数",
            "target": "训练标签",
        }
    )


def localized_model_selection_table(frame: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "model_type",
        "target_label",
        "top_n",
        "validation_objective_mean",
        "validation_objective_std",
        "validation_excess_annualized_return",
        "validation_avg_turnover",
        "train_objective",
        "train_annualized_return",
        "train_max_drawdown",
    ]
    available = [column for column in columns if column in frame.columns]
    return frame[available].rename(
        columns={
            "model_type": "模型类型",
            "target_label": "训练标签",
            "top_n": "持仓数",
            "validation_objective_mean": "滚动验证目标分均值",
            "validation_objective_std": "滚动验证目标分波动",
            "validation_excess_annualized_return": "滚动验证年化超额",
            "validation_avg_turnover": "滚动验证平均换手",
            "train_objective": "全训练期目标分",
            "train_annualized_return": "全训练期年化收益",
            "train_max_drawdown": "全训练期最大回撤",
        }
    )


def localized_validation_windows(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    return frame.rename(
        columns={
            "window_id": "验证窗口",
            "train_end": "训练截止日",
            "validation_start": "验证开始日",
            "validation_end": "验证结束日",
        }
    )


def localized_actions_table(frame: pd.DataFrame) -> pd.DataFrame:
    return frame[["factor_name", "mean_ic", "positive_ratio", "ai_action", "ai_reason"]].rename(
        columns={
            "factor_name": "因子",
            "mean_ic": "平均IC",
            "positive_ratio": "正IC占比",
            "ai_action": "AI动作归类",
            "ai_reason": "原因",
        }
    )


def localized_commonality_table(frame: pd.DataFrame) -> pd.DataFrame:
    return frame[["factor_name", "strong_sample_median_z", "universe_median_z", "median_diff_z", "ai_commonality"]].rename(
        columns={
            "factor_name": "因子",
            "strong_sample_median_z": "强势样本中位Z",
            "universe_median_z": "全市场中位Z",
            "median_diff_z": "差异",
            "ai_commonality": "AI共性归纳",
        }
    )


def build_no_leakage_check_table() -> pd.DataFrame:
    checks = pd.DataFrame(
        [
            {
                "检查项": "财务指标可得性",
                "处理方式": "财务面板按公告日ann_date向后匹配到交易日",
                "结论": "避免报告期数据提前进入历史样本",
            },
            {
                "检查项": "价量因子",
                "处理方式": "动量、反转、波动率、换手均使用pct_change或rolling历史窗口",
                "结论": "信号仅使用t日及以前行情",
            },
            {
                "检查项": "训练标签",
                "处理方式": f"模型权重和参数选择仅使用{MODEL_TRAIN_END_DATE}及以前标签",
                "结论": f"与{TEST_START_DATE}后的样本外区间隔离",
            },
            {
                "检查项": "模型参数选择",
                "处理方式": "候选模型先在训练期内部做滚动验证，再用全训练期复核，不用最终样本外结果筛选",
                "结论": "降低单段训练期筛优偏差，最终样本外结果只用于验证和复盘",
            },
            {
                "检查项": "60分钟样本选择",
                "处理方式": "分钟样本股票按训练期成交额中位数选取",
                "结论": "不使用样本外流动性挑选股票",
            },
        ]
    )
    checks.to_csv(TABLE_DIR / "no_leakage_checklist.csv", index=False, encoding="utf-8-sig")
    return checks


def write_report_docx(
    coverage: pd.DataFrame,
    no_leakage: pd.DataFrame,
    train_ic: pd.DataFrame,
    oos_ic: pd.DataFrame,
    factor_group_summary: pd.DataFrame,
    actions: pd.DataFrame,
    weights: pd.DataFrame,
    model_selection: pd.DataFrame,
    coefficients: pd.DataFrame,
    validation_windows: pd.DataFrame,
    commonality: pd.DataFrame,
    quantile: pd.DataFrame,
    backtest: BacktestResult,
    timing_summary: pd.DataFrame,
    intraday_ic: pd.DataFrame,
) -> None:
    document = Document()
    apply_report_styles(document)

    title = document.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title.add_run("选股与择时中AI可应用部分因子总结方案")
    run.bold = True
    run.font.name = "Microsoft YaHei"
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
    run.font.size = Pt(20)

    subtitle = document.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle_run = subtitle.add_run("增强优化数据支撑版")
    subtitle_run.bold = True
    subtitle_run.font.name = "Microsoft YaHei"
    subtitle_run._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
    subtitle_run.font.size = Pt(14)

    date_paragraph = document.add_paragraph()
    date_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    date_run = date_paragraph.add_run("生成日期：2026年05月25日")
    date_run.font.name = "Microsoft YaHei"
    date_run._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
    date_run.font.size = Pt(10.5)

    document.add_page_break()

    add_heading(document, "一、方案定位与核心结论", 1)
    if not backtest.summary.empty:
        summary_row = backtest.summary.iloc[0]
        selected_model = model_selection.iloc[0] if not model_selection.empty else None
        model_text = f"{selected_model['target_label']} / Top{int(selected_model['top_n'])}" if selected_model is not None else "训练期最优组合"
        document.add_paragraph(
            "本方案定位为AI增强型选股与择时研究流程。AI承担候选因子归纳、因子有效性筛选、模型组合参数枚举、"
            "回测复盘解释和市场状态识别等工作，量化数据底座负责提供可复现的行情、财务、交易约束和分钟级价量证据。"
        )
        document.add_paragraph(
            f"本轮训练期内选定模型为{model_text}，样本外组合年化收益为{summary_row['annualized_return']:.2%}，"
            f"沪深300同期年化收益为{summary_row['benchmark_annualized_return']:.2%}，年化超额为{summary_row['excess_annualized_return']:.2%}，"
            f"最大回撤为{summary_row['max_drawdown']:.2%}，平均换手为{summary_row['avg_turnover']:.2%}。"
            "该结果表明，AI辅助流程能够把因子研究从人工经验枚举推进到可审计、可复盘、可迭代的系统化流程。"
        )

    add_heading(document, "二、数据底座与研究口径", 1)
    document.add_paragraph(
        "本方案使用当前本地A股研究数据底座完成实证补充。"
        "目的不是宣称AI可以替代量化研究，而是展示AI可以嵌入研究流程：先自动识别因子有效性和冗余，"
        "再给出因子组合权重、样本共性解释、回测复盘和择时状态归因，最终形成可供研究员复核的结构化结论。"
    )
    add_table(document, "表1：数据覆盖情况", coverage.rename(columns={"dataset": "数据集", "row_count": "记录数/文件数", "note": "说明"}), 10)
    add_table(document, "表2：未来函数与样本外隔离检查", no_leakage, 8)

    add_heading(document, "（一）研究口径与防未来函数设计", 2)
    document.add_paragraph(
        "本轮优化将研究过程拆分为训练、滚动验证、全训练期复核和最终样本外验证四个环节。"
        f"因子权重、Ridge系数和持仓参数的形成均限制在{MODEL_TRAIN_END_DATE}及以前；"
        f"{TEST_START_DATE}之后只用于最终样本外检验、图表展示和复盘解释。"
        "财务指标使用公告日向后匹配，价量指标使用历史滚动窗口，模型选择优先依据训练期内部滚动验证结果，以降低未来数据泄露和单段样本筛优偏差。"
    )

    add_heading(document, "（二）因子筛选：用AI辅助形成候选因子动作清单", 2)
    document.add_paragraph(
        f"本次以{START_DATE}以来的可交易股票样本为基础，将{MODEL_TRAIN_END_DATE}及以前作为权重和参数形成区间，"
        f"{TEST_START_DATE}以来作为样本外观察区间。候选因子覆盖估值、质量、成长、资本结构、反转与趋势、相对强弱、波动防御、价格位置以及流动性/拥挤等九类信号。"
        "AI辅助部分并不直接生成交易结论，而是根据平均IC、IC_IR和正IC占比，把因子分为“核心加权、辅助过滤、观察保留、反向验证或降权”。"
    )
    add_table(document, "表3：训练期因子IC摘要", localized_ic_table(train_ic), 10)
    add_table(document, "表4：样本外因子IC摘要", localized_ic_table(oos_ic), 10)
    add_table(document, "表5：AI辅助因子动作清单", localized_actions_table(actions), 10)
    add_table(document, "表6：因子分组稳定性摘要", localized_factor_group_table(factor_group_summary), 10)
    add_picture_if_exists(document, FIGURE_DIR / "oos_factor_ic_bar.png")
    add_picture_if_exists(document, FIGURE_DIR / "factor_correlation_heatmap.png")

    add_heading(document, "（三）模型选择：训练期内比较目标期限与持仓数量", 2)
    if not model_selection.empty:
        selected = model_selection.iloc[0]
        document.add_paragraph(
            f"本轮没有直接用最终样本外表现挑模型，而是在训练期内部比较未来5日、未来20日两类标签下的多因子IC加权与Ridge横截面模型，并对Top50/100/200/300持仓数量做滚动验证。"
            f"滚动验证目标函数综合收益、超额、回撤和换手后，当前选定方案为{selected['model_type']} / {selected['target_label']} / Top{int(selected['top_n'])}。"
            "这个流程更接近真实量化研究：先看训练期内部跨阶段稳定性，再看全训练期复核结果，最后把最终样本外单独留作验证。"
        )
        add_table(document, "表7：滚动验证窗口划分", localized_validation_windows(validation_windows), 8)
        add_table(
            document,
            "表8：模型选择结果（按滚动验证优先排序）",
            localized_model_selection_table(model_selection),
            8,
        )

    add_heading(document, "（四）因子组合优化：从人工等权走向可解释权重", 2)
    if not weights.empty:
        top_weight_text = "、".join([f"{row.factor_name}({row.weight:.1%})" for row in weights.head(4).itertuples()])
    else:
        top_weight_text = "因子有效性不足，暂未形成稳定权重"
    document.add_paragraph(
        "根据训练期IC和稳定性自动形成组合权重，优先选择方向为正、正IC占比较高且IC_IR较好的因子。"
        f"本轮权重靠前的因子包括：{top_weight_text}。"
        "这类方法适合让AI承担“规则化初筛与解释”的角色，研究员再结合行业、市值和交易约束做二次确认。"
    )
    add_table(document, "表9：AI辅助优化因子权重", localized_weight_table(weights), 10)
    if not coefficients.empty:
        selected_score_col = model_selection.iloc[0]["score_col"] if not model_selection.empty else ""
        selected_coefficients = coefficients[coefficients["score_col"] == selected_score_col].copy()
        if not selected_coefficients.empty:
            selected_coefficients["abs_coef"] = selected_coefficients["coefficient"].abs()
            add_table(document, "表10：选定Ridge模型主要特征系数", localized_coefficient_table(selected_coefficients.sort_values("abs_coef", ascending=False).head(10)), 10)
    if not quantile.empty:
        ls_return = quantile["long_short"].mean() * 252
        document.add_paragraph(
            f"样本外分层检验中，综合分Q5-Q1日均多空收益折年约为{ls_return:.2%}。"
            "分层收益曲线用于检验综合分是否具备排序能力，也可作为AI复盘模型是否过度依赖单一风格的输入。"
        )
    add_picture_if_exists(document, FIGURE_DIR / "optimized_long_short_nav.png")

    add_heading(document, "（五）选股模型测试：样本外组合回测与AI复盘切入点", 2)
    if not backtest.summary.empty:
        row = backtest.summary.iloc[0]
        document.add_paragraph(
            f"以训练期选定方案每日调仓、单边交易成本{format_fee_rate(DEFAULT_FEE_RATE)}估算，样本外组合年化收益为{row['annualized_return']:.2%}，"
            f"沪深300同期年化收益为{row['benchmark_annualized_return']:.2%}，年化超额为{row['excess_annualized_return']:.2%}，"
            f"最大回撤为{row['max_drawdown']:.2%}，平均换手为{row['avg_turnover']:.2%}。"
            "该结果适合作为AI复盘输入：当收益不稳定或回撤扩大时，AI可自动追问是否存在风格暴露过度、换手过高、因子拥挤或市场状态错配。"
        )
        add_table(
            document,
            "表11：样本外组合回测摘要",
            backtest.summary.rename(
                columns={
                    "trading_days": "交易日数",
                    "annualized_return": "组合年化收益",
                    "benchmark_annualized_return": "基准年化收益",
                    "excess_annualized_return": "年化超额",
                    "annualized_volatility": "年化波动",
                    "sharpe": "Sharpe",
                    "max_drawdown": "最大回撤",
                    "excess_max_drawdown": "超额最大回撤",
                    "win_rate": "胜率",
                    "avg_turnover": "平均换手",
                }
            ),
            1,
        )
    add_picture_if_exists(document, FIGURE_DIR / SELECTED_NAV_FIGURE)

    add_heading(document, "（六）样本共性分析：把强势样本转化为候选因子假设", 2)
    document.add_paragraph(
        "对样本外未来20个交易日收益进入当日横截面前10%的股票进行共性对比，可以看到强势样本在哪些标准化因子上相对全市场更突出。"
        "这一过程对应报告前文提到的“给AI一批强势股票，让AI归纳共性因子”：AI的价值在于把大量横截面数据快速压缩为可验证假设。"
    )
    add_table(document, "表12：强势样本相对全市场的共性因子", localized_commonality_table(commonality), 10)

    add_heading(document, "（七）60分钟数据：日内结构作为选股和择时的辅助标签", 2)
    if not intraday_ic.empty:
        best = intraday_ic.iloc[0]
        document.add_paragraph(
            f"基于60分钟价量数据，本次抽取近期流动性较好的股票样本，计算日内收益、首小时强弱、尾盘成交占比、日内振幅和日内波动等特征。"
            f"其中样本内表现相对靠前的日内结构变量为{best['factor_name']}，平均IC为{best['mean_ic']:.4f}。"
            "这说明分钟数据更适合作为AI辅助标签：帮助识别资金交易结构、尾盘确认、日内波动放大等短周期信息，而不是单独替代日频基本面因子。"
        )
        add_table(document, "表13：60分钟日内结构特征IC", localized_ic_table(intraday_ic), 8)
    else:
        document.add_paragraph("60分钟数据本轮未形成足够可匹配样本，可在后续扩大分钟数据读取范围后继续补充。")
    add_picture_if_exists(document, FIGURE_DIR / "intraday_60m_ic_bar.png")

    add_heading(document, "（八）择时状态识别：从信号阈值走向状态解释", 2)
    document.add_paragraph(
        "择时部分使用沪深300趋势、市场宽度、成交量和波动率构造市场状态。"
        "AI在这里的落地方式是把状态标签、未来收益、胜率和解释文本组合起来，用于辅助判断当前模型应该偏进攻、防御还是等待确认。"
    )
    add_table(
        document,
        "表14：市场状态与未来5日收益",
        timing_summary.rename(
            columns={
                "regime": "市场状态",
                "observations": "观测日数",
                "avg_next_5d_return": "未来5日平均收益",
                "win_rate": "胜率",
                "avg_adv_ratio": "平均上涨家数占比",
                "ai_timing_read": "AI解释",
            }
        ),
        8,
    )
    add_picture_if_exists(document, FIGURE_DIR / "timing_regime_enhanced.png")

    add_heading(document, REPORT_LANDING_SECTION_TITLE, 2)
    document.add_paragraph(REPORT_LANDING_PARAGRAPH)

    add_heading(document, "十、关键步骤汇总与AI执行方法论", 1)
    document.add_paragraph(
        "本项目的落地方式，不是让AI直接替代研究判断，而是把研究目标拆解为任务边界设定、数据底座复用、候选因子构建、滚动验证选模、样本外回测复盘和正式报告输出六个环节。"
        "在该框架下，AI承担结构化归纳、参数枚举、结果解释与文档汇总职责，研究人员负责数据口径确认、策略取舍与最终结论审定，从而形成可复现、可审计、可持续迭代的研究闭环。"
    )
    document.add_paragraph(
        "本轮升级后，第十章的作用不再只是补充说明，而是用于沉淀本项目已经验证过的方法路径：一方面说明技术因子、机器学习和分钟结构特征如何被纳入统一研究框架；另一方面说明未来函数防范、滚动验证和样本外隔离如何在实际工程中落地。"
    )
    add_table(
        document,
        "表15：关键步骤、AI执行动作与输出结果汇总",
        pd.DataFrame(
            [
                ["任务边界设定", "研究目标、数据范围、报告用途、可用目录", "拆分选股、择时、复盘和报告模块", "研究边界、训练期、滚动验证期和样本外区间"],
                ["数据底座梳理", "DuckDB日频底座、交易约束、指数、60分钟价量", "识别字段、覆盖范围与口径风险", "覆盖情况表、未来函数检查表"],
                ["候选因子构建", "基本面、技术面、流动性、价格位置与分钟标签", "批量生成因子、标准化、分组归纳与相关性识别", "因子IC摘要、分组稳定性、动作清单"],
                ["模型组合验证", "训练标签、持仓数量、交易成本、候选模型", "滚动验证枚举模型并按目标函数排序", "滚动验证表、全训练期复核结果、选定模型"],
                ["样本外复盘", "最终样本外净值、回撤、换手、分层收益、市场状态", "归纳优势、短板与适用环境", "回测摘要图表、择时解释、问题清单"],
                ["报告固化", "表格、图形、模型说明、项目过程", "组织为正式方案文字并保留工程化路径", "正式Word报告、摘要Markdown、输出目录"],
            ],
            columns=["环节", "输入材料", "AI执行动作", "输出结果"],
        ),
        10,
    )
    add_table(
        document,
        "表16：本项目中AI与研究员的分工方式",
        pd.DataFrame(
            [
                ["研究员", "定义任务目标、确认数据口径、判断模型取舍、审核最终结论"],
                ["AI", "批量生成因子、输出滚动验证与回测结果、归纳图表结论、组织正式报告表达"],
                ["人机协同结果", "形成可复现的研究工程，而不是一次性文字报告；后续可继续迭代新因子、新模型和新验证框架"],
            ],
            columns=["角色", "职责"],
        ),
        10,
    )
    document.save(DOC_TARGET)


def write_markdown_summary(
    train_ic: pd.DataFrame,
    oos_ic: pd.DataFrame,
    weights: pd.DataFrame,
    model_selection: pd.DataFrame,
    backtest: BacktestResult,
    timing_summary: pd.DataFrame,
    intraday_ic: pd.DataFrame,
) -> None:
    lines = [
        "# AI报告任务一增强数据支撑摘要",
        "",
        f"- 研究起始日期：{START_DATE}",
        f"- 训练期：{START_DATE} 至 {MODEL_TRAIN_END_DATE}",
        f"- 样本外观察期：{TEST_START_DATE} 之后",
    ]
    if not train_ic.empty:
        lines.append(f"- 训练期平均IC最高因子：{train_ic.iloc[0]['factor_name']} ({train_ic.iloc[0]['mean_ic']:.4f})")
    if not oos_ic.empty:
        lines.append(f"- 样本外平均IC最高因子：{oos_ic.iloc[0]['factor_name']} ({oos_ic.iloc[0]['mean_ic']:.4f})")
    if not weights.empty:
        lines.append("- AI辅助权重：" + "，".join([f"{row.factor_name} {row.weight:.1%}" for row in weights.itertuples()]))
    if not model_selection.empty:
        selected = model_selection.iloc[0]
        lines.append(f"- 训练期选定模型：{selected['model_type']} / {selected['target_label']} / Top{int(selected['top_n'])}")
    if not backtest.summary.empty:
        row = backtest.summary.iloc[0]
        lines.append(f"- 选定组合样本外年化收益：{row['annualized_return']:.2%}")
        lines.append(f"- 选定组合样本外年化超额：{row['excess_annualized_return']:.2%}")
        lines.append(f"- 选定组合最大回撤：{row['max_drawdown']:.2%}")
    if not timing_summary.empty:
        best = timing_summary.iloc[0]
        lines.append(f"- 未来5日平均收益最高的市场状态：{best['regime']} ({best['avg_next_5d_return']:.2%})")
    if not intraday_ic.empty:
        best_intraday = intraday_ic.iloc[0]
        lines.append(f"- 60分钟样本中IC最高特征：{best_intraday['factor_name']} ({best_intraday['mean_ic']:.4f})")
    (OUTPUT_DIR / "summary_enhanced.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    ensure_directories()
    font_name = configure_plot_font()
    con = connect_duckdb()
    try:
        benchmark = load_benchmark(con)
        daily = load_daily_frame(con)
        factor_frame = build_factor_frame(daily, benchmark)
        coverage = build_coverage_summary(con, factor_frame)
        no_leakage = build_no_leakage_check_table()

        train_ic = build_ic_summary(factor_frame, start_date=START_DATE, end_date=MODEL_TRAIN_END_DATE)
        oos_ic = build_ic_summary(factor_frame, start_date=TEST_START_DATE)
        train_ic.to_csv(TABLE_DIR / "factor_ic_train.csv", index=False, encoding="utf-8-sig")
        oos_ic.to_csv(TABLE_DIR / "factor_ic_oos.csv", index=False, encoding="utf-8-sig")
        factor_group_summary = build_factor_group_summary(train_ic, oos_ic)

        actions = build_ai_actions(train_ic)
        factor_frame, weights_dict, weights, model_selection, backtest, coefficients, validation_windows = build_model_scores_and_select(factor_frame, benchmark)
        factor_corr = build_factor_correlation(factor_frame)
        commonality = build_sample_commonality(factor_frame)
        quantile = build_quantile_returns(factor_frame)
        _, timing_summary = build_timing_regime(con)
        _, intraday_ic = load_intraday_features(factor_frame)
    finally:
        con.close()

    save_figures(train_ic, oos_ic, factor_corr, quantile, backtest, timing_summary, intraday_ic)
    write_report_docx(
        coverage,
        no_leakage,
        train_ic,
        oos_ic,
        factor_group_summary,
        actions,
        weights,
        model_selection,
        coefficients,
        validation_windows,
        commonality,
        quantile,
        backtest,
        timing_summary,
        intraday_ic,
    )
    write_markdown_summary(train_ic, oos_ic, weights, model_selection, backtest, timing_summary, intraday_ic)

    print(f"plot_font={font_name}")
    print(f"tables={TABLE_DIR}")
    print(f"figures={FIGURE_DIR}")
    print(f"report={DOC_TARGET}")


if __name__ == "__main__":
    main()
