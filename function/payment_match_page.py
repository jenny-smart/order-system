# -*- coding: utf-8 -*-
"""付款後5碼及星和診所比對（獨立對帳功能）。"""

import importlib
from datetime import date

import streamlit as st

from memo_system import payment_match
from function.ui_common import step
from function.memo_shared import get_session


def render(backend_email, backend_password, env):
    global payment_match
    payment_match = importlib.reload(payment_match)
    email, env_option = backend_email, env
    step("3", "付款後5碼及星和診所比對（獨立功能）")
    st.caption("固定付款方式 ATM；查詢結果寫入 K:S，不使用原 ATM 待付款清單。")
    today = date.today()
    c1, c2, c3, c4 = st.columns(4)
    with c1: region = st.selectbox("地區", ["台北", "台中", "桃園", "新竹", "高雄"], key="payment_match_region")
    with c2: paid_start = st.date_input("付款日期-起", value=today.replace(day=1), key="payment_match_start")
    with c3: paid_end = st.date_input("付款日期-迄", value=today, key="payment_match_end")
    with c4: status_label = st.selectbox("付款狀態", ["已付款", "待付款"], key="payment_match_status")

    search_btn = st.button("🔍 搜尋付款訂單", use_container_width=True, disabled=not st.session_state.credentials_ready, key="payment_match_search")
    log_box_local = st.empty()

    def payment_log(msg):
        st.session_state.logs.append(str(msg))
        try: log_box_local.text("\n".join(st.session_state.logs[-2000:]))
        except Exception: pass

    current_context = (region, str(email or "").strip().lower())
    if st.session_state.get("payment_match_context") != current_context:
        st.session_state.payment_match_rows = None

    if search_btn:
        try:
            st.session_state.logs = []
            session = get_session(email, env_option, ui_logger=payment_log)
            st.session_state.payment_match_rows = payment_match.search_orders(
                session, paid_start.strftime("%Y-%m-%d"), paid_end.strftime("%Y-%m-%d"),
                "1" if status_label == "已付款" else "0",
                region=region, login_email=email, ui_logger=payment_log,
            )
            st.session_state.payment_match_context = current_context
        except Exception as exc:
            payment_log(f"❌ 查詢失敗：{exc}")
            st.error(str(exc))

    rows = st.session_state.get("payment_match_rows")
    if rows is not None:
        st.metric("查到筆數", len(rows))
        if rows:
            st.dataframe(rows, use_container_width=True, hide_index=True)
            if st.button("📥 貼到 K:S 待比對區", type="primary", use_container_width=True, key="payment_match_paste"):
                try:
                    result = payment_match.paste_orders(region, rows, ui_logger=payment_log)
                    st.success(f"已從第 {result['start_row']} 列貼上 {result['pasted']} 筆。")
                except Exception as exc:
                    st.error(f"貼上失敗：{exc}")

    if st.button("🔗 比對銀行 B:H 與訂單 K:S", use_container_width=True, key="payment_match_run"):
        try:
            result = payment_match.match_bank_rows(region, ui_logger=payment_log)
            st.success(f"完成：配對 {result['matched_orders']} 筆訂單；待人工確認 {result['review']} 列。")
        except Exception as exc:
            st.error(f"比對失敗：{exc}")

