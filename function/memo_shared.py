# -*- coding: utf-8 -*-
"""memo 系統各功能共用的登入 session 快取（登入本身由 memo_system/ui.py 的
Step 1 設定好 shared.memo_backend.set_runtime_credentials／set_env 之後，這裡
只負責沿用或視帳號／環境是否切換重新登入）。"""

import streamlit as st

from shared import memo_backend as memo

DEFAULT_RESULT = {
    "processed": 0, "success": 0, "failed": 0,
    "skipped": 0, "updated_orders": 0, "errors": [],
}


def normalize_result(r):
    base = DEFAULT_RESULT.copy()
    if isinstance(r, dict):
        base.update(r)
    if not isinstance(base.get("errors"), list):
        base["errors"] = []
    return base


def get_session(email, env_option, ui_logger=None):
    desired_email = str(email or "").strip()
    desired_env = str(env_option or "prod").strip()
    if (st.session_state.auth_session is not None
            and (st.session_state.get("auth_email") != desired_email
                 or st.session_state.get("auth_env") != desired_env)):
        st.session_state.auth_session = None
        st.session_state.is_logged_in = False
    if st.session_state.auth_session is not None:
        return st.session_state.auth_session
    if not st.session_state.get("credentials_ready"):
        raise RuntimeError("請先在「登入」區塊輸入帳號密碼")
    session = memo.login(ui_logger=ui_logger)
    st.session_state.auth_session = session
    st.session_state.is_logged_in = True
    st.session_state.login_identity = desired_email
    st.session_state.auth_email = desired_email
    st.session_state.auth_env = desired_env
    return session
