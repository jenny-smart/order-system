# ============================================================
# 檔名：vip_calendar_test_app.py
# 功能：VIP 訂單／Google Calendar 同步測試入口；正式整併完成後刪除。
# 更新時間：2026-08-19
# ============================================================
# -*- coding: utf-8 -*-
from datetime import date, timedelta
import calendar

import streamlit as st
import function.vip_calendar_sync as vcs
from function.vip_calendar_patch_bundle import apply_all

# Streamlit 會重跑腳本；同一程序只套一次 patch。
if not getattr(vcs, "_vip_patches_applied", False):
    apply_all(vcs)
    vcs._vip_patches_applied = True

st.set_page_config(page_title="VIP 訂單／Google 日曆同步測試", layout="wide")
st.title("VIP 訂單／Google 日曆同步測試")

col1, col2, col3 = st.columns([3.2, 3.2, 1.2])
with col1:
    backend_email = st.text_input("後台帳號")
with col2:
    backend_password = st.text_input("後台密碼", type="password")
with col3:
    env_label = st.selectbox("環境", ["prod（正式機 backend）", "dev（測試機 backend-dev）"], index=1)
    env = "dev" if env_label.startswith("dev") else "prod"

st.divider()
query_mode = st.radio("查詢方式", ["月份", "日期區間"], horizontal=True, key="vipcal_query_mode")
today = date.today()

if query_mode == "月份":
    year_options = list(range(today.year - 1, today.year + 3))
    q1, q2 = st.columns(2)
    with q1:
        query_year = st.selectbox("年份", year_options, index=year_options.index(today.year), key="vipcal_query_year")
    with q2:
        query_month = st.selectbox("月份", list(range(1, 13)), index=today.month - 1, format_func=lambda m: f"{m} 月", key="vipcal_query_month")
    last_day = calendar.monthrange(int(query_year), int(query_month))[1]
    query_date_s = date(int(query_year), int(query_month), 1)
    query_date_e = date(int(query_year), int(query_month), last_day)
else:
    r1, r2 = st.columns(2)
    with r1:
        query_date_s = st.date_input("查詢起日", value=today - timedelta(days=30), key="vipcal_range_s")
    with r2:
        query_date_e = st.date_input("查詢迄日", value=today + timedelta(days=90), key="vipcal_range_e")
    if query_date_s > query_date_e:
        st.error("查詢起日不可晚於查詢迄日")
        st.stop()

st.session_state["vipcal_query_date_s"] = query_date_s.isoformat()
st.session_state["vipcal_query_date_e"] = query_date_e.isoformat()
st.caption(f"查詢範圍：{query_date_s.isoformat()} ～ {query_date_e.isoformat()}")

vcs.render_vip_calendar_sync(backend_email.strip(), backend_password.strip(), env)
