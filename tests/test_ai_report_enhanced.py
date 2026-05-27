import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "deliverables"
    / "ai_report_task1"
    / "generate_ai_report_enhanced.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location("generate_ai_report_enhanced", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_winsorized_zscore_handles_outliers_and_constant_values():
    module = load_module()
    values = pd.Series([1.0, 2.0, 3.0, 1000.0])
    z = module.winsorized_zscore(values)
    assert np.isfinite(z).all()
    assert abs(float(z.mean())) < 1e-9
    assert float(z.max()) < 2.0

    constant = module.winsorized_zscore(pd.Series([5.0, 5.0, 5.0]))
    assert constant.tolist() == [0.0, 0.0, 0.0]


def test_build_factor_weights_prefers_positive_stable_ic_and_ignores_negative():
    module = load_module()
    summary = pd.DataFrame(
        [
            {"factor": "bp", "mean_ic": 0.03, "ic_ir": 0.20, "positive_ratio": 0.58},
            {"factor": "reversal_5", "mean_ic": 0.02, "ic_ir": 0.10, "positive_ratio": 0.56},
            {"factor": "momentum_20", "mean_ic": -0.04, "ic_ir": -0.20, "positive_ratio": 0.40},
        ]
    )
    weights = module.build_factor_weights(summary)
    assert set(weights) == {"bp", "reversal_5"}
    assert weights["bp"] > weights["reversal_5"]
    assert abs(sum(weights.values()) - 1.0) < 1e-9


def test_describe_ai_factor_actions_translates_stats_to_actions():
    module = load_module()
    summary = pd.DataFrame(
        [
            {"factor": "bp", "mean_ic": 0.03, "ic_ir": 0.20, "positive_ratio": 0.58},
            {"factor": "momentum_20", "mean_ic": -0.04, "ic_ir": -0.20, "positive_ratio": 0.40},
            {"factor": "quality_roe", "mean_ic": 0.01, "ic_ir": 0.01, "positive_ratio": 0.51},
        ]
    )
    actions = module.describe_ai_factor_actions(summary)
    assert actions.loc[actions["factor"] == "bp", "ai_action"].iloc[0] == "核心加权"
    assert actions.loc[actions["factor"] == "momentum_20", "ai_action"].iloc[0] == "反向验证或降权"
    assert actions.loc[actions["factor"] == "quality_roe", "ai_action"].iloc[0] == "观察保留"


def test_select_best_model_config_uses_training_objective_only():
    module = load_module()
    configs = pd.DataFrame(
        [
            {
                "model_id": "train_winner",
                "target": "next_return",
                "score_col": "score_next_return",
                "top_n": 50,
                "train_objective": 0.20,
                "oos_annualized_return": -0.10,
            },
            {
                "model_id": "future_winner",
                "target": "next_5d_return",
                "score_col": "score_next_5d_return",
                "top_n": 100,
                "train_objective": 0.05,
                "oos_annualized_return": 0.50,
            },
        ]
    )
    selected = module.select_best_model_config(configs)
    assert selected["model_id"] == "train_winner"
    assert selected["score_col"] == "score_next_return"


def test_model_training_end_date_is_before_oos_start():
    module = load_module()
    assert module.MODEL_TRAIN_END_DATE < module.TEST_START_DATE


def test_format_fee_rate_uses_actual_decimal_cost():
    module = load_module()
    assert module.format_fee_rate(0.001) == "0.10%"
    assert module.format_fee_rate(0.0005) == "0.05%"


def test_report_language_avoids_advisory_second_person_tone():
    module = load_module()
    assert "建议" not in module.REPORT_LANDING_SECTION_TITLE
    assert "建议" not in module.REPORT_LANDING_PARAGRAPH
    assert "你" not in module.REPORT_LANDING_PARAGRAPH
