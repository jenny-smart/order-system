# ============================================================
# 檔名：function/line_notice_generator.py
# 功能：LINE 通知產生器；依單筆／多筆訂單編號產生客戶通知訊息。
# 更新時間：2026-08-19
# ============================================================
# -*- coding: utf-8 -*-
import streamlit as st
from shared import notification_service
from function.ui_common import step, info_panel, copy_button, NJ_MEMO


def render(backend_email, backend_password, env):
    step("3", "LINE 通知產生器")
    col_left, col_right = st.columns([3, 1])
    with col_left:
        info_panel("使用說明", ["輸入已成立訂單編號，每行一個，可一次輸入多筆。", "系統讀取訂單日期、地址、付款方式與金額，區域由地址自動判斷。"])
        line_order_nos_input = st.text_area("訂單編號（每行一個）", value="", height=120, placeholder="LC00211537\nLC00211538", key="line_order_nos")
        if st.button("產生 LINE 訊息", width="stretch", key="make-line-from-order-no"):
            if not backend_email.strip() or not backend_password.strip():
                st.error("請先輸入後台帳號密碼")
            else:
                raw_lines = [x.strip() for x in line_order_nos_input.splitlines() if x.strip()]
                order_groups = []
                for line in raw_lines:
                    nos = [n.strip() for n in line.split(",") if n.strip()]
                    if nos: order_groups.append(nos)
                if not order_groups:
                    st.error("請輸入至少一個訂單編號")
                else:
                    st.session_state.line_from_order_nos_results = []
                    for _k in list(st.session_state.keys()):
                        if _k.startswith("line_text_") or _k.startswith("nj_memo_"): del st.session_state[_k]
                    results_list = []
                    for nos in order_groups:
                        label = "、".join(nos)
                        try:
                            with st.spinner(f"查詢訂單 {label}…"):
                                line_result, line_text = notification_service.build_combined_line_message_from_order_nos(env_name=env, backend_email=backend_email.strip(), backend_password=backend_password.strip(), order_nos=nos)
                            safe_result = {k: v for k, v in line_result.items() if k != "session"}
                            results_list.append({"order_no": label, "result": safe_result, "text": line_text, "error": None})
                        except Exception as e:
                            results_list.append({"order_no": label, "result": None, "text": "", "error": str(e)})
                    st.session_state.line_from_order_nos_results = results_list
                    st.rerun()
    with col_right:
        st.markdown('<div class="sec-label">N-J Memo</div>', unsafe_allow_html=True)
        st.text_area("N-J Memo", NJ_MEMO, height=220, key="nj_memo_fixed", label_visibility="collapsed")
        copy_button("複製 N-J Memo", NJ_MEMO, "copy-nj-memo-fixed")
    results_list = st.session_state.get("line_from_order_nos_results", [])
    for idx, item in enumerate(results_list):
        if item["error"]:
            st.error(f"訂單 {item['order_no']} 產生失敗：{item['error']}"); continue
        line_result, line_text = item["result"], item["text"]
        all_nos = line_result.get("all_order_nos") or [line_result.get("order_no")]
        order_no_display = "、".join(str(n) for n in all_nos if n)
        is_combined, is_multi_date = len(all_nos) > 1, line_result.get("multi_date", False)
        combined_note = "　⚠️ 跨日合併單" if (is_combined and is_multi_date) else ("　⚠️ 同日合併單" if is_combined else "")
        st.caption(f"訂單：{order_no_display}{combined_note}　付款方式：{line_result.get('payway')}　區域：{line_result.get('region')}　金額：{line_result.get('service_amount') or '—'}　車馬費：{line_result.get('fare') or '0'}")
        st.text_area(f"LINE 訊息（{line_result.get('order_no')}）", line_text, height=380, label_visibility="collapsed")
        copy_button("複製 LINE 訊息", line_text, f"copy-line-msg-{idx}")
        if idx < len(results_list) - 1: st.markdown("<hr>", unsafe_allow_html=True)
