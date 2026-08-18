# ============================================================
# 檔名：shared/order_status_service.py
# 功能：訂單狀態／既有訂單後處理服務相容層；隔離 orders.py 狀態邏輯。
# 更新時間：2026-08-19
# ============================================================
# -*- coding: utf-8 -*-
from __future__ import annotations
import orders as _legacy


def process_existing_order(*args, **kwargs):
    return _legacy.process_existing_order_only(*args, **kwargs)


def build_row_result(*args, **kwargs):
    return _legacy.build_row_result(*args, **kwargs)


def legacy_status_call(function_name: str, *args, **kwargs):
    fn = getattr(_legacy, function_name, None)
    if fn is None:
        raise AttributeError(f"orders 找不到狀態函式：{function_name}")
    return fn(*args, **kwargs)
