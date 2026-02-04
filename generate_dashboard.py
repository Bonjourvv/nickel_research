#!/usr/bin/env python3
"""
============================================================
生成网页看板 HTML
============================================================

读取 data/raw/ 下的 CSV 数据，生成一个可以浏览器直接打开的 HTML 看板。

使用方法：
    cd nickel_research
    python3 generate_dashboard.py

生成的文件：dashboard.html（双击即可打开）
============================================================
"""

import sys
import os
import csv
import json
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.settings import (
    IFIND_REFRESH_TOKEN, WATCH_LIST, RAW_DIR,
    NICKEL_MAIN, SS_MAIN, PRICE_ALERT_THRESHOLD, OI_ALERT_THRESHOLD
)
from src.data_fetcher.ths_client import TonghuashunClient
from src.macro.macro_indicators import MacroDataFetcher, EDB_INDICATORS, FUTURES_INDICATORS


def fetch_fresh_data():
    """拉取最新数据并保存CSV，返回数据字典"""
    if not IFIND_REFRESH_TOKEN or IFIND_REFRESH_TOKEN == "在这里填写你的refresh_token":
        print("❌ 请先配置 refresh_token")
        return None

    client = TonghuashunClient(IFIND_REFRESH_TOKEN)
    today = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d")
    codes = ",".join(WATCH_LIST)

    print(f"📡 拉取数据: {codes}, {start} ~ {today}")
    result = client.get_history_quotes(
        codes=codes,
        indicators="open,high,low,close,volume,amount,openInterest,changeRatio",
        start_date=start,
        end_date=today
    )

    # 保存CSV
    os.makedirs(RAW_DIR, exist_ok=True)
    all_data = {}

    if 'tables' in result:
        for table in result['tables']:
            code = table.get('thscode', 'unknown')
            time_list = table.get('time', [])
            data = table.get('table', {})

            rows = []
            for i in range(len(time_list)):
                row = {'date': time_list[i]}
                for ind in data:
                    vals = data[ind]
                    row[ind] = vals[i] if i < len(vals) else None
                rows.append(row)

            all_data[code] = rows

            # 保存CSV
            safe_code = code.replace('.', '_')
            filepath = os.path.join(RAW_DIR, f"{safe_code}_daily.csv")
            if rows:
                fieldnames = list(rows[0].keys())
                with open(filepath, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(rows)
                print(f"  💾 {filepath} ({len(rows)} 条)")

    return all_data


def load_csv_data():
    """从已有CSV加载数据"""
    all_data = {}
    for code in WATCH_LIST:
        safe_code = code.replace('.', '_').upper()
        filepath = os.path.join(RAW_DIR, f"{safe_code}_daily.csv")
        if not os.path.exists(filepath):
            # 尝试小写
            safe_code_lower = code.replace('.', '_')
            filepath = os.path.join(RAW_DIR, f"{safe_code_lower}_daily.csv")

        if os.path.exists(filepath):
            rows = []
            with open(filepath, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    rows.append(row)
            all_data[code.upper()] = rows
    return all_data


def detect_alerts(rows):
    """检测异常信号"""
    alerts = []
    if len(rows) < 2:
        return alerts

    latest = rows[-1]
    prev = rows[-2]

    try:
        close_now = float(latest.get('close', 0))
        close_prev = float(prev.get('close', 0))
        if close_prev > 0:
            pct = (close_now - close_prev) / close_prev * 100
            if abs(pct) >= PRICE_ALERT_THRESHOLD:
                alerts.append({
                    'type': 'price',
                    'direction': '上涨' if pct > 0 else '下跌',
                    'value': f"{abs(pct):.2f}%",
                    'detail': f"{close_now:.0f} ← {close_prev:.0f}"
                })
    except (ValueError, TypeError):
        pass

    try:
        oi_now = float(latest.get('openInterest', 0))
        oi_prev = float(prev.get('openInterest', 0))
        if oi_prev > 0:
            pct = (oi_now - oi_prev) / oi_prev * 100
            if abs(pct) >= OI_ALERT_THRESHOLD:
                alerts.append({
                    'type': 'oi',
                    'direction': '增仓' if pct > 0 else '减仓',
                    'value': f"{abs(pct):.2f}%",
                    'detail': f"{oi_now:.0f} ← {oi_prev:.0f}"
                })
    except (ValueError, TypeError):
        pass

    return alerts


def generate_html(all_data: dict, macro_data: dict = None) -> str:
    """生成完整HTML"""

    if macro_data is None:
        macro_data = {}

    name_map = {
        'NIZL.SHF': ('沪镍主力', 'ni'),
        'SSZL.SHF': ('不锈钢主力', 'ss'),
    }

    # 准备图表数据
    chart_datasets = {}
    summary_cards = []
    alert_items = []

    for code, rows in all_data.items():
        code_upper = code.upper()
        name, short = name_map.get(code_upper, (code, code))

        if not rows:
            continue

        # 图表数据：最近60个交易日
        recent = rows[-60:] if len(rows) > 60 else rows

        dates = [r['date'] for r in recent]
        closes = []
        volumes = []
        ois = []
        for r in recent:
            try:
                closes.append(float(r.get('close', 0)))
            except (ValueError, TypeError):
                closes.append(0)
            try:
                volumes.append(float(r.get('volume', 0)))
            except (ValueError, TypeError):
                volumes.append(0)
            try:
                ois.append(float(r.get('openInterest', 0)))
            except (ValueError, TypeError):
                ois.append(0)

        chart_datasets[short] = {
            'name': name,
            'code': code_upper,
            'dates': dates,
            'closes': closes,
            'volumes': volumes,
            'ois': ois,
        }

        # 摘要卡片
        latest = rows[-1]
        prev = rows[-2] if len(rows) >= 2 else rows[-1]

        try:
            close_now = float(latest.get('close', 0))
            close_prev = float(prev.get('close', 0))
            change = close_now - close_prev
            change_pct = (change / close_prev * 100) if close_prev else 0
        except (ValueError, TypeError):
            close_now = change = change_pct = 0

        try:
            vol = float(latest.get('volume', 0))
        except (ValueError, TypeError):
            vol = 0

        try:
            oi = float(latest.get('openInterest', 0))
            oi_prev = float(prev.get('openInterest', 0))
            oi_change = ((oi - oi_prev) / oi_prev * 100) if oi_prev else 0
        except (ValueError, TypeError):
            oi = oi_change = 0

        try:
            high = float(latest.get('high', 0))
            low = float(latest.get('low', 0))
        except (ValueError, TypeError):
            high = low = 0

        summary_cards.append({
            'name': name,
            'code': code_upper,
            'short': short,
            'date': latest.get('date', ''),
            'close': close_now,
            'change': change,
            'change_pct': change_pct,
            'high': high,
            'low': low,
            'volume': vol,
            'oi': oi,
            'oi_change': oi_change,
        })

        # 异常检测
        alerts = detect_alerts(rows)
        for a in alerts:
            alert_items.append({**a, 'name': name, 'code': code_upper, 'date': latest.get('date', '')})

    # 计算MA均线
    for short, ds in chart_datasets.items():
        closes = ds['closes']
        ma5 = []
        ma10 = []
        ma20 = []
        for i in range(len(closes)):
            ma5.append(round(sum(closes[max(0,i-4):i+1]) / min(5, i+1), 1) if i >= 0 else None)
            ma10.append(round(sum(closes[max(0,i-9):i+1]) / min(10, i+1), 1) if i >= 4 else None)
            ma20.append(round(sum(closes[max(0,i-19):i+1]) / min(20, i+1), 1) if i >= 9 else None)
        ds['ma5'] = ma5
        ds['ma10'] = ma10
        ds['ma20'] = ma20

    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>镍 · 不锈钢 研究看板</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@300;400;500;700;900&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
<style>
:root {{
  --bg-primary: #0a0e17;
  --bg-card: #111827;
  --bg-card-hover: #1a2235;
  --border: #1e293b;
  --text-primary: #e2e8f0;
  --text-secondary: #94a3b8;
  --text-muted: #64748b;
  --accent: #38bdf8;
  --accent-glow: rgba(56, 189, 248, 0.15);
  --green: #22c55e;
  --green-bg: rgba(34, 197, 94, 0.1);
  --red: #ef4444;
  --red-bg: rgba(239, 68, 68, 0.1);
  --amber: #f59e0b;
  --amber-bg: rgba(245, 158, 11, 0.1);
}}

* {{ margin: 0; padding: 0; box-sizing: border-box; }}

body {{
  font-family: 'Noto Sans SC', -apple-system, BlinkMacSystemFont, sans-serif;
  background: var(--bg-primary);
  color: var(--text-primary);
  min-height: 100vh;
  overflow-x: hidden;
}}

.noise-overlay {{
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.03'/%3E%3C/svg%3E");
  pointer-events: none;
  z-index: 0;
}}

.gradient-orb {{
  position: fixed;
  border-radius: 50%;
  filter: blur(80px);
  opacity: 0.07;
  pointer-events: none;
  z-index: 0;
}}
.gradient-orb.orb1 {{ width: 600px; height: 600px; background: #38bdf8; top: -200px; right: -100px; }}
.gradient-orb.orb2 {{ width: 400px; height: 400px; background: #818cf8; bottom: -100px; left: -50px; }}

.container {{
  max-width: 1400px;
  margin: 0 auto;
  padding: 32px 24px;
  position: relative;
  z-index: 1;
}}

/* ---- Header ---- */
header {{
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  margin-bottom: 40px;
  padding-bottom: 24px;
  border-bottom: 1px solid var(--border);
}}

header h1 {{
  font-size: 28px;
  font-weight: 900;
  letter-spacing: -0.5px;
  background: linear-gradient(135deg, #e2e8f0 0%, #38bdf8 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}}

header h1 span {{
  font-weight: 300;
  opacity: 0.6;
  font-size: 18px;
  margin-left: 8px;
}}

.update-time {{
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  color: var(--text-muted);
  display: flex;
  align-items: center;
  gap: 6px;
}}

.update-time .dot {{
  width: 6px;
  height: 6px;
  background: var(--green);
  border-radius: 50%;
  animation: pulse 2s infinite;
}}

@keyframes pulse {{
  0%, 100% {{ opacity: 1; }}
  50% {{ opacity: 0.3; }}
}}

/* ---- Alert Banner ---- */
.alerts-banner {{
  background: linear-gradient(135deg, rgba(239, 68, 68, 0.08) 0%, rgba(245, 158, 11, 0.06) 100%);
  border: 1px solid rgba(239, 68, 68, 0.2);
  border-radius: 12px;
  padding: 16px 20px;
  margin-bottom: 32px;
  animation: slideDown 0.5s ease;
}}

@keyframes slideDown {{
  from {{ opacity: 0; transform: translateY(-10px); }}
  to {{ opacity: 1; transform: translateY(0); }}
}}

.alerts-banner h3 {{
  font-size: 13px;
  font-weight: 700;
  color: var(--red);
  text-transform: uppercase;
  letter-spacing: 1px;
  margin-bottom: 10px;
  display: flex;
  align-items: center;
  gap: 6px;
}}

.alert-row {{
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 6px 0;
  font-size: 14px;
  color: var(--text-secondary);
}}

.alert-row + .alert-row {{
  border-top: 1px solid rgba(239, 68, 68, 0.08);
  padding-top: 8px;
  margin-top: 2px;
}}

.alert-tag {{
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 4px;
  white-space: nowrap;
}}

.alert-tag.price {{ background: var(--red-bg); color: var(--red); }}
.alert-tag.oi {{ background: var(--amber-bg); color: var(--amber); }}

/* ---- Summary Cards ---- */
.cards-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(420px, 1fr));
  gap: 20px;
  margin-bottom: 36px;
}}

.summary-card {{
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 24px;
  transition: all 0.25s ease;
  position: relative;
  overflow: hidden;
}}

.summary-card::before {{
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 3px;
  border-radius: 14px 14px 0 0;
}}

.summary-card.up::before {{ background: linear-gradient(90deg, var(--green), transparent); }}
.summary-card.down::before {{ background: linear-gradient(90deg, var(--red), transparent); }}

.summary-card:hover {{
  border-color: var(--accent);
  box-shadow: 0 0 30px var(--accent-glow);
  transform: translateY(-2px);
}}

.card-header {{
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 20px;
}}

.card-name {{
  font-size: 20px;
  font-weight: 700;
}}

.card-code {{
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 2px;
}}

.card-price {{
  text-align: right;
}}

.card-price .price {{
  font-family: 'JetBrains Mono', monospace;
  font-size: 32px;
  font-weight: 600;
  letter-spacing: -1px;
}}

.card-price .change {{
  font-family: 'JetBrains Mono', monospace;
  font-size: 14px;
  font-weight: 600;
  margin-top: 2px;
}}

.card-price .change.up {{ color: var(--green); }}
.card-price .change.down {{ color: var(--red); }}

.card-metrics {{
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
  color: var(--text-secondary);
}}

.metric .sub {{
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  margin-top: 1px;
}}

.metric .sub.up {{ color: var(--green); }}
.metric .sub.down {{ color: var(--red); }}

/* ---- Charts Section ---- */
.charts-section {{
  margin-bottom: 36px;
}}

.section-title {{
  font-size: 16px;
  font-weight: 700;
  color: var(--text-secondary);
  margin-bottom: 20px;
  display: flex;
  align-items: center;
  gap: 8px;
}}

.section-title::before {{
  content: '';
  width: 3px;
  height: 16px;
  background: var(--accent);
  border-radius: 2px;
}}

.chart-grid {{
  display: grid;
  grid-template-columns: 1fr;
  gap: 20px;
}}

.chart-box {{
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 20px;
}}

.chart-box h4 {{
  font-size: 14px;
  font-weight: 500;
  color: var(--text-secondary);
  margin-bottom: 16px;
}}

.chart-container {{
  position: relative;
  height: 320px;
}}

/* ---- Data Table ---- */
.table-box {{
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 20px;
  overflow-x: auto;
}}

.table-box h4 {{
  font-size: 14px;
  font-weight: 500;
  color: var(--text-secondary);
  margin-bottom: 16px;
}}

table {{
  width: 100%;
  border-collapse: collapse;
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
}}

th {{
  text-align: right;
  padding: 8px 12px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  font-size: 10px;
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
}}

th:first-child {{ text-align: left; }}

td {{
  text-align: right;
  padding: 8px 12px;
  color: var(--text-secondary);
  border-bottom: 1px solid rgba(30, 41, 59, 0.5);
  white-space: nowrap;
}}

td:first-child {{ text-align: left; color: var(--text-muted); }}

tr:hover td {{ background: rgba(56, 189, 248, 0.03); }}

.td-up {{ color: var(--green) !important; }}
.td-down {{ color: var(--red) !important; }}

/* ---- Footer ---- */
footer {{
  text-align: center;
  padding: 40px 0 20px;
  color: var(--text-muted);
  font-size: 12px;
  border-top: 1px solid var(--border);
  margin-top: 40px;
}}

/* ---- Responsive ---- */
@media (max-width: 768px) {{
  .cards-grid {{ grid-template-columns: 1fr; }}
  .card-metrics {{ grid-template-columns: repeat(2, 1fr); }}
  header {{ flex-direction: column; align-items: flex-start; gap: 8px; }}
  .card-price .price {{ font-size: 24px; }}
}}
</style>
</head>
<body>
<div class="noise-overlay"></div>
<div class="gradient-orb orb1"></div>
<div class="gradient-orb orb2"></div>

<div class="container">

<header>
  <div>
    <h1>镍 · 不锈钢<span>研究看板</span></h1>
  </div>
  <div class="update-time">
    <div class="dot"></div>
    更新于 {now_str}
  </div>
</header>
"""

    # Alert Banner
    if alert_items:
        html += '<div class="alerts-banner">\n'
        html += '  <h3>⚡ 异常信号</h3>\n'
        for a in alert_items:
            tag_class = 'price' if a['type'] == 'price' else 'oi'
            tag_label = '价格' if a['type'] == 'price' else '持仓'
            html += f'  <div class="alert-row">\n'
            html += f'    <span class="alert-tag {tag_class}">{tag_label}</span>\n'
            html += f'    <span><strong>{a["name"]}</strong> {a["direction"]} {a["value"]}</span>\n'
            html += f'    <span style="color:var(--text-muted);font-size:12px">{a["detail"]}</span>\n'
            html += f'    <span style="color:var(--text-muted);font-size:11px;margin-left:auto">{a["date"]}</span>\n'
            html += f'  </div>\n'
        html += '</div>\n'

    # Summary Cards
    html += '<div class="cards-grid">\n'
    for card in summary_cards:
        up_down = 'up' if card['change'] >= 0 else 'down'
        price_str = f"{card['close']:,.0f}"
        change_str = f"{card['change']:+,.0f}"
        pct_str = f"{card['change_pct']:+.2f}%"
        arrow = '▲' if card['change'] >= 0 else '▼'

        oi_direction = 'up' if card['oi_change'] >= 0 else 'down'
        oi_sign = '+' if card['oi_change'] >= 0 else ''

        html += f"""
  <div class="summary-card {up_down}">
    <div class="card-header">
      <div>
        <div class="card-name">{card['name']}</div>
        <div class="card-code">{card['code']}</div>
      </div>
      <div class="card-price">
        <div class="price">{price_str}</div>
        <div class="change {up_down}">{arrow} {change_str} ({pct_str})</div>
      </div>
    </div>
    <div class="card-metrics">
      <div class="metric">
        <div class="label">最高</div>
        <div class="value">{card['high']:,.0f}</div>
      </div>
      <div class="metric">
        <div class="label">最低</div>
        <div class="value">{card['low']:,.0f}</div>
      </div>
      <div class="metric">
        <div class="label">成交量</div>
        <div class="value">{card['volume']:,.0f}</div>
      </div>
      <div class="metric">
        <div class="label">持仓量</div>
        <div class="value">{card['oi']:,.0f}</div>
        <div class="sub {oi_direction}">{oi_sign}{card['oi_change']:.1f}%</div>
      </div>
    </div>
  </div>
"""
    html += '</div>\n'

    # Charts
    html += '<div class="charts-section">\n'
    html += '  <div class="section-title">价格走势 · 近60个交易日</div>\n'
    html += '  <div class="chart-grid">\n'

    for short, ds in chart_datasets.items():
        html += f"""
    <div class="chart-box">
      <h4>{ds['name']}（{ds['code']}）— 收盘价 / 均线 / 成交量</h4>
      <div class="chart-container">
        <canvas id="chart_{short}"></canvas>
      </div>
    </div>
"""
    html += '  </div>\n</div>\n'

    # Data Table - 最近15个交易日
    for short, ds in chart_datasets.items():
        recent_n = 15
        html += f'<div class="table-box" style="margin-bottom:20px">\n'
        html += f'  <h4>{ds["name"]} 近期行情数据</h4>\n'
        html += '  <table>\n'
        html += '    <thead><tr>'
        html += '<th>日期</th><th>开盘</th><th>最高</th><th>最低</th><th>收盘</th><th>涨跌</th><th>成交量</th><th>持仓量</th>'
        html += '</tr></thead>\n'
        html += '    <tbody>\n'

        closes = ds['closes']
        recent_start = max(0, len(closes) - recent_n)

        for i in range(len(closes) - 1, recent_start - 1, -1):
            date = ds['dates'][i]
            c = closes[i]
            prev_c = closes[i-1] if i > 0 else c
            chg = c - prev_c
            chg_pct = (chg / prev_c * 100) if prev_c else 0
            cls = 'td-up' if chg >= 0 else 'td-down'

            # 从all_data取完整行
            code_upper = ds['code']
            row_data = all_data.get(code_upper, [])
            if i < len(row_data):
                r = row_data[-(len(closes)-i)]
            else:
                r = {}

            o = float(r.get('open', 0)) if r.get('open') else 0
            h = float(r.get('high', 0)) if r.get('high') else 0
            l = float(r.get('low', 0)) if r.get('low') else 0
            v = float(r.get('volume', 0)) if r.get('volume') else 0
            oi = float(r.get('openInterest', 0)) if r.get('openInterest') else 0

            html += f'      <tr><td>{date}</td>'
            html += f'<td>{o:,.0f}</td><td>{h:,.0f}</td><td>{l:,.0f}</td>'
            html += f'<td class="{cls}">{c:,.0f}</td>'
            html += f'<td class="{cls}">{chg:+,.0f} ({chg_pct:+.1f}%)</td>'
            html += f'<td>{v:,.0f}</td><td>{oi:,.0f}</td></tr>\n'

        html += '    </tbody>\n  </table>\n</div>\n'

    # 宏观数据部分
    macro_html = generate_macro_html_section(macro_data)
    html += macro_html

    # Footer
    html += f"""
<footer>
  镍/不锈钢研究辅助系统 · 数据来源: 同花顺iFinD · 生成时间: {now_str}
</footer>

</div>

<script>
Chart.defaults.color = '#64748b';
Chart.defaults.borderColor = 'rgba(30, 41, 59, 0.5)';
Chart.defaults.font.family = "'JetBrains Mono', monospace";
Chart.defaults.font.size = 11;
"""

    # Chart.js 绘图
    for short, ds in chart_datasets.items():
        dates_json = json.dumps(ds['dates'])
        closes_json = json.dumps(ds['closes'])
        ma5_json = json.dumps(ds['ma5'])
        ma10_json = json.dumps(ds['ma10'])
        ma20_json = json.dumps(ds['ma20'])
        volumes_json = json.dumps(ds['volumes'])

        # 计算涨跌色
        vol_colors = []
        for i in range(len(ds['closes'])):
            if i == 0:
                vol_colors.append('rgba(100,116,139,0.4)')
            elif ds['closes'][i] >= ds['closes'][i-1]:
                vol_colors.append('rgba(34,197,94,0.35)')
            else:
                vol_colors.append('rgba(239,68,68,0.35)')
        vol_colors_json = json.dumps(vol_colors)

        html += f"""
(function() {{
  const ctx = document.getElementById('chart_{short}').getContext('2d');
  new Chart(ctx, {{
    data: {{
      labels: {dates_json},
      datasets: [
        {{
          type: 'line',
          label: '收盘价',
          data: {closes_json},
          borderColor: '#38bdf8',
          backgroundColor: 'rgba(56,189,248,0.05)',
          borderWidth: 2,
          pointRadius: 0,
          pointHoverRadius: 4,
          fill: true,
          tension: 0.1,
          yAxisID: 'y',
          order: 1
        }},
        {{
          type: 'line',
          label: 'MA5',
          data: {ma5_json},
          borderColor: '#f59e0b',
          borderWidth: 1,
          borderDash: [],
          pointRadius: 0,
          tension: 0.3,
          yAxisID: 'y',
          order: 2
        }},
        {{
          type: 'line',
          label: 'MA10',
          data: {ma10_json},
          borderColor: '#a78bfa',
          borderWidth: 1,
          pointRadius: 0,
          tension: 0.3,
          yAxisID: 'y',
          order: 3
        }},
        {{
          type: 'line',
          label: 'MA20',
          data: {ma20_json},
          borderColor: '#f472b6',
          borderWidth: 1,
          borderDash: [4,2],
          pointRadius: 0,
          tension: 0.3,
          yAxisID: 'y',
          order: 4
        }},
        {{
          type: 'bar',
          label: '成交量',
          data: {volumes_json},
          backgroundColor: {vol_colors_json},
          yAxisID: 'y1',
          order: 5,
          barPercentage: 0.7,
        }}
      ]
    }},
    options: {{
      responsive: true,
      maintainAspectRatio: false,
      interaction: {{
        mode: 'index',
        intersect: false,
      }},
      plugins: {{
        legend: {{
          position: 'top',
          labels: {{
            usePointStyle: true,
            pointStyle: 'line',
            padding: 16,
            font: {{ size: 11 }}
          }}
        }},
        tooltip: {{
          backgroundColor: 'rgba(17,24,39,0.95)',
          borderColor: '#1e293b',
          borderWidth: 1,
          padding: 12,
          titleFont: {{ size: 12 }},
          bodyFont: {{ size: 11 }},
          callbacks: {{
            label: function(ctx) {{
              let val = ctx.parsed.y;
              if (ctx.dataset.yAxisID === 'y1') return ctx.dataset.label + ': ' + val.toLocaleString();
              return ctx.dataset.label + ': ' + val.toLocaleString();
            }}
          }}
        }}
      }},
      scales: {{
        x: {{
          ticks: {{
            maxTicksLimit: 10,
            font: {{ size: 10 }}
          }},
          grid: {{ display: false }}
        }},
        y: {{
          position: 'left',
          grid: {{ color: 'rgba(30,41,59,0.3)' }},
          ticks: {{
            font: {{ size: 10 }},
            callback: function(v) {{ return v.toLocaleString(); }}
          }}
        }},
        y1: {{
          position: 'right',
          grid: {{ display: false }},
          ticks: {{
            font: {{ size: 10 }},
            callback: function(v) {{ return (v/10000).toFixed(0) + '万'; }}
          }}
        }}
      }}
    }}
  }});
}})();
"""

    # 宏观数据图表JS
    macro_js = generate_macro_chart_js(macro_data)
    html += macro_js

    html += """
</script>
</body>
</html>"""

    return html


def fetch_macro_data():
    """拉取宏观指标数据"""
    if not IFIND_REFRESH_TOKEN or IFIND_REFRESH_TOKEN == "在这里填写你的refresh_token":
        return {}

    try:
        fetcher = MacroDataFetcher(IFIND_REFRESH_TOKEN)
        macro_data = fetcher.fetch_all(days=180)
        fetcher.save_to_csv(macro_data)
        return macro_data
    except Exception as e:
        print(f"⚠️ 宏观数据拉取失败: {e}")
        return {}


def load_macro_csv():
    """从本地CSV加载宏观数据"""
    macro_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "macro")
    all_data = {}

    if not os.path.exists(macro_dir):
        return all_data

    for filename in os.listdir(macro_dir):
        if not filename.endswith('.csv'):
            continue

        name = filename.replace('.csv', '').replace('_', ' ')
        filepath = os.path.join(macro_dir, filename)

        rows = []
        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                for key in row:
                    if key != 'date' and row[key]:
                        try:
                            row[key] = float(row[key])
                        except ValueError:
                            pass
                rows.append(row)

        all_data[name] = rows

    return all_data


def generate_macro_html_section(macro_data: dict) -> str:
    """生成宏观数据HTML部分"""
    if not macro_data:
        return ""

    html = """
<div class="charts-section" style="margin-top:36px">
  <div class="section-title">宏观指标 · 近180个交易日</div>
  <div class="chart-grid">
"""

    # 为每个宏观指标生成图表区域
    for name, rows in macro_data.items():
        if not rows:
            continue

        safe_id = name.replace(' ', '_').replace('/', '_')

        # 判断是EDB指标还是期货指标
        if 'value' in rows[0]:
            # EDB指标（单值）
            latest = rows[-1]
            val = latest.get('value', 0)
            date = latest.get('date', '')

            # 计算变化
            if len(rows) >= 2:
                prev = rows[-2]
                prev_val = prev.get('value', 0)
                if prev_val:
                    chg = val - prev_val
                    pct = (chg / prev_val) * 100
                    chg_str = f"{chg:+,.2f} ({pct:+.2f}%)"
                    chg_class = "up" if chg >= 0 else "down"
                else:
                    chg_str = "N/A"
                    chg_class = ""
            else:
                chg_str = "N/A"
                chg_class = ""

            html += f"""
    <div class="chart-box">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:16px">
        <h4 style="margin:0">{name}</h4>
        <div style="text-align:right">
          <div style="font-family:'JetBrains Mono',monospace;font-size:24px;font-weight:600">{val:,.2f}</div>
          <div style="font-size:12px;color:var(--text-muted)">{date}</div>
          <div class="change {chg_class}" style="font-size:12px">{chg_str}</div>
        </div>
      </div>
      <div class="chart-container" style="height:200px">
        <canvas id="macro_{safe_id}"></canvas>
      </div>
    </div>
"""
        else:
            # 期货指标（OHLC）
            latest = rows[-1]
            close = latest.get('close', 0)
            date = latest.get('date', '')

            if len(rows) >= 2:
                prev = rows[-2]
                prev_close = prev.get('close', 0)
                if prev_close:
                    chg = close - prev_close
                    pct = (chg / prev_close) * 100
                    chg_str = f"{chg:+,.0f} ({pct:+.2f}%)"
                    chg_class = "up" if chg >= 0 else "down"
                else:
                    chg_str = "N/A"
                    chg_class = ""
            else:
                chg_str = "N/A"
                chg_class = ""

            html += f"""
    <div class="chart-box">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:16px">
        <h4 style="margin:0">{name}</h4>
        <div style="text-align:right">
          <div style="font-family:'JetBrains Mono',monospace;font-size:24px;font-weight:600">{close:,.0f}</div>
          <div style="font-size:12px;color:var(--text-muted)">{date}</div>
          <div class="change {chg_class}" style="font-size:12px">{chg_str}</div>
        </div>
      </div>
      <div class="chart-container" style="height:200px">
        <canvas id="macro_{safe_id}"></canvas>
      </div>
    </div>
"""

    html += "  </div>\n</div>\n"
    return html


def generate_macro_chart_js(macro_data: dict) -> str:
    """生成宏观指标的Chart.js代码"""
    if not macro_data:
        return ""

    js = ""

    for name, rows in macro_data.items():
        if not rows:
            continue

        safe_id = name.replace(' ', '_').replace('/', '_')

        # 取最近90个数据点
        recent = rows[-90:] if len(rows) > 90 else rows
        dates = [r['date'] for r in recent]

        if 'value' in recent[0]:
            # EDB指标
            values = [r.get('value', 0) for r in recent]
            dates_json = json.dumps(dates)
            values_json = json.dumps(values)

            js += f"""
(function() {{
  const ctx = document.getElementById('macro_{safe_id}').getContext('2d');
  new Chart(ctx, {{
    type: 'line',
    data: {{
      labels: {dates_json},
      datasets: [{{
        label: '{name}',
        data: {values_json},
        borderColor: '#38bdf8',
        backgroundColor: 'rgba(56,189,248,0.1)',
        borderWidth: 2,
        pointRadius: 0,
        pointHoverRadius: 3,
        fill: true,
        tension: 0.2
      }}]
    }},
    options: {{
      responsive: true,
      maintainAspectRatio: false,
      plugins: {{
        legend: {{ display: false }}
      }},
      scales: {{
        x: {{
          ticks: {{ maxTicksLimit: 6, font: {{ size: 10 }} }},
          grid: {{ display: false }}
        }},
        y: {{
          ticks: {{
            font: {{ size: 10 }},
            callback: function(v) {{ return v.toLocaleString(); }}
          }},
          grid: {{ color: 'rgba(30,41,59,0.3)' }}
        }}
      }}
    }}
  }});
}})();
"""
        else:
            # 期货指标
            closes = [r.get('close', 0) for r in recent]
            dates_json = json.dumps(dates)
            closes_json = json.dumps(closes)

            js += f"""
(function() {{
  const ctx = document.getElementById('macro_{safe_id}').getContext('2d');
  new Chart(ctx, {{
    type: 'line',
    data: {{
      labels: {dates_json},
      datasets: [{{
        label: '{name}',
        data: {closes_json},
        borderColor: '#a78bfa',
        backgroundColor: 'rgba(167,139,250,0.1)',
        borderWidth: 2,
        pointRadius: 0,
        pointHoverRadius: 3,
        fill: true,
        tension: 0.2
      }}]
    }},
    options: {{
      responsive: true,
      maintainAspectRatio: false,
      plugins: {{
        legend: {{ display: false }}
      }},
      scales: {{
        x: {{
          ticks: {{ maxTicksLimit: 6, font: {{ size: 10 }} }},
          grid: {{ display: false }}
        }},
        y: {{
          ticks: {{
            font: {{ size: 10 }},
            callback: function(v) {{ return v.toLocaleString(); }}
          }},
          grid: {{ color: 'rgba(30,41,59,0.3)' }}
        }}
      }}
    }}
  }});
}})();
"""

    return js


def main():
    print("=" * 60)
    print("📊 生成研究看板")
    print("=" * 60)

    # 尝试拉取最新数据
    all_data = fetch_fresh_data()

    if not all_data:
        print("\n尝试从本地CSV加载...")
        all_data = load_csv_data()

    if not all_data:
        print("❌ 没有可用数据，请先运行 run_daily.py")
        return

    # 拉取宏观数据
    print("\n📊 拉取宏观指标...")
    macro_data = fetch_macro_data()

    if not macro_data:
        print("尝试从本地加载宏观数据...")
        macro_data = load_macro_csv()

    print(f"\n📄 生成 HTML ...")
    html = generate_html(all_data, macro_data)

    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard.html")
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"✅ 看板已生成: {output_path}")
    print(f"   双击 dashboard.html 或在终端执行: open dashboard.html")


if __name__ == "__main__":
    main()
