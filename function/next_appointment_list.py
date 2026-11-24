# -*- coding: utf-8 -*-
"""評價管理預約下次服務（原「整理預約下次服務」）。

更新記錄：
2026-11-25
- 改名「評價管理預約下次服務」。
- 搜尋結果可直接寫入該區內勤工作表單「評價預約」分頁（主名單之後插列，與每日排程同一套寫法）：
  姓名帶 LINE 聊天連結、電話帶訂單管理電話查詢連結，地址一起寫入；地址取自該次評價的訂單編號那張訂單。
  已在名單（訂單編號）的略過；查詢訂單失敗的列不寫入。
"""

import streamlit as st

import quick_order as qo
from function.ui_common import step, info_panel, copy_button


def render(backend_email, backend_password, env):
    step("3", "評價管理預約下次服務")
    info_panel("使用說明", [
        "搜尋「評價日期」區間內、有勾選預約下次服務的評價紀錄。",
        "每一筆會回頭查詢被評價的訂單本身，抓出電話/地址/服務日期時數/人數。",
        "查詢筆數多時（例如整月）會需要一點時間，請耐心等候。",
        "按「寫入評價預約」會插到該區內勤工作表單「評價預約」主名單之後：姓名帶 LINE 連結、電話帶查詢連結，地址取自被評價的那張訂單。",
        "已在名單（同訂單編號）的不會重複寫入；查詢訂單失敗的列不寫入。",
    ])
    rn_col1, rn_col2 = st.columns(2)
    with rn_col1:
        rn_date_s = st.date_input("評價日期-起", value=None, key="rn_date_s")
    with rn_col2:
        rn_date_e = st.date_input("評價日期-迄", value=None, key="rn_date_e")
    if st.button("🔍 開始搜尋", key="rn_search_btn", use_container_width=True):
        if not backend_email.strip() or not backend_password.strip():
            st.error("請先在上方輸入後台帳號密碼")
        else:
            try:
                with st.spinner("查詢評價與訂單中，可能需要一點時間…"):
                    rn_results = qo.fetch_rating_next_appointments(
                        env_name=env, backend_email=backend_email.strip(),
                        backend_password=backend_password.strip(),
                        date_s=rn_date_s.strftime("%Y-%m-%d") if rn_date_s else "",
                        date_e=rn_date_e.strftime("%Y-%m-%d") if rn_date_e else "",
                    )
                st.session_state.rn_results = rn_results
                st.session_state.pop("rn_write_result", None)
            except Exception as e:
                st.error(f"搜尋失敗：{e}")

    rn_results = st.session_state.get("rn_results")
    if rn_results is not None:
        if not rn_results:
            st.info("這個區間內沒有預約下次服務的評價紀錄。")
        else:
            st.success(f"✅ 找到 {len(rn_results)} 筆預約下次服務的紀錄：")
            # v2026.07.07 新增：姓名可以直接點擊連到客人的 LINE 聊天視窗。
            # st.dataframe 的 LinkColumn 沒辦法讓儲存格顯示「姓名文字」但連到
            # 「另一個網址」（display_text 只能重新格式化網址本身的文字），
            # 所以改用 markdown 表格，姓名欄直接用 [姓名](LINE網址) 的超連結。
            _rn_headers = ["評價日期", "姓名", "電話", "地址", "預約下次日期", "預約下次時間", "服務日期及時間", "服務人數", "訂單編號"]
            _rn_md_lines = [
                "| " + " | ".join(_rn_headers) + " |",
                "|" + "|".join(["---"] * len(_rn_headers)) + "|",
            ]
            for r in rn_results:
                name_cell = f"[{r['姓名']}]({r['LINE']})" if r.get("LINE") else r["姓名"]
                _rn_md_lines.append(
                    "| " + " | ".join([
                        r["評價日期"], name_cell, r["電話"], r["地址"],
                        r["預約下次日期"], r["預約下次時間"], r["服務日期及時間"], r["服務人數"],
                        r["訂單編號"],
                    ]) + " |"
                )
            st.markdown("\n".join(_rn_md_lines))
            rn_text = "\n".join(
                f"{r['評價日期']}/ {r['姓名']}/ {r['電話']} /{r['地址']}/{r['預約下次日期']} "
                f"/{r['預約下次時間']}/{r['服務日期及時間']} {r['服務人數']}/{r['訂單編號']}"
                for r in rn_results
            )
            # v2026.07.07 新增：Google Sheets 貼上時要能自動分欄，必須是用
            # Tab 字元分隔（貼上純文字時瀏覽器複製到剪貼簿只會是斜線分隔的
            # 一整行文字，Sheets 不會自動拆欄）。這裡另外組一份 Tab 分隔版本，
            # 供貼到 Google Sheets 專用。
            rn_tsv = "\n".join(
                ["\t".join(_rn_headers + ["LINE"])] +
                [
                    "\t".join([
                        r["評價日期"], r["姓名"], r["電話"], r["地址"],
                        r["預約下次日期"], r["預約下次時間"], r["服務日期及時間"], r["服務人數"],
                        r["訂單編號"], r.get("LINE") or "",
                    ])
                    for r in rn_results
                ]
            )
            copy_button("複製整理結果（文字訊息用）", rn_text, "copy_rn_results")
            copy_button("複製整理結果（貼到 Google Sheets 用，會自動分欄，含 LINE 網址）", rn_tsv, "copy_rn_results_tsv")
            _render_write(rn_results, env)


def _render_write(rn_results, env):
    """寫入內勤工作表單「評價預約」：姓名／電話帶連結，地址一起寫。"""
    from shared import rating_schedule as rs

    writable = [r for r in rn_results if not str(r.get("服務日期及時間", "")).startswith("⚠️")]
    failed = len(rn_results) - len(writable)
    st.divider()
    region_default = "台北"
    try:
        from accounts import ACCOUNTS
        from orders import get_region_by_address

        first_addr = next((r.get("地址") for r in writable if r.get("地址")), "")
        region_default = get_region_by_address(first_addr, ACCOUNTS) or "台北" if first_addr else "台北"
    except Exception:
        pass
    regions = list(rs.BOOKING_LAYOUTS)
    region = st.selectbox("寫入地區（內勤工作表單「評價預約」）", regions,
                          index=regions.index(region_default) if region_default in regions else 0, key="rn_region")
    if failed:
        st.warning(f"有 {failed} 筆查詢訂單失敗，不會寫入。")
    if st.button(f"✍️ 寫入{region}「評價預約」（{len(writable)} 筆，已在名單的會略過）", key="rn_write_btn",
                 type="primary", use_container_width=True, disabled=not writable):
        try:
            import quick_order as qo

            base_url = qo._configure_environment(env)
            with st.spinner("寫入評價預約中…"):
                st.session_state.rn_write_result = rs.append_bookings(region, writable, base_url)
        except Exception as e:
            st.error(f"寫入失敗：{e}")
    result = st.session_state.get("rn_write_result")
    if result:
        msg = f"✅ 已寫入 {result['saved']} 筆"
        if result.get("existing"):
            msg += f"；已在名單略過 {len(result['existing'])} 筆（{'、'.join(result['existing'])}）"
        st.success(msg)
        st.markdown(f"[開啟評價預約分頁]({result['sheet_url']})")
