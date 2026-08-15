# -*- coding: utf-8 -*-
"""雙向訂單檢查：Google Sheet 成單工作表 vs. 後台。"""

import streamlit as st

from orders import run_standalone_consistency_check
from function.ui_common import step, info_panel


def render(backend_email, backend_password, env, accounts):
    step("3", "雙向訂單檢查")
    info_panel("功能說明", [
        "不用重新跑一次批次建單，直接針對一份已經有「訂單編號」欄位的成單工作表，"
        "跟後台系統做一次雙向比對。",
        "方向一：工作表寫的訂單編號，回查後台是否真的存在，電話/地址/日期/時段是否跟這一列相符。",
        "方向二（加強版，需要填服務日期區間）：不是只查工作表裡已出現的電話，"
        "而是直接抓後台這段日期區間內的『全部』已付款訂單，逐筆核對訂單編號有沒有"
        "出現在工作表裡——這樣才抓得到「客人電話整筆漏登記進工作表」這種情況。",
        "沒有填日期區間的話，方向二只會用舊方式（工作表裡已出現的電話）去查，"
        "抓不到完全沒登記進工作表的訂單，建議務必填上服務日期區間。",
    ])

    dc_sheet_name = st.text_input("工作表名稱", value="", placeholder="例：202604", key="dc_sheet_name")
    dc_region = st.selectbox("只檢查特定區域（不指定則檢查全部）", ["全部"] + list(accounts.keys()), key="dc_region")

    st.markdown("**方向二用：服務日期區間**（建議務必填寫，才能抓到工作表完全漏登記的訂單）")
    dc_col1, dc_col2 = st.columns(2)
    with dc_col1:
        dc_date_start = st.date_input("服務日期-起", value=None, key="dc_date_start")
    with dc_col2:
        dc_date_end = st.date_input("服務日期-迄", value=None, key="dc_date_end")

    if st.button("🔍 開始雙向比對", use_container_width=True, key="dc_run_btn", type="primary"):
        if not backend_email.strip() or not backend_password.strip():
            st.error("請先在上方輸入後台帳號密碼")
        elif not dc_sheet_name.strip():
            st.error("請輸入工作表名稱")
        else:
            try:
                with st.spinner("讀取工作表 → 登入後台 → 雙向比對中（有填日期區間的話會多花一點時間掃後台整段期間的訂單）…"):
                    dc_problems = run_standalone_consistency_check(
                        env_name=env,
                        backend_email=backend_email.strip(),
                        backend_password=backend_password.strip(),
                        sheet_name=dc_sheet_name.strip(),
                        region=None if dc_region == "全部" else dc_region,
                        date_range_start=dc_date_start.strftime("%Y-%m-%d") if dc_date_start else None,
                        date_range_end=dc_date_end.strftime("%Y-%m-%d") if dc_date_end else None,
                    )
                st.session_state.dc_result = {"problems": dc_problems, "sheet_name": dc_sheet_name.strip()}
            except Exception as e:
                st.error(f"檢查失敗：{e}")

    dc_result = st.session_state.get("dc_result")
    if dc_result:
        st.markdown("#### 檢查結果")
        _problems = dc_result.get("problems") or []
        if _problems:
            st.error(f"⚠️ 工作表「{dc_result.get('sheet_name')}」發現 {len(_problems)} 筆異常，請人工確認：")
            for _p in _problems:
                _row_label = f"第 {_p.get('row_num')} 列" if _p.get("row_num") is not None else "（系統反查，不是特定一列）"
                st.warning(f"{_row_label}（訂單 {_p.get('order_no', '') or '（無）'}）：{_p.get('issue')}")
        else:
            st.success(f"✅ 工作表「{dc_result.get('sheet_name')}」檢查通過，訂單編號皆與電話/地址/日期/時段相符，後台也沒有查到工作表未記錄的訂單。")
