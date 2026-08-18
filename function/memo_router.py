# ============================================================
# 檔名：function/memo_router.py
# 功能：原 memo_system UI 的輕量路由；由 ordersapp.py 共用登入資訊直接派送到各 function。
# 更新時間：2026-08-19
# ============================================================
# -*- coding: utf-8 -*-
from __future__ import annotations

import streamlit as st
from shared import memo_backend as memo
from function import memo_customer_service
from function import shift_management
from function import atm_reconciliation
from function import payment_match_page
from function import change_order_page
from function import assessment_tool

SECTION_RENDERERS = {
    "📋 客服作業": memo_customer_service.render,
    "📅 排班管理": shift_management.render,
    "💰 財務對帳": atm_reconciliation.render,
    "💳 付款後5碼及星和診所比對": payment_match_page.render,
    "🔄 服務異動": change_order_page.render,
    "📐 評估文字工具": assessment_tool.render,
}

DEFAULT_STATE = {
    "logs": [], "result": None, "is_running": False,
    "is_logged_in": False, "preview_rows": [], "last_mode": "",
    "login_identity": "", "sheet_summary": None,
    "shift_import_rows": [], "shift_dry_run_result": None,
    "lemon_candidate": None, "lemon_assign_result": None,
    "atm_result": None, "atm_match_result": None,
    "atm_list_rows": None, "atm_list_paste_result": None,
    "clear_person_result": None,
    "lemon_scan_entries": None, "lemon_clear_results": None,
    "co_calc_rows": [], "co_pending_rows": [],
    "co_phone_orders": [], "co_selected_order_no": "",
    "co_selected_order_detail": None,
    "auth_session": None, "auth_env": "", "auth_email": "",
    "credentials_ready": False, "assess_v1": "", "assess_v2": "",
}


def _prepare_runtime(email: str, password: str, env: str) -> None:
    for key, value in DEFAULT_STATE.items():
        if key not in st.session_state:
            st.session_state[key] = value
    st.session_state.is_running = False
    memo.set_env(env)
    change_order_page.set_env(env)
    memo.set_runtime_credentials(email, password)
    st.session_state.credentials_ready = bool((email or "").strip()) and bool((password or "").strip())
    if st.session_state.is_logged_in and (
        (st.session_state.auth_env and st.session_state.auth_env != env)
        or (st.session_state.auth_email and st.session_state.auth_email != (email or "").strip())
    ):
        st.session_state.auth_session = None
        st.session_state.is_logged_in = False


def render(section: str, email: str, password: str, env: str) -> None:
    """由 ordersapp 主選單直接呼叫原 memo 功能，不再需要 memo_system/ui.py。"""
    renderer = SECTION_RENDERERS.get(section)
    if renderer is None:
        st.error(f"未知功能：{section}")
        return
    _prepare_runtime(email, password, env)
    renderer(email, password, env)
