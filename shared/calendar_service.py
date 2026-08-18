# ============================================================
# 檔名：shared/calendar_service.py
# 功能：Google Calendar 同步服務相容層；隔離 orders.py 日曆相關實作。
# 更新時間：2026-08-19
# ============================================================
# -*- coding: utf-8 -*-
from __future__ import annotations
import orders as _legacy


def build_service(*args, **kwargs):
    return _legacy.build_gcal_service(*args, **kwargs)


def legacy_calendar_call(function_name: str, *args, **kwargs):
    fn = getattr(_legacy, function_name, None)
    if fn is None:
        raise AttributeError(f"orders 找不到日曆函式：{function_name}")
    return fn(*args, **kwargs)
