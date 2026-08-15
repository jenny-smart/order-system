# -*- coding: utf-8 -*-
"""週末服務 LINE 提醒。"""

import streamlit as st

from function.weekend_reminders import (
    upcoming_weekend, previous_workday, find_paid_weekend_orders,
    load_tracking_rows, merge_tracking_rows, save_tracking_rows,
    tracking_rows_tsv,
    NOTICE_STATUSES, REPLY_STATUSES,
)
from function.ui_common import step, info_panel, copy_button


def render(backend_email, backend_password, env):
    step("3", "週末服務 LINE 提醒")
    info_panel("建議流程", [
        "在畫面顯示的『建議執行日』查詢名單；系統只列服務日期區間內的已付款訂單。",
        "名單中的『新增』代表尚未寫入追蹤表；『已存在』代表訂單編號已記錄。",
        "勾選後按『儲存勾選名單』，只會寫入 Google Sheet，不會發送 LINE。",
        "需要通知時請開啟 LINE、複製訊息並由客服人工送出。",
        "客人回覆後改為『已回覆』；當天下班前仍未回覆者改為『需追蹤』。",
        "追蹤狀態會保存到既有 Google 試算表的『週末服務提醒』分頁。",
    ])
    _default_sat, _default_sun = upcoming_weekend()
    try:
        from memo_system.change_order import TAIWAN_PUBLIC_HOLIDAYS
        _holidays = TAIWAN_PUBLIC_HOLIDAYS
    except Exception:
        _holidays = set()
    _suggested_run_day = previous_workday(_default_sat, _holidays)
    st.info(f"建議執行日：{_suggested_run_day.strftime('%Y-%m-%d')}；預設服務區間：{_default_sat}～{_default_sun}")
    st.caption("此頁不會透過程式發送 LINE；只保存勾選名單與人工追蹤狀態。")

    st.markdown("**服務日期區間**")
    wr_c1, wr_c2 = st.columns(2)
    with wr_c1:
        wr_date_s = st.date_input("服務日期-起", value=_default_sat, key="wr_date_s")
    with wr_c2:
        wr_date_e = st.date_input("服務日期-迄", value=_default_sun, key="wr_date_e")

    if st.button("🔍 查詢已付款名單", use_container_width=True, type="primary", key="wr_search"):
        if not backend_email.strip() or not backend_password.strip():
            st.error("請先在上方輸入後台帳號密碼")
        elif wr_date_s > wr_date_e:
            st.error("服務日期起日不可晚於迄日")
        else:
            try:
                with st.spinner("登入後台並查詢已付款訂單…"):
                    _orders, _debug = find_paid_weekend_orders(
                        env, backend_email.strip(), backend_password.strip(),
                        wr_date_s.strftime("%Y-%m-%d"), wr_date_e.strftime("%Y-%m-%d"),
                    )
                    _tracking = load_tracking_rows()
                st.session_state.wr_rows = merge_tracking_rows(_orders, _tracking)
                st.session_state.wr_debug = _debug
                st.session_state.pop("wr_editor", None)
            except Exception as e:
                st.error(f"查詢失敗：{e}")

    wr_rows = st.session_state.get("wr_rows")
    if wr_rows is not None:
        _debug = st.session_state.get("wr_debug", {})
        st.caption(f"後台：{_debug.get('base_url', '')}｜找到 {len(wr_rows)} 筆已付款服務")
        if _debug.get("hit_page_limit"):
            st.warning("查詢已達 20 頁上限，請縮小日期範圍後再查，避免漏單。")
        if not wr_rows:
            st.success("此服務日期區間沒有已付款訂單。")
        else:
            wr_select_all = st.checkbox(
                "全選名單（取消勾選可全部取消）",
                value=False,
                key="wr_select_all",
            )
            if st.session_state.get("wr_select_all_previous") != wr_select_all:
                st.session_state.wr_select_all_previous = wr_select_all
                st.session_state.pop("wr_editor", None)
            _editable = [
                {
                    "選取": wr_select_all,
                    **{k: v for k, v in row.items() if k != "LINE訊息"},
                }
                for row in wr_rows
            ]
            _edited = st.data_editor(
                _editable, use_container_width=True, hide_index=True, key="wr_editor",
                column_order=[
                    "選取", "資料狀態", "訂單編號", "服務日期", "姓名",
                    "通知狀態", "通知時間",
                    "回覆狀態", "回覆時間", "LINE",
                    "服務時間", "電話", "地址", "LINE ID",
                    "回覆備註", "發送錯誤", "最後更新",
                ],
                disabled=[
                    "訂單編號", "服務日期", "服務時間", "姓名", "電話", "地址",
                    "LINE", "LINE ID", "資料狀態", "通知時間", "回覆時間",
                    "發送錯誤", "最後更新",
                ],
                column_config={
                    "選取": st.column_config.CheckboxColumn("儲存", help="只儲存勾選訂單，不會發送 LINE"),
                    "資料狀態": st.column_config.TextColumn(
                        "資料狀態", help="新增＝Google Sheet 尚無此訂單編號；已存在＝將更新原列，不會重複新增。",
                    ),
                    "LINE": st.column_config.LinkColumn("LINE", display_text="開啟聊天"),
                    "LINE ID": st.column_config.TextColumn("LINE ID", help="由 LINE 聊天網址／客人回覆自動記錄"),
                    "通知狀態": st.column_config.SelectboxColumn("通知狀態", options=NOTICE_STATUSES, required=True),
                    "通知時間": st.column_config.TextColumn(
                        "實際發送時間",
                        help="客服人工確認已送出後，將通知狀態改為「已通知」並儲存時自動記錄。",
                    ),
                    "回覆狀態": st.column_config.SelectboxColumn("回覆狀態", options=REPLY_STATUSES, required=True),
                },
            )
            _edited_records = _edited.to_dict("records") if hasattr(_edited, "to_dict") else _edited
            _message_by_order = {row["訂單編號"]: row.get("LINE訊息", "") for row in wr_rows}
            _rows_with_messages = [
                {**row, "LINE訊息": _message_by_order.get(row.get("訂單編號"), "")}
                for row in _edited_records
            ]

            if st.button(
                "💾 儲存勾選名單（不發送 LINE）",
                use_container_width=True,
                type="primary",
                key="wr_save_selected",
            ):
                _selected = [row for row in _rows_with_messages if row.get("選取")]
                if not _selected:
                    st.warning("請至少勾選一筆訂單。")
                else:
                    try:
                        _new_count = sum(row.get("資料狀態") == "新增" for row in _selected)
                        _updated_count = len(_selected) - _new_count
                        save_tracking_rows(_selected)
                        _selected_order_nos = {
                            row.get("訂單編號") for row in _selected
                        }
                        for row in _edited_records:
                            if row.get("訂單編號") in _selected_order_nos:
                                row["資料狀態"] = "已存在"
                        st.session_state.wr_rows = [
                            {**row, "LINE訊息": _message_by_order.get(row.get("訂單編號"), "")}
                            for row in _edited_records
                        ]
                        st.success(
                            f"已儲存 {len(_selected)} 筆：新增 {_new_count} 筆、"
                            f"更新 {_updated_count} 筆；同訂單編號不會重複。"
                        )
                    except Exception as e:
                        st.error(f"儲存失敗：{e}")

            if st.button("💾 儲存通知／回覆狀態", use_container_width=True, key="wr_save"):
                try:
                    count = save_tracking_rows(_edited_records)
                    st.success(f"已保存 {count} 筆追蹤狀態。")
                except Exception as e:
                    st.error(f"儲存失敗：{e}")

            copy_button(
                "複製追蹤紀錄（貼到 Google Sheets 會自動分欄）",
                tracking_rows_tsv(_edited_records),
                "wr_copy_tracking",
            )

            st.markdown("#### LINE 提醒訊息")
            for _idx, _row in enumerate(wr_rows):
                with st.expander(f"{_row['服務日期']} {_row['服務時間']}｜{_row['姓名']}｜{_row['訂單編號']}"):
                    st.text_area("訊息", _row["LINE訊息"], height=220, key=f"wr_msg_{_row['訂單編號']}")
                    copy_button("複製訊息", _row["LINE訊息"], f"wr_copy_{_idx}")
                    if _row.get("LINE"):
                        st.link_button("開啟 LINE 聊天", _row["LINE"])
                    else:
                        st.warning("此訂單沒有 LINE 聊天連結，請改用電話聯絡。")
