# 镍/不锈钢期货研究辅助系统

## 📁 项目结构

```
nickel_research/
├── config/
│   └── settings.py          ← 配置文件（填写 refresh_token）
├── src/
│   └── data_fetcher/
│       └── ths_client.py     ← 同花顺 HTTP API 客户端
├── data/
│   ├── raw/                  ← 原始数据（CSV）
│   ├── processed/            ← 处理后数据
│   └── manual/               ← 手动录入数据（Mysteel等）
├── logs/                     ← 运行日志
├── test_api.py               ← 🔑 第一步：测试 API 连接
├── run_daily.py              ← 📊 第二步：每日数据拉取
├── requirements.txt          ← Python 依赖
└── README.md                 ← 你正在看的文件
```

## 🚀 快速开始

### 第零步：安装 Python 环境

在 Mac 终端执行：

```bash
# 检查 Python 版本（需要 3.8+）
python3 --version

# 如果没有 Python，用 Homebrew 安装
brew install python3
```

### 第一步：安装依赖

```bash
cd nickel_research
pip3 install -r requirements.txt
```

### 第二步：获取 refresh_token

**这是最关键的一步！** refresh_token 是 HTTP API 的"钥匙"。

**方法 A（推荐）：网页版**
1. 打开：https://quantapi.10jqka.com.cn/gwstatic/static/ds_web/super-command-web/index.html#/AccountDetails
2. 用账号登录
3. 页面上能看到 refresh_token，复制它

**方法 B：Windows 超级命令工具**
1. 在 Windows 电脑下载接口包：https://quantapi.10jqka.com.cn → 下载中心
2. 解压后打开 `Bin/Tool/SuperCommand.exe`
3. 用公司账号登录
4. 菜单：工具 → refresh_token 查询
5. 复制显示的字符串

### 第三步：测试连接

```bash
python3 test_api.py
```

按提示粘贴 refresh_token，如果看到沪镍行情数据，说明连接成功！

### 第四步：每日使用

```bash
# 拉取最新行情
python3 run_daily.py
```

## 📡 同花顺 HTTP API 说明

### 认证流程

```
refresh_token (永久) → access_token (7天有效) → 调用数据接口
```

- refresh_token：只需获取一次，除非主动刷新
- access_token：程序会自动管理，7天到期自动续期

### API 基础地址

```
https://quantapi.51ifind.com/api/v1/
```

### 主要接口

| 接口 | 端点 | 用途 |
|------|------|------|
| 历史行情 | cmd_history_quotation | 日/周/月K线 |
| 实时行情 | real_time_quotation | 最新价格 |
| 高频数据 | high_frequency | 分钟K线 |
| 基础数据 | basic_data_service | 合约信息 |
| 日期序列 | date_sequence | 指标时间序列 |
| 经济数据库 | edb_service | 宏观指标 |
| 数据用量 | data_statistics | 用量查询 |

### 合约代码

- 沪镍主力：`niZL.SHF`
- 不锈钢主力：`ssZL.SHF`
- 具体月份合约：如 `ni2502.SHF`（镍2025年2月合约）

### 流量限制

- 行情数据：15000万条/周
- 基础数据：500万条/周
- EDB数据：500条/周

日常使用完全够用，不用担心超限。

## ❓ 常见问题

**Q: 报错 "Device exceed limit"**
A: 一个 access_token 最多绑定20个IP。刷新 access_token 即可（删除 config/.token_cache.json）。

**Q: 返回数据为空**
A: 检查日期是否为交易日，非交易日没有数据。

**Q: 如何查看合约代码？**
A: 沪镍=ni+月份.SHF，不锈钢=ss+月份.SHF，主力合约加ZL。
