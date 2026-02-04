#!/usr/bin/env python3
"""
============================================================
每日数据拉取脚本
============================================================

功能：
    1. 拉取沪镍、不锈钢的日线行情
    2. 拉取美元指数
    3. 保存为 CSV 文件
    4. 检测异常波动并输出提醒

使用方法：
    cd nickel_research
    python run_daily.py

后续可以用 crontab 设置每天自动执行：
    # 每天下午4点执行（收盘后）
    0 16 * * 1-5 cd /你的路径/nickel_research && python run_daily.py
============================================================
"""

import sys
import os
import json
import csv
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.settings import (
    IFIND_REFRESH_TOKEN, WATCH_LIST,
    RAW_DIR, PROCESSED_DIR, LOG_DIR,
    PRICE_ALERT_THRESHOLD, OI_ALERT_THRESHOLD,
    NICKEL_MAIN, SS_MAIN
)
from src.data_fetcher.ths_client import TonghuashunClient

import logging

# 日志配置
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, f"daily_{datetime.now().strftime('%Y%m%d')}.log"),
                          encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def fetch_daily_quotes(client: TonghuashunClient):
    """拉取日线行情数据"""
    today = datetime.now().strftime("%Y-%m-%d")
    # 拉最近60天的数据（用于计算技术指标）
    start = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
    codes = ",".join(WATCH_LIST)

    logger.info(f"拉取日线行情: {codes}, {start} ~ {today}")

    result = client.get_history_quotes(
        codes=codes,
        indicators="open,high,low,close,volume,amount,openInterest,changeRatio",
        start_date=start,
        end_date=today
    )

    return result


def save_quotes_to_csv(result: dict):
    """将行情数据保存为 CSV"""
    os.makedirs(RAW_DIR, exist_ok=True)

    if 'tables' not in result:
        logger.error("返回数据格式异常，没有 tables 字段")
        return []

    saved_files = []
    for table in result['tables']:
        code = table.get('thscode', 'unknown')
        time_list = table.get('time', [])
        data = table.get('table', {})

        if not time_list:
            logger.warning(f"{code}: 没有数据")
            continue

        # 文件名：如 niZL_SHF_daily.csv
        safe_code = code.replace('.', '_')
        filename = f"{safe_code}_daily.csv"
        filepath = os.path.join(RAW_DIR, filename)

        # 构建行数据
        indicators = list(data.keys())
        rows = []
        for i in range(len(time_list)):
            row = {'date': time_list[i]}
            for ind in indicators:
                vals = data[ind]
                row[ind] = vals[i] if i < len(vals) else None
            rows.append(row)

        # 写入 CSV
        fieldnames = ['date'] + indicators
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        logger.info(f"  保存: {filepath} ({len(rows)} 条)")
        saved_files.append((code, filepath, rows))

    return saved_files


def check_alerts(saved_files: list):
    """检测异常波动"""
    alerts = []

    for code, filepath, rows in saved_files:
        if len(rows) < 2:
            continue

        latest = rows[-1]
        prev = rows[-2]

        # 涨跌幅检测
        if latest.get('close') and prev.get('close'):
            try:
                change_pct = (float(latest['close']) - float(prev['close'])) / float(prev['close']) * 100
                if abs(change_pct) >= PRICE_ALERT_THRESHOLD:
                    direction = "📈 上涨" if change_pct > 0 else "📉 下跌"
                    alert_msg = (
                        f"⚠️ 价格异常波动 | {code}\n"
                        f"  {direction} {abs(change_pct):.2f}%\n"
                        f"  收盘价: {latest['close']} (前日: {prev['close']})\n"
                        f"  日期: {latest['date']}"
                    )
                    alerts.append(alert_msg)
                    logger.warning(alert_msg)
            except (ValueError, TypeError):
                pass

        # 持仓量变化检测
        if latest.get('openInterest') and prev.get('openInterest'):
            try:
                oi_change = (float(latest['openInterest']) - float(prev['openInterest'])) / float(prev['openInterest']) * 100
                if abs(oi_change) >= OI_ALERT_THRESHOLD:
                    direction = "增仓" if oi_change > 0 else "减仓"
                    alert_msg = (
                        f"⚠️ 持仓量异常 | {code}\n"
                        f"  {direction} {abs(oi_change):.2f}%\n"
                        f"  持仓量: {latest['openInterest']} (前日: {prev['openInterest']})\n"
                        f"  日期: {latest['date']}"
                    )
                    alerts.append(alert_msg)
                    logger.warning(alert_msg)
            except (ValueError, TypeError):
                pass

    return alerts


def print_daily_summary(saved_files: list):
    """打印每日行情摘要"""
    print("\n" + "=" * 70)
    print(f"📊 每日行情摘要 | {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 70)

    for code, filepath, rows in saved_files:
        if not rows:
            continue

        latest = rows[-1]
        print(f"\n{'─' * 50}")

        # 品种名称映射
        name_map = {
            NICKEL_MAIN: "沪镍主力",
            SS_MAIN: "不锈钢主力",
        }
        name = name_map.get(code, code)
        print(f"  {name} ({code})")
        print(f"  日期: {latest.get('date', 'N/A')}")

        close = latest.get('close', 'N/A')
        open_p = latest.get('open', 'N/A')
        high = latest.get('high', 'N/A')
        low = latest.get('low', 'N/A')
        vol = latest.get('volume', 'N/A')
        oi = latest.get('openInterest', 'N/A')

        print(f"  开盘: {open_p}  |  最高: {high}  |  最低: {low}  |  收盘: {close}")
        print(f"  成交量: {vol}  |  持仓量: {oi}")

        # 计算涨跌幅
        if len(rows) >= 2 and latest.get('close') and rows[-2].get('close'):
            try:
                change = float(latest['close']) - float(rows[-2]['close'])
                change_pct = change / float(rows[-2]['close']) * 100
                emoji = "🔴" if change < 0 else "🟢"
                print(f"  涨跌: {emoji} {change:+.0f} ({change_pct:+.2f}%)")
            except (ValueError, TypeError):
                pass

    print(f"\n{'=' * 70}")


def main():
    logger.info("=" * 50)
    logger.info("开始每日数据拉取")
    logger.info("=" * 50)

    # 检查 token
    if not IFIND_REFRESH_TOKEN or IFIND_REFRESH_TOKEN == "在这里填写你的refresh_token":
        print("❌ 请先配置 refresh_token!")
        print("   编辑 config/settings.py 或运行 python test_api.py")
        return

    # 创建客户端
    client = TonghuashunClient(IFIND_REFRESH_TOKEN)

    # 拉取数据
    result = fetch_daily_quotes(client)

    # 保存数据
    saved_files = save_quotes_to_csv(result)

    if not saved_files:
        logger.error("没有获取到任何数据")
        return

    # 打印摘要
    print_daily_summary(saved_files)

    # 检测异常
    alerts = check_alerts(saved_files)

    if alerts:
        print(f"\n🚨 发现 {len(alerts)} 条异常提醒:")
        for a in alerts:
            print(a)
    else:
        print("\n✅ 未发现异常波动")

    logger.info("每日数据拉取完成")


if __name__ == "__main__":
    main()
