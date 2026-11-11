# -*- coding: utf-8 -*-
"""整理姓名／電話連結：任一 Google Sheet 工作表，姓名加 LINE 聊天連結、電話加後台訂單管理電話查詢連結。

更新記錄：
2026-11-11（新增）
- 輸入 Google Sheet 網址或 ID、工作表名稱、姓名欄、電話欄（LINE 欄可選）、起訖列。
- 先預覽要改的儲存格，確認後才寫入；已經是連結（=HYPERLINK）的不動。
- LINE 網址：有指定 LINE 欄就用該列的網址，否則用電話查後台訂單管理取得（用上方登入的後台帳號）。
- 快速帶入：清潔客訴、評價預約（台北／台中）的欄位設定。
"""
import streamlit as st

from function.ui_common import step, info_panel

PRESETS = {
    "自訂": None,
    "清潔客訴（台北／台中）": dict(tab="清潔客訴", name="G", phone="H", line="", first=3),
    "評價預約（台北）": dict(tab="評價預約", name="C", phone="D", line="K", first=2),
    "評價預約（台中）": dict(tab="評價預約", name="A", phone="E", line="J", first=1),
}


def _apply_preset():
    preset = PRESETS.get(st.session_state.get("sl_preset"))
    if preset:
        st.session_state.sl_tab = preset["tab"]
        st.session_state.sl_name = preset["name"]
        st.session_state.sl_phone = preset["phone"]
        st.session_state.sl_line = preset["line"]
        st.session_state.sl_first = preset["first"]
    st.session_state.pop("sl_plan", None)


def render(backend_email, backend_password, env):
    from shared import rating_schedule as rs

    step("1", "整理姓名／電話連結")
    info_panel("使用說明", [
        "姓名加上 LINE 聊天連結，電話加上後台訂單管理的電話查詢連結。",
        "可用在任何工作表：貼 Google Sheet 網址或 ID，填工作表名稱與欄位字母。",
        "LINE 網址：有填 LINE 欄就用該列的網址，沒有就用電話查後台訂單（請先在上方輸入後台帳密）。",
        "已經是連結的儲存格不會改；先按「預覽」確認，再按「寫入」。",
        "服務帳號需要有該試算表的編輯權限。",
    ])
    st.session_state.setdefault("sl_first", 2)
    st.selectbox("快速帶入", list(PRESETS), key="sl_preset", on_change=_apply_preset)
    st.text_input("Google Sheet 網址或 ID", key="sl_sheet",
                  placeholder="https://docs.google.com/spreadsheets/d/…")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.text_input("工作表名稱", key="sl_tab")
    with c2:
        st.text_input("姓名欄", key="sl_name", placeholder="例如 G")
    with c3:
        st.text_input("電話欄", key="sl_phone", placeholder="例如 H")
    with c4:
        st.text_input("LINE 欄（可留空）", key="sl_line")
    c5, c6 = st.columns(2)
    with c5:
        st.number_input("起始列", min_value=1, step=1, key="sl_first")
    with c6:
        st.number_input("結束列（0＝到最後一筆）", min_value=0, step=1, key="sl_last")

    if st.button("🔍 預覽", key="sl_preview", use_container_width=True):
        st.session_state.pop("sl_plan", None)
        try:
            if not backend_email.strip() or not backend_password.strip():
                raise ValueError("請先在上方輸入後台帳號密碼（查 LINE 連結用）")
            name_col = rs.col_index(st.session_state.sl_name)
            phone_col = rs.col_index(st.session_state.sl_phone)
            line_text = str(st.session_state.get("sl_line", "") or "").strip()
            line_col = rs.col_index(line_text) if line_text else 0
            key = rs.spreadsheet_key(st.session_state.sl_sheet)
            tab = str(st.session_state.sl_tab or "").strip()
            if not tab:
                raise ValueError("請填工作表名稱")
            from shared.gsheet import build_gsheet_client

            with st.spinner("讀取工作表、查詢 LINE 連結中…（筆數多時需要一點時間）"):
                ws = build_gsheet_client().open_by_key(key).worksheet(tab)
                session, base_url = rs.login_session(backend_email.strip(), backend_password.strip(), env)
                updates = rs.plan_sheet_links(ws, session, base_url, name_col, phone_col,
                                              int(st.session_state.sl_first), int(st.session_state.sl_last or 0),
                                              line_col)
            st.session_state.sl_plan = {"key": key, "tab": tab, "updates": updates}
        except Exception as exc:
            st.error(f"預覽失敗：{exc}")

    plan = st.session_state.get("sl_plan")
    if plan is None:
        return
    updates = plan["updates"]
    if not updates:
        st.info("沒有需要更新的儲存格（都已是連結，或查不到電話／LINE）。")
        return
    names = sum(1 for u in updates if "chat.line.biz" in u["values"][0][0])
    st.success(f"將更新 {len(updates)} 格：姓名 LINE 連結 {names} 格、電話查詢連結 {len(updates) - names} 格")
    st.dataframe([{"儲存格": u["range"], "新內容": u["values"][0][0]} for u in updates[:500]],
                 use_container_width=True, hide_index=True)
    if len(updates) > 500:
        st.caption(f"只顯示前 500 格（共 {len(updates)} 格）")
    if st.button(f"✍️ 寫入 {plan['tab']}（{len(updates)} 格）", key="sl_write", type="primary",
                 use_container_width=True):
        try:
            from shared.gsheet import build_gsheet_client

            ws = build_gsheet_client().open_by_key(plan["key"]).worksheet(plan["tab"])
            rs.apply_updates(ws, updates)
            st.success(f"✅ 已寫入 {len(updates)} 格")
            st.session_state.pop("sl_plan", None)
        except Exception as exc:
            st.error(f"寫入失敗：{exc}")
