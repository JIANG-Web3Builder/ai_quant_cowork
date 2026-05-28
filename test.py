import tushare as ts
ts.set_token("")
pro = ts.pro_api()

BARRA_CANDIDATE_FIELDS = [
    "beta",
    "momentum",
    "size",
    "earnings_yield",
    "residual_volatility",
    "growth",
    "book_to_price",
    "leverage",
    "liquidity",
    "non_linear_size",
]


def fetch_barra_like_factors(ts_code: str, start_date: str, end_date: str) -> None:
    try:
        factor_df = pro.query(
            "stk_factor_pro",
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date,
        )
    except Exception as e:
        print(f"Tushare 因子接口调用失败，错误信息: {e}")
        return

    if factor_df.empty:
        print("未获取到因子数据，请检查股票代码、日期范围或 Tushare 权限。")
        return

    selected_columns = [
        column
        for column in ["ts_code", "trade_date", *BARRA_CANDIDATE_FIELDS]
        if column in factor_df.columns
    ]

    if len(selected_columns) > 2:
        print("成功获取 Barra 风格候选因子！")
        print(factor_df[selected_columns].head())
        return

    print("已拉取到 Tushare 因子数据，但当前返回列中没有识别到常见 Barra 风格字段。")
    print("接口实际返回字段如下：")
    print(factor_df.columns.tolist())
    print(factor_df.head())


fetch_barra_like_factors(ts_code="000001.SZ", start_date="20250101", end_date="20250528")

