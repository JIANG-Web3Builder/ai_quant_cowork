# A-Stock Research

本项目用于构建 A 股本地研究数据底座，服务于：

- 因子研究
- 日频回测
- 数据探索与查询
- 后续机器学习数据集准备

当前已具备：

- 日线行情、复权因子、每日指标导入
- 基础主数据与交易日历导入
- 财务指标与财务报表导入框架
- DuckDB / SQLite 元数据注册
- 研究面板与可交易面板构建

常用脚本：

- `python scripts/bootstrap_history.py --start-date 20220101`
- `python scripts/bootstrap_reference_data.py --start-date 20220101`
- `python scripts/bootstrap_fina_indicator.py --dataset fina_indicator --limit 50`
- `python scripts/build_tradable_panel.py`
- `python scripts/build_first_factors.py`
