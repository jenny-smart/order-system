# -*- coding: utf-8 -*-
"""order-system package bootstrap.

ordersapp.py imports memo_system.ui before rendering the unified function menu.
Use that import point to inject the new modular order functions without rewriting
or duplicating the large ordersapp.py file.
"""

from __future__ import annotations

import inspect
import re

import streamlit as st

_NEW_OPTIONS = [
    (
        "批次建單優化：同一會員／地址可一次複選多個日期與時段，查班後批次建立。",
        "batch_optimized",
    ),
    (
        "檸檬保留單建單：分析未配班人力、逐日期／時段調整保留張數後批次建立。",
        "reserve_create",
    ),
    (
        "檸檬保留單取消：依期間、時段與客人備註搜尋，逐筆安全取消系統保留單。",
        "reserve_cancel",
    ),
]


def _strip_number(text: str) -> str:
    return re.sub(r"^\s*\d+\.\s*", "", str(text or "")).strip()


def _augment_menu(options):
    """Insert new A-section functions while preserving all existing menu entries."""
    original = list(options or [])
    descriptions = {_strip_number(x) for x in original}
    if all(label in descriptions for label, _ in _NEW_OPTIONS):
        return original

    # Put optimized batch immediately after existing batch item. Reserve functions
    # follow the existing order-creation items, before the B-section header.
    result = []
    batch_inserted = False
    reserves_inserted = False
    for value in original:
        text = str(value)
        desc = _strip_number(text)
        if text.strip().startswith("── B. 訂單附屬功能") and not reserves_inserted:
            for label, _ in _NEW_OPTIONS[1:]:
                result.append(label)
            reserves_inserted = True
        result.append(text)
        if desc.startswith("批次建單：") and not batch_inserted:
            result.append(_NEW_OPTIONS[0][0])
            batch_inserted = True

    if not batch_inserted:
        # Fallback: insert just after A header when existing label changes later.
        insert_at = 1 if result and str(result[0]).strip().startswith("── A.") else 0
        result.insert(insert_at, _NEW_OPTIONS[0][0])
    if not reserves_inserted:
        result.extend([label for label, _ in _NEW_OPTIONS[1:]])

    # Re-number actual functions but keep category header rows untouched.
    numbered = []
    counter = 0
    for value in result:
        text = str(value)
        if text.strip().startswith("──"):
            numbered.append(text)
            continue
        counter += 1
        numbered.append(f"{counter}. {_strip_number(text)}")
    return numbered


def _render_custom(target: str, app_globals: dict):
    email = str(app_globals.get("backend_email") or "")
    password = str(app_globals.get("backend_password") or "")
    env = str(app_globals.get("env") or "")

    st.markdown("<hr>", unsafe_allow_html=True)
    if target == "batch_optimized":
        from function.batch_booking_optimized import render
        render(email, password, env)
    elif target == "reserve_create":
        from function.reserve_menu import render_create
        render_create(email, password, env)
    elif target == "reserve_cancel":
        from function.reserve_menu import render_cancel
        render_cancel(email, password, env)
    st.stop()


def _install_menu_patch():
    if getattr(st, "_order_system_modular_menu_patch", False):
        return

    original_selectbox = st.selectbox

    def patched_selectbox(label, options, *args, **kwargs):
        if str(label) != "功能選單" or kwargs.get("key") != "unified_function_select":
            return original_selectbox(label, options, *args, **kwargs)

        augmented = _augment_menu(options)
        selected = original_selectbox(label, augmented, *args, **kwargs)
        desc = _strip_number(selected)
        target = next((key for text, key in _NEW_OPTIONS if desc == text), None)
        if target:
            caller = inspect.currentframe().f_back
            app_globals = caller.f_globals if caller is not None else {}
            _render_custom(target, app_globals)

        # ordersapp.py looks the returned string up in its original option list.
        # Map existing selections back to the exact original label/number.
        for original in list(options or []):
            if _strip_number(original) == desc:
                return original
        return selected

    st.selectbox = patched_selectbox
    st._order_system_modular_menu_patch = True


_install_menu_patch()
