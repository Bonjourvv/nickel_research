# 镍/不锈钢研究系统 - 项目结构速查

> 最后更新: 2026-02-03
> 版本: v0.2（含宏观数据模块）

---

## 📁 目录结构总览

```
nickel_research/
│
├── config/                     # ⚙️ 配置中心
│   ├── __init__.py
│   └── settings.py             # 【核心】所有配置项
│
├── src/                        # 📦 源代码
│   ├── data_fetcher/           # 数据拉取模块
│   │   ├── __init__.py
│   │   └── ths_client.py       # 【核心】同花顺API封装
│   │
│   └── macro/                  # 宏观数据模块
│       ├── __init__.py
│       └── macro_indicators.py # 【核心】宏观指标配置和拉取
│
├── data/                       # 💾 数据存储（自动生成）
│   ├── raw/                    # 原始行情CSV
│   ├── macro/                  # 宏观指标CSV
│   ├── processed/              # 处理后数据（暂未使用）
│   └── manual/                 # 手工录入数据（暂未使用）
│
├── run_daily.py                # 🚀 每日行情拉取脚本
├── fetch_macro.py              # 🚀 宏观数据拉取脚本
├── generate_dashboard.py       # 🚀 生成HTML看板
├── realtime_monitor.py         # 🚀 盘中实时监控（新增）
├── test_api.py                 # 🧪 API连接测试
├── dashboard.html              # 📊 生成的看板（自动生成）
├── requirements.txt            # 📋 Python依赖
└── README.md                   # 📖 说明文档
```

---

## 🔧 核心文件详解

### 1. `config/settings.py` - 配置中心

**作用**: 集中管理所有配置，改配置只需要动这一个文件

**重要配置项**:
```python
# API认证
IFIND_REFRESH_TOKEN = "xxx"     # 同花顺API令牌，有效期看账户（你的到2026-03-31）

# 监控合约
WATCH_LIST = ["niZL.SHF", "ssZL.SHF"]   # 监控的合约列表
NICKEL_MAIN = "niZL.SHF"                 # 沪镍主力合约代码
SS_MAIN = "ssZL.SHF"                     # 不锈钢主力合约代码

# 预警阈值
PRICE_ALERT_THRESHOLD = 2.0    # 价格波动超过2%触发预警
OI_ALERT_THRESHOLD = 5.0       # 持仓变化超过5%触发预警

# 数据目录
RAW_DIR = "data/raw"           # 原始数据存放路径
```

**什么时候改这里**:
- ✏️ Token过期了 → 更新 `IFIND_REFRESH_TOKEN`
- ✏️ 想监控其他合约 → 修改 `WATCH_LIST`
- ✏️ 预警太频繁/太少 → 调整阈值

---

### 2. `src/data_fetcher/ths_client.py` - API客户端

**作用**: 封装所有同花顺iFinD HTTP API调用，其他模块不直接调API

**核心类**: `TonghuashunClient`

**主要方法**:
| 方法 | 用途 | 调用示例 |
|------|------|----------|
| `get_access_token()` | 用refresh_token换access_token | 自动调用，一般不用管 |
| `get_history_quotes()` | 拉取日/周/月K线 | 获取沪镍日线数据 |
| `get_realtime_quotes()` | 获取实时行情 | 盘中监控用 |
| `get_high_frequency()` | 分钟级数据 | 盘中高频监控 |
| `get_edb_data()` | EDB经济数据库 | 拉取宏观指标（有月度配额限制） |
| `get_trade_dates()` | 交易日历 | 判断是否交易日 |

**什么时候改这里**:
- ✏️ 需要调用新的API接口 → 加新方法
- ✏️ API返回格式变了 → 修改解析逻辑
- 🚫 一般不动，除非API有变化

---

### 3. `src/macro/macro_indicators.py` - 宏观数据模块

**作用**: 管理和拉取宏观经济指标

**重要配置**:
```python
# EDB指标（通过edb_service拉取，有月度配额）
EDB_INDICATORS = {
    "LME镍库存": {"id": "S004303610", "unit": "吨", ...},
    "美元指数": {"id": "G002600885", "unit": "点", ...},
}

# 期货指标（通过行情接口拉取，无配额限制）
FUTURES_INDICATORS = {
    "沪镍连续": {"code": "NI00.SHF", "unit": "元/吨", ...},
}
```

**核心类**: `MacroDataFetcher`

**主要方法**:
| 方法 | 用途 |
|------|------|
| `fetch_edb_indicator()` | 拉取单个EDB指标 |
| `fetch_futures_indicator()` | 拉取期货行情指标 |
| `fetch_all()` | 拉取所有已配置的宏观指标 |
| `save_to_csv()` | 保存数据到CSV |
| `load_from_csv()` | 从本地CSV加载 |

**什么时候改这里**:
- ✏️ 新增宏观指标 → 在 `EDB_INDICATORS` 或 `FUTURES_INDICATORS` 添加
- ✏️ 指标ID变了 → 更新对应的 `id` 或 `code`

---

### 4. `run_daily.py` - 每日行情拉取

**作用**: 拉取沪镍、不锈钢的日线数据，检测异常并打印报告

**执行流程**:
```
运行 python3 run_daily.py
    │
    ├── 1. 读取 config/settings.py 获取配置
    │
    ├── 2. 调用 ths_client.py 拉取最近N天行情
    │
    ├── 3. 保存到 data/raw/NIZL_SHF_daily.csv
    │              data/raw/SSZL_SHF_daily.csv
    │
    ├── 4. 对比今日 vs 昨日数据
    │
    └── 5. 超过阈值 → 打印⚠️预警信息
```

**输出文件**:
- `data/raw/NIZL_SHF_daily.csv` - 沪镍主力日线
- `data/raw/SSZL_SHF_daily.csv` - 不锈钢主力日线

**什么时候改这里**:
- ✏️ 改预警逻辑 → 修改 `detect_alerts()` 函数
- ✏️ 改拉取天数 → 修改 `days` 参数
- ✏️ 改输出格式 → 修改打印部分

---

### 5. `fetch_macro.py` - 宏观数据拉取

**作用**: 单独拉取宏观指标数据

**执行流程**:
```
运行 python3 fetch_macro.py
    │
    ├── 1. 读取 config/settings.py 获取token
    │
    ├── 2. 调用 macro_indicators.py 拉取所有宏观指标
    │       ├── LME镍库存（EDB接口）
    │       ├── 美元指数（EDB接口）
    │       └── 沪镍连续（行情接口）
    │
    └── 3. 保存到 data/macro/*.csv
```

**输出文件**:
- `data/macro/LME镍库存.csv`
- `data/macro/美元指数.csv`
- `data/macro/沪镍连续.csv`

**注意**: EDB接口有月度配额限制，超限会报错

---

### 6. `generate_dashboard.py` - 生成HTML看板

**作用**: 汇总所有数据，生成可视化HTML页面

**执行流程**:
```
运行 python3 generate_dashboard.py
    │
    ├── 1. 拉取/加载行情数据
    │       ├── 优先从API拉最新
    │       └── 失败则从 data/raw/*.csv 加载
    │
    ├── 2. 拉取/加载宏观数据
    │       ├── 优先从API拉最新
    │       └── 失败则从 data/macro/*.csv 加载
    │
    ├── 3. 检测异常信号
    │
    ├── 4. 生成HTML
    │       ├── 异常信号横幅
    │       ├── 价格摘要卡片
    │       ├── K线走势图（含MA均线）
    │       ├── 行情数据表
    │       └── 宏观指标图表
    │
    └── 5. 输出 dashboard.html
```

**输出文件**:
- `dashboard.html` - 双击即可在浏览器打开

**看板包含**:
| 区块 | 内容 |
|------|------|
| 异常信号横幅 | 价格/持仓异常预警（红色高亮） |
| 价格卡片 | 沪镍、不锈钢的最新价、涨跌、持仓 |
| 走势图 | 近60日收盘价 + MA5/10/20 + 成交量 |
| 数据表 | 近15个交易日明细 |
| 宏观指标 | LME库存、美元指数、沪镍连续走势 |

**什么时候改这里**:
- ✏️ 改看板样式 → 修改CSS部分
- ✏️ 加新图表 → 修改 `generate_html()` 函数
- ✏️ 改技术指标 → 修改MA计算逻辑

---

### 7. `test_api.py` - API连接测试

**作用**: 验证API配置是否正确

**执行流程**:
```
运行 python3 test_api.py
    │
    ├── 1. 测试获取 access_token
    │
    ├── 2. 测试拉取沪镍行情
    │
    └── 3. 测试查询数据用量
```

**什么时候用**:
- 🔍 新配置token后验证
- 🔍 API报错时排查问题

---

## 🔄 数据流向图

```
┌─────────────────────────────────────────────────────────────────┐
│                        同花顺 iFinD API                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │ 行情接口     │  │ EDB接口     │  │ 其他接口    │              │
│  │ (无配额)    │  │ (有月配额)  │  │             │              │
│  └──────┬──────┘  └──────┬──────┘  └─────────────┘              │
└─────────┼────────────────┼──────────────────────────────────────┘
          │                │
          ▼                ▼
┌─────────────────────────────────────────────────────────────────┐
│                     ths_client.py                                │
│            (统一封装所有API调用，管理Token)                        │
└─────────────────────────────────────────────────────────────────┘
          │                │
          ▼                ▼
┌─────────────────┐  ┌─────────────────┐
│  run_daily.py   │  │ fetch_macro.py  │
│  (行情+预警)     │  │ (宏观指标)      │
└────────┬────────┘  └────────┬────────┘
         │                    │
         ▼                    ▼
┌─────────────────┐  ┌─────────────────┐
│  data/raw/*.csv │  │ data/macro/*.csv│
└────────┬────────┘  └────────┬────────┘
         │                    │
         └────────┬───────────┘
                  ▼
       ┌─────────────────────┐
       │generate_dashboard.py│
       │   (汇总+可视化)      │
       └──────────┬──────────┘
                  ▼
       ┌─────────────────────┐
       │   dashboard.html    │
       │   (浏览器打开查看)   │
       └─────────────────────┘
```

---

## 📋 常见修改速查

| 我想... | 改哪里 | 具体位置 |
|---------|--------|----------|
| 换Token | `config/settings.py` | `IFIND_REFRESH_TOKEN` |
| 加新合约监控 | `config/settings.py` | `WATCH_LIST` 列表 |
| 改预警阈值 | `config/settings.py` | `PRICE_ALERT_THRESHOLD` / `OI_ALERT_THRESHOLD` |
| 加新宏观指标 | `src/macro/macro_indicators.py` | `EDB_INDICATORS` 或 `FUTURES_INDICATORS` |
| 改看板样式 | `generate_dashboard.py` | `<style>` 部分 |
| 加新技术指标 | `generate_dashboard.py` | MA计算逻辑附近 |
| 改数据拉取天数 | 各脚本的 `days` 参数 | `fetch_all(days=365)` |

---

## 🚀 日常使用命令

```bash
# 进入项目目录
cd nickel_research

# 测试API连接
python3 test_api.py

# 拉取每日行情（含预警）
python3 run_daily.py

# 单独拉取宏观数据
python3 fetch_macro.py

# 生成HTML看板（自动拉取所有数据）
python3 generate_dashboard.py

# 打开看板
open dashboard.html          # Mac
start dashboard.html         # Windows
xdg-open dashboard.html      # Linux
```

---

## ⚠️ 已知限制

| 限制 | 说明 | 解决方案 |
|------|------|----------|
| EDB月度配额 | 超限后无法拉取宏观数据 | 等下月重置 / 申请提额 / 用替代数据源 |
| Token有效期 | refresh_token到2026-03-31 | 到期前重新获取 |
| 非交易时间 | 无法获取实时行情 | 正常，等开盘 |

---

## 📈 后续规划

| 功能 | 状态 | 优先级 |
|------|------|--------|
| 微信推送报警 | 🔴 未开始 | 高 |
| 布林带/MACD | 🔴 未开始 | 中 |
| 席位持仓分析 | 🔴 未开始 | 中 |
| 定时任务 | 🔴 未开始 | 中 |
| 研报聚合 | 🔴 未开始 | 低 |

---

## 📞 问题排查

**Q: API报错 "exceeded this month"**
A: EDB接口月度配额用完了，等下月或用期货行情接口替代

**Q: Token获取失败**
A: 检查refresh_token是否过期，重新从超级命令工具获取

**Q: 数据为空**
A: 可能是非交易时间，或合约代码错误

**Q: 看板打开是空白**
A: 检查是否有 data/raw/*.csv 文件，先运行 run_daily.py
