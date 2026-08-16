# -*- coding: utf-8 -*-
"""後台 API 共用工具，供 orders.py／quick_order.py 共用。

目前放兩邊完全重複的一小塊（PURCHASE_FILTER_PARAMS_TEMPLATE 常數、
_fetch_order_edit_id），以及原本只有 quick_order.py 有、但不依賴
_configure_environment（env 切換邏輯，屬於 Phase 3 範圍）的訂單查詢工具
（依電話查訂單卡片、除錯資訊）。login/CSRF/會員查詢等其餘後台 API 仍留在
orders.py／quick_order.py 原地，尚未搬遷。
"""

import re

import orders
from shared.text_parsing import normalize_phone

# v2026.07.05：後台 /purchase 訂單列表頁的搜尋表單，瀏覽器送出時會帶上全部
# 欄位（沒填的欄位是空字串，不是完全不送）。如果我們用 requests 查詢時只帶
# 想篩選的那一兩個參數（例如只送 phone），後台某些邏輯是用「這個參數有沒有
# 出現在請求裡」而不是「值是不是空字串」來判斷，可能會觸發跟瀏覽器不一樣的
# 預設篩選（例如自動加上當月日期區間），導致查到的結果變少甚至查無資料。
# 所以查詢時一律以這份樣板為底，只覆蓋真正要篩選的欄位，其餘保持空字串。
PURCHASE_FILTER_PARAMS_TEMPLATE = {
    "keyword": "", "name": "", "phone": "", "orderNo": "",
    "date_s": "", "date_e": "", "clean_date_s": "", "clean_date_e": "",
    "paid_at_s": "", "paid_at_e": "", "refundDateS": "", "refundDateE": "",
    "buy": "", "area_id": "", "isCharge": "", "isRefund": "",
    "payway": "", "purchase_status": "", "progress_status": "",
    "invoiceStatus": "", "otherFee": "", "orderBy": "",
}


def _fetch_order_edit_id(session, order_no):
    params = dict(PURCHASE_FILTER_PARAMS_TEMPLATE)
    params["orderNo"] = str(order_no).strip()
    resp = session.get(orders.PURCHASE_URL, params=params, headers=orders.HEADERS, allow_redirects=True)
    if resp.status_code != 200:
        return None
    m = re.search(r"/purchase/edit/(\d+)", resp.text)
    return m.group(1) if m else None


PURCHASE_STATUS_PAID = "1"

_LAST_PURCHASE_FETCH_DEBUG = {}


def get_last_purchase_fetch_debug():
    return dict(_LAST_PURCHASE_FETCH_DEBUG)


def _block_matches_phone_filter(block, phone_norm):
    if not phone_norm:
        return True
    joined = "\n".join(block.get("lines", []))
    compact = joined.replace("-", "").replace(" ", "")
    if phone_norm in compact:
        return True
    visible_phones = {
        normalize_phone(m.group(0))
        for m in re.finditer(r"(?:\+?886[-\s]?)?0?9[\d\-\s]{8,12}", joined)
    }
    visible_phones.discard("")
    if visible_phones:
        return phone_norm in visible_phones
    return True


def _fetch_purchase_blocks_for_phone(session, phone, name="", purchase_status=""):
    global _LAST_PURCHASE_FETCH_DEBUG
    params = dict(PURCHASE_FILTER_PARAMS_TEMPLATE)
    params["phone"] = normalize_phone(phone)
    if purchase_status:
        params["purchase_status"] = purchase_status
    if name and not params["phone"]:
        params["name"] = name
    resp = session.get(orders.PURCHASE_URL, params=params, headers=orders.HEADERS, allow_redirects=True)
    raw_blocks = []
    if resp.status_code == 200:
        raw_blocks = orders.extract_order_cards_from_purchase_html(resp.text)
    looks_like_login_page = "login" in resp.url.lower() or (len(raw_blocks) == 0 and "password" in resp.text.lower())
    effective_purchase_status = purchase_status
    fallback_info = {}
    if purchase_status and resp.status_code == 200 and not raw_blocks and not looks_like_login_page:
        fallback_params = dict(PURCHASE_FILTER_PARAMS_TEMPLATE)
        fallback_params["phone"] = normalize_phone(phone)
        if name and not fallback_params["phone"]:
            fallback_params["name"] = name
        fallback_resp = session.get(orders.PURCHASE_URL, params=fallback_params, headers=orders.HEADERS, allow_redirects=True)
        fallback_blocks = []
        if fallback_resp.status_code == 200:
            fallback_blocks = orders.extract_order_cards_from_purchase_html(fallback_resp.text)
        fallback_info = {
            "fallback_request_url": getattr(fallback_resp.request, "url", ""),
            "fallback_status_code": fallback_resp.status_code,
            "fallback_raw_block_count": len(fallback_blocks),
        }
        if fallback_blocks:
            resp = fallback_resp
            raw_blocks = fallback_blocks
            effective_purchase_status = ""
            looks_like_login_page = "login" in resp.url.lower()
    _LAST_PURCHASE_FETCH_DEBUG = {
        "request_url": getattr(resp.request, "url", ""), "final_url": resp.url,
        "status_code": resp.status_code, "purchase_status_filter": purchase_status,
        "effective_purchase_status_filter": effective_purchase_status,
        "raw_block_count": len(raw_blocks), "looks_like_login_page": looks_like_login_page,
        "snippet": resp.text[:300].replace("\n", " ").strip() if resp.status_code == 200 else "",
        **fallback_info,
    }
    if resp.status_code != 200:
        return []
    phone_norm = normalize_phone(phone)
    if not phone_norm:
        _LAST_PURCHASE_FETCH_DEBUG["filtered_block_count"] = len(raw_blocks)
        return raw_blocks
    filtered = [block for block in raw_blocks if _block_matches_phone_filter(block, phone_norm)]
    _LAST_PURCHASE_FETCH_DEBUG["filtered_block_count"] = len(filtered)
    return filtered


def list_order_numbers_for_phone(session, phone, name=""):
    blocks = _fetch_purchase_blocks_for_phone(session, phone, name=name)
    return {block["order_no"] for block in blocks if block.get("order_no")}
