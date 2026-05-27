import tushare as ts
ts.set_token("fec59e1b5eb7dc96dd8219440f268352c326181c08b8d5b7f464ae68")
pro = ts.pro_api()
print(pro.trade_cal(exchange="", start_date="20220101", end_date="20220110", is_open="1").head())

