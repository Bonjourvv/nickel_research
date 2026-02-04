#!/usr/bin/env python3
"""
============================================================
镍/不锈钢研究系统 - API 连接测试脚本
============================================================

使用方法：
    1. 先获取 refresh_token（见下方说明）
    2. 在终端运行:
       cd nickel_research
       python test_api.py

获取 refresh_token 的方法：
    - 需要在 Windows 电脑上操作一次（可以找公司同事帮忙）
    - 下载 Windows 版接口包: https://quantapi.51ifind.com → 下载中心
    - 解压后打开 Bin/Tool/SuperCommand.exe
    - 用公司账号 xmxy399 密码 415b47 登录
    - 点击菜单: 工具 → refresh_token 查询
    - 复制显示的 refresh_token 字符串
    
    或者：
    - 登录网页版超级命令
    - https://quantapi.10jqka.com.cn/gwstatic/static/ds_web/super-command-web/index.html#/AccountDetails
    - 用公司账号登录后可以查看 refresh_token
============================================================
"""

import sys
import os

# 把项目根目录加到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.data_fetcher.ths_client import test_connection


def main():
    print()
    print("🔧 镍/不锈钢研究系统 - API 连接测试")
    print()

    # 先尝试从配置文件读取
    try:
        from config.settings import IFIND_REFRESH_TOKEN
        if IFIND_REFRESH_TOKEN and IFIND_REFRESH_TOKEN != "在这里填写你的refresh_token":
            print(f"从配置文件读取到 refresh_token")
            test_connection(IFIND_REFRESH_TOKEN)
            return
    except ImportError:
        pass

    # 如果配置文件没有，让用户手动输入
    print("你还没有配置 refresh_token。")
    print()
    print("获取方法:")
    print("  方法1: 登录网页版超级命令，查看账号详情")
    print("         https://quantapi.10jqka.com.cn/gwstatic/static/ds_web/super-command-web/index.html#/AccountDetails")
    print("  方法2: 在 Windows 电脑上用 SuperCommand.exe → 工具 → refresh_token 查询")
    print()

    token = input("请粘贴你的 refresh_token（或输入 q 退出）: ").strip()

    if token.lower() == 'q':
        print("退出")
        return

    if not token:
        print("❌ token 不能为空")
        return

    # 测试连接
    test_connection(token)

    # 测试成功后，提示保存
    print()
    save = input("是否将 refresh_token 保存到配置文件？(y/n): ").strip().lower()
    if save == 'y':
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "config", "settings.py")
        try:
            with open(config_path, 'r') as f:
                content = f.read()
            content = content.replace(
                'IFIND_REFRESH_TOKEN = "在这里填写你的refresh_token"',
                f'IFIND_REFRESH_TOKEN = "{token}"'
            )
            with open(config_path, 'w') as f:
                f.write(content)
            print(f"✅ 已保存到 {config_path}")
        except Exception as e:
            print(f"⚠️ 保存失败: {e}")
            print(f"请手动编辑 config/settings.py，填入 refresh_token")


if __name__ == "__main__":
    main()
