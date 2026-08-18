# ============================================================
# 檔名：shared/availability_service.py
# 功能：建單前日期／時段／人力可用性查詢服務；統一班表查詢入口。
# 更新時間：2026-08-19
# ============================================================
# -*- coding: utf-8 -*-

"""日期、時段與人力可用性服務。

安全原則：不自行推算人力、不放寬完整時段條件；目前完整沿用
quick_order.quick_check_available_slots 已驗證的正式機判斷。
"""

from __future__ import annotations

import quick_order as _legacy

PERIOD_HOUR_MAP = {
    "08:30-12:30": 4,
    "09:00-11:00": 2,
    "09:00-12:00": 3,
    "14:00-16:00": 2,
    "14:00-17:00": 3,
    "14:00-18:00": 4,
    "09:00-16:00": 6,
    "09:00-18:00": 8,
}


def check_available_slots(
    env_name: str,
    payway: str,
    lookup_result: dict,
    address: str,
    clean_type_id: str,
    date_s: str,
    hour: str,
    *,
    person: str,
    periods,
    period_hours=None,
):
    return _legacy.quick_check_available_slots(
        env_name,
        payway,
        lookup_result,
        address,
        clean_type_id,
        date_s,
        hour,
        person=person,
        periods=periods,
        period_hours=period_hours or PERIOD_HOUR_MAP,
    )
