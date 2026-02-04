#!/usr/bin/env python3
"""
============================================================
实时行情监控模块
============================================================

盘中实时监控沪镍、不锈钢价格，触发阈值自动预警。

使用方法：
    cd nickel_research
    python3 realtime_monitor.py

运行后会持续监控直到手动停止（Ctrl+C）或收盘。

配置项在 config/settings.py：
    - WATCH_LIST: 监控的合约
    - PRICE_ALERT_THRESHOLD: 价格预警阈值
    - OI_ALERT_THRESHOLD: 持仓预警阈值
============================================================
"""

import sys
import os
import time
import json
from datetime import datetime, timedelta
from typing import Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.settings import (
    IFIND_REFRESH_TOKEN, WATCH_LIST,
    PRICE_ALERT_THRESHOLD, OI_ALERT_THRESHOLD
)
from src.data_fetcher.ths_client import TonghuashunClient


# ============================================================
# 监控配置
# ============================================================

# 刷新间隔（秒）
REFRESH_INTERVAL = 30

# 交易时间段（上期所）
TRADING_SESSIONS = [
    ("09:00", "10:15"),
    ("10:30", "11:30"),
    ("13:30", "15:00"),
    ("21:00", "23:00"),  # 夜盘
]

# 预警冷却时间（同一合约同一类型预警的最小间隔，秒）
ALERT_COOLDOWN = 300  # 5分钟

# 合约名称映射
NAME_MAP = {
    "NIZL.SHF": "沪镍主力",
    "SSZL.SHF": "不锈钢主力",
}


class RealtimeMonitor:
    """实时行情监控器"""

    def __init__(self, refresh_token: str):
        self.client = TonghuashunClient(refresh_token)
        self.watch_list = WATCH_LIST
        
        # 上一次的价格/持仓（用于计算变化）
        self.last_data: Dict[str, dict] = {}
        
        # 今日开盘价（用于计算日内涨跌幅）
        self.open_prices: Dict[str, float] = {}
        
        # 预警冷却记录
        self.alert_cooldown: Dict[str, datetime] = {}
        
        # 日志文件
        self.log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
        os.makedirs(self.log_dir, exist_ok=True)

    def is_trading_time(self) -> bool:
        """判断当前是否为交易时间"""
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        
        for start, end in TRADING_SESSIONS:
            if start <= current_time <= end:
                return True
        return False

    def fetch_realtime(self) -> Optional[Dict[str, dict]]:
        """获取实时行情"""
        codes = ",".join(self.watch_list)
        indicators = "latest,open,high,low,volume,amount,openInterest,changeRatio"
        
        try:
            result = self.client.get_realtime_quotes(codes, indicators)
            
            if result.get('errorcode') != 0:
                print(f"❌ API错误: {result.get('errmsg', '未知错误')}")
                return None
            
            data = {}
            for table in result.get('tables', []):
                code = table.get('thscode', '').upper()
                table_data = table.get('table', {})
                
                data[code] = {
                    'time': table.get('time', [''])[0],
                    'latest': table_data.get('latest', [0])[0],
                    'open': table_data.get('open', [0])[0],
                    'high': table_data.get('high', [0])[0],
                    'low': table_data.get('low', [0])[0],
                    'volume': table_data.get('volume', [0])[0],
                    'amount': table_data.get('amount', [0])[0],
                    'openInterest': table_data.get('openInterest', [0])[0],
                    'changeRatio': table_data.get('changeRatio', [0])[0],
                }
            
            return data
            
        except Exception as e:
            print(f"❌ 获取行情失败: {e}")
            return None

    def check_alerts(self, code: str, current: dict) -> list:
        """检查是否触发预警"""
        alerts = []
        name = NAME_MAP.get(code, code)
        now = datetime.now()
        
        # 获取上一次数据
        last = self.last_data.get(code, {})
        
        # 1. 日内涨跌幅预警（基于开盘价）
        open_price = current.get('open', 0)
        latest = current.get('latest', 0)
        
        if open_price and latest:
            day_change_pct = (latest - open_price) / open_price * 100
            
            if abs(day_change_pct) >= PRICE_ALERT_THRESHOLD:
                alert_key = f"{code}_day_price"
                if self._can_alert(alert_key):
                    direction = "上涨" if day_change_pct > 0 else "下跌"
                    alerts.append({
                        'type': 'day_price',
                        'code': code,
                        'name': name,
                        'message': f"日内{direction} {abs(day_change_pct):.2f}%",
                        'detail': f"开盘 {open_price:,.0f} → 现价 {latest:,.0f}",
                        'level': 'high' if abs(day_change_pct) >= PRICE_ALERT_THRESHOLD * 2 else 'medium'
                    })
                    self._record_alert(alert_key)
        
        # 2. 短期价格急变预警（相比上次查询）
        if last:
            last_price = last.get('latest', 0)
            if last_price and latest:
                short_change_pct = (latest - last_price) / last_price * 100
                
                # 短期变化超过0.5%就预警
                if abs(short_change_pct) >= 0.5:
                    alert_key = f"{code}_short_price"
                    if self._can_alert(alert_key):
                        direction = "急涨" if short_change_pct > 0 else "急跌"
                        alerts.append({
                            'type': 'short_price',
                            'code': code,
                            'name': name,
                            'message': f"短期{direction} {abs(short_change_pct):.2f}%",
                            'detail': f"{last_price:,.0f} → {latest:,.0f} ({REFRESH_INTERVAL}秒内)",
                            'level': 'high'
                        })
                        self._record_alert(alert_key)
        
        # 3. 持仓量大幅变化预警
        if last:
            last_oi = last.get('openInterest', 0)
            current_oi = current.get('openInterest', 0)
            
            if last_oi and current_oi:
                oi_change_pct = (current_oi - last_oi) / last_oi * 100
                
                # 持仓变化超过1%
                if abs(oi_change_pct) >= 1.0:
                    alert_key = f"{code}_oi"
                    if self._can_alert(alert_key):
                        direction = "增仓" if oi_change_pct > 0 else "减仓"
                        alerts.append({
                            'type': 'oi',
                            'code': code,
                            'name': name,
                            'message': f"大幅{direction} {abs(oi_change_pct):.2f}%",
                            'detail': f"{last_oi:,.0f} → {current_oi:,.0f}",
                            'level': 'medium'
                        })
                        self._record_alert(alert_key)
        
        # 4. 触及日内新高/新低
        high = current.get('high', 0)
        low = current.get('low', 0)
        
        if latest and high and latest >= high * 0.999:  # 接近日内高点
            alert_key = f"{code}_high"
            if self._can_alert(alert_key):
                alerts.append({
                    'type': 'high',
                    'code': code,
                    'name': name,
                    'message': f"触及日内新高",
                    'detail': f"最高 {high:,.0f}",
                    'level': 'low'
                })
                self._record_alert(alert_key)
        
        if latest and low and latest <= low * 1.001:  # 接近日内低点
            alert_key = f"{code}_low"
            if self._can_alert(alert_key):
                alerts.append({
                    'type': 'low',
                    'code': code,
                    'name': name,
                    'message': f"触及日内新低",
                    'detail': f"最低 {low:,.0f}",
                    'level': 'low'
                })
                self._record_alert(alert_key)
        
        return alerts

    def _can_alert(self, alert_key: str) -> bool:
        """检查是否可以发送预警（冷却时间）"""
        last_alert = self.alert_cooldown.get(alert_key)
        if last_alert is None:
            return True
        return (datetime.now() - last_alert).total_seconds() >= ALERT_COOLDOWN

    def _record_alert(self, alert_key: str):
        """记录预警时间"""
        self.alert_cooldown[alert_key] = datetime.now()

    def print_alert(self, alert: dict):
        """打印预警信息"""
        level_icons = {
            'high': '🚨',
            'medium': '⚠️',
            'low': '📢'
        }
        icon = level_icons.get(alert['level'], '📢')
        
        print(f"\n{icon} 【{alert['name']}】{alert['message']}")
        print(f"   {alert['detail']}")
        print(f"   时间: {datetime.now().strftime('%H:%M:%S')}")

    def print_status(self, data: Dict[str, dict]):
        """打印当前行情状态"""
        now = datetime.now().strftime("%H:%M:%S")
        
        # 清屏效果（可选）
        # print("\033[H\033[J", end="")
        
        print(f"\n{'='*60}")
        print(f"📊 实时行情监控 | {now} | 刷新间隔 {REFRESH_INTERVAL}秒")
        print(f"{'='*60}")
        
        for code, d in data.items():
            name = NAME_MAP.get(code, code)
            latest = d.get('latest', 0)
            open_p = d.get('open', 0)
            high = d.get('high', 0)
            low = d.get('low', 0)
            change_ratio = d.get('changeRatio', 0)
            oi = d.get('openInterest', 0)
            volume = d.get('volume', 0)
            
            # 涨跌标识
            if change_ratio > 0:
                arrow = "▲"
                color_start = "\033[92m"  # 绿色
            elif change_ratio < 0:
                arrow = "▼"
                color_start = "\033[91m"  # 红色
            else:
                arrow = "─"
                color_start = ""
            color_end = "\033[0m" if color_start else ""
            
            print(f"\n【{name}】{code}")
            print(f"  现价: {color_start}{latest:>10,.0f} {arrow} {change_ratio:+.2f}%{color_end}")
            print(f"  开盘: {open_p:>10,.0f}    最高: {high:>10,.0f}")
            print(f"  最低: {low:>10,.0f}    持仓: {oi:>10,.0f}")
            print(f"  成交: {volume:>10,.0f} 手")
        
        print(f"\n{'─'*60}")
        print(f"按 Ctrl+C 停止监控")

    def log_data(self, data: Dict[str, dict]):
        """记录数据到日志文件"""
        today = datetime.now().strftime("%Y-%m-%d")
        log_file = os.path.join(self.log_dir, f"realtime_{today}.jsonl")
        
        record = {
            'timestamp': datetime.now().isoformat(),
            'data': data
        }
        
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def run(self):
        """启动监控"""
        print("=" * 60)
        print("🚀 启动实时行情监控")
        print("=" * 60)
        print(f"监控合约: {', '.join(self.watch_list)}")
        print(f"刷新间隔: {REFRESH_INTERVAL} 秒")
        print(f"价格预警阈值: {PRICE_ALERT_THRESHOLD}%")
        print(f"持仓预警阈值: {OI_ALERT_THRESHOLD}%")
        print("=" * 60)
        
        if not self.is_trading_time():
            print("\n⏰ 当前非交易时间，仍将启动监控...")
        
        try:
            while True:
                # 获取实时数据
                data = self.fetch_realtime()
                
                if data:
                    # 打印状态
                    self.print_status(data)
                    
                    # 检查预警
                    for code, current in data.items():
                        alerts = self.check_alerts(code, current)
                        for alert in alerts:
                            self.print_alert(alert)
                    
                    # 记录日志
                    self.log_data(data)
                    
                    # 更新上次数据
                    self.last_data = data
                
                # 等待下次刷新
                time.sleep(REFRESH_INTERVAL)
                
        except KeyboardInterrupt:
            print("\n\n👋 监控已停止")
            self._save_summary()

    def _save_summary(self):
        """保存今日监控摘要"""
        if not self.last_data:
            return
        
        print("\n📋 今日监控摘要:")
        for code, d in self.last_data.items():
            name = NAME_MAP.get(code, code)
            print(f"  {name}: 最新 {d.get('latest', 0):,.0f}, 涨跌 {d.get('changeRatio', 0):+.2f}%")


def main():
    if not IFIND_REFRESH_TOKEN or IFIND_REFRESH_TOKEN == "在这里填写你的refresh_token":
        print("❌ 请先在 config/settings.py 配置 refresh_token")
        return
    
    monitor = RealtimeMonitor(IFIND_REFRESH_TOKEN)
    monitor.run()


if __name__ == "__main__":
    main()
