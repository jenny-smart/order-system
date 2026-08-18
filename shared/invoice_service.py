# ============================================================
# 檔名：shared/invoice_service.py
# 功能：發票／載具相關服務相容層；逐步隔離 quick_order 發票實作。
# 更新時間：2026-08-19
# ============================================================
# -*- coding: utf-8 -*-
from __future__ import annotations
import quick_order as _legacy


def legacy_invoice_call(function_name: str, *args, **kwargs):
    """暫時統一發票函式入口；搬移實作後上層呼叫介面不變。"""
    fn = getattr(_legacy, function_name, None)
    if fn is None:
        raise AttributeError(f"quick_order 找不到發票函式：{function_name}")
    return fn(*args, **kwargs)
