# ============================================================
# 檔名：shared/pricing_service.py
# 功能：價格／儲值金方案計算服務；逐步隔離 quick_order 內價格相關函式。
# 更新時間：2026-08-19
# ============================================================
# -*- coding: utf-8 -*-

"""價格與儲值金計算服務。

目前先保留相容性，將已存在且被上層使用的價格相關函式集中在本模組。
待價格公式與後台 calculate_hour 邏輯完全確認後，再把實作逐步搬離 quick_order.py。
"""

from __future__ import annotations

import quick_order as _legacy


def get_stored_value(*args, **kwargs):
    return _legacy.get_stored_value(*args, **kwargs)


def calc_stored_value_plan(*args, **kwargs):
    return _legacy.calc_stored_value_plan(*args, **kwargs)


def calculate_service_price(*args, **kwargs):
    """相容入口；只有 legacy 提供對應函式時才使用。"""
    fn = getattr(_legacy, "calculate_service_price", None)
    if fn is None:
        raise AttributeError("legacy quick_order 尚未提供 calculate_service_price")
    return fn(*args, **kwargs)
