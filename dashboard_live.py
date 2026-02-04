#!/usr/bin/env python3
"""
============================================================
镍/不锈钢研究看板（合并版）
============================================================

整合实时行情 + 历史数据 + 宏观指标，一个页面全搞定。

使用方法：
    cd nickel_research
    python3 dashboard_live.py

功能：
    - 顶部：实时行情卡片（每30秒刷新）
    - 中部：预警信号
    - 下部：历史走势图 + 宏观指标
    - 底部：数据明细表

页面自动刷新，终端持续运行直到 Ctrl+C
============================================================
"""

import sys
import os
import time
import csv
import json
import webbrowser
from datetime import datetime, timedelta
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.settings import (
    IFIND_REFRESH_TOKEN, WATCH_LIST, RAW_DIR,
    PRICE_ALERT_THRESHOLD, OI_ALERT_THRESHOLD
)
from src.data_fetcher.ths_client import TonghuashunClient


# ============================================================
# 配置
# ============================================================

REFRESH_INTERVAL = 30  # 页面刷新间隔（秒）

NAME_MAP = {
    "NIZL.SHF": ("沪镍主力", "ni"),
    "SSZL.SHF": ("不锈钢主力", "ss"),
}

MACRO_INDICATORS = {
    "沪镍连续": {"code": "NI00.SHF", "type": "futures"},
}


class UnifiedDashboard:
    """统一看板"""

    def __init__(self, refresh_token: str):
        self.client = TonghuashunClient(refresh_token)
        self.output_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "dashboard_live.html"
        )
        self.alerts_history = []
        self.last_realtime: Dict[str, dict] = {}
        self.history_data: Dict[str, List[dict]] = {}
        self.macro_data: Dict[str, List[dict]] = {}

    # ========================================
    # 数据获取
    # ========================================

    def fetch_realtime(self) -> Optional[Dict[str, dict]]:
        """获取实时行情"""
        codes = ",".join(WATCH_LIST)
        indicators = "latest,open,high,low,volume,amount,openInterest,changeRatio"

        try:
            result = self.client.get_realtime_quotes(codes, indicators)
            if result.get('errorcode') != 0:
                return None

            data = {}
            for table in result.get('tables', []):
                code = table.get('thscode', '').upper()
                td = table.get('table', {})
                data[code] = {
                    'time': table.get('time', [''])[0],
                    'latest': td.get('latest', [0])[0],
                    'open': td.get('open', [0])[0],
                    'high': td.get('high', [0])[0],
                    'low': td.get('low', [0])[0],
                    'volume': td.get('volume', [0])[0],
                    'amount': td.get('amount', [0])[0],
                    'openInterest': td.get('openInterest', [0])[0],
                    'changeRatio': td.get('changeRatio', [0])[0],
                }
            return data
        except Exception as e:
            print(f"❌ 实时行情失败: {e}")
            return None

    def fetch_history(self, days: int = 60) -> Dict[str, List[dict]]:
        """获取历史数据"""
        codes = ",".join(WATCH_LIST)
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days + 30)).strftime("%Y-%m-%d")

        try:
            result = self.client.get_history_quotes(
                codes=codes,
                indicators="open,high,low,close,volume,amount,openInterest,changeRatio",
                start_date=start_date,
                end_date=end_date
            )

            data = {}
            if 'tables' in result:
                for table in result['tables']:
                    code = table.get('thscode', '').upper()
                    time_list = table.get('time', [])
                    td = table.get('table', {})

                    rows = []
                    for i in range(len(time_list)):
                        row = {'date': time_list[i]}
                        for key in ['open', 'high', 'low', 'close', 'volume', 'amount', 'openInterest', 'changeRatio']:
                            vals = td.get(key, [])
                            row[key] = vals[i] if i < len(vals) else None
                        rows.append(row)

                    # 只保留最近N天
                    data[code] = rows[-days:] if len(rows) > days else rows

            return data
        except Exception as e:
            print(f"❌ 历史数据失败: {e}")
            return {}

    def fetch_macro(self, days: int = 90) -> Dict[str, List[dict]]:
        """获取宏观指标"""
        data = {}
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days + 30)).strftime("%Y-%m-%d")

        for name, config in MACRO_INDICATORS.items():
            if config['type'] == 'futures':
                try:
                    result = self.client.get_history_quotes(
                        codes=config['code'],
                        indicators="close",
                        start_date=start_date,
                        end_date=end_date
                    )
                    if 'tables' in result and result['tables']:
                        table = result['tables'][0]
                        time_list = table.get('time', [])
                        closes = table.get('table', {}).get('close', [])

                        rows = []
                        for i in range(len(time_list)):
                            rows.append({
                                'date': time_list[i],
                                'value': closes[i] if i < len(closes) else None
                            })
                        data[name] = rows[-days:]
                except Exception as e:
                    print(f"⚠️ {name} 获取失败: {e}")

        return data

    # ========================================
    # 预警检测
    # ========================================

    def check_alerts(self, realtime: Dict[str, dict]) -> List[dict]:
        """检查预警"""
        alerts = []
        now_str = datetime.now().strftime('%H:%M:%S')

        for code, current in realtime.items():
            name, _ = NAME_MAP.get(code, (code, code))
            latest = current.get('latest', 0)
            change_ratio = current.get('changeRatio', 0)

            # 日内涨跌幅
            if abs(change_ratio) >= PRICE_ALERT_THRESHOLD:
                direction = "上涨" if change_ratio > 0 else "下跌"
                alerts.append({
                    'time': now_str,
                    'name': name,
                    'type': 'price',
                    'message': f"日内{direction} {abs(change_ratio):.2f}%",
                    'level': 'high' if abs(change_ratio) >= PRICE_ALERT_THRESHOLD * 1.5 else 'medium'
                })

            # 短期急变
            if self.last_realtime and code in self.last_realtime:
                last_price = self.last_realtime[code].get('latest', 0)
                if last_price and latest:
                    short_pct = (latest - last_price) / last_price * 100
                    if abs(short_pct) >= 0.3:
                        direction = "急涨" if short_pct > 0 else "急跌"
                        alerts.append({
                            'time': now_str,
                            'name': name,
                            'type': 'short',
                            'message': f"{direction} {abs(short_pct):.2f}%",
                            'level': 'high'
                        })

        return alerts

    # ========================================
    # HTML生成
    # ========================================

    def generate_html(self, realtime: Dict[str, dict]) -> str:
        """生成完整HTML"""
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # ---- 实时卡片 ----
        cards_html = ""
        for code, d in realtime.items():
            name, short = NAME_MAP.get(code, (code, code))
            latest = d.get('latest', 0)
            open_p = d.get('open', 0)
            high = d.get('high', 0)
            low = d.get('low', 0)
            change_ratio = d.get('changeRatio', 0)
            oi = d.get('openInterest', 0)
            volume = d.get('volume', 0)
            amount = d.get('amount', 0)

            day_change = latest - open_p if open_p else 0
            up_down = 'up' if change_ratio >= 0 else 'down'
            arrow = '▲' if change_ratio >= 0 else '▼'
            amplitude = ((high - low) / open_p * 100) if open_p else 0

            cards_html += f"""
        <div class="realtime-card {up_down}">
            <div class="card-header">
                <div>
                    <div class="card-name">{name}</div>
                    <div class="card-code">{code}</div>
                </div>
                <div class="card-price-wrap">
                    <div class="price">{latest:,.0f}</div>
                    <div class="change {up_down}">{arrow} {day_change:+,.0f} ({change_ratio:+.2f}%)</div>
                </div>
            </div>
            <div class="card-metrics">
                <div class="metric"><span class="label">开盘</span><span class="value">{open_p:,.0f}</span></div>
                <div class="metric"><span class="label">最高</span><span class="value up">{high:,.0f}</span></div>
                <div class="metric"><span class="label">最低</span><span class="value down">{low:,.0f}</span></div>
                <div class="metric"><span class="label">振幅</span><span class="value">{amplitude:.2f}%</span></div>
                <div class="metric"><span class="label">成交</span><span class="value">{volume:,.0f}</span></div>
                <div class="metric"><span class="label">金额</span><span class="value">{amount/1e8:.1f}亿</span></div>
                <div class="metric"><span class="label">持仓</span><span class="value">{oi:,.0f}</span></div>
                <div class="metric"><span class="label">时间</span><span class="value" style="font-size:10px">{d.get('time','')[-8:]}</span></div>
            </div>
        </div>
"""

        # ---- 预警列表 ----
        alerts_html = ""
        recent_alerts = self.alerts_history[-8:] if self.alerts_history else []
        if recent_alerts:
            for a in reversed(recent_alerts):
                level = a.get('level', 'medium')
                alerts_html += f"""
            <div class="alert-item {level}">
                <span class="alert-time">{a['time']}</span>
                <span class="alert-name">{a['name']}</span>
                <span class="alert-msg">{a['message']}</span>
            </div>"""
        else:
            alerts_html = '<div class="no-alerts">暂无预警</div>'

        # ---- 历史走势图数据 ----
        chart_data_js = ""
        for code, rows in self.history_data.items():
            if not rows:
                continue
            name, short = NAME_MAP.get(code, (code, code))

            dates = [r['date'] for r in rows]
            closes = [r.get('close', 0) or 0 for r in rows]
            volumes = [r.get('volume', 0) or 0 for r in rows]

            # MA计算
            ma5, ma10, ma20 = [], [], []
            for i in range(len(closes)):
                ma5.append(round(sum(closes[max(0,i-4):i+1])/min(5,i+1), 1))
                ma10.append(round(sum(closes[max(0,i-9):i+1])/min(10,i+1), 1) if i >= 4 else None)
                ma20.append(round(sum(closes[max(0,i-19):i+1])/min(20,i+1), 1) if i >= 9 else None)

            # 成交量颜色
            vol_colors = []
            for i in range(len(closes)):
                if i == 0:
                    vol_colors.append('rgba(100,116,139,0.4)')
                elif closes[i] >= closes[i-1]:
                    vol_colors.append('rgba(34,197,94,0.4)')
                else:
                    vol_colors.append('rgba(239,68,68,0.4)')

            chart_data_js += f"""
chartData['{short}'] = {{
    name: '{name}',
    dates: {json.dumps(dates)},
    closes: {json.dumps(closes)},
    volumes: {json.dumps(volumes)},
    ma5: {json.dumps(ma5)},
    ma10: {json.dumps(ma10)},
    ma20: {json.dumps(ma20)},
    volColors: {json.dumps(vol_colors)}
}};
"""

        # ---- 宏观指标数据 ----
        macro_js = ""
        for name, rows in self.macro_data.items():
            if not rows:
                continue
            safe_id = name.replace(' ', '_')
            dates = [r['date'] for r in rows]
            values = [r.get('value', 0) or 0 for r in rows]

            macro_js += f"""
macroData['{safe_id}'] = {{
    name: '{name}',
    dates: {json.dumps(dates)},
    values: {json.dumps(values)}
}};
"""

        # ---- 数据表 ----
        tables_html = ""
        for code, rows in self.history_data.items():
            if not rows:
                continue
            name, _ = NAME_MAP.get(code, (code, code))
            recent = rows[-10:]

            tables_html += f"""
        <div class="data-table">
            <h4>{name} 近期数据</h4>
            <table>
                <thead>
                    <tr><th>日期</th><th>开盘</th><th>最高</th><th>最低</th><th>收盘</th><th>涨跌</th><th>成交量</th><th>持仓</th></tr>
                </thead>
                <tbody>
"""
            for r in reversed(recent):
                close = r.get('close', 0) or 0
                chg_ratio = r.get('changeRatio', 0) or 0
                cls = 'up' if chg_ratio >= 0 else 'down'
                tables_html += f"""
                    <tr>
                        <td>{r['date']}</td>
                        <td>{r.get('open',0) or 0:,.0f}</td>
                        <td>{r.get('high',0) or 0:,.0f}</td>
                        <td>{r.get('low',0) or 0:,.0f}</td>
                        <td class="{cls}">{close:,.0f}</td>
                        <td class="{cls}">{chg_ratio:+.2f}%</td>
                        <td>{r.get('volume',0) or 0:,.0f}</td>
                        <td>{r.get('openInterest',0) or 0:,.0f}</td>
                    </tr>"""
            tables_html += """
                </tbody>
            </table>
        </div>
"""

        # ---- 完整HTML ----
        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="refresh" content="{REFRESH_INTERVAL}">
<title>镍/不锈钢研究看板</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Noto+Sans+SC:wght@400;500;700;900&display=swap" rel="stylesheet">
<style>
:root {{
    --bg: #0a0e17;
    --card: #111827;
    --card-hover: #1a2235;
    --border: #1e293b;
    --text: #e2e8f0;
    --text-secondary: #94a3b8;
    --text-muted: #64748b;
    --green: #22c55e;
    --red: #ef4444;
    --amber: #f59e0b;
    --blue: #38bdf8;
    --purple: #a78bfa;
}}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{
    font-family: 'Noto Sans SC', sans-serif;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
}}
.container {{ max-width: 1400px; margin: 0 auto; padding: 24px; }}

/* Header */
header {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 24px;
    padding-bottom: 16px;
    border-bottom: 1px solid var(--border);
}}
h1 {{
    font-size: 26px;
    font-weight: 900;
    background: linear-gradient(135deg, #e2e8f0, #38bdf8);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}}
.live-badge {{
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 11px;
    font-weight: 500;
    color: var(--green);
    background: rgba(34,197,94,0.1);
    padding: 4px 12px;
    border-radius: 20px;
    margin-left: 12px;
}}
.live-badge .dot {{
    width: 8px; height: 8px;
    background: var(--green);
    border-radius: 50%;
    animation: pulse 1.5s infinite;
}}
@keyframes pulse {{
    0%,100% {{ opacity:1; transform:scale(1); }}
    50% {{ opacity:0.4; transform:scale(0.8); }}
}}
.update-time {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    color: var(--text-muted);
}}

/* Realtime Cards */
.realtime-section {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
    gap: 20px;
    margin-bottom: 24px;
}}
.realtime-card {{
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 20px;
    position: relative;
    overflow: hidden;
}}
.realtime-card::before {{
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 4px;
}}
.realtime-card.up::before {{ background: linear-gradient(90deg, var(--green), transparent); }}
.realtime-card.down::before {{ background: linear-gradient(90deg, var(--red), transparent); }}
.card-header {{
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 16px;
}}
.card-name {{ font-size: 20px; font-weight: 700; }}
.card-code {{ font-family: 'JetBrains Mono', monospace; font-size: 11px; color: var(--text-muted); margin-top: 2px; }}
.card-price-wrap {{ text-align: right; }}
.price {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 36px;
    font-weight: 600;
    letter-spacing: -1px;
}}
.change {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 14px;
    margin-top: 2px;
}}
.change.up {{ color: var(--green); }}
.change.down {{ color: var(--red); }}
.card-metrics {{
    display: grid;
    grid-template-columns: repeat(8, 1fr);
    gap: 8px;
    padding-top: 12px;
    border-top: 1px solid var(--border);
}}
.metric {{ text-align: center; }}
.metric .label {{ font-size: 10px; color: var(--text-muted); margin-bottom: 2px; }}
.metric .value {{ font-family: 'JetBrains Mono', monospace; font-size: 12px; }}
.metric .value.up {{ color: var(--green); }}
.metric .value.down {{ color: var(--red); }}

/* Alerts */
.alerts-section {{
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 16px;
    margin-bottom: 24px;
}}
.alerts-section h3 {{
    font-size: 13px;
    font-weight: 600;
    color: var(--text-secondary);
    margin-bottom: 10px;
}}
.alert-item {{
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 6px 10px;
    border-radius: 6px;
    font-size: 12px;
    margin-bottom: 4px;
}}
.alert-item.high {{ background: rgba(239,68,68,0.1); border-left: 3px solid var(--red); }}
.alert-item.medium {{ background: rgba(245,158,11,0.1); border-left: 3px solid var(--amber); }}
.alert-time {{ font-family: 'JetBrains Mono', monospace; font-size: 10px; color: var(--text-muted); }}
.alert-name {{ font-weight: 600; min-width: 70px; }}
.alert-msg {{ color: var(--text-secondary); }}
.no-alerts {{ color: var(--text-muted); font-size: 12px; text-align: center; padding: 10px; }}

/* Charts */
.charts-section {{ margin-bottom: 24px; }}
.section-title {{
    font-size: 14px;
    font-weight: 600;
    color: var(--text-secondary);
    margin-bottom: 16px;
    display: flex;
    align-items: center;
    gap: 8px;
}}
.section-title::before {{
    content: '';
    width: 3px; height: 14px;
    background: var(--blue);
    border-radius: 2px;
}}
.charts-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(500px, 1fr));
    gap: 20px;
}}
.chart-box {{
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 16px;
}}
.chart-box h4 {{
    font-size: 13px;
    font-weight: 500;
    color: var(--text-secondary);
    margin-bottom: 12px;
}}
.chart-container {{ position: relative; height: 280px; }}

/* Macro */
.macro-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
    gap: 16px;
    margin-top: 16px;
}}
.macro-box {{
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 16px;
}}
.macro-box h4 {{ font-size: 13px; color: var(--text-secondary); margin-bottom: 8px; }}
.macro-chart {{ height: 150px; }}

/* Tables */
.tables-section {{ margin-bottom: 24px; }}
.data-table {{
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 16px;
    margin-bottom: 16px;
    overflow-x: auto;
}}
.data-table h4 {{
    font-size: 13px;
    color: var(--text-secondary);
    margin-bottom: 12px;
}}
table {{ width: 100%; border-collapse: collapse; font-family: 'JetBrains Mono', monospace; font-size: 11px; }}
th {{ text-align: right; padding: 6px 10px; font-weight: 600; color: var(--text-muted); border-bottom: 1px solid var(--border); font-size: 10px; }}
th:first-child {{ text-align: left; }}
td {{ text-align: right; padding: 6px 10px; color: var(--text-secondary); border-bottom: 1px solid rgba(30,41,59,0.5); }}
td:first-child {{ text-align: left; color: var(--text-muted); }}
td.up {{ color: var(--green); }}
td.down {{ color: var(--red); }}
tr:hover td {{ background: rgba(56,189,248,0.03); }}

/* Footer */
footer {{
    text-align: center;
    padding: 20px 0;
    color: var(--text-muted);
    font-size: 11px;
    border-top: 1px solid var(--border);
}}

/* Countdown */
.countdown {{
    position: fixed;
    bottom: 16px; right: 16px;
    background: var(--card);
    border: 1px solid var(--border);
    padding: 6px 14px;
    border-radius: 20px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    color: var(--text-muted);
}}

@media (max-width: 768px) {{
    .realtime-section {{ grid-template-columns: 1fr; }}
    .card-metrics {{ grid-template-columns: repeat(4, 1fr); }}
    .charts-grid {{ grid-template-columns: 1fr; }}
}}
</style>
</head>
<body>
<div class="container">

<header>
    <h1>镍 · 不锈钢 <span class="live-badge"><span class="dot"></span>LIVE</span></h1>
    <div class="update-time">{now_str}</div>
</header>

<div class="realtime-section">
{cards_html}
</div>

<div class="alerts-section">
    <h3>⚡ 实时预警</h3>
    {alerts_html}
</div>

<div class="charts-section">
    <div class="section-title">历史走势 · 近60个交易日</div>
    <div class="charts-grid">
        <div class="chart-box">
            <h4>沪镍主力</h4>
            <div class="chart-container"><canvas id="chart_ni"></canvas></div>
        </div>
        <div class="chart-box">
            <h4>不锈钢主力</h4>
            <div class="chart-container"><canvas id="chart_ss"></canvas></div>
        </div>
    </div>

    <div class="section-title" style="margin-top:24px">宏观指标</div>
    <div class="macro-grid">
        <div class="macro-box">
            <h4>沪镍连续</h4>
            <div class="macro-chart"><canvas id="macro_沪镍连续"></canvas></div>
        </div>
    </div>
</div>

<div class="tables-section">
    <div class="section-title">数据明细</div>
    {tables_html}
</div>

<footer>
    镍/不锈钢研究系统 · 每{REFRESH_INTERVAL}秒自动刷新 · 数据来源: 同花顺iFinD
</footer>

</div>

<div class="countdown" id="countdown">{REFRESH_INTERVAL}s</div>

<script>
// 图表默认样式
Chart.defaults.color = '#64748b';
Chart.defaults.borderColor = 'rgba(30,41,59,0.5)';
Chart.defaults.font.family = "'JetBrains Mono', monospace";
Chart.defaults.font.size = 10;

// 数据
const chartData = {{}};
const macroData = {{}};

{chart_data_js}
{macro_js}

// 绘制主图
function drawMainChart(canvasId, data) {{
    if (!data) return;
    const ctx = document.getElementById(canvasId).getContext('2d');
    new Chart(ctx, {{
        data: {{
            labels: data.dates,
            datasets: [
                {{
                    type: 'line',
                    label: '收盘价',
                    data: data.closes,
                    borderColor: '#38bdf8',
                    backgroundColor: 'rgba(56,189,248,0.05)',
                    borderWidth: 2,
                    pointRadius: 0,
                    fill: true,
                    tension: 0.1,
                    yAxisID: 'y'
                }},
                {{
                    type: 'line',
                    label: 'MA5',
                    data: data.ma5,
                    borderColor: '#f59e0b',
                    borderWidth: 1,
                    pointRadius: 0,
                    tension: 0.3,
                    yAxisID: 'y'
                }},
                {{
                    type: 'line',
                    label: 'MA10',
                    data: data.ma10,
                    borderColor: '#a78bfa',
                    borderWidth: 1,
                    pointRadius: 0,
                    tension: 0.3,
                    yAxisID: 'y'
                }},
                {{
                    type: 'line',
                    label: 'MA20',
                    data: data.ma20,
                    borderColor: '#f472b6',
                    borderWidth: 1,
                    borderDash: [4,2],
                    pointRadius: 0,
                    tension: 0.3,
                    yAxisID: 'y'
                }},
                {{
                    type: 'bar',
                    label: '成交量',
                    data: data.volumes,
                    backgroundColor: data.volColors,
                    yAxisID: 'y1',
                    barPercentage: 0.6
                }}
            ]
        }},
        options: {{
            responsive: true,
            maintainAspectRatio: false,
            interaction: {{ mode: 'index', intersect: false }},
            plugins: {{
                legend: {{ display: true, position: 'top', labels: {{ usePointStyle: true, pointStyle: 'line', padding: 12, font: {{ size: 10 }} }} }}
            }},
            scales: {{
                x: {{ ticks: {{ maxTicksLimit: 8 }}, grid: {{ display: false }} }},
                y: {{ position: 'left', grid: {{ color: 'rgba(30,41,59,0.3)' }}, ticks: {{ callback: v => v.toLocaleString() }} }},
                y1: {{ position: 'right', grid: {{ display: false }}, ticks: {{ callback: v => (v/10000).toFixed(0)+'万' }} }}
            }}
        }}
    }});
}}

// 绘制宏观图
function drawMacroChart(canvasId, data) {{
    if (!data) return;
    const ctx = document.getElementById(canvasId).getContext('2d');
    new Chart(ctx, {{
        type: 'line',
        data: {{
            labels: data.dates,
            datasets: [{{
                label: data.name,
                data: data.values,
                borderColor: '#a78bfa',
                backgroundColor: 'rgba(167,139,250,0.1)',
                borderWidth: 2,
                pointRadius: 0,
                fill: true,
                tension: 0.2
            }}]
        }},
        options: {{
            responsive: true,
            maintainAspectRatio: false,
            plugins: {{ legend: {{ display: false }} }},
            scales: {{
                x: {{ ticks: {{ maxTicksLimit: 5 }}, grid: {{ display: false }} }},
                y: {{ ticks: {{ callback: v => v.toLocaleString() }}, grid: {{ color: 'rgba(30,41,59,0.3)' }} }}
            }}
        }}
    }});
}}

// 初始化图表
if (chartData['ni']) drawMainChart('chart_ni', chartData['ni']);
if (chartData['ss']) drawMainChart('chart_ss', chartData['ss']);
if (macroData['沪镍连续']) drawMacroChart('macro_沪镍连续', macroData['沪镍连续']);

// 倒计时
let sec = {REFRESH_INTERVAL};
setInterval(() => {{
    sec--;
    if (sec <= 0) sec = {REFRESH_INTERVAL};
    document.getElementById('countdown').textContent = sec + 's';
}}, 1000);
</script>
</body>
</html>"""
        return html

    # ========================================
    # 运行
    # ========================================

    def update(self) -> bool:
        """更新数据和HTML"""
        # 获取实时数据
        realtime = self.fetch_realtime()
        if not realtime:
            return False

        # 检查预警
        alerts = self.check_alerts(realtime)
        if alerts:
            self.alerts_history.extend(alerts)
            for a in alerts:
                print(f"  🚨 {a['name']} {a['message']}")

        # 更新 last_realtime
        self.last_realtime = realtime

        # 生成HTML
        html = self.generate_html(realtime)
        with open(self.output_path, 'w', encoding='utf-8') as f:
            f.write(html)

        return True

    def run(self):
        """启动看板"""
        print("=" * 60)
        print("🚀 启动统一研究看板")
        print("=" * 60)

        # 首次加载历史和宏观数据
        print("📊 加载历史数据...")
        self.history_data = self.fetch_history(days=60)
        print(f"  ✅ 加载 {len(self.history_data)} 个品种")

        print("📊 加载宏观数据...")
        self.macro_data = self.fetch_macro(days=90)
        print(f"  ✅ 加载 {len(self.macro_data)} 个指标")

        # 首次更新
        print("📊 获取实时行情...")
        if self.update():
            print(f"  ✅ 看板已生成: {self.output_path}")
            webbrowser.open(f"file://{self.output_path}")
        else:
            print("  ❌ 获取失败")
            return

        print(f"\n✅ 看板运行中，每{REFRESH_INTERVAL}秒刷新")
        print("   按 Ctrl+C 停止\n")

        try:
            while True:
                time.sleep(REFRESH_INTERVAL)
                now = datetime.now().strftime('%H:%M:%S')
                if self.update():
                    print(f"[{now}] ✅ 已刷新")
                else:
                    print(f"[{now}] ⚠️ 刷新失败")
        except KeyboardInterrupt:
            print("\n\n👋 看板已停止")


def main():
    if not IFIND_REFRESH_TOKEN or IFIND_REFRESH_TOKEN == "在这里填写你的refresh_token":
        print("❌ 请先配置 refresh_token")
        return

    dashboard = UnifiedDashboard(IFIND_REFRESH_TOKEN)
    dashboard.run()


if __name__ == "__main__":
    main()
