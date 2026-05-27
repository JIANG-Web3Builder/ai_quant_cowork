import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "deliverables"
    / "ai_report_task1"
    / "add_technical_ml_chapter.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location("add_technical_ml_chapter", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_compute_rsi_uses_history_only():
    module = load_module()
    close = pd.Series([10, 11, 12, 11, 13, 14, 13, 15], dtype=float)
    rsi = module.compute_rsi(close, window=3)
    changed_future = close.copy()
    changed_future.iloc[-1] = 100
    changed_rsi = module.compute_rsi(changed_future, window=3)
    assert np.allclose(rsi.iloc[:-1].fillna(-1), changed_rsi.iloc[:-1].fillna(-1))


def test_select_model_uses_training_objective_not_oos_return():
    module = load_module()
    table = pd.DataFrame(
        [
            {"model_id": "train_best", "train_objective": 0.4, "oos_annualized_return": -0.2},
            {"model_id": "future_best", "train_objective": 0.1, "oos_annualized_return": 1.2},
        ]
    )
    selected = module.select_best_model(table)
    assert selected["model_id"] == "train_best"


def test_ridge_coefficients_have_expected_shape():
    module = load_module()
    x = np.array([[1.0, 0.0], [0.0, 1.0], [1.0, 1.0], [-1.0, 0.0]])
    y = np.array([1.0, 0.5, 1.2, -0.8])
    coef = module.fit_ridge(x, y, alpha=0.1)
    assert coef.shape == (2,)
    assert np.isfinite(coef).all()


def test_build_factor_frame_does_not_look_forward_for_technical_factors():
    module = load_module()
    dates = pd.date_range("2023-01-02", periods=80, freq="B")
    prices = pd.Series(np.linspace(10, 18, len(dates)) + np.sin(np.arange(len(dates)) / 3), index=dates)
    raw = pd.DataFrame(
        {
            "ts_code": "000001.SZ",
            "trade_date": dates.strftime("%Y%m%d"),
            "open": prices.to_numpy(),
            "high": (prices * 1.02).to_numpy(),
            "low": (prices * 0.98).to_numpy(),
            "close": prices.to_numpy(),
            "pre_close": prices.shift(1).fillna(prices.iloc[0]).to_numpy(),
            "pct_chg": prices.pct_change().fillna(0).to_numpy() * 100,
            "amount": np.linspace(10000, 20000, len(dates)),
            "adj_close": prices.to_numpy(),
            "turnover_rate": np.linspace(1.0, 2.0, len(dates)),
            "turnover_rate_f": np.linspace(1.0, 2.0, len(dates)),
            "volume_ratio": 1.0,
            "pe_ttm": 12.0,
            "pb": 1.5,
            "dv_ttm": 2.0,
            "total_mv": 100000.0,
            "circ_mv": 80000.0,
            "roe": 8.0,
            "roa": 4.0,
            "debt_to_assets": 45.0,
            "ocfps": 0.8,
            "q_sales_yoy": 5.0,
            "netprofit_yoy": 6.0,
            "name": "test stock",
            "market": "main",
            "is_tradable": True,
            "can_buy": True,
            "can_sell": True,
            "listed_days": 500,
            "industry": "test",
        }
    )
    benchmark = pd.DataFrame(
        {
            "trade_date": dates.strftime("%Y%m%d"),
            "index_ret_20": 0.01,
            "index_ret_60": 0.03,
            "benchmark_return": 0.0,
        }
    )

    base = module.build_factor_frame(raw, benchmark)
    changed_raw = raw.copy()
    changed_raw.loc[changed_raw.index[-1], ["high", "low", "close", "adj_close"]] = 100.0
    changed_raw.loc[changed_raw.index[-1], "pct_chg"] = 500.0
    changed = module.build_factor_frame(changed_raw, benchmark)

    checked_columns = [
        "momentum_20",
        "bias_20",
        "neg_volatility_20",
        "range_position_20",
        "boll_pos_20",
        "rsi_14",
        "neg_amihud_20",
    ]
    for column in checked_columns:
        left = base[column].iloc[:-1].fillna(-999)
        right = changed[column].iloc[:-1].fillna(-999)
        assert np.allclose(left, right)
