# A 股数据框架项目导读

这份文档是给你快速读懂当前项目用的，重点解释：

- 项目里每个目录和文件是干什么的
- 当前正在导入的本地数据放在哪里
- 每类 Parquet 数据是什么、字段是什么意思
- 你后续做因子研究、回测时最常会接触哪些数据

---

## 1. 先用一句话理解这个项目

这个项目是在本地搭一个 **A 股研究数据底层框架**，把 Tushare 的日线数据、复权因子、每日指标导入到本地 Parquet 文件里，再通过 `daily_base` 这种研究面板给后续因子研究、回测、机器学习使用。

你可以把它理解成一条数据流水线：

```text
Tushare -> raw -> canonical -> panel -> 因子研究 / 回测 / ML
```

---

## 2. 项目根目录结构说明

当前项目根目录大致是这样：

```text
a_stock_research/
  .env
  .env.example
  .gitignore
  README.md
  PROJECT_GUIDE.md
  pyproject.toml
  configs/
  data/
  scripts/
  src/
  tests/
  test.py
```

下面逐个解释。

---

## 3. 根目录下每个文件的作用

### `.env`

这是 **本地私密配置文件**。

目前最重要的是：

```env
TUSHARE_TOKEN=你的token
```

作用：

- 给程序提供 Tushare token
- 不应该提交到 Git 仓库
- 只在你本机生效

### `.env.example`

这是 **环境变量模板文件**。

作用：

- 告诉你 `.env` 应该长什么样
- 供以后复制配置用
- 不应该放真实 token

### `.gitignore`

告诉 Git 哪些文件不要提交。

当前主要忽略：

- `.env`
- `data/`
- `*.duckdb`
- `*.sqlite`
- Python 缓存目录

作用：

- 避免把本地数据和 token 提交上去

### `README.md`

项目简介。

作用：

- 简单描述这个项目是做什么的
- 以后可以扩展成使用说明文档

### `pyproject.toml`

Python 项目的依赖和打包配置文件。

这里定义了项目依赖，比如：

- `tushare`
- `pandas`
- `polars`
- `pyarrow`
- `duckdb`
- `python-dotenv`
- `PyYAML`

作用：

- 安装依赖
- 让项目可以作为 Python 包运行

### `test.py`

这是你临时写的 **Tushare token 验证脚本**。

作用：

- 用最小代码确认 token 是否可用

它不是核心框架的一部分，更像一次调试验证文件。

---

## 4. `configs/` 目录说明

```text
configs/
  data_sources.yaml
  storage.yaml
```

### `configs/data_sources.yaml`

定义数据源相关配置。

目前主要是：

- Tushare 请求间隔
- 最大重试次数
- 首批要用的 endpoint

作用：

- 集中管理采集参数
- 后续加 AKShare、yfinance 也可以放这里

### `configs/storage.yaml`

定义本地存储路径和命名。

作用：

- 统一规定 `raw / canonical / panel / metadata` 等目录
- 避免把路径写死在代码里

---

## 5. `scripts/` 目录说明

```text
scripts/
  bootstrap_history.py
  update_daily.py
```

### `scripts/bootstrap_history.py`

这是 **历史全量导入脚本**。

当前作用：

- 从 `20220101` 开始拉取历史数据
- 导入：
  - `daily`
  - `adj_factor`
  - `daily_basic`
- 同时生成 `panel/daily_base`

你现在后台跑的就是它。

### `scripts/update_daily.py`

这是 **日常增量更新脚本**。

作用：

- 默认更新当天数据
- 适合以后每天收盘后刷新本地数据

---

## 6. `src/` 目录说明

这是核心代码目录。

```text
src/asr/
  config/
  data_sources/
  ingestion/
  metadata/
  storage/
  transform/
  utils/
```

其中 `asr` 是项目包名。

### `src/asr/config/`

#### `settings.py`

这是 **配置加载中心**。

作用：

- 读取 `.env`
- 读取 YAML 配置文件
- 组装成程序运行时可用的配置对象

你可以理解成：

- 程序的“设置中心”

### `src/asr/data_sources/`

#### `tushare_client.py`

这是 **Tushare 数据访问封装**。

作用：

- 初始化 Tushare Pro API
- 发请求
- 做简单重试
- 打印采集日志

你以后如果接 AKShare、yfinance，也会有对应的 client。

### `src/asr/ingestion/`

#### `historical_importer.py`

这是当前最核心的文件之一。

作用：

- 拉交易日历
- 按交易日逐天请求数据
- 把数据写到 `raw` 和 `canonical`
- 构建 `daily_base` 面板
- 注册 DuckDB 视图
- 更新 SQLite 水位线

你可以把它理解成：

- 当前项目的“主导入器”

### `src/asr/storage/`

#### `parquet_store.py`

这是 **Parquet 写入工具**。

作用：

- 按分区写 Parquet
- 当前按 `trade_date=YYYYMMDD/part.parquet` 的形式落盘

### `src/asr/metadata/`

#### `registry.py`

这是 **元数据注册器**。

作用：

- 在 SQLite 里记录：
  - 某张表更新到哪天
  - 总行数
  - 最后更新时间
- 在 DuckDB 里注册 view

用途：

- 以后你可以直接查哪些表更新到了什么程度

### `src/asr/transform/`

#### `panel_builder.py`

这是 **研究面板构建逻辑**。

虽然当前历史导入器里用了更直接的方式拼接，但它的目标是：

- 把多个事实表 join 成研究更方便用的面板

### `src/asr/utils/`

这里放公共小工具。

#### `dates.py`

- 日期格式处理

#### `logging.py`

- 日志初始化

---

## 7. `tests/` 目录说明

```text
tests/
  test_smoke.py
```

现在只有一个最简单的 smoke test。

作用：

- 先保证测试框架在
- 后续可以往里面补：
  - 配置测试
  - Parquet 写入测试
  - 数据校验测试

---

## 8. `data/` 目录说明（最关键）

这是你以后最常会接触的数据目录。

当前结构大致是：

```text
data/
  raw/
    tushare/
      daily/
      adj_factor/
      daily_basic/
  canonical/
    ashare_eod/
    adj_factor/
    daily_basic/
  panel/
    daily_base/
  metadata/
    research.duckdb
    metadata.sqlite
```

---

## 9. `raw/` 是什么

### 定义

`raw` 是 **原始数据层**。

这里的数据尽量保留“从 Tushare 拉下来的原貌”。

例如：

```text
data/raw/tushare/daily/trade_date=20220104/part.parquet
```

### 作用

- 做数据留痕
- 方便以后排查问题
- 如果 canonical 逻辑写错了，可以从 raw 重新加工

### 你平时会不会直接用它？

一般 **不会直接用于研究**。

研究应该尽量使用：

- `canonical`
- `panel`

---

## 10. `canonical/` 是什么

### 定义

`canonical` 是 **标准事实层**。

这里的数据已经经过了一定标准化，主要目的是：

- 列名稳定
- 主键稳定
- 分区方式统一
- 方便后续 join 和研究

当前有三类核心表：

- `ashare_eod`
- `adj_factor`
- `daily_basic`

---

## 11. `panel/` 是什么

### 定义

`panel` 是 **研究面板层**。

这里的数据不只是“原始事实”，而是把多个表提前对齐、拼接好，让你后续直接拿来做研究。

当前最重要的是：

- `daily_base`

### 为什么它重要

如果没有 `panel`，你每次做研究都要自己拼：

- 日线行情
- 复权因子
- 每日指标

这会让 notebook 又慢又乱。

有了 `daily_base`，你就可以直接用一张表开始研究。

---

## 12. `metadata/` 是什么

### `research.duckdb`

这是 DuckDB 数据库文件。

作用：

- 给 Parquet 建视图
- 用 SQL 快速查询本地数据

### `metadata.sqlite`

这是 SQLite 元数据文件。

作用：

- 记录每张数据集的更新状态
- 例如：更新到哪天、多少行、最后更新时间

---

## 13. 当前几类 Parquet 表分别是什么

现在你最需要理解四张数据：

1. `ashare_eod`
2. `adj_factor`
3. `daily_basic`
4. `daily_base`

---

## 14. `ashare_eod` 字段解释

样例字段：

```text
['ts_code', 'trade_date', 'open', 'high', 'low', 'close', 'pre_close', 'change', 'pct_chg', 'vol', 'amount']
```

### 字段说明

- **`ts_code`**
  - 股票代码，Tushare 格式
  - 例如：`000001.SZ`、`600000.SH`

- **`trade_date`**
  - 交易日
  - 格式：`YYYYMMDD`

- **`open`**
  - 开盘价

- **`high`**
  - 最高价

- **`low`**
  - 最低价

- **`close`**
  - 收盘价
  - 注意：这是未复权价格

- **`pre_close`**
  - 前一交易日收盘价

- **`change`**
  - 涨跌额
  - 一般可理解为：`close - pre_close`

- **`pct_chg`**
  - 涨跌幅（百分比）
  - 例如 `2.35` 表示涨了 `2.35%`

- **`vol`**
  - 成交量
  - Tushare 日线里通常是“手”
  - 1 手 = 100 股

- **`amount`**
  - 成交额
  - 通常是“千元”或接口定义的金额单位
  - 实际使用时最好结合 Tushare 文档确认单位

### 用途

`ashare_eod` 主要用于：

- 收益率计算
- 技术指标
- 价格类因子
- 回测价格输入

---

## 15. `adj_factor` 字段解释

样例字段：

```text
['ts_code', 'trade_date', 'adj_factor']
```

### 字段说明

- **`ts_code`**
  - 股票代码

- **`trade_date`**
  - 交易日

- **`adj_factor`**
  - 复权因子
  - 用来把价格转换成前复权或后复权口径

### 它是干什么的

A 股有：

- 分红
- 送股
- 配股
- 拆合

如果直接用原始 `close` 做长期收益比较，可能会失真。

所以通常会构造复权价格，例如：

```text
adj_close = close * adj_factor
```

当前 `daily_base` 就已经帮你生成了：

- `adj_close`

### 用途

- 长期收益率研究
- 趋势、动量、反转类因子
- 回测中避免除权除息导致的价格跳变误判

---

## 16. `daily_basic` 字段解释

样例字段：

```text
['ts_code', 'trade_date', 'close', 'turnover_rate', 'turnover_rate_f', 'volume_ratio', 'pe', 'pe_ttm', 'pb', 'ps', 'ps_ttm', 'dv_ratio', 'dv_ttm', 'total_share', 'float_share', 'free_share', 'total_mv', 'circ_mv']
```

这是最容易让人“看不懂参数”的一张表，我重点解释。

### 价格相关

- **`close`**
  - 当日收盘价
  - 这里重复存了一次收盘价
  - 在构建 `daily_base` 时已经避免和 `ashare_eod.close` 冲突

### 流动性 / 交易活跃度

- **`turnover_rate`**
  - 换手率
  - 通常是：成交股数 / 流通股本
  - 数值越大，说明交易越活跃

- **`turnover_rate_f`**
  - 自由流通股口径换手率
  - 比普通换手率更贴近真实可交易流通盘

- **`volume_ratio`**
  - 量比
  - 通常衡量当日成交量相对近期平均量的放大程度
  - 大于 1 通常表示放量

### 估值类

- **`pe`**
  - 市盈率（静态）

- **`pe_ttm`**
  - 滚动市盈率（TTM）
  - 研究里通常比 `pe` 更常用

- **`pb`**
  - 市净率

- **`ps`**
  - 市销率（静态）

- **`ps_ttm`**
  - 滚动市销率（TTM）

- **`dv_ratio`**
  - 股息率

- **`dv_ttm`**
  - 滚动股息率（TTM）

### 股本 / 市值类

- **`total_share`**
  - 总股本

- **`float_share`**
  - 流通股本

- **`free_share`**
  - 自由流通股本

- **`total_mv`**
  - 总市值

- **`circ_mv`**
  - 流通市值

### 用途

`daily_basic` 最常用于：

- 估值因子
- 规模因子
- 流动性因子
- 换手率因子
- 交易拥挤度 / 活跃度研究

---

## 17. `daily_base` 字段解释

`daily_base` 是当前最值得你直接使用的一张面板表。

它大致来自：

```text
ashare_eod + adj_factor + daily_basic
```

目前至少会包含：

- `ashare_eod` 的行情字段
- `adj_factor`
- `daily_basic` 的估值/换手/市值字段
- `adj_close`

### `adj_close`

这是当前导入器额外构造的字段：

```text
adj_close = close * adj_factor
```

### 用途

如果你想直接开始研究，最适合先看：

- `data/panel/daily_base/...`

因为它已经是一张“研究可直接使用”的表。

---

## 18. 我建议你以后优先使用哪一层

### 平时研究

优先用：

- **`panel/daily_base`**

### 需要看原始行情

用：

- **`canonical/ashare_eod`**

### 需要看复权因子

用：

- **`canonical/adj_factor`**

### 需要看估值、市值、换手

用：

- **`canonical/daily_basic`**

### 排查导入问题

用：

- **`raw/tushare/...`**

---

## 19. 以后最可能新增的东西

后续这个项目大概率还会补这些数据层：

- `stock_basic`
- `trade_calendar`
- 指数日线
- 行业分类
- ST / 停牌 / 涨跌停状态
- 财务数据
- 因子结果层
- 回测数据集层

也就是说，现在你看到的是 **第一版可运行底座**，不是最终全量版。

---

## 20. 你现在最该先掌握什么

如果你刚开始用这个项目，建议先只理解这四样：

1. **`ashare_eod` 是原始日线行情**
2. **`adj_factor` 是复权因子**
3. **`daily_basic` 是估值/市值/换手等每日指标**
4. **`daily_base` 是研究最方便直接用的面板**

只要你把这四张表搞懂，后面做：

- 动量因子
- 反转因子
- 规模因子
- 估值因子
- 简单双分组回测

就已经足够开始了。

---

## 21. 一个简单的理解方式

你可以把当前数据层理解成：

- **`ashare_eod`**：今天这只股票涨没涨、成交多少
- **`adj_factor`**：这只股票历史价格要不要复权
- **`daily_basic`**：这只股票今天贵不贵、大不大、活不活跃
- **`daily_base`**：把上面这些都整理到一张表里，方便你研究

---

## 22. 后续如果你想继续让我补什么

我后面还可以继续帮你写几种文档：

- **字段字典版**
  - 把每张表每个字段做成更完整的 Data Dictionary

- **研究使用版**
  - 教你怎么从 `daily_base` 开始做第一个因子

- **回测使用版**
  - 教你怎么从这些 Parquet 做一个最简单的选股回测

- **DuckDB 查询版**
  - 教你怎么直接用 SQL 查这些本地 Parquet

如果你愿意，下一步我可以继续给你补一份：

**`FIELD_DICTIONARY.md`** 或 **`FIRST_FACTOR_EXAMPLE.md`**
