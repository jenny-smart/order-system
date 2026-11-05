# -*- coding: utf-8 -*-
"""後台／Google 日曆雙向比對。"""

from datetime import date, timedelta
from urllib.parse import quote

import streamlit as st

from shared.env_config import compute_env_urls
from orders import (
    PURCHASE_FILTER_PARAMS_TEMPLATE,
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
        _render_result(cc_result, compute_env_urls(env)["BASE_URL"])


# ---------- 檢查結果：表格呈現＋後台／會員／日曆連結 ----------

CALENDAR_SEARCH_URL = "https://calendar.google.com/calendar/r/search?q="


def _order_url(base_url, order_no):
    order_no = str(order_no or "").strip()
    return f"{base_url}/purchase?orderNo={order_no}" if order_no else None


def _member_url(base_url, phone, name):
    """後台訂單管理依電話（無電話改姓名）查詢的結果頁。
    帶上完整搜尋表單欄位（未填為空字串），避免後台套用預設日期篩選；
    中文不轉碼，表格才顯示得出姓名。"""
    phone = str(phone or "").strip()
    name = "" if phone else str(name or "").strip()
    if not phone and not name:
        return None
    params = dict(PURCHASE_FILTER_PARAMS_TEMPLATE, phone=phone, name=name)
    return f"{base_url}/purchase?" + "&".join(f"{k}={v}" for k, v in params.items())


def _calendar_search_url(name, phone):
    """Google 日曆搜尋該客人；日曆事件標題是「姓名-地址標籤,電話」，以姓名搜尋最穩。"""
    keyword = str(name or "").strip() or str(phone or "").strip()
    return CALENDAR_SEARCH_URL + quote(keyword) if keyword else None


def build_issue_rows(cc_result, base_url):
    """把比對結果整理成三張表的列（純函式，方便測試）。"""
    def row(item, order_no, extra=None):
        out = {
            "訂單編號": _order_url(base_url, order_no),
            "姓名": item.get("name", "") or "",
            "會員": _member_url(base_url, item.get("phone"), item.get("name")),
            "LINE": item.get("line_url") or None,
            "服務日期": item.get("service_date", ""),
            "時段": item.get("service_time", ""),
            "區域": item.get("region", ""),
            "地址": item.get("address", ""),
            "異常說明": item.get("reason") or item.get("issue", ""),
            "查日曆": _calendar_search_url(item.get("name"), item.get("phone")),
        }
        out.update(extra or {})
        return out

    duplicates = []
    for idx, item in enumerate(cc_result.get("backend_duplicates") or [], 1):
        for order_no in item.get("order_nos") or []:
            duplicates.append(row(item, order_no, {"組別": f"第 {idx} 組"}))
    backend_missing = [row(item, item.get("order_no"))
                       for item in cc_result.get("backend_missing_in_calendar") or []]
    calendar_missing = [row(item, item.get("order_no"), {
        "日曆事件": item.get("event_link") or None,
        "日曆標題": item.get("event_summary", ""),
    }) for item in cc_result.get("calendar_missing_in_backend") or []]
    return {
        "duplicates": duplicates,
        "backend_missing": backend_missing,
        "calendar_missing": calendar_missing,
    }


_COLUMN_CONFIG = {
    "組別": st.column_config.TextColumn("組別", width="small"),
    "訂單編號": st.column_config.LinkColumn(
        "訂單編號", display_text=r"orderNo=(.+)$", help="點擊開啟後台該筆訂單"),
    "姓名": st.column_config.TextColumn("姓名", width="small"),
    "會員": st.column_config.LinkColumn(
        "電話", display_text=r"[?&](?:phone|name)=([^&]+)", help="點擊開啟後台訂單管理，查此人的訂單"),
    "LINE": st.column_config.LinkColumn("LINE@", display_text="💬 開啟聊天", help="開啟客人的 LINE@ 聊天"),
    "服務日期": st.column_config.TextColumn("服務日期", width="small"),
    "時段": st.column_config.TextColumn("時段", width="small"),
    "區域": st.column_config.TextColumn("區域", width="small"),
    "地址": st.column_config.TextColumn("地址", width="large"),
    "異常說明": st.column_config.TextColumn("異常說明", width="medium"),
    "查日曆": st.column_config.LinkColumn(
        "日曆", display_text="🔍 查此人", help="在 Google 日曆搜尋這位客人"),
    "日曆事件": st.column_config.LinkColumn("日曆事件", display_text="📅 開啟事件"),
    "日曆標題": st.column_config.TextColumn("日曆標題", width="medium"),
}


def _issue_table(rows, columns, key):
    st.dataframe(
        [{c: r.get(c) for c in columns} for r in rows],
        column_config={c: _COLUMN_CONFIG[c] for c in columns},
        column_order=columns,
        hide_index=True,
        width="stretch",
        key=key,
    )


def _render_result(cc_result, base_url):
    st.markdown("#### 檢查結果")
    tables = build_issue_rows(cc_result, base_url)
    n_dup = len(cc_result.get("backend_duplicates") or [])
    n_bm = len(tables["backend_missing"])
    n_cm = len(tables["calendar_missing"])
    if not (n_dup or n_bm or n_cm):
        st.success("✅ 檢查通過，後台已付款訂單與 Google 日曆黃色事件皆一一對應。")
        return

    m1, m2, m3 = st.columns(3)
    m1.metric("後台重複（組）", n_dup)
    m2.metric("後台有、日曆沒有", n_bm)
    m3.metric("日曆有、後台沒有", n_cm)
    st.caption("訂單編號 → 後台訂單；電話 → 後台訂單管理查此人訂單；💬 → 客人 LINE@ 聊天；🔍 → Google 日曆搜尋此人（需在日曆勾選該區日曆才搜得到）。")

    base_cols = ["訂單編號", "姓名", "會員", "LINE", "服務日期", "時段", "區域", "地址"]
    tab_specs = [
        (f"後台重複（{n_dup}）", tables["duplicates"],
         ["組別"] + base_cols + ["查日曆"], "cc_tbl_dup"),
        (f"後台有、日曆沒有（{n_bm}）", tables["backend_missing"],
         base_cols + ["異常說明", "查日曆"], "cc_tbl_bm"),
        (f"日曆有、後台沒有（{n_cm}）", tables["calendar_missing"],
         ["日曆事件", "日曆標題"] + base_cols + ["異常說明", "查日曆"], "cc_tbl_cm"),
    ]
    tabs = st.tabs([label for label, *_ in tab_specs])
    for tab, (label, rows, columns, key) in zip(tabs, tab_specs):
        with tab:
            if rows:
                _issue_table(rows, columns, key)
            else:
                st.success("沒有異常")
