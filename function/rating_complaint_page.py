# -*- coding: utf-8 -*-
"""評價管理客訴：評價管理中「尚可／不滿意」或「滿意但有負面意見」的評價，登記到內勤工作表單「清潔客訴」。

更新記錄：
2026-11-11（新增）
- 與上班日 07:00 排程（shared/rating_schedule.py job=complaint）相同規則，可手動選地區與評價時間區間。
- 先預覽（新增／已登記略過、登記原因），確認後插入「清潔客訴」最後一筆客訴之後；可勾選記行事曆。
- 姓名帶 LINE 連結、電話帶訂單管理電話查詢連結。
"""
from datetime import datetime, time

import streamlit as st

from function.ui_common import step, info_panel


def render(backend_email, backend_password, env):
    from shared import rating_schedule as rs
    from shared.weekend_reminder_schedule import load_work_calendar

    step("1", "評價管理客訴")
    info_panel("使用說明", [
        "搜尋評價管理在指定「評價時間」區間內，服務滿意度為「尚可」「不滿意」，"
        "或「滿意」但評價項目非正面／意見有負面字詞（例：不乾淨、沒擦、效率不好）的評價。",
        "後台帳密決定查哪一區的評價，請選擇對應地區的內勤工作表單。",
        "先預覽，確認後寫入「清潔客訴」（插在最後一筆客訴之後）；已登記過的自動略過。",
        "上班日 07:00 會自動跑一次（前一上班日 07:00～今天 07:00）。",
    ])
    today = datetime.now(rs.TZ).date()
    try:
        default_start = rs.query_window(today, load_work_calendar())[0].date()
    except Exception:
        default_start = today
    region = st.selectbox("地區（內勤工作表單）", list(rs.REGIONS), key="rc_region")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        d_s = st.date_input("評價日期-起", value=default_start, key="rc_ds")
    with c2:
        t_s = st.time_input("時間-起", value=time(7, 0), key="rc_ts")
    with c3:
        d_e = st.date_input("評價日期-迄", value=today, key="rc_de")
    with c4:
        t_e = st.time_input("時間-迄", value=time(7, 0), key="rc_te")
    window = (datetime.combine(d_s, t_s), datetime.combine(d_e, t_e))

    if st.button("🔍 預覽", key="rc_preview", use_container_width=True):
        st.session_state.pop("rc_plan", None)
        try:
            if not backend_email.strip() or not backend_password.strip():
                raise ValueError("請先在上方輸入後台帳號密碼")
            if window[0] >= window[1]:
                raise ValueError("起始時間要早於結束時間")
            with st.spinner("查詢評價與訂單中…"):
                session, base_url = rs.login_session(backend_email.strip(), backend_password.strip(), env)
                plan = rs.plan_complaints(region, session, base_url, window)
            st.session_state.rc_plan = {"plan": plan, "window": window, "region": region}
        except Exception as exc:
            st.error(f"預覽失敗：{exc}")

    saved = st.session_state.pop("rc_saved", None)
    if saved:
        st.success(saved)
    state = st.session_state.get("rc_plan")
    if not state:
        return
    plan = state["plan"]
    st.caption(f"{state['region']}｜{state['window'][0]:%m/%d %H:%M} ～ {state['window'][1]:%m/%d %H:%M}｜"
               f"區間評價 {plan['ratings']} 筆")
    if not plan["preview"]:
        st.info("這個區間沒有需要登記的評價。")
        return
    st.dataframe(plan["preview"], use_container_width=True, hide_index=True)
    n = len(plan["rows"])
    st.markdown(f"[開啟清潔客訴分頁]({plan['sheet_url']})")
    if not n:
        st.info("都已登記過，沒有要新增的列。")
        return
    add_calendar = st.checkbox("寫入後記 jenny@hers.com.tw 行事曆", value=True, key="rc_calendar")
    if st.button(f"✍️ 寫入清潔客訴（新增 {n} 筆）", key="rc_write", type="primary", use_container_width=True):
        try:
            rs.write_complaints(plan)
            msg = f"✅ {state['region']} 清潔客訴已新增 {n} 筆"
            if add_calendar:
                result = {state["region"]: {"saved": n, "sheet_url": plan["sheet_url"], "error": "",
                                            "summary_lines": plan["summary_lines"]}}
                msg += "；" + "；".join(rs.write_calendar("complaint", result, state["window"], datetime.now(rs.TZ)))
            st.session_state.rc_saved = msg
            st.session_state.pop("rc_plan", None)
            st.rerun()
        except Exception as exc:
            st.error(f"寫入失敗：{exc}")
