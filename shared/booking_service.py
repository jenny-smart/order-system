# ============================================================
# 檔名：shared/booking_service.py
# 功能：建單領域統一 Facade；串接會員查詢、班表可用性、訂單建立等拆分服務。
# 更新時間：2026-08-19
# ============================================================
# -*- coding: utf-8 -*-

"""Stable booking-service boundary used by modular order-system features.

新功能只依賴本 Facade，不直接依賴巨大 quick_order.py。
已拆出的功能改由 member_service / availability_service / order_creator 提供；
尚未拆出的環境與共用常數暫時由 legacy quick_order 相容提供。
"""

from __future__ import annotations

from typing import Any

import quick_order as _legacy
from shared import availability_service, member_service, order_creator

PERIOD_HOUR_MAP = availability_service.PERIOD_HOUR_MAP


def lookup_member(env_name: str, backend_email: str, backend_password: str, phone: str, clean_type_id: str = "1") -> dict:
    return member_service.lookup_member(
        env_name, backend_email, backend_password, phone, clean_type_id=clean_type_id
    )


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
    return availability_service.check_available_slots(
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


def create_order(**kwargs) -> dict:
    return order_creator.create_order(**kwargs)


def update_order_note(session, base_url: str, order_no: str, note: str):
    return order_creator.update_order_note(session, base_url, order_no, note)


def configure_environment(env_name: str) -> str:
    return _legacy._configure_environment(env_name)


def request_headers() -> dict:
    return dict(getattr(_legacy, "HEADERS", {}) or {})


def legacy_attr(name: str, default: Any = None) -> Any:
    """Temporary escape hatch while remaining quick_order functions are migrated."""
    return getattr(_legacy, name, default)
