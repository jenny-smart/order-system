# -*- coding: utf-8 -*-
"""查詢無LINE連結訂單。"""

import streamlit as st

from orders import find_orders_without_line_link
from function.ui_common import step, info_panel


def render(backend_email, backend_password, env):
    step("3", "查詢無LINE連結訂單")
    info_panel("功能說明", [
        "搜尋訂購資訊裡沒有LINE連結的訂單，列出訂單編號/姓名/電話。",
        "三種日期區間都可以留空不篩，訂購日期/付款日期/服務日期各自獨立，"
        "可以只填其中一種，也可以同時填多種（會同時套用）。",
    ])

    st.markdown("**訂購日期區間**")
    nl_col1, nl_col2 = st.columns(2)
    with nl_col1:
        nl_date_s = st.date_input("訂購日期-起", value=None, key="nl_date_s")
    with nl_col2:
        nl_date_e = st.date_input("訂購日期-迄", value=None, key="nl_date_e")

    st.markdown("**付款日期區間**")
    nl_col3, nl_col4 = st.columns(2)
    with nl_col3:
        nl_paid_s = st.date_input("付款日期-起", value=None, key="nl_paid_s")
    with nl_col4:
        nl_paid_e = st.date_input("付款日期-迄", value=None, key="nl_paid_e")

    st.markdown("**服務日期區間**")
    nl_col5, nl_col6 = st.columns(2)
    with nl_col5:
        nl_clean_s = st.date_input("服務日期-起", value=None, key="nl_clean_s")
    with nl_col6:
        nl_clean_e = st.date_input("服務日期-迄", value=None, key="nl_clean_e")

    if st.button("🔍 開始搜尋", use_container_width=True, key="nl_run_btn", type="primary"):
        if not backend_email.strip() or not backend_password.strip():
            st.error("請先在上方輸入後台帳號密碼")
        else:
            try:
                with st.spinner("登入後台 → 搜尋訂單中（依篩選範圍大小，可能需要一點時間）…"):
                    nl_results, nl_debug = find_orders_without_line_link(
                        env_name=env,
                        backend_email=backend_email.strip(),
                        backend_password=backend_password.strip(),
                        date_s=nl_date_s.strftime("%Y-%m-%d") if nl_date_s else None,
                        date_e=nl_date_e.strftime("%Y-%m-%d") if nl_date_e else None,
                        paid_at_s=nl_paid_s.strftime("%Y-%m-%d") if nl_paid_s else None,
                        paid_at_e=nl_paid_e.strftime("%Y-%m-%d") if nl_paid_e else None,
                        clean_date_s=nl_clean_s.strftime("%Y-%m-%d") if nl_clean_s else None,
                        clean_date_e=nl_clean_e.strftime("%Y-%m-%d") if nl_clean_e else None,
                        return_debug=True,
                    )
                st.session_state.nl_results = nl_results
                st.session_state.nl_debug = nl_debug
            except Exception as e:
                st.error(f"搜尋失敗：{e}")

    nl_results = st.session_state.get("nl_results")
    nl_debug = st.session_state.get("nl_debug")
    if nl_debug is not None:
        st.caption(
            f"🔧 除錯資訊：環境＝{nl_debug['env']}，實際連線＝{nl_debug['base_url']}，"
            f"後台掃描到候選訂單 {nl_debug['scanned_candidates']} 筆，"
            f"符合「沒有LINE連結」{nl_debug['matched_without_line']} 筆。"
            "（如果候選訂單是 0 筆，代表問題出在登入/篩選這一關，不是真的都有 LINE 連結）"
        )
        if nl_debug.get("hit_page_limit"):
            st.warning(
                f"⚠️ 掃描撞到頁數上限（80 頁）就停了，代表符合篩選條件的候選訂單可能還有更多"
                "沒掃到，結果可能不完整。建議縮小日期範圍，或請 Claude 調高 max_pages。"
            )
    if nl_results is not None:
        if nl_results:
            st.warning(f"⚠️ 找到 {len(nl_results)} 筆沒有LINE連結的訂單：")
            st.dataframe(
                [{"訂單編號": r["order_no"], "姓名": r["name"], "電話": r["phone"]} for r in nl_results],
                use_container_width=True, hide_index=True,
            )
        else:
            st.success("✅ 這個篩選範圍內的訂單都有LINE連結。")
