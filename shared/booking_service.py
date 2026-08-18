# -*- coding: utf-8 -*-
"""Stable booking-service boundary used by modular order-system features.

Why this exists
---------------
quick_order.py is still a large legacy compatibility engine. New feature modules
should not import it directly. They import this module instead. Today these
functions delegate to quick_order.py; later each implementation can be moved into
smaller shared modules without changing every UI/function caller again.

This is a strangler-style migration boundary: behavior stays the same first,
implementation moves behind the boundary gradually.
"""

from __future__ import annotations

from typing import Any

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


def lookup_member(env_name: str, backend_email: str, backend_password: str, phone: str, clean_type_id: str = "1") -> dict:
    return _legacy.quick_lookup_member(
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


def create_order(**kwargs) -> dict:
    return _legacy.quick_create_order(**kwargs)


def update_order_note(session, base_url: str, order_no: str, note: str):
    return _legacy._update_order_note(session, base_url, order_no, note)


def configure_environment(env_name: str) -> str:
    return _legacy._configure_environment(env_name)


def request_headers() -> dict:
    return dict(getattr(_legacy, "HEADERS", {}) or {})


def legacy_attr(name: str, default: Any = None) -> Any:
    """Temporary escape hatch while remaining quick_order functions are migrated.

    New code should prefer explicit wrappers above. This function prevents new
    feature modules from importing quick_order.py directly while migration is in
    progress.
    """
    return getattr(_legacy, name, default)
