# -*- coding: utf-8 -*-
"""金額期間檢查：掃日期區間內已付款／待付款訂單，找出改期跨大掃除期間後金額沒重算的訂單。

更新記錄：
2026-11-28（新增）
- 選訂購日期或服務日期區間（預設 11/11～今天），逐筆比對金額與服務日期所屬期間價格。
- 金額剛好是其他期間（非大掃除／PART1／PART2）或另一種平假日的價格 → 列出，需重新成立訂單。
- 只查詢，不修改後台。
- 顯示逐日進度條（第幾天／總天數、已檢查與異常筆數）。
"""
from datetime import date, datetime

import streamlit as st

from function.ui_common import step, info_panel


def render(backend_email, backend_password, env):
    from memo_system import memo
    from shared import price_period_check as ppc

    step("1", "金額期間檢查：改期後金額未重算")
    info_panel("使用說明", [
        "查日期區間內「已付款」「待付款」的訂單，用（總金額－車馬費）比對服務日期所屬期間的價格。",
        "金額剛好是其他期間（非大掃除／大掃除 PART1／PART2）或另一種平假日的價格，就列出，需重新成立訂單。",
        "改期的訂單訂購日期不變，掃「訂購日期」可找出近期成立後被改期的訂單；也可改掃「服務日期」。",
        "單筆對不上時會用電話查同一服務日期的其他訂單，合計（例：原單＋補差價單）正確就不列出。",
        "有部分退款／待退款或加收的訂單，會讀後台的退款、加收金額調整後再比對（例：9000 退 1800 → 7200）。",
        "用了優惠券、折抵、合併或補單等對不上任何價格的訂單不列出。後台帳密決定查哪一區。只查詢，不修改後台。",
    ])
    today = datetime.now(ppc.TZ).date()
    by = st.radio("日期種類", list(ppc.DATE_FIELDS), horizontal=True, key="ppc_by")
    c1, c2 = st.columns(2)
    with c1:
        start = st.date_input(f"{by}-起", value=date(today.year, 11, 11) if today.month >= 11 else today, key="ppc_start")
    with c2:
        end = st.date_input(f"{by}-迄", value=today, key="ppc_end")

    if st.button("🔍 開始檢查", key="ppc_run", use_container_width=True):
        st.session_state.pop("ppc_result", None)
        logs = []
        try:
            if not str(backend_email or "").strip() or not str(backend_password or "").strip():
                raise ValueError("請先在上方輸入後台帳號密碼")
            memo.set_env(env)
            memo.set_runtime_credentials(backend_email.strip(), backend_password.strip())
            bar = st.progress(0.0, text="登入後台中…")
            session = memo.login()

            def show(done, total, day, scanned, bad):
                text = (f"{by} {day:%m/%d}（第 {min(done + 1, total)}／{total} 天）查詢中…" if done < total
                        else f"完成 {total}／{total} 天")
                bar.progress(done / total if total else 1.0, text=f"{text}｜已檢查 {scanned} 筆｜金額異常 {bad} 筆")

            result = ppc.scan(session, start, end, by, log=logs.append, progress=show)
            st.session_state.ppc_result = {"result": result, "by": by, "start": start, "end": end, "logs": logs}
        except Exception as exc:
            st.error(f"檢查失敗：{exc}")

    state = st.session_state.get("ppc_result")
    if not state:
        return
    result = state["result"]
    st.caption(f"{state['by']} {state['start']:%Y/%m/%d} ～ {state['end']:%Y/%m/%d}｜"
               f"檢查 {result['scanned']} 筆｜金額異常 {len(result['rows'])} 筆")
    with st.expander("查詢 LOG"):
        st.text("\n".join(state["logs"]) or "（無）")
    st.caption("應收金額：依目前金額推定的客戶等級（VIP／一般客）、服務日所屬期間與平假日計算；差額＝應收－目前。")
    if not result["rows"]:
        st.success("沒有找到改期後金額未重算的訂單。")
        return
    st.dataframe(
        result["rows"], use_container_width=True, hide_index=True,
        column_config={
            "LINE連結": st.column_config.LinkColumn("LINE連結", display_text="開啟對話"),
            "訂單連結": st.column_config.LinkColumn("訂單連結", display_text="開啟訂單"),
        },
    )
