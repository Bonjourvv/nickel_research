#!/usr/bin/env python3
"""
============================================================
实时网页看板
============================================================

生成一个自动刷新的HTML页面，实时显示行情。

使用方法：
    cd nickel_research
    python3 realtime_web.py

运行后：
1. 自动生成 realtime.html
2. 自动用浏览器打开
3. 页面每30秒自动刷新
4. 终端持续运行，按 Ctrl+C 停止
============================================================
"""

import sys
import os
import time
import json
import webbrowser
import subprocess
from datetime import datetime
from typing import Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.settings import (
    IFIND_REFRESH_TOKEN, WATCH_LIST,
    PRICE_ALERT_THRESHOLD, OI_ALERT_THRESHOLD
)
from src.data_fetcher.ths_client import TonghuashunClient


# ============================================================
# 配置
# ============================================================

REFRESH_INTERVAL = 30  # 刷新间隔（秒）

NAME_MAP = {
    "NIZL.SHF": "沪镍主力",
    "SSZL.SHF": "不锈钢主力",
}


class RealtimeWebDashboard:
    """实时网页看板"""

    def __init__(self, refresh_token: str):
        self.client = TonghuashunClient(refresh_token)
        self.watch_list = WATCH_LIST
        self.output_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "realtime.html"
        )
        self.alerts_history = []  # 最近的预警记录
        self.last_data: Dict[str, dict] = {}

    def fetch_realtime(self) -> Optional[Dict[str, dict]]:
        """获取实时行情"""
        codes = ",".join(self.watch_list)
        indicators = "latest,open,high,low,volume,amount,openInterest,changeRatio"

        try:
            result = self.client.get_realtime_quotes(codes, indicators)

            if result.get('errorcode') != 0:
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

    def check_alerts(self, data: Dict[str, dict]) -> list:
        """检查预警"""
        alerts = []

        for code, current in data.items():
            name = NAME_MAP.get(code, code)
            latest = current.get('latest', 0)
            open_p = current.get('open', 0)
            change_ratio = current.get('changeRatio', 0)

            # 日内涨跌幅预警
            if abs(change_ratio) >= PRICE_ALERT_THRESHOLD:
                direction = "上涨" if change_ratio > 0 else "下跌"
                alerts.append({
                    'time': datetime.now().strftime('%H:%M:%S'),
                    'name': name,
                    'type': 'price',
                    'message': f"日内{direction} {abs(change_ratio):.2f}%",
                    'level': 'high' if abs(change_ratio) >= PRICE_ALERT_THRESHOLD * 2 else 'medium'
                })

            # 短期急变
            if self.last_data and code in self.last_data:
                last_price = self.last_data[code].get('latest', 0)
                if last_price and latest:
                    short_change = (latest - last_price) / last_price * 100
                    if abs(short_change) >= 0.3:
                        direction = "急涨" if short_change > 0 else "急跌"
                        alerts.append({
                            'time': datetime.now().strftime('%H:%M:%S'),
                            'name': name,
                            'type': 'short',
                            'message': f"{direction} {abs(short_change):.2f}% ({REFRESH_INTERVAL}秒内)",
                            'level': 'high'
                        })

        return alerts

    def generate_html(self, data: Dict[str, dict]) -> str:
        """生成HTML"""
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 构建卡片数据
        cards_html = ""
        for code, d in data.items():
            name = NAME_MAP.get(code, code)
            latest = d.get('latest', 0)
            open_p = d.get('open', 0)
            high = d.get('high', 0)
            low = d.get('low', 0)
            change_ratio = d.get('changeRatio', 0)
            oi = d.get('openInterest', 0)
            volume = d.get('volume', 0)
            amount = d.get('amount', 0)

            # 计算日内变化
            if open_p:
                day_change = latest - open_p
            else:
                day_change = 0

            up_down = 'up' if change_ratio >= 0 else 'down'
            arrow = '▲' if change_ratio >= 0 else '▼'

            # 计算振幅
            amplitude = ((high - low) / open_p * 100) if open_p else 0

            cards_html += f"""
        <div class="card {up_down}">
            <div class="card-header">
                <div class="card-name">{name}</div>
                <div class="card-code">{code}</div>
            </div>
            <div class="card-price">
                <span class="price">{latest:,.0f}</span>
                <span class="change {up_down}">{arrow} {day_change:+,.0f} ({change_ratio:+.2f}%)</span>
            </div>
            <div class="card-grid">
                <div class="metric">
                    <div class="label">开盘</div>
                    <div class="value">{open_p:,.0f}</div>
                </div>
                <div class="metric">
                    <div class="label">最高</div>
                    <div class="value up">{high:,.0f}</div>
                </div>
                <div class="metric">
                    <div class="label">最低</div>
                    <div class="value down">{low:,.0f}</div>
                </div>
                <div class="metric">
                    <div class="label">振幅</div>
                    <div class="value">{amplitude:.2f}%</div>
                </div>
                <div class="metric">
                    <div class="label">成交量</div>
                    <div class="value">{volume:,.0f}</div>
                </div>
                <div class="metric">
                    <div class="label">成交额</div>
                    <div class="value">{amount/100000000:.2f}亿</div>
                </div>
                <div class="metric">
                    <div class="label">持仓量</div>
                    <div class="value">{oi:,.0f}</div>
                </div>
                <div class="metric">
                    <div class="label">数据时间</div>
                    <div class="value" style="font-size:11px">{d.get('time', '')[-8:]}</div>
                </div>
            </div>
        </div>
"""

        # 预警列表
        alerts_html = ""
        if self.alerts_history:
            for alert in self.alerts_history[-10:]:  # 最近10条
                level_class = alert.get('level', 'medium')
                alerts_html += f"""
            <div class="alert-item {level_class}">
                <span class="alert-time">{alert['time']}</span>
                <span class="alert-name">{alert['name']}</span>
                <span class="alert-msg">{alert['message']}</span>
            </div>
"""

        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="refresh" content="{REFRESH_INTERVAL}">
<title>实时行情监控 - 镍/不锈钢</title>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Noto+Sans+SC:wght@400;500;700&display=swap" rel="stylesheet">
<style>
:root {{
    --bg: #0f172a;
    --card-bg: #1e293b;
    --border: #334155;
    --text: #e2e8f0;
    --text-muted: #94a3b8;
    --green: #22c55e;
    --red: #ef4444;
    --amber: #f59e0b;
    --blue: #38bdf8;
}}

* {{ margin: 0; padding: 0; box-sizing: border-box; }}

body {{
    font-family: 'Noto Sans SC', sans-serif;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
    padding: 24px;
}}

.container {{
    max-width: 1200px;
    margin: 0 auto;
}}

header {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 24px;
    padding-bottom: 16px;
    border-bottom: 1px solid var(--border);
}}

h1 {{
    font-size: 24px;
    font-weight: 700;
    display: flex;
    align-items: center;
    gap: 12px;
}}

h1 .live {{
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    font-weight: 500;
    color: var(--green);
    background: rgba(34, 197, 94, 0.1);
    padding: 4px 10px;
    border-radius: 20px;
}}

h1 .live .dot {{
    width: 8px;
    height: 8px;
    background: var(--green);
    border-radius: 50%;
    animation: pulse 1.5s infinite;
}}

@keyframes pulse {{
    0%, 100% {{ opacity: 1; transform: scale(1); }}
    50% {{ opacity: 0.5; transform: scale(0.8); }}
}}

.update-info {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    color: var(--text-muted);
}}

.cards {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(380px, 1fr));
    gap: 20px;
    margin-bottom: 24px;
}}

.card {{
    background: var(--card-bg);
    border-radius: 16px;
    padding: 24px;
    border: 1px solid var(--border);
    position: relative;
    overflow: hidden;
}}

.card::before {{
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 4px;
}}

.card.up::before {{ background: linear-gradient(90deg, var(--green), transparent); }}
.card.down::before {{ background: linear-gradient(90deg, var(--red), transparent); }}

.card-header {{
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    margin-bottom: 16px;
}}

.card-name {{
    font-size: 20px;
    font-weight: 700;
}}

.card-code {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    color: var(--text-muted);
}}

.card-price {{
    margin-bottom: 20px;
}}

.card-price .price {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 42px;
    font-weight: 600;
    letter-spacing: -2px;
}}

.card-price .change {{
    display: block;
    font-family: 'JetBrains Mono', monospace;
    font-size: 16px;
    margin-top: 4px;
}}

.card-price .change.up {{ color: var(--green); }}
.card-price .change.down {{ color: var(--red); }}

.card-grid {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 12px;
    padding-top: 16px;
    border-top: 1px solid var(--border);
}}

.metric {{
    text-align: center;
}}

.metric .label {{
    font-size: 11px;
    color: var(--text-muted);
    margin-bottom: 4px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}}

.metric .value {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 14px;
    font-weight: 500;
}}

.metric .value.up {{ color: var(--green); }}
.metric .value.down {{ color: var(--red); }}

.alerts-section {{
    background: var(--card-bg);
    border-radius: 16px;
    padding: 20px;
    border: 1px solid var(--border);
}}

.alerts-section h3 {{
    font-size: 14px;
    font-weight: 600;
    color: var(--text-muted);
    margin-bottom: 12px;
    display: flex;
    align-items: center;
    gap: 8px;
}}

.alert-item {{
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 8px 12px;
    border-radius: 8px;
    margin-bottom: 6px;
    font-size: 13px;
}}

.alert-item.high {{
    background: rgba(239, 68, 68, 0.1);
    border-left: 3px solid var(--red);
}}

.alert-item.medium {{
    background: rgba(245, 158, 11, 0.1);
    border-left: 3px solid var(--amber);
}}

.alert-time {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    color: var(--text-muted);
}}

.alert-name {{
    font-weight: 600;
    min-width: 80px;
}}

.alert-msg {{
    color: var(--text-muted);
}}

.no-alerts {{
    color: var(--text-muted);
    font-size: 13px;
    text-align: center;
    padding: 20px;
}}

footer {{
    text-align: center;
    margin-top: 24px;
    padding-top: 16px;
    border-top: 1px solid var(--border);
    font-size: 12px;
    color: var(--text-muted);
}}

.countdown {{
    position: fixed;
    bottom: 20px;
    right: 20px;
    background: var(--card-bg);
    border: 1px solid var(--border);
    padding: 8px 16px;
    border-radius: 20px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    color: var(--text-muted);
}}
</style>
</head>
<body>

<div class="container">
    <header>
        <h1>
            镍 · 不锈钢
            <span class="live"><span class="dot"></span>实时监控</span>
        </h1>
        <div class="update-info">更新于 {now_str}</div>
    </header>

    <div class="cards">
{cards_html}
    </div>

    <div class="alerts-section">
        <h3>⚡ 最近预警</h3>
        {alerts_html if alerts_html else '<div class="no-alerts">暂无预警信号</div>'}
    </div>

    <footer>
        页面每 {REFRESH_INTERVAL} 秒自动刷新 · 数据来源: 同花顺iFinD
    </footer>
</div>

<div class="countdown" id="countdown">下次刷新: {REFRESH_INTERVAL}s</div>

<script>
let seconds = {REFRESH_INTERVAL};
setInterval(() => {{
    seconds--;
    if (seconds <= 0) seconds = {REFRESH_INTERVAL};
    document.getElementById('countdown').textContent = '下次刷新: ' + seconds + 's';
}}, 1000);
</script>

</body>
</html>"""
        return html

    def update(self):
        """更新一次数据和HTML"""
        data = self.fetch_realtime()

        if not data:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️ 获取数据失败")
            return False

        # 检查预警
        alerts = self.check_alerts(data)
        if alerts:
            self.alerts_history.extend(alerts)
            for a in alerts:
                print(f"[{a['time']}] 🚨 {a['name']} {a['message']}")

        # 生成HTML
        html = self.generate_html(data)
        with open(self.output_path, 'w', encoding='utf-8') as f:
            f.write(html)

        # 更新last_data
        self.last_data = data

        return True

    def run(self):
        """启动实时看板"""
        print("=" * 60)
        print("🌐 启动实时网页看板")
        print("=" * 60)
        print(f"输出文件: {self.output_path}")
        print(f"刷新间隔: {REFRESH_INTERVAL} 秒")
        print("=" * 60)

        # 首次更新
        if self.update():
            # 打开浏览器
            print(f"\n🌐 正在打开浏览器...")
            webbrowser.open(f"file://{self.output_path}")

        print(f"\n✅ 看板已启动，终端会显示预警信息")
        print(f"   按 Ctrl+C 停止\n")

        try:
            while True:
                time.sleep(REFRESH_INTERVAL)
                now = datetime.now().strftime('%H:%M:%S')
                if self.update():
                    print(f"[{now}] ✅ 数据已更新")
                else:
                    print(f"[{now}] ⚠️ 更新失败，等待重试")

        except KeyboardInterrupt:
            print("\n\n👋 实时看板已停止")


def main():
    if not IFIND_REFRESH_TOKEN or IFIND_REFRESH_TOKEN == "在这里填写你的refresh_token":
        print("❌ 请先在 config/settings.py 配置 refresh_token")
        return

    dashboard = RealtimeWebDashboard(IFIND_REFRESH_TOKEN)
    dashboard.run()


if __name__ == "__main__":
    main()
