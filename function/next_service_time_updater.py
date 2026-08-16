# -*- coding: utf-8 -*-
"""更新建議下次服務時間。"""

import streamlit as st

import function.next_service_dates as nsd
from function.ui_common import step, info_panel


def render(backend_email, backend_password, env):
    step("3", "更新建議下次服務時間")
    info_panel("功能說明", [
        "依「地址(B欄) + 電話(E欄)」查後台該電話底下所有訂單，比對地址後取最近3次"
        "服務日期，寫入 L/M/N 欄（L=最近一次，N=最遠一次）。",
        "登入帳密沿用 Step 1 上方輸入的後台帳號密碼，不用另外輸入。",
        "會自動跳過純儲值金訂單與已取消/已退款訂單。",
    ])

    _nsd_sheet_options = {
        f"{i+1}. {region}｜gid={gid}": (region, spreadsheet_id, gid)
        for i, (region, spreadsheet_id, gid) in enumerate(nsd.SHEETS)
    }
    nsd_sheet_choice = st.selectbox(
        "目標工作表", ["全部四份"] + list(_nsd_sheet_options.keys()), key="nsd_sheet_choice",
    )

    if st.button("🚀 開始查詢並更新", use_container_width=True, key="nsd_run_btn", type="primary"):
        nsd_logs = []
        nsd_log_box = st.empty()

        def _nsd_ui_log(msg):
            nsd_logs.append(str(msg))
            nsd_log_box.text("\n".join(nsd_logs[-200:]))

        if not backend_email.strip() or not backend_password.strip():
            st.error("請先在上方 Step 1 輸入後台帳號密碼")
        else:
            try:
                targets = nsd.SHEETS if nsd_sheet_choice == "全部四份" else [_nsd_sheet_options[nsd_sheet_choice]]
                total_updated = 0
                with st.spinner("查詢中，依資料量可能需要幾分鐘…"):
                    _session = nsd.login_backend(env, backend_email.strip(), backend_password.strip())
                    for _region, _spreadsheet_id, _gid in targets:
                        _nsd_ui_log(f"▶ 開始處理：{_region}｜gid={_gid}")
                        total_updated += nsd.update_next_service_dates_sheet(
                            _session, _spreadsheet_id, _gid, logger=_nsd_ui_log,
                        )
                st.success(f"✅ 完成，共更新 {total_updated} 列。")
            except Exception as e:
                st.error(f"執行失敗：{e}")
