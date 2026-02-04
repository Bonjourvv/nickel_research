#!/usr/bin/env python3
"""
============================================================
宏观指标数据模块
============================================================

管理镍/不锈钢相关的宏观经济指标：
- EDB经济数据库指标（美元指数、LME镍库存等）
- 期货行情指标（沪镍连续等）

使用方法：
    from src.macro.macro_indicators import MacroDataFetcher
    fetcher = MacroDataFetcher(refresh_token)
    data = fetcher.fetch_all()
============================================================
"""

import os
import sys
import csv
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.data_fetcher.ths_client import TonghuashunClient


# ============================================================
# 宏观指标配置
# ============================================================

# EDB经济数据库指标（通过 edb_service 接口查询）
EDB_INDICATORS = {
    "LME镍库存": {
        "id": "S004303610",
        "unit": "吨",
        "frequency": "日",
        "category": "库存",
        "description": "LME镍库存量，反映全球镍供需状况的核心指标"
    },
    "美元指数": {
        "id": "G002600885",
        "unit": "点",
        "frequency": "日",
        "category": "宏观",
        "description": "美元对一篮子货币的汇率指数，影响以美元计价的商品价格"
    },
}

# 期货行情指标（通过 cmd_history_quotation 接口查询）
FUTURES_INDICATORS = {
    "沪镍连续": {
        "code": "NI00.SHF",
        "unit": "元/吨",
        "frequency": "日",
        "category": "价格",
        "description": "上期所镍期货连续合约，国内镍定价基准"
    },
}

# 待补充的指标（查到ID后添加）
PENDING_INDICATORS = """
以下指标待查询ID后补充：
- 上期所镍库存
- 中国PMI
- 沪镍仓单
- 镍矿进口量
- 不锈钢产量
- 印尼镍矿出口政策相关
"""


class MacroDataFetcher:
    """宏观数据拉取器"""

    def __init__(self, refresh_token: str):
        self.client = TonghuashunClient(refresh_token)
        self.data_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "data", "macro"
        )
        os.makedirs(self.data_dir, exist_ok=True)

    def fetch_edb_indicator(self, name: str, days: int = 365) -> Optional[List[dict]]:
        """
        拉取单个EDB指标数据

        参数:
            name: 指标名称（如"LME镍库存"）
            days: 拉取最近多少天的数据

        返回:
            [{"date": "2025-01-01", "value": 12345.0}, ...]
        """
        if name not in EDB_INDICATORS:
            print(f"❌ 未知指标: {name}")
            return None

        config = EDB_INDICATORS[name]
        indicator_id = config["id"]

        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        print(f"📡 拉取 {name} ({indicator_id}): {start_date} ~ {end_date}")

        try:
            result = self.client.get_edb_data(
                indicator_ids=indicator_id,
                start_date=start_date,
                end_date=end_date
            )

            # 解析返回数据
            if 'tables' in result and len(result['tables']) > 0:
                table = result['tables'][0]
                time_list = table.get('time', [])
                data_table = table.get('table', {})

                # EDB返回的数据结构：table 里的 key 是指标ID
                values = data_table.get(indicator_id, [])

                rows = []
                for i, date in enumerate(time_list):
                    val = values[i] if i < len(values) else None
                    if val is not None and val != '':
                        try:
                            rows.append({
                                "date": date,
                                "value": float(val) if val else None
                            })
                        except (ValueError, TypeError):
                            pass

                print(f"  ✅ 获取 {len(rows)} 条数据")
                return rows
            else:
                print(f"  ⚠️ 返回数据为空")
                if 'errmsg' in result:
                    print(f"  错误信息: {result['errmsg']}")
                return []

        except Exception as e:
            print(f"  ❌ 拉取失败: {e}")
            return None

    def fetch_futures_indicator(self, name: str, days: int = 365) -> Optional[List[dict]]:
        """
        拉取期货行情指标

        参数:
            name: 指标名称（如"沪镍连续"）
            days: 拉取最近多少天的数据

        返回:
            [{"date": "2025-01-01", "open": 123, "high": 125, "low": 121, "close": 124, "volume": 1000}, ...]
        """
        if name not in FUTURES_INDICATORS:
            print(f"❌ 未知指标: {name}")
            return None

        config = FUTURES_INDICATORS[name]
        code = config["code"]

        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        print(f"📡 拉取 {name} ({code}): {start_date} ~ {end_date}")

        try:
            result = self.client.get_history_quotes(
                codes=code,
                indicators="open,high,low,close,volume,amount,openInterest",
                start_date=start_date,
                end_date=end_date
            )

            if 'tables' in result and len(result['tables']) > 0:
                table = result['tables'][0]
                time_list = table.get('time', [])
                data_table = table.get('table', {})

                rows = []
                for i, date in enumerate(time_list):
                    row = {"date": date}
                    for key in ['open', 'high', 'low', 'close', 'volume', 'amount', 'openInterest']:
                        vals = data_table.get(key, [])
                        if i < len(vals) and vals[i] is not None and vals[i] != '':
                            try:
                                row[key] = float(vals[i])
                            except (ValueError, TypeError):
                                row[key] = None
                        else:
                            row[key] = None
                    rows.append(row)

                print(f"  ✅ 获取 {len(rows)} 条数据")
                return rows
            else:
                print(f"  ⚠️ 返回数据为空")
                return []

        except Exception as e:
            print(f"  ❌ 拉取失败: {e}")
            return None

    def fetch_all(self, days: int = 365) -> Dict[str, List[dict]]:
        """
        拉取所有已配置的宏观指标

        返回:
            {
                "LME镍库存": [{"date": ..., "value": ...}, ...],
                "美元指数": [...],
                "沪镍连续": [{"date": ..., "open": ..., "close": ...}, ...],
            }
        """
        all_data = {}

        print("\n" + "=" * 60)
        print("📊 拉取宏观指标数据")
        print("=" * 60)

        # 拉取 EDB 指标
        for name in EDB_INDICATORS:
            data = self.fetch_edb_indicator(name, days)
            if data:
                all_data[name] = data

        # 拉取期货指标
        for name in FUTURES_INDICATORS:
            data = self.fetch_futures_indicator(name, days)
            if data:
                all_data[name] = data

        return all_data

    def save_to_csv(self, all_data: Dict[str, List[dict]]):
        """保存数据到CSV文件"""
        for name, rows in all_data.items():
            if not rows:
                continue

            safe_name = name.replace("/", "_").replace(" ", "_")
            filepath = os.path.join(self.data_dir, f"{safe_name}.csv")

            fieldnames = list(rows[0].keys())
            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)

            print(f"  💾 {filepath} ({len(rows)} 条)")

    def load_from_csv(self) -> Dict[str, List[dict]]:
        """从CSV加载已有数据"""
        all_data = {}

        if not os.path.exists(self.data_dir):
            return all_data

        for filename in os.listdir(self.data_dir):
            if not filename.endswith('.csv'):
                continue

            name = filename.replace('.csv', '').replace('_', ' ')
            filepath = os.path.join(self.data_dir, filename)

            rows = []
            with open(filepath, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # 转换数值类型
                    for key in row:
                        if key != 'date' and row[key]:
                            try:
                                row[key] = float(row[key])
                            except ValueError:
                                pass
                    rows.append(row)

            all_data[name] = rows

        return all_data


# ============================================================
# 命令行测试
# ============================================================

def main():
    """测试宏观数据拉取"""
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from config.settings import IFIND_REFRESH_TOKEN

    if not IFIND_REFRESH_TOKEN or IFIND_REFRESH_TOKEN == "在这里填写你的refresh_token":
        print("❌ 请先在 config/settings.py 配置 refresh_token")
        return

    fetcher = MacroDataFetcher(IFIND_REFRESH_TOKEN)

    # 拉取最近1年的数据
    all_data = fetcher.fetch_all(days=365)

    # 保存到CSV
    print("\n📁 保存数据到 data/macro/ ...")
    fetcher.save_to_csv(all_data)

    # 打印摘要
    print("\n" + "=" * 60)
    print("📋 数据摘要")
    print("=" * 60)

    for name, rows in all_data.items():
        if not rows:
            continue

        latest = rows[-1]
        print(f"\n【{name}】")
        print(f"  最新日期: {latest.get('date', 'N/A')}")

        if 'value' in latest:
            print(f"  最新值: {latest['value']}")
        elif 'close' in latest:
            print(f"  收盘价: {latest.get('close', 'N/A')}")
            print(f"  持仓量: {latest.get('openInterest', 'N/A')}")

        # 计算变化
        if len(rows) >= 2:
            prev = rows[-2]
            if 'value' in latest and 'value' in prev:
                if prev['value'] and latest['value']:
                    chg = latest['value'] - prev['value']
                    pct = (chg / prev['value']) * 100
                    print(f"  日变化: {chg:+.2f} ({pct:+.2f}%)")
            elif 'close' in latest and 'close' in prev:
                if prev['close'] and latest['close']:
                    chg = latest['close'] - prev['close']
                    pct = (chg / prev['close']) * 100
                    print(f"  日涨跌: {chg:+.0f} ({pct:+.2f}%)")


if __name__ == "__main__":
    main()
