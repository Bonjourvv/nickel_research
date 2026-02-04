#!/usr/bin/env python3
"""
============================================================
拉取宏观指标数据
============================================================

使用方法：
    cd nickel_research
    python3 fetch_macro.py

数据保存在 data/macro/ 目录下
============================================================
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.settings import IFIND_REFRESH_TOKEN
from src.macro.macro_indicators import MacroDataFetcher


def main():
    print("=" * 60)
    print("📊 宏观指标数据拉取")
    print("=" * 60)

    if not IFIND_REFRESH_TOKEN or IFIND_REFRESH_TOKEN == "在这里填写你的refresh_token":
        print("❌ 请先在 config/settings.py 配置 refresh_token")
        return

    fetcher = MacroDataFetcher(IFIND_REFRESH_TOKEN)

    # 拉取最近1年数据
    all_data = fetcher.fetch_all(days=365)

    if not all_data:
        print("\n❌ 没有获取到数据")
        return

    # 保存CSV
    print("\n📁 保存数据...")
    fetcher.save_to_csv(all_data)

    # 打印最新数据
    print("\n" + "-" * 60)
    print("📋 最新数据一览")
    print("-" * 60)

    for name, rows in all_data.items():
        if not rows:
            continue

        latest = rows[-1]
        date = latest.get('date', 'N/A')

        if 'value' in latest:
            val = latest['value']
            print(f"  {name}: {val:,.2f}  ({date})")
        elif 'close' in latest:
            close = latest.get('close', 0)
            print(f"  {name}: {close:,.0f}  ({date})")

    print("\n✅ 完成!")


if __name__ == "__main__":
    main()
