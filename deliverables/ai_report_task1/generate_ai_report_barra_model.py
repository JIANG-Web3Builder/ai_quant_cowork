from __future__ import annotations

from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

import generate_ai_report_enhanced as base


WORK_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = WORK_DIR / "outputs_barra"
TABLE_DIR = OUTPUT_DIR / "tables"
SUMMARY_PATH = OUTPUT_DIR / "summary_barra.md"

STYLE_EXPOSURE_COLUMNS = {
    "size": "z_neg_log_total_mv",
    "value": "z_bp",
    "momentum": "z_momentum_60",
    "volatility": "z_neg_volatility_20",
    "liquidity": "z_neg_amihud_20",
    "quality": "z_quality_roe",
}

STYLE_EXPOSURE_LABELS = {
    "size": "规模",
    "value": "估值",
    "momentum": "动量",
    "volatility": "低波",
    "liquidity": "流动性",
    "quality": "质量",
}

TOP_N_CANDIDATES = [50, 100, 200, 300]


def ensure_directories() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    TABLE_DIR.mkdir(parents=True, exist_ok=True)


def connect_duckdb() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(base.DUCKDB_PATH), read_only=True)


def build_factor_frame_with_industry(raw: pd.DataFrame, benchmark: pd.DataFrame) -> pd.DataFrame:
    factor_frame = base.build_factor_frame(raw, benchmark)
    industry_frame = raw[["ts_code", "trade_date", "industry"]].copy()
    industry_frame["ts_code"] = industry_frame["ts_code"].astype(str)
    industry_frame["trade_date"] = industry_frame["trade_date"].astype(str)
    industry_frame["industry"] = industry_frame["industry"].fillna("未知行业").astype(str)
    industry_frame = industry_frame.drop_duplicates(["ts_code", "trade_date"])
    merged = factor_frame.merge(industry_frame, on=["ts_code", "trade_date"], how="left")
    merged["industry"] = merged["industry"].fillna("未知行业").replace("", "未知行业")
    return merged


def _style_exposure_columns(data: pd.DataFrame) -> list[str]:
    return [column for column in STYLE_EXPOSURE_COLUMNS.values() if column in data.columns]


def neutralize_score_by_barra_exposures(
    data: pd.DataFrame,
    raw_score_col: str,
    industry_col: str = "industry",
) -> pd.Series:
    style_columns = _style_exposure_columns(data)
    neutralized_parts: list[pd.Series] = []

    for _, day in data.groupby("trade_date", sort=False):
        day_view = day[[raw_score_col, industry_col, "research_universe", *style_columns]].copy()
        valid_mask = day_view["research_universe"].fillna(False) & day_view[raw_score_col].notna()
        if int(valid_mask.sum()) < max(30, len(style_columns) + 5):
            fallback = pd.Series(np.nan, index=day.index, dtype=float)
            fallback.loc[valid_mask] = base.winsorized_zscore(day_view.loc[valid_mask, raw_score_col])
            neutralized_parts.append(fallback)
            continue

        y = pd.to_numeric(day_view.loc[valid_mask, raw_score_col], errors="coerce")
        style_matrix = (
            day_view.loc[valid_mask, style_columns]
            .apply(pd.to_numeric, errors="coerce")
            .replace([np.inf, -np.inf], np.nan)
            .fillna(0.0)
        )
        industry_matrix = pd.get_dummies(
            day_view.loc[valid_mask, industry_col].fillna("未知行业").astype(str),
            prefix="industry",
            dtype=float,
        )
        if industry_matrix.shape[1] > 1:
            industry_matrix = industry_matrix.iloc[:, 1:]
        else:
            industry_matrix = industry_matrix.iloc[:, 0:0]

        x_parts = [np.ones((len(y), 1), dtype=float)]
        if style_columns:
            x_parts.append(style_matrix.to_numpy(dtype=float))
        if not industry_matrix.empty:
            x_parts.append(industry_matrix.to_numpy(dtype=float))
        x = np.hstack(x_parts)
        beta, *_ = np.linalg.lstsq(x, y.to_numpy(dtype=float), rcond=None)
        residual = y.to_numpy(dtype=float) - x @ beta

        neutralized = pd.Series(np.nan, index=day.index, dtype=float)
        neutralized.loc[y.index] = base.winsorized_zscore(pd.Series(residual, index=y.index))
        neutralized_parts.append(neutralized)

    return pd.concat(neutralized_parts).sort_index()


def build_backtest_snapshot(summary: pd.DataFrame, prefix: str) -> pd.DataFrame:
    if summary.empty:
        result = pd.DataFrame(
            columns=[
                "metric",
                "value",
                "display_name",
                "snapshot_group",
            ]
        )
    else:
        row = summary.iloc[0]
        result = pd.DataFrame(
            [
                {"metric": "annualized_return", "value": float(row["annualized_return"]), "display_name": "年化收益", "snapshot_group": prefix},
                {"metric": "benchmark_annualized_return", "value": float(row["benchmark_annualized_return"]), "display_name": "基准年化收益", "snapshot_group": prefix},
                {"metric": "excess_annualized_return", "value": float(row["excess_annualized_return"]), "display_name": "年化超额", "snapshot_group": prefix},
                {"metric": "annualized_volatility", "value": float(row["annualized_volatility"]), "display_name": "年化波动", "snapshot_group": prefix},
                {"metric": "sharpe", "value": float(row["sharpe"]), "display_name": "Sharpe", "snapshot_group": prefix},
                {"metric": "max_drawdown", "value": float(row["max_drawdown"]), "display_name": "最大回撤", "snapshot_group": prefix},
                {"metric": "excess_max_drawdown", "value": float(row["excess_max_drawdown"]), "display_name": "超额最大回撤", "snapshot_group": prefix},
                {"metric": "win_rate", "value": float(row["win_rate"]), "display_name": "胜率", "snapshot_group": prefix},
                {"metric": "avg_turnover", "value": float(row["avg_turnover"]), "display_name": "平均换手", "snapshot_group": prefix},
                {"metric": "trading_days", "value": float(row["trading_days"]), "display_name": "交易日数", "snapshot_group": prefix},
            ]
        )
    result.to_csv(TABLE_DIR / f"barra_{prefix}_snapshot.csv", index=False, encoding="utf-8-sig")
    return result


def build_exposure_comparison(style_exposure: pd.DataFrame, industry_exposure: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    if not style_exposure.empty:
        for row in style_exposure.itertuples():
            rows.append(
                {
                    "exposure_type": "style",
                    "name": row.style_name,
                    "mean_exposure": float(row.active_exposure_mean),
                    "abs_mean_exposure": float(row.active_exposure_abs_mean),
                }
            )
    if not industry_exposure.empty:
        for row in industry_exposure.head(10).itertuples():
            rows.append(
                {
                    "exposure_type": "industry",
                    "name": row.industry,
                    "mean_exposure": float(row.active_weight_mean),
                    "abs_mean_exposure": float(row.active_weight_abs_mean),
                }
            )
    result = pd.DataFrame(rows)
    result.to_csv(TABLE_DIR / "barra_exposure_comparison.csv", index=False, encoding="utf-8-sig")
    return result


def build_local_factor_weight_table(weights: dict[str, float], ic_summary: pd.DataFrame, output_name: str) -> pd.DataFrame:
    rows = [{"factor": factor, "factor_name": base.FACTOR_LABELS.get(factor, factor), "weight": weight} for factor, weight in weights.items()]
    table = pd.DataFrame(rows)
    if table.empty:
        table = pd.DataFrame(columns=["factor", "factor_name", "weight", "mean_ic", "ic_ir", "positive_ratio"])
    else:
        table = table.sort_values("weight", ascending=False).reset_index(drop=True)
        table = table.merge(ic_summary[["factor", "mean_ic", "ic_ir", "positive_ratio"]], on="factor", how="left")
    table.to_csv(TABLE_DIR / output_name, index=False, encoding="utf-8-sig")
    return table


def summarize_style_active_exposure(
    data: pd.DataFrame,
    score_col: str,
    top_n: int,
    start_date: str,
    end_date: str | None = None,
) -> pd.DataFrame:
    style_columns = _style_exposure_columns(data)
    required = ["trade_date", "research_universe", score_col, *style_columns]
    panel = data.loc[data["research_universe"].fillna(False), required].copy()
    panel = panel[panel["trade_date"] >= start_date]
    if end_date:
        panel = panel[panel["trade_date"] <= end_date]
    panel = panel.dropna(subset=[score_col])

    rows: list[dict[str, float | str]] = []
    for trade_date, day in panel.groupby("trade_date"):
        if len(day) < max(30, top_n // 2):
            continue
        selected = day.sort_values(score_col, ascending=False).head(top_n)
        for style_name, column in STYLE_EXPOSURE_COLUMNS.items():
            if column not in day.columns:
                continue
            rows.append(
                {
                    "trade_date": trade_date,
                    "style": style_name,
                    "style_name": STYLE_EXPOSURE_LABELS[style_name],
                    "selected_mean": float(pd.to_numeric(selected[column], errors="coerce").mean()),
                    "universe_mean": float(pd.to_numeric(day[column], errors="coerce").mean()),
                }
            )
    exposure = pd.DataFrame(rows)
    if exposure.empty:
        result = pd.DataFrame(columns=["style", "style_name", "active_exposure_mean", "active_exposure_abs_mean"])
    else:
        exposure["active_exposure"] = exposure["selected_mean"] - exposure["universe_mean"]
        result = (
            exposure.groupby(["style", "style_name"], as_index=False)
            .agg(
                active_exposure_mean=("active_exposure", "mean"),
                active_exposure_abs_mean=("active_exposure", lambda s: float(np.abs(pd.to_numeric(s, errors="coerce")).mean())),
            )
            .sort_values("active_exposure_abs_mean", ascending=False)
            .reset_index(drop=True)
        )
    return result


def summarize_industry_active_weight(
    data: pd.DataFrame,
    score_col: str,
    top_n: int,
    start_date: str,
    end_date: str | None = None,
) -> pd.DataFrame:
    required = ["trade_date", "industry", "research_universe", score_col]
    panel = data.loc[data["research_universe"].fillna(False), required].copy()
    panel = panel[panel["trade_date"] >= start_date]
    if end_date:
        panel = panel[panel["trade_date"] <= end_date]
    panel = panel.dropna(subset=[score_col])
    panel["industry"] = panel["industry"].fillna("未知行业").astype(str)

    rows: list[dict[str, float | str]] = []
    for trade_date, day in panel.groupby("trade_date"):
        if len(day) < max(30, top_n // 2):
            continue
        selected = day.sort_values(score_col, ascending=False).head(top_n)
        selected_weight = selected["industry"].value_counts(normalize=True)
        universe_weight = day["industry"].value_counts(normalize=True)
        for industry in sorted(set(selected_weight.index).union(universe_weight.index)):
            rows.append(
                {
                    "trade_date": trade_date,
                    "industry": industry,
                    "selected_weight": float(selected_weight.get(industry, 0.0)),
                    "universe_weight": float(universe_weight.get(industry, 0.0)),
                }
            )
    industry_frame = pd.DataFrame(rows)
    if industry_frame.empty:
        result = pd.DataFrame(columns=["industry", "active_weight_mean", "active_weight_abs_mean"])
    else:
        industry_frame["active_weight"] = industry_frame["selected_weight"] - industry_frame["universe_weight"]
        result = (
            industry_frame.groupby("industry", as_index=False)
            .agg(
                active_weight_mean=("active_weight", "mean"),
                active_weight_abs_mean=("active_weight", lambda s: float(np.abs(pd.to_numeric(s, errors="coerce")).mean())),
            )
            .sort_values("active_weight_abs_mean", ascending=False)
            .reset_index(drop=True)
        )
    return result


def build_barra_scores_and_select(
    data: pd.DataFrame,
    benchmark: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, base.BacktestResult]:
    scored = data
    model_rows: list[dict[str, object]] = []
    model_weights: dict[str, dict[str, float]] = {}
    model_ic: dict[str, pd.DataFrame] = {}
    ridge_coefficients: dict[str, pd.DataFrame] = {}
    validation_windows = pd.DataFrame(base.build_validation_windows(scored))
    base_validation_panel = scored[["ts_code", "trade_date", "research_universe", "next_return", "industry", *_style_exposure_columns(scored)]].copy()

    for target in base.TARGET_LABELS:
        ic_summary = base.build_ic_summary(scored, target=target, start_date=base.START_DATE, end_date=base.MODEL_TRAIN_END_DATE)

        ensemble_weights = base.build_factor_weights(ic_summary, max_factors=10)
        raw_ensemble_col = f"raw_ensemble_{target}"
        neutral_ensemble_col = f"barra_ensemble_{target}"
        scored[raw_ensemble_col] = base.compute_weighted_score_series(scored, ensemble_weights)
        scored[neutral_ensemble_col] = neutralize_score_by_barra_exposures(scored, raw_ensemble_col)
        model_weights[neutral_ensemble_col] = ensemble_weights
        model_ic[neutral_ensemble_col] = ic_summary

        raw_ridge_col = f"raw_ridge_{target}"
        neutral_ridge_col = f"barra_ridge_{target}"
        ridge_coef = base.fit_ridge_coefficients(scored, target, base.DAILY_FACTOR_COLUMNS, base.MODEL_TRAIN_END_DATE, alpha=25.0)
        scored[raw_ridge_col] = base.compute_ridge_score_series(scored, base.DAILY_FACTOR_COLUMNS, ridge_coef)
        scored[neutral_ridge_col] = neutralize_score_by_barra_exposures(scored, raw_ridge_col)
        ridge_coefficients[neutral_ridge_col] = pd.DataFrame(
            {
                "feature": base.DAILY_FACTOR_COLUMNS,
                "feature_name": [base.FACTOR_LABELS.get(feature, feature) for feature in base.DAILY_FACTOR_COLUMNS],
                "factor_group": [base.FACTOR_GROUP_MAP.get(feature, "其他") for feature in base.DAILY_FACTOR_COLUMNS],
                "coefficient": ridge_coef,
                "target": target,
                "score_col": neutral_ridge_col,
                "neutralization": "industry+style",
            }
        ).sort_values("coefficient", ascending=False)
        model_weights[neutral_ridge_col] = {}
        model_ic[neutral_ridge_col] = ic_summary

        for model_type, score_col in [
            ("Barra风格行业中性-多因子IC加权", neutral_ensemble_col),
            ("Barra风格行业中性-Ridge横截面", neutral_ridge_col),
        ]:
            validation_panels: list[pd.DataFrame] = []
            for window in validation_windows.to_dict("records"):
                if "多因子" in model_type:
                    window_ic = base.build_ic_summary(scored, target=target, start_date=base.START_DATE, end_date=str(window["train_end"]))
                    window_weights = base.build_factor_weights(window_ic, max_factors=10)
                    window_raw_score = base.compute_weighted_score_series(scored, window_weights)
                else:
                    window_coef = base.fit_ridge_coefficients(scored, target, base.DAILY_FACTOR_COLUMNS, str(window["train_end"]), alpha=25.0)
                    window_raw_score = base.compute_ridge_score_series(scored, base.DAILY_FACTOR_COLUMNS, window_coef)

                window_panel = base_validation_panel.copy()
                window_panel["window_raw_score"] = window_raw_score
                window_panel["window_score"] = neutralize_score_by_barra_exposures(window_panel, "window_raw_score")
                validation_panels.append(
                    pd.DataFrame(
                        {
                            "ts_code": window_panel["ts_code"],
                            "trade_date": window_panel["trade_date"],
                            "research_universe": window_panel["research_universe"],
                            "next_return": window_panel["next_return"],
                            "window_score": window_panel["window_score"],
                            "validation_start": str(window["validation_start"]),
                            "validation_end": str(window["validation_end"]),
                        }
                    )
                )

            for top_n in TOP_N_CANDIDATES:
                validation_rows: list[pd.Series] = []
                for window_data in validation_panels:
                    validation_result = base.run_top_portfolio_backtest(
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
                    validation_objective_mean = float(validation_frame.apply(base.model_objective, axis=1).mean())
                    validation_objective_std = float(validation_frame.apply(base.model_objective, axis=1).std(ddof=0)) if len(validation_frame) > 1 else 0.0
                    validation_excess_mean = float(validation_frame["excess_annualized_return"].mean())
                    validation_drawdown_mean = float(validation_frame["max_drawdown"].mean())
                    validation_turnover_mean = float(validation_frame["avg_turnover"].mean())
                else:
                    validation_objective_mean = np.nan
                    validation_objective_std = np.nan
                    validation_excess_mean = np.nan
                    validation_drawdown_mean = np.nan
                    validation_turnover_mean = np.nan

                train_result = base.run_top_portfolio_backtest(
                    scored,
                    benchmark,
                    score_col=score_col,
                    start_date=base.START_DATE,
                    end_date=base.MODEL_TRAIN_END_DATE,
                    top_n=top_n,
                    output_prefix=None,
                )
                if train_result.summary.empty:
                    continue

                row = train_result.summary.iloc[0].to_dict()
                model_rows.append(
                    {
                        "model_id": f"{score_col}_top{top_n}",
                        "model_type": model_type,
                        "target": target,
                        "target_label": base.TARGET_LABELS[target],
                        "score_col": score_col,
                        "top_n": top_n,
                        "neutralization": "industry+style",
                        "validation_window_count": int(len(validation_rows)),
                        "validation_objective_mean": validation_objective_mean,
                        "validation_objective_std": validation_objective_std,
                        "validation_excess_annualized_return": validation_excess_mean,
                        "validation_max_drawdown": validation_drawdown_mean,
                        "validation_avg_turnover": validation_turnover_mean,
                        "train_objective": base.model_objective(pd.Series(row)),
                        "train_annualized_return": row["annualized_return"],
                        "train_benchmark_annualized_return": row["benchmark_annualized_return"],
                        "train_excess_annualized_return": row["excess_annualized_return"],
                        "train_sharpe": row["sharpe"],
                        "train_max_drawdown": row["max_drawdown"],
                        "train_avg_turnover": row["avg_turnover"],
                    }
                )

    config_table = pd.DataFrame(model_rows).sort_values(
        ["validation_objective_mean", "validation_objective_std", "train_objective"],
        ascending=[False, True, False],
    ).reset_index(drop=True)
    config_table.to_csv(TABLE_DIR / "barra_model_selection.csv", index=False, encoding="utf-8-sig")

    selected = base.select_best_model_config(config_table)
    selected_score_col = str(selected["score_col"])
    selected_ic = model_ic[selected_score_col]
    selected_weights = model_weights[selected_score_col]

    if selected_weights:
        selected_weight_table = build_local_factor_weight_table(selected_weights, selected_ic, "barra_selected_factor_weights.csv")
    else:
        coefficient_table = ridge_coefficients[selected_score_col].copy()
        coefficient_table["weight"] = coefficient_table["coefficient"].abs()
        total_weight = float(coefficient_table["weight"].sum()) if not coefficient_table.empty else 0.0
        if total_weight > 0:
            coefficient_table["weight"] = coefficient_table["weight"] / total_weight
        selected_weight_table = coefficient_table.rename(columns={"feature": "factor", "feature_name": "factor_name"})[
            ["factor", "factor_name", "weight"]
        ]
        selected_weight_table = selected_weight_table.merge(
            selected_ic[["factor", "mean_ic", "positive_ratio"]],
            on="factor",
            how="left",
        ).sort_values("weight", ascending=False).reset_index(drop=True)
        selected_weight_table.to_csv(TABLE_DIR / "barra_selected_factor_weights.csv", index=False, encoding="utf-8-sig")

    coefficients = pd.concat(ridge_coefficients.values(), ignore_index=True) if ridge_coefficients else pd.DataFrame()
    coefficients.to_csv(TABLE_DIR / "barra_ridge_coefficients.csv", index=False, encoding="utf-8-sig")
    validation_windows.to_csv(TABLE_DIR / "barra_validation_windows.csv", index=False, encoding="utf-8-sig")

    train_result = base.run_top_portfolio_backtest(
        scored,
        benchmark,
        score_col=selected_score_col,
        start_date=base.START_DATE,
        end_date=base.MODEL_TRAIN_END_DATE,
        top_n=int(selected["top_n"]),
        output_prefix=None,
    )
    train_result.performance.to_csv(TABLE_DIR / "barra_selected_train_backtest_daily.csv", index=False, encoding="utf-8-sig")
    train_result.summary.to_csv(TABLE_DIR / "barra_selected_train_backtest_summary.csv", index=False, encoding="utf-8-sig")

    oos_result = base.run_top_portfolio_backtest(
        scored,
        benchmark,
        score_col=selected_score_col,
        start_date=base.TEST_START_DATE,
        top_n=int(selected["top_n"]),
        output_prefix=None,
    )
    oos_result.performance.to_csv(TABLE_DIR / "barra_selected_oos_backtest_daily.csv", index=False, encoding="utf-8-sig")
    oos_result.summary.to_csv(TABLE_DIR / "barra_selected_oos_backtest_summary.csv", index=False, encoding="utf-8-sig")

    style_exposure = summarize_style_active_exposure(
        scored,
        selected_score_col,
        top_n=int(selected["top_n"]),
        start_date=base.TEST_START_DATE,
    )
    style_exposure.to_csv(TABLE_DIR / "barra_style_active_exposure_oos.csv", index=False, encoding="utf-8-sig")

    industry_exposure = summarize_industry_active_weight(
        scored,
        selected_score_col,
        top_n=int(selected["top_n"]),
        start_date=base.TEST_START_DATE,
    )
    industry_exposure.to_csv(TABLE_DIR / "barra_industry_active_weight_oos.csv", index=False, encoding="utf-8-sig")

    exposure_comparison = build_exposure_comparison(style_exposure, industry_exposure)
    build_backtest_snapshot(train_result.summary, "train")
    build_backtest_snapshot(oos_result.summary, "oos")

    selected_df = pd.DataFrame([selected])
    selected_df.to_csv(TABLE_DIR / "barra_selected_model.csv", index=False, encoding="utf-8-sig")
    return scored, selected, selected_weight_table, coefficients, style_exposure, industry_exposure, exposure_comparison, oos_result


def write_summary(
    selected: pd.Series,
    oos_result: base.BacktestResult,
    style_exposure: pd.DataFrame,
    industry_exposure: pd.DataFrame,
) -> None:
    lines = [
        "# Barra-like 风格行业中性增强版模型摘要",
        "",
        f"- 选中模型：`{selected['model_type']}`",
        f"- 目标标签：`{base.TARGET_LABELS.get(str(selected['target']), str(selected['target']))}`",
        f"- 持仓数量：`Top{int(selected['top_n'])}`",
        f"- 得分列：`{selected['score_col']}`",
        f"- 中性化方式：`{selected.get('neutralization', 'industry+style')}`",
        "",
    ]
    if not oos_result.summary.empty:
        row = oos_result.summary.iloc[0]
        lines.extend(
            [
                "## 样本外表现",
                "",
                f"- 年化收益：`{row['annualized_return']:.2%}`",
                f"- 年化超额：`{row['excess_annualized_return']:.2%}`",
                f"- 最大回撤：`{row['max_drawdown']:.2%}`",
                f"- 平均换手：`{row['avg_turnover']:.2%}`",
                "",
            ]
        )
    if not style_exposure.empty:
        lines.extend(["## 风格主动暴露", ""])
        for row in style_exposure.head(6).itertuples():
            lines.append(f"- {row.style_name}：平均主动暴露 `{row.active_exposure_mean:.4f}`，绝对主动暴露 `{row.active_exposure_abs_mean:.4f}`")
        lines.append("")
    if not industry_exposure.empty:
        lines.extend(["## 行业主动权重", ""])
        for row in industry_exposure.head(10).itertuples():
            lines.append(f"- {row.industry}：平均主动权重 `{row.active_weight_mean:.4f}`，绝对主动权重 `{row.active_weight_abs_mean:.4f}`")
        lines.append("")
    SUMMARY_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    ensure_directories()
    con = connect_duckdb()
    try:
        benchmark = base.load_benchmark(con)
        raw = base.load_daily_frame(con)
    finally:
        con.close()

    factor_frame = build_factor_frame_with_industry(raw, benchmark)
    _, selected, _, coefficients, style_exposure, industry_exposure, _, oos_result = build_barra_scores_and_select(factor_frame, benchmark)
    write_summary(selected, oos_result, style_exposure, industry_exposure)

    print(f"tables={TABLE_DIR}")
    print(f"summary={SUMMARY_PATH}")
    print(f"selected_model={selected['model_type']}")
    print(f"selected_score_col={selected['score_col']}")
    if not coefficients.empty:
        print(f"ridge_features={len(coefficients)}")


if __name__ == "__main__":
    main()
