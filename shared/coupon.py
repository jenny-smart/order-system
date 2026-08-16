# -*- coding: utf-8 -*-
"""優惠券建立共用邏輯，供 quick_order.py 內多個功能（訂單轉換、儲值金補價差等）共用。

create_coupon（獨立登入版本，供 UI 直接呼叫）留在 quick_order.py，因為它依賴
quick_order.py 自己的 _configure_environment（env_name -> 改寫 orders.py 的
BASE_URL 等全域設定），屬於 Phase 1 刻意不動的環境切換邏輯範圍；但它仍會呼叫
這裡的 _get_newest_coupon_code。
"""

import re
import time

import orders

COUPON_COMPANY_ID_MAP = {"台北": "1", "桃園": "2", "新竹": "3", "台中": "4"}
COUPON_SERVICE_ITEM_MAP = {
    "居家清潔": "1", "辦公室清潔": "2", "裝修細清": "3", "年節大掃除": "4",
    "冷氣機清潔": "5", "洗衣機清潔": "6", "沙發/床墊清潔": "7", "整理收納": "8",
}
COUPON_TYPE_MAP = {
    "不得與其他優惠券重複": "1",
    "可重複使用，每個帳號限用一次": "2",
    "可重複使用，不限使用次數": "3",
}
COUPON_ADD_URL_PATH = "/coupon/add"


def _get_newest_coupon_code(session, base_url, prefix):
    try:
        list_resp = session.get(f"{base_url}/coupon", headers=orders.HEADERS, allow_redirects=True)
        if list_resp.status_code != 200:
            return ""
        ids = re.findall(r"/coupon/detail/(\d+)", list_resp.text)
        if not ids:
            return ""
        prefix_esc = re.escape(prefix)
        for coupon_id in ids[:10]:
            detail_resp = session.get(f"{base_url}/coupon/detail/{coupon_id}", headers=orders.HEADERS)
            if detail_resp.status_code != 200:
                continue
            codes = re.findall(rf"\b{prefix_esc}[A-Za-z0-9]*\b", detail_resp.text)
            if codes:
                return codes[0]
        return ""
    except Exception:
        return ""


def _build_coupon_via_session(session, base_url, title, discount, date_s, date_e, prefix, piece, regions, service_items):
    """用既有 session 建優惠券，不重新登入。回傳實際優惠碼字串。"""
    coupon_add_url = f"{base_url}{COUPON_ADD_URL_PATH}"
    get_resp = session.get(coupon_add_url, headers=orders.HEADERS, allow_redirects=True)
    if get_resp.status_code != 200:
        raise Exception("無法開啟優惠券新增頁面")
    token_m = re.search(r'<meta name="csrf-token" content="([^"]+)"', get_resp.text)
    csrf = token_m.group(1) if token_m else ""
    if not csrf:
        raise Exception("無法取得 CSRF token")
    coupon_fields = [
        ("coupon_type_id", "1"), ("title", str(title)),
        ("date_s", str(date_s)), ("date_e", str(date_e)),
        ("prefix", str(prefix)), ("discount", str(int(float(discount)))),
        ("piece", str(int(piece))), ("_token", csrf),
    ]
    for rn in (regions or ["台北", "台中"]):
        coupon_fields.append(("company_id[]", COUPON_COMPANY_ID_MAP.get(rn, "1")))
    for svc in (service_items or ["居家清潔", "裝修細清"]):
        coupon_fields.append(("service_item[]", COUPON_SERVICE_ITEM_MAP.get(svc, "1")))
    coupon_files = [(k, (None, v)) for k, v in coupon_fields]
    post_headers = {k: v for k, v in orders.HEADERS.items() if k.lower() != "content-type"}
    post_resp = session.post(coupon_add_url, files=coupon_files, headers=post_headers, allow_redirects=True)
    if post_resp.status_code not in (200, 302):
        snippet = post_resp.text[:200].replace("\n", " ")
        raise Exception(f"優惠券建立失敗：HTTP {post_resp.status_code}｜{snippet}")
    if post_resp.url and "add" in post_resp.url:
        raise Exception("優惠券建立失敗：後台驗證未通過，請確認區域/服務項目欄位")
    time.sleep(1)
    return _get_newest_coupon_code(session, base_url, str(prefix))
