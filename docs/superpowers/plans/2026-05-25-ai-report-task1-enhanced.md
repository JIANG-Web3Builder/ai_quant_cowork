# AI Report Task1 Enhanced Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a stronger data-supported Word report for AI applications in A-share stock selection and market timing.

**Architecture:** Add one focused enhanced research script under `deliverables/ai_report_task1`, keeping the existing script and outputs intact. The script computes robust daily factors, AI-style factor diagnostics, a transparent optimized score, intraday 60-minute features, timing regimes, figures, CSV tables, markdown notes, and a final Word report copied from the original submission document.

**Tech Stack:** Python, pandas, numpy, duckdb, python-docx, matplotlib, pytest.

---

### Task 1: Testable Research Helpers

**Files:**
- Create: `tests/test_ai_report_enhanced.py`
- Create: `deliverables/ai_report_task1/generate_ai_report_enhanced.py`

- [ ] **Step 1: Write failing tests**

```python
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "deliverables" / "ai_report_task1" / "generate_ai_report_enhanced.py"


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
        ]
    )
    actions = module.describe_ai_factor_actions(summary)
    assert actions.loc[actions["factor"] == "bp", "ai_action"].iloc[0] == "核心加权"
    assert actions.loc[actions["factor"] == "momentum_20", "ai_action"].iloc[0] == "反向验证或降权"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_ai_report_enhanced.py -q`
Expected: FAIL because `generate_ai_report_enhanced.py` does not exist.

- [ ] **Step 3: Implement helper functions and script skeleton**

Implement `winsorized_zscore`, `build_factor_weights`, and `describe_ai_factor_actions` in `deliverables/ai_report_task1/generate_ai_report_enhanced.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_ai_report_enhanced.py -q`
Expected: PASS.

### Task 2: Full Enhanced Research Pipeline

**Files:**
- Modify: `deliverables/ai_report_task1/generate_ai_report_enhanced.py`

- [ ] **Step 1: Load data**

Query DuckDB tables `daily_fundamental_base`, `tradable_daily_base`, `stock_basic`, and `index_daily`; read 60-minute parquet files only for a bounded recent sample to keep runtime practical.

- [ ] **Step 2: Compute daily factors**

Use robust factor definitions: value (`bp`, `ep_ttm`, `dividend_yield`), size (`neg_log_total_mv`), liquidity (`neg_turnover_20d_avg`), reversal (`reversal_5`), low volatility (`neg_volatility_20`), quality (`roe`, `roa`, `ocfps`), growth (`q_sales_yoy`, `netprofit_yoy`).

- [ ] **Step 3: Compute diagnostics**

Create CSVs for coverage, factor IC, factor correlation, AI action recommendations, strong-sample commonality, factor weights, quantile returns, long-short NAV, top portfolio backtest, timing regimes, and intraday features.

- [ ] **Step 4: Generate report assets**

Create figures for factor IC, factor correlation heatmap, optimized long-short NAV, top portfolio NAV, timing regime returns, and intraday feature commonality.

- [ ] **Step 5: Write Word report**

Copy the source Word document, append a clean Chinese section with methods, data evidence, tables, figures, and AI landing recommendations.

### Task 3: Verification

**Files:**
- Read: generated CSVs, figures, and Word report

- [ ] **Step 1: Run the enhanced script**

Run: `python deliverables/ai_report_task1/generate_ai_report_enhanced.py`
Expected: prints output paths and creates `deliverables/ai_report_task1/outputs_enhanced`.

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_ai_report_enhanced.py -q`
Expected: PASS.

- [ ] **Step 3: Inspect generated data**

Open summary CSVs and verify there are non-empty rows, plausible factor signs, and a non-empty Word file.

- [ ] **Step 4: Summarize output**

Report final Word path, key metrics, and any limitations.
