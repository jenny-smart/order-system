# -*- coding: utf-8 -*-
"""後台／Google 日曆雙向比對。"""

from datetime import date, timedelta

import streamlit as st

from orders import (
    format_calendar_consistency_issue,
    get_calendar_compare_allowed_region,
    run_backend_calendar_consistency_check,
)
from function.ui_common import step, info_panel


def render(backend_email, backend_password, env, google_calendar_map):
    step("3", "後台／Google 日曆雙向比對")
    info_panel("功能說明", [
        "以 Google 日曆事件的時間與顏色為比對基準（沿用既有慣例：紫色＝未安排、"
        "黃色＝已安排、綠色＝暫停），只有黃色事件代表「已安排／應該已成單」，"
        "才會拿來跟後台已付款訂單互相比對。",
        "後台反查以該月份日曆曾出現的人員為母名單，非日曆管理客戶不列異常。",
        "日曆姓名後方的「-XXXX」視為地址標籤，例如「陳靜萱-文山區」會和後台文山區地址配對。",
        "方向一（後台有、日曆沒有）：後台這段服務日期區間內的已付款訂單，"
        "找不到同一人／地址／日期時段完全相符的黃色日曆事件。",
        "方向二（日曆有、後台沒有）：日曆這段期間的黃色事件，找不到日期／時段"
        "且同一人／地址／日期時段相符的後台已付款訂單。",
        "後台若同一人／地址／日期時段出現多筆訂單，也會另外列為異常。",
        "同一筆不一致只會顯示一次，不會在兩個方向重複列錯。",
        "只能比對已設定 Google Calendar ID 的區域（目前為：" + "、".join(google_calendar_map.keys()) + "）。",
    ])

    cc_date_c1, cc_date_c2 = st.columns(2)
    with cc_date_c1:
        cc_date_s = st.date_input("服務日期-起", value=date.today(), key="cc_date_s")
    with cc_date_c2:
        cc_date_e = st.date_input("服務日期-迄", value=date.today() + timedelta(days=7), key="cc_date_e")
    cc_allowed_region = get_calendar_compare_allowed_region(backend_email)
    cc_region_options = [cc_allowed_region] if cc_allowed_region else ["全部"] + list(google_calendar_map.keys())
    cc_region = st.selectbox("比對區域", cc_region_options, key="cc_region")
    if cc_allowed_region:
        st.caption(f"此登入帳號只能比對{cc_allowed_region}區。")

    if st.button("🔍 開始雙向比對", use_container_width=True, key="cc_run_btn", type="primary"):
        if not backend_email.strip() or not backend_password.strip():
            st.error("請先在上方輸入後台帳號密碼")
        elif cc_date_s > cc_date_e:
            st.error("服務日期起日不可晚於迄日")
        else:
            try:
                with st.spinner("登入後台、查詢已付款訂單並讀取 Google 日曆事件，雙向比對中…"):
                    cc_result = run_backend_calendar_consistency_check(
                        env_name=env,
                        backend_email=backend_email.strip(),
                        backend_password=backend_password.strip(),
                        date_range_start=cc_date_s.strftime("%Y-%m-%d"),
                        date_range_end=cc_date_e.strftime("%Y-%m-%d"),
                        region=None if cc_region == "全部" else cc_region,
                    )
                st.session_state.cc_result = cc_result
            except Exception as e:
                st.error(f"檢查失敗：{e}")

    cc_result = st.session_state.get("cc_result")
    if cc_result:
        st.markdown("#### 檢查結果")
        _backend_missing = cc_result.get("backend_missing_in_calendar") or []
        _calendar_missing = cc_result.get("calendar_missing_in_backend") or []
        _backend_duplicates = cc_result.get("backend_duplicates") or []
        if not _backend_missing and not _calendar_missing and not _backend_duplicates:
            st.success("✅ 檢查通過，後台已付款訂單與 Google 日曆黃色事件皆一一對應。")
        else:
            if _backend_duplicates:
                st.error(f"⚠️ 後台同人同址同日期時段重複：{len(_backend_duplicates)} 組")
                for _p in _backend_duplicates:
                    st.warning(format_calendar_consistency_issue(_p))
            if _backend_missing:
                st.error(f"⚠️ 後台有、日曆沒有：{len(_backend_missing)} 筆")
                for _p in _backend_missing:
                    st.warning(format_calendar_consistency_issue(_p))
            if _calendar_missing:
                st.error(f"⚠️ 日曆有、後台沒有：{len(_calendar_missing)} 筆")
                for _p in _calendar_missing:
                    st.warning(format_calendar_consistency_issue(_p))
                    if _p.get("event_link"):
                        st.link_button("開啟日曆事件", _p["event_link"], key=f"cc_event_{_p.get('event_link')}")
