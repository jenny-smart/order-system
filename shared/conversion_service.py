# ============================================================
# 檔名：shared/conversion_service.py
# 功能：訂單轉換／儲值金補價差服務；隔離 quick_order 內高風險轉單流程。
# 更新時間：2026-08-19
# ============================================================
# -*- coding: utf-8 -*-

"""訂單轉換服務邊界。

轉單涉及原單重派、新單建立、儲值金與補價差，風險較高；本階段只建立
穩定 Facade，不搬動已驗證的 legacy 實作。後續會逐函式加入測試後再遷移。
"""

from __future__ import annotations

import quick_order as _legacy


def convert_order(*args, **kwargs):
    return _legacy.convert_order(*args, **kwargs)


def convert_order_multi(*args, **kwargs):
    return _legacy.convert_order_multi(*args, **kwargs)


def convert_order_stage1_reassign_original(*args, **kwargs):
    return _legacy.convert_order_stage1_reassign_original(*args, **kwargs)


def convert_order_stage2_create_new_orders(*args, **kwargs):
    return _legacy.convert_order_stage2_create_new_orders(*args, **kwargs)


def stored_value_makeup_convert(*args, **kwargs):
    return _legacy.stored_value_makeup_convert(*args, **kwargs)


def stored_value_makeup_create_stored_order(*args, **kwargs):
    return _legacy.stored_value_makeup_create_stored_order(*args, **kwargs)


def stored_value_makeup_create_paid_order(*args, **kwargs):
    return _legacy.stored_value_makeup_create_paid_order(*args, **kwargs)


def create_stored_value_purchase_order(*args, **kwargs):
    return _legacy.create_stored_value_purchase_order(*args, **kwargs)
