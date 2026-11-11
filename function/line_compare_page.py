# -*- coding: utf-8 -*-
"""代客預訂 LINE 比對（第一步）：撈出待比對的代客預訂訂單，貼到內勤工作表單「line比對」分頁。

更新記錄：
2026-11-12（新增）
- 選地區與訂購日期區間（預設今天），查已付款／待付款且卡片上方有「代客預訂」的訂單。
- 先預覽（新增／已在工作表），確認後貼到「line比對」分頁最下方；訂購人帶 LINE 連結、
  電話號碼帶訂單管理電話搜尋連結。「比對對話結果」留白，下一步做 LINE 對話比對時再填。
"""
from datetime import datetime

import streamlit as st

from function.ui_common import step, info_panel


def render(backend_email, backend_password, env):
    from memo_system import memo
    from shared import line_compare_sheet as lc

    step("1", "代客預訂 LINE 比對：撈出待比對訂單")
    info_panel("使用說明", [
        "依訂購日期區間查詢付款狀態「已付款」「待付款」的訂單，只留訂單上方有「代客預訂：○○」的訂單。",
        "後台帳密決定查哪一區的訂單，請選擇對應地區的內勤工作表單。",
        "先預覽，確認後貼到「line比對」分頁最下方；訂單編號已在分頁上的自動略過。",
        "訂購人可點開客人 LINE 對話、電話號碼可點開訂單管理的電話搜尋結果。",
        "「訂單金額（推算人數）」的人數是依金額、時數與單價推算；「比對對話結果」先留白。只查詢，不會修改後台。",
    ])
    today = datetime.now(lc.TZ).date()
    region = st.selectbox("地區（內勤工作表單）", list(lc.REGIONS), key="lcmp_region")
    c1, c2 = st.columns(2)
    with c1:
        start = st.date_input("訂購日期-起", value=today, key="lcmp_start")
    with c2:
        end = st.date_input("訂購日期-迄", value=today, key="lcmp_end")

    if st.button("🔍 預覽", key="lcmp_preview", use_container_width=True):
        st.session_state.pop("lcmp_plan", None)
        logs = []
        try:
            if not str(backend_email or "").strip() or not str(backend_password or "").strip():
                raise ValueError("請先在上方輸入後台帳號密碼")
            if not start or not end:
                raise ValueError("請選擇完整的訂購日期區間")
            memo.set_env(env)
            memo.set_runtime_credentials(backend_email.strip(), backend_password.strip())
            with st.spinner("查詢後台訂單中…"):
                session = memo.login()
                result = lc.plan(region, session, memo.BASE_URL, start, end, log=logs.append)
            st.session_state.lcmp_plan = {"plan": result, "start": start, "end": end, "logs": logs}
        except Exception as exc:
            st.error(f"預覽失敗：{exc}")

    saved = st.session_state.pop("lcmp_saved", None)
    if saved:
        st.success(saved)
    state = st.session_state.get("lcmp_plan")
    if not state:
        return
    result = state["plan"]
    st.caption(f"{result['region']}｜訂購日期 {state['start']:%Y/%m/%d} ～ {state['end']:%Y/%m/%d}｜"
               f"代客預訂 {len(result['rows'])} 筆")
    with st.expander("查詢 LOG"):
        st.text("\n".join(state["logs"]) or "（無）")
    st.markdown(f"[開啟 line比對 分頁]({result['sheet_url']})")
    if not result["preview"]:
        st.info("這個區間沒有已付款／待付款的代客預訂訂單。")
        return
    st.dataframe(
        result["preview"], use_container_width=True, hide_index=True,
        column_config={"LINE連結": st.column_config.LinkColumn("LINE連結", display_text="開啟對話")},
    )
    n = len(result["new_rows"])
    if not n:
        st.info("都已在工作表上，沒有要新增的列。")
        return
    if st.button(f"✍️ 貼到 line比對（新增 {n} 筆）", key="lcmp_write", type="primary", use_container_width=True):
        try:
            count = lc.write(result)
            st.session_state.lcmp_saved = f"✅ {result['region']} line比對已新增 {count} 筆"
            st.session_state.pop("lcmp_plan", None)
            st.rerun()
        except Exception as exc:
            st.error(f"寫入失敗：{exc}")
