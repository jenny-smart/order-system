# -*- coding: utf-8 -*-
"""專員隔日上班提醒。"""

from datetime import date, timedelta

import streamlit as st

from function.cleaner_reminders import find_paid_cleaner_reminders
from function.ui_common import step, info_panel, copy_button


def render(backend_email, backend_password, env):
    step("3", "專員隔日上班提醒")
    info_panel("操作方式", [
        "可設定服務日期區間；只納入已付款訂單，並把同一位專員跨日工作整合成一則訊息。",
        "系統會由專員名單及詳細資料讀取 LINE 連結；勾選名單後逐筆複製訊息並開啟聊天。",
        "此頁使用 LINE 官方帳號管理後台連結，因此由客服確認後人工送出。",
    ])
    cr_date_c1, cr_date_c2 = st.columns(2)
    with cr_date_c1:
        cr_service_date_s = st.date_input(
            "服務日期-起",
            value=date.today() + timedelta(days=1),
            key="cr_service_date_s",
        )
    with cr_date_c2:
        cr_service_date_e = st.date_input(
            "服務日期-迄",
            value=date.today() + timedelta(days=2),
            key="cr_service_date_e",
        )
    if st.button(
        "🔍 查詢已付款訂單並整合專員名單",
        use_container_width=True,
        type="primary",
        key="cr_search",
    ):
        if not backend_email.strip() or not backend_password.strip():
            st.error("請先在上方輸入後台帳號密碼")
        elif cr_service_date_s > cr_service_date_e:
            st.error("服務日期起日不可晚於迄日")
        else:
            try:
                with st.spinner("查詢已付款訂單與專員 LINE 資料…"):
                    _cleaner_rows, _cleaner_debug = find_paid_cleaner_reminders(
                        env,
                        backend_email.strip(),
                        backend_password.strip(),
                        cr_service_date_s.strftime("%Y-%m-%d"),
                        cr_service_date_e.strftime("%Y-%m-%d"),
                    )
                st.session_state.cr_rows = _cleaner_rows
                st.session_state.cr_debug = _cleaner_debug
                st.session_state.pop("cr_editor", None)
            except Exception as e:
                st.error(f"查詢失敗：{e}")

    cr_rows = st.session_state.get("cr_rows")
    if cr_rows is not None:
        _debug = st.session_state.get("cr_debug", {})
        st.caption(
            f"找到 {_debug.get('cleaner_count', 0)} 位專員，"
            f"共 {_debug.get('job_count', 0)} 筆專員工作"
        )
        if _debug.get("hit_page_limit"):
            st.warning("查詢已達 20 頁上限，請確認是否有漏單。")
        if not cr_rows:
            st.success("此服務日期沒有已付款且已排專員的訂單。")
        else:
            cr_select_all = st.checkbox(
                "全選有 LINE 連結的專員（取消勾選可全部取消）",
                value=True,
                key="cr_select_all",
            )
            if st.session_state.get("cr_select_all_previous") != cr_select_all:
                st.session_state.cr_select_all_previous = cr_select_all
                st.session_state.pop("cr_editor", None)
            _cleaner_table = [{
                "選取": bool(cr_select_all and row.get("line_url")),
                "專員": row["name"],
                "工作筆數": len(row["jobs"]),
                "服務日期": "、".join(sorted({
                    job.get("service_date", "") for job in row["jobs"]
                    if job.get("service_date")
                })),
                "LINE狀態": "已有連結" if row.get("line_url") else "查無連結",
            } for row in cr_rows]
            _cleaner_edited = st.data_editor(
                _cleaner_table,
                hide_index=True,
                use_container_width=True,
                disabled=["專員", "工作筆數", "服務日期", "LINE狀態"],
                key="cr_editor",
            )
            _cleaner_records = (
                _cleaner_edited.to_dict("records")
                if hasattr(_cleaner_edited, "to_dict")
                else list(_cleaner_edited or [])
            )
            _selected_names = {
                row["專員"] for row in _cleaner_records if row.get("選取")
            }
            st.markdown("#### 專員提醒訊息")
            for _idx, _row in enumerate(cr_rows):
                if _row["name"] not in _selected_names:
                    continue
                with st.expander(
                    f"{_row['name']}｜{len(_row['jobs'])} 筆工作｜"
                    f"{'已有 LINE' if _row.get('line_url') else '查無 LINE'}"
                ):
                    _message = st.text_area(
                        "訊息",
                        _row["message"],
                        height=260,
                        key=(
                            f"cr_msg_{_row['name']}_"
                            f"{_row['service_date_s']}_{_row['service_date_e']}"
                        ),
                    )
                    copy_button("複製訊息", _message, f"cr_copy_{_idx}")
                    if _row.get("line_url"):
                        st.link_button("開啟專員 LINE 聊天", _row["line_url"])
                    else:
                        st.warning("專員詳細資料沒有 LINE 連結，請改用電話聯絡。")
