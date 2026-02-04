"""
同花顺 iFinD HTTP API 客户端
===========================
封装所有与同花顺API的交互，其他模块只需要调用这个客户端。

HTTP API 调用流程：
1. 用 refresh_token 换取 access_token（7天有效）
2. 用 access_token 放在请求头里调数据
3. 所有接口都是 POST 请求，参数用 JSON 格式

API 基础地址: https://quantapi.51ifind.com/api/v1/
"""

import requests
import json
import time
import os
import logging
from datetime import datetime, timedelta

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


class TonghuashunClient:
    """同花顺 HTTP API 客户端"""

    BASE_URL = "https://quantapi.51ifind.com/api/v1"

    def __init__(self, refresh_token: str):
        """
        初始化客户端

        参数:
            refresh_token: 从超级命令工具获取的 refresh_token
        """
        self.refresh_token = refresh_token
        self.access_token = None
        self.token_expire_time = None

        # token 缓存文件（避免重复获取）
        self.token_cache_file = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "config",
            ".token_cache.json"
        )

        # 尝试从缓存加载 token
        self._load_token_cache()

    # ============================================================
    # Token 管理
    # ============================================================

    def _load_token_cache(self):
        """从本地缓存加载 access_token"""
        if os.path.exists(self.token_cache_file):
            try:
                with open(self.token_cache_file, 'r') as f:
                    cache = json.load(f)
                expire_time = datetime.fromisoformat(cache['expire_time'])
                if expire_time > datetime.now():
                    self.access_token = cache['access_token']
                    self.token_expire_time = expire_time
                    logger.info(f"从缓存加载 token，有效期至 {expire_time.strftime('%Y-%m-%d %H:%M')}")
                    return
            except Exception as e:
                logger.warning(f"读取 token 缓存失败: {e}")

    def _save_token_cache(self):
        """缓存 access_token 到本地"""
        try:
            cache = {
                'access_token': self.access_token,
                'expire_time': self.token_expire_time.isoformat()
            }
            os.makedirs(os.path.dirname(self.token_cache_file), exist_ok=True)
            with open(self.token_cache_file, 'w') as f:
                json.dump(cache, f)
        except Exception as e:
            logger.warning(f"保存 token 缓存失败: {e}")

    def get_access_token(self) -> str:
        """
        用 refresh_token 换取 access_token

        access_token 有效期7天，在有效期内重复调用会返回同一个 token。
        """
        # 如果已有有效 token，直接返回
        if self.access_token and self.token_expire_time and self.token_expire_time > datetime.now():
            return self.access_token

        url = f"{self.BASE_URL}/get_access_token"
        headers = {
            "Content-Type": "application/json",
            "refresh_token": self.refresh_token
        }

        logger.info("正在获取 access_token ...")
        try:
            resp = requests.post(url, headers=headers, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            if data.get('errorcode') != 0:
                error_msg = data.get('errmsg', '未知错误')
                logger.error(f"获取 token 失败: {error_msg}")
                raise Exception(f"获取 access_token 失败: {error_msg}")

            self.access_token = data['data']['access_token']
            # token 有效期7天，但我们保守设置为6天
            self.token_expire_time = datetime.now() + timedelta(days=6)

            logger.info(f"获取 access_token 成功!")
            self._save_token_cache()

            return self.access_token

        except requests.RequestException as e:
            logger.error(f"网络请求失败: {e}")
            raise

    def _get_headers(self) -> dict:
        """获取带 token 的请求头"""
        token = self.get_access_token()
        return {
            "Content-Type": "application/json",
            "access_token": token
        }

    def _post(self, endpoint: str, params: dict) -> dict:
        """
        发送 POST 请求到同花顺 API

        参数:
            endpoint: API 端点，如 "cmd_history_quotation"
            params: 请求体参数（字典）
        返回:
            API 返回的 JSON 数据
        """
        url = f"{self.BASE_URL}/{endpoint}"
        headers = self._get_headers()

        try:
            resp = requests.post(url, json=params, headers=headers, timeout=60)
            resp.raise_for_status()
            data = resp.json()

            # 检查错误
            if 'errorcode' in data and data['errorcode'] != 0:
                error_msg = data.get('errmsg', '未知错误')
                logger.error(f"API 调用失败 [{endpoint}]: {error_msg}")
                return data

            return data

        except requests.RequestException as e:
            logger.error(f"请求失败 [{endpoint}]: {e}")
            raise

    # ============================================================
    # 行情数据接口
    # ============================================================

    def get_history_quotes(self, codes: str, indicators: str,
                           start_date: str, end_date: str,
                           params: dict = None) -> dict:
        """
        历史行情：获取日/周/月频率的行情数据

        参数:
            codes: 合约代码，多个用逗号分隔，如 "niZL.SHF,ssZL.SHF"
            indicators: 指标，如 "open,high,low,close,volume,amount,openInterest"
            start_date: 开始日期，如 "2025-01-01"
            end_date: 结束日期，如 "2025-12-31"
            params: 额外参数，如 {"Fill": "Blank"}

        返回:
            API 原始返回数据
        """
        body = {
            "codes": codes,
            "indicators": indicators,
            "startdate": start_date,
            "enddate": end_date,
        }
        if params:
            body["functionpara"] = params
        else:
            body["functionpara"] = {"Fill": "Blank"}

        return self._post("cmd_history_quotation", body)

    def get_realtime_quotes(self, codes: str, indicators: str) -> dict:
        """
        实时行情：获取最新行情数据

        参数:
            codes: 合约代码
            indicators: 指标，如 "latest,open,high,low,volume,amount,openInterest"

        返回:
            API 原始返回数据
        """
        body = {
            "codes": codes,
            "indicators": indicators,
        }
        return self._post("real_time_quotation", body)

    def get_high_frequency(self, codes: str, indicators: str,
                            start_time: str, end_time: str) -> dict:
        """
        高频序列：获取分钟级数据

        参数:
            codes: 合约代码
            indicators: 指标
            start_time: 开始时间，如 "2025-01-15 09:00:00"
            end_time: 结束时间，如 "2025-01-15 15:00:00"

        返回:
            API 原始返回数据
        """
        body = {
            "codes": codes,
            "indicators": indicators,
            "starttime": start_time,
            "endtime": end_time,
        }
        return self._post("high_frequency", body)

    # ============================================================
    # 基础数据接口
    # ============================================================

    def get_basic_data(self, codes: str, indicators: list) -> dict:
        """
        基础数据：获取证券基本信息、财务等数据

        参数:
            codes: 合约代码
            indicators: 指标列表，每个指标是 {"indicator": "xxx", "indiparams": ["yyy"]}

        返回:
            API 原始返回数据
        """
        body = {
            "codes": codes,
            "indipara": indicators,
        }
        return self._post("basic_data_service", body)

    # ============================================================
    # 日期序列接口
    # ============================================================

    def get_date_serial(self, codes: str, indicators: list,
                         start_date: str, end_date: str,
                         params: dict = None) -> dict:
        """
        日期序列：获取基础数据指标的时间序列

        参数:
            codes: 合约代码
            indicators: 指标列表
            start_date: 开始日期
            end_date: 结束日期
            params: 额外参数

        返回:
            API 原始返回数据
        """
        body = {
            "codes": codes,
            "startdate": start_date,
            "enddate": end_date,
            "indipara": indicators,
        }
        if params:
            body["functionpara"] = params
        else:
            body["functionpara"] = {"Fill": "Blank"}

        return self._post("date_sequence", body)

    # ============================================================
    # EDB 经济数据库接口
    # ============================================================

    def get_edb_data(self, indicator_ids: str,
                      start_date: str, end_date: str) -> dict:
        """
        EDB经济数据库：获取宏观经济指标数据

        参数:
            indicator_ids: EDB指标ID，多个用逗号分隔
            start_date: 开始日期
            end_date: 结束日期

        返回:
            API 原始返回数据

        常用EDB指标ID示例（需要在iFinD终端查询具体ID）：
            - 美元指数
            - PMI
            - LME镍库存
            等
        """
        body = {
            "indicators": indicator_ids,
            "startdate": start_date,
            "enddate": end_date,
        }
        return self._post("edb_service", body)

    # ============================================================
    # 数据使用量查询
    # ============================================================

    def get_data_usage(self) -> dict:
        """查询当前账号的数据使用量"""
        return self._post("data_statistics", {})

    # ============================================================
    # 辅助工具函数
    # ============================================================

    def get_trade_dates(self, market: str, start_date: str,
                         end_date: str) -> dict:
        """
        查询交易日历

        参数:
            market: 交易所代码，上期所 = "142001"
            start_date: 开始日期
            end_date: 结束日期
        """
        body = {
            "marketcode": market,
            "functionpara": {
                "dateType": "0",
                "period": "D",
                "dateFormat": "0",
                "output": "sequencedate"
            },
            "startdate": start_date,
            "enddate": end_date,
        }
        return self._post("get_trade_dates", body)


# ============================================================
# 快捷测试函数
# ============================================================

def test_connection(refresh_token: str):
    """
    测试 API 连接是否正常

    用法：
        python -c "from src.data_fetcher.ths_client import test_connection; test_connection('你的refresh_token')"
    """
    print("=" * 60)
    print("同花顺 iFinD HTTP API 连接测试")
    print("=" * 60)

    # 步骤1: 获取 access_token
    print("\n[步骤1] 获取 access_token ...")
    client = TonghuashunClient(refresh_token)
    try:
        token = client.get_access_token()
        print(f"  ✅ 成功! token = {token[:20]}...")
    except Exception as e:
        print(f"  ❌ 失败! 错误: {e}")
        print("\n可能的原因:")
        print("  1. refresh_token 填写错误")
        print("  2. 网络无法访问 quantapi.51ifind.com")
        print("  3. 账号权限问题，联系同花顺客服 952555")
        return

    # 步骤2: 拉取沪镍主力合约最近5天日线
    print("\n[步骤2] 拉取沪镍主力合约最近行情 ...")
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        start = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

        result = client.get_history_quotes(
            codes="niZL.SHF",
            indicators="open,high,low,close,volume,amount,openInterest",
            start_date=start,
            end_date=today
        )

        if 'tables' in result and len(result['tables']) > 0:
            table = result['tables'][0]
            code = table.get('thscode', '未知')
            time_list = table.get('time', [])
            data_table = table.get('table', {})

            print(f"  ✅ 成功! 合约: {code}")
            print(f"  📊 获取到 {len(time_list)} 条日线数据")

            # 打印最近5条
            n = min(5, len(time_list))
            print(f"\n  最近 {n} 个交易日:")
            print(f"  {'日期':<12} {'开盘':>8} {'最高':>8} {'最低':>8} {'收盘':>8} {'持仓量':>10}")
            print(f"  {'-'*60}")

            close_list = data_table.get('close', [])
            open_list = data_table.get('open', [])
            high_list = data_table.get('high', [])
            low_list = data_table.get('low', [])
            oi_list = data_table.get('openInterest', [])

            for i in range(-n, 0):
                date = time_list[i] if i < len(time_list) else "N/A"
                o = open_list[i] if open_list else "N/A"
                h = high_list[i] if high_list else "N/A"
                l = low_list[i] if low_list else "N/A"
                c = close_list[i] if close_list else "N/A"
                oi = oi_list[i] if oi_list else "N/A"
                print(f"  {date:<12} {o:>8} {h:>8} {l:>8} {c:>8} {oi:>10}")
        else:
            print(f"  ⚠️ 返回数据为空，可能是非交易时间或合约代码问题")
            print(f"  原始返回: {json.dumps(result, ensure_ascii=False, indent=2)[:500]}")

    except Exception as e:
        print(f"  ❌ 失败! 错误: {e}")

    # 步骤3: 查询数据使用量
    print("\n[步骤3] 查询数据使用量 ...")
    try:
        usage = client.get_data_usage()
        print(f"  ✅ {json.dumps(usage, ensure_ascii=False, indent=2)[:300]}")
    except Exception as e:
        print(f"  ⚠️ 查询失败: {e}")

    print("\n" + "=" * 60)
    print("测试完成!")
    print("=" * 60)
