# -*- coding: utf-8 -*-
"""後台 dev/prod 環境切換的單一計算來源。

orders.py／quick_order.py 以及好幾個外部檔案（cancel_order.py、
weekend_reminders.py、next_service_dates.py）過去都各自手動組一次
「BASE_URL → LOGIN_URL／BOOKING_URL／PURCHASE_URL…」這一串網址，曾經
真的出過「改了 BASE_URL 卻漏改 LOGIN_URL，選 prod 卻用 dev session 登入」
的事故（orders.py changelog v2026.07.06 有記錄）。這裡把「給定 env_name，
這 10 個網址／設定分別是什麼」的計算集中成一個函式，所有呼叫端都改成用
這份計算結果整批覆蓋目標模組的全域變數，讓同一個 env_name 永遠得到完全
一致的一組網址，不會再有漏同步的可能。

BASE_URL 等變數本身仍然留在 orders.py（沒有搬到這裡），因為 orders.py
內部有幾十個地方直接讀取這些裸名稱；只有「怎麼算出這些值」搬進來。
"""

from env import BASE_URL_DEV, BASE_URL_PROD, ORDER_PREFIX_DEV, ORDER_PREFIX_PROD


ENV_KEYS = (
    "BASE_URL", "ORDER_PREFIX", "LOGIN_URL", "BOOKING_URL", "PURCHASE_URL",
    "GET_MEMBER_URL", "CHECK_CONTAIN_URL", "CALCULATE_HOUR_URL",
    "GET_SECTION_URL", "MAIL_SUCCESS_URL",
)


def compute_env_urls(env_name):
    """回傳給定 env_name（"dev" 或其他視為 "prod"）對應的完整網址/前綴組合。"""
    base_url = BASE_URL_DEV if env_name == "dev" else BASE_URL_PROD
    order_prefix = ORDER_PREFIX_DEV if env_name == "dev" else ORDER_PREFIX_PROD
    return {
        "BASE_URL": base_url,
        "ORDER_PREFIX": order_prefix,
        "LOGIN_URL": f"{base_url}/login",
        "BOOKING_URL": f"{base_url}/booking/stored_value_routine",
        "PURCHASE_URL": f"{base_url}/purchase",
        "GET_MEMBER_URL": f"{base_url}/ajax/get_member",
        "CHECK_CONTAIN_URL": f"{base_url}/ajax/check_contain",
        "CALCULATE_HOUR_URL": f"{base_url}/ajax/calculate_hour",
        "GET_SECTION_URL": f"{base_url}/ajax/get_section",
        "MAIL_SUCCESS_URL": f"{base_url}/purchase/mail_success/{{order_no}}",
    }


def compute_env_url_tuple(env_name):
    """跟 compute_env_urls 同一份計算，但回傳固定順序（見 ENV_KEYS）的 tuple，
    方便用 `BASE_URL, ORDER_PREFIX, ... = compute_env_url_tuple(env_name)`
    這種明確賦值語法（讓 pyflakes 等靜態分析工具追蹤得到，不像
    globals().update(...) 那樣對工具是不透明的黑盒）。"""
    urls = compute_env_urls(env_name)
    return tuple(urls[k] for k in ENV_KEYS)


def apply_env(target_module, env_name):
    """把 compute_env_urls(env_name) 的結果整批寫進 target_module 的全域變數
    （例如 apply_env(orders, "dev")），回傳這組結果的 BASE_URL 方便呼叫端使用。
    給「跨模組」寫入用（例如 quick_order.py 寫 orders.py 的全域）；
    orders.py 自己內部請用 compute_env_url_tuple 明確賦值，不要用這個，
    以免 pyflakes 看不到 orders.py 自己的全域變數賦值。"""
    urls = compute_env_urls(env_name)
    vars(target_module).update(urls)
    return urls["BASE_URL"]
