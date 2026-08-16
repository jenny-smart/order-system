# -*- coding: utf-8 -*-
"""後台 API 共用工具，供 orders.py／quick_order.py 共用。

目前只放兩邊完全重複的一小塊（PURCHASE_FILTER_PARAMS_TEMPLATE 常數、
_fetch_order_edit_id）；orders.py 原本的說明是「不匯入 quick_order（避免
循環匯入：quick_order 本身會匯入 orders）」，所以各自放一份，這裡把它
合併成一份供兩邊共用。login/會員查詢/訂單卡片HTML解析等其餘後台 API
仍留在 orders.py／quick_order.py 原地，尚未搬遷。
"""

import re

import orders

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
