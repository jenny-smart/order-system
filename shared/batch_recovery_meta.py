# -*- coding: utf-8 -*-
"""中斷復原／回填時，依訂單編號精確抓後台資料。

移植自 orders-system batch_recovery_meta.py。原版以 monkeypatch 取代
orders.fetch_order_meta_by_order_no；order-system 改由
orders.fetch_order_meta_by_order_no 直接先呼叫 exact_fetch_order_meta，
精確查詢失敗（回傳 None）才退回原本的訂單列表頁比對。
"""
from __future__ import annotations


def exact_fetch_order_meta(session, order_no):
    """以 orderNo 篩選 /purchase，只接受訂單編號完全相同的卡片；查不到回傳 None。"""
    import orders

    order_no = str(order_no or "").strip()
    if not order_no:
        return None

    try:
        params = dict(orders.PURCHASE_FILTER_PARAMS_TEMPLATE)
        params["orderNo"] = order_no
        resp = session.get(
            orders.PURCHASE_URL,
            params=params,
            headers=orders.HEADERS,
            allow_redirects=True,
        )
        if resp.status_code != 200:
            return None
        for block in orders.extract_order_cards_from_purchase_html(resp.text):
            if str(block.get("order_no") or "").strip() != order_no:
                continue
            lines = block.get("lines", [])
            service_date, service_time = orders._extract_service_date_time(lines)
            return {
                "服務人員": orders._extract_staff_line(lines) or "無人力",
                "服務狀態": orders._extract_status_line(lines) or "未處理",
                "車馬費": orders._extract_fare_line("\n".join(lines)) or "0",
                "服務日期": service_date or "",
                "服務時間": service_time or "",
            }
    except Exception:
        pass
    # 精確查詢失敗才退回既有行為；不因補強功能影響原流程。
    return None
