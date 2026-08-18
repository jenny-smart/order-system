# ============================================================
# 檔名：shared/payment_service.py
# 功能：付款／儲值金訂單服務相容層；隔離 quick_order 付款相關實作。
# 更新時間：2026-08-19
# ============================================================
# -*- coding: utf-8 -*-
from __future__ import annotations
import quick_order as _legacy


def create_stored_value_purchase_order(*args, **kwargs):
    return _legacy.create_stored_value_purchase_order(*args, **kwargs)


def stored_value_makeup_create_stored_order(*args, **kwargs):
    return _legacy.stored_value_makeup_create_stored_order(*args, **kwargs)


def stored_value_makeup_create_paid_order(*args, **kwargs):
    return _legacy.stored_value_makeup_create_paid_order(*args, **kwargs)
