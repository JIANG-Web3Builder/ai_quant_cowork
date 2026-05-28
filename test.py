import tushare as ts
ts.set_token("")
pro = ts.pro_api()
print(pro.trade_cal(exchange="", start_date="20220101", end_date="20220110", is_open="1").head())

