# ============================================================
# 檔名：shared/order_creator.py
# 功能：訂單建立與建單後備註更新服務；隔離 quick_order 的建單實作。
# 更新時間：2026-08-19
# ============================================================
# -*- coding: utf-8 -*-

"""訂單建立服務。

目前只建立穩定邊界，不改動正式機建單 payload、價格、人力驗證或付款流程。
待回歸測試齊全後，再逐段把 quick_create_order 內部實作搬入較小模組。
"""

from __future__ import annotations

import quick_order as _legacy


def create_order(**kwargs) -> dict:
    return _legacy.quick_create_order(**kwargs)


def update_order_note(session, base_url: str, order_no: str, note: str):
    return _legacy._update_order_note(session, base_url, order_no, note)
