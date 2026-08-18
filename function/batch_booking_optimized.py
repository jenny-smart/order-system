# ============================================================
# 檔名：function/batch_booking_optimized.py
# 功能：批次建單優化 UI；多日期、多時段查班與批次建單，不影響既有批次建單。
# 更新時間：2026-08-19
# ============================================================
# -*- coding: utf-8 -*-
from datetime import date, timedelta
import pandas as pd
import streamlit as st
from accounts import ACCOUNTS
from function.ui_common import step, info_panel
from shared.batch_booking_core import PERIOD_HOUR_MAP, SlotPlan, build_grid, execute_batch
from shared import booking_service, order_query_service

PERIODS = list(PERIOD_HOUR_MAP.keys())


def _member_addresses(lookup_result):
    payload = lookup_result.get("member_payload") or {}
    member = payload.get("member") or {}
    result = []
    for row in member.get("memberAddressList") or []:
        if isinstance(row, dict):
            addr = str(row.get("address") or "").strip()
            if addr and addr not in result:
                result.append(addr)
    last = payload.get("lastPurchase") or {}
    last_addr = str(last.get("address") or "").strip() if isinstance(last, dict) else ""
    if last_addr and last_addr not in result:
        result.insert(0, last_addr)
    return result


def _check_one(lookup, env, payway, address, clean_type_id, date_s, period, person):
    rows = booking_service.check_available_slots(env, payway, lookup, address, clean_type_id, date_s, str(PERIOD_HOUR_MAP[period]), person=str(person), periods=[period], period_hours=PERIOD_HOUR_MAP)
    row = rows[0] if rows else {}
    return bool(row.get("available")), str(row.get("staff") or "")


def _editor_rows(slots):
    return [{"執行": bool(s.selected), "日期": s.service_date, "時段": s.period, "有人力": bool(s.available), "可用專員": s.staff} for s in slots]


def render(backend_email: str, backend_password: str, env: str) -> None:
    step("3", "批次建單優化")
    info_panel("功能說明", ["新增功能，不修改既有『批次建單（Google Sheet）』。", "可一次選擇日期範圍與多個服務時段。", "建單前逐張重查即時人力，避免重複占用。", "儲值金客人亦可一次建立多個有人力時段。"])
    info_panel("效率設計", ["日期 × 時段集中查班。", "建單共用 batch_booking_core。", "新 Sheet 型流程採每 10 筆 checkpoint 批次回寫。"])
    if not backend_email.strip() or not backend_password.strip():
        st.warning("請先輸入上方後台帳號與密碼。")
        return

    phone = st.text_input("會員手機", key="batch_opt_phone")
    if st.button("讀取會員", width="stretch", key="batch_opt_lookup"):
        try:
            with st.spinner("讀取會員中..."):
                st.session_state.batch_opt_lookup_result = booking_service.lookup_member(env, backend_email.strip(), backend_password.strip(), phone.strip(), clean_type_id="1")
            st.session_state.pop("batch_opt_slots", None)
            st.session_state.pop("batch_opt_results", None)
            st.success("會員讀取完成。") if st.session_state.batch_opt_lookup_result.get("member_payload") else st.error("查無會員。")
        except Exception as exc:
            st.session_state.batch_opt_lookup_result = None
            st.error(str(exc))

    lookup = st.session_state.get("batch_opt_lookup_result")
    if not lookup or not lookup.get("member_payload"):
        return
    addresses = _member_addresses(lookup)
    if not addresses:
        st.error("此會員沒有可用既有地址。")
        return

    c1, c2, c3 = st.columns(3)
    with c1: address = st.selectbox("服務地址", addresses, key="batch_opt_address")
    with c2: payway = st.selectbox("付款方式", ["信用卡", "ATM", "儲值金"], key="batch_opt_payway")
    with c3: person = st.number_input("服務人數", 1, 10, 2, 1, key="batch_opt_person")
    region = order_query_service.get_region(address, ACCOUNTS) or "台北"
    clean_type_id = "1"
    st.caption(f"地址判斷區域：{region}｜目前環境：{'正式機 prod' if env == 'prod' else '測試機 dev'}")

    d1, d2 = st.columns(2); today = date.today()
    with d1: start = st.date_input("開始日期", today + timedelta(days=1), key="batch_opt_start")
    with d2: end = st.date_input("結束日期", today + timedelta(days=14), key="batch_opt_end")
    periods = st.multiselect("候選服務時段（可複選）", PERIODS, default=["09:00-12:00", "14:00-17:00"], key="batch_opt_periods")

    if st.button("檢查日期 × 時段人力", width="stretch", key="batch_opt_check"):
        if end < start or not periods:
            st.error("請確認日期範圍並至少選擇一個時段。")
            return
        slots = build_grid(start, end, periods)
        with st.spinner("逐日檢查人力..."):
            for slot in slots:
                try:
                    slot.available, slot.staff = _check_one(lookup, env, payway, address, clean_type_id, slot.service_date, slot.period, person)
                    slot.selected = slot.available
                except Exception as exc:
                    slot.available = slot.selected = False; slot.note = str(exc)
        st.session_state.batch_opt_slots = slots
        st.session_state.pop("batch_opt_results", None)

    slots = st.session_state.get("batch_opt_slots") or []
    if not slots: return
    editor_df = pd.DataFrame(_editor_rows(slots))
    edited = st.data_editor(editor_df, width="stretch", hide_index=True, disabled=[c for c in editor_df.columns if c != "執行"], column_config={"執行": st.column_config.CheckboxColumn("執行")}, key="batch_opt_editor")
    selected_slots = [SlotPlan(service_date=str(r["日期"]), period=str(r["時段"]), available=True, selected=True, quantity=1, staff=str(r.get("可用專員") or "")) for r in edited.to_dict("records") if bool(r.get("執行")) and bool(r.get("有人力"))]
    st.info(f"目前選擇 {len(selected_slots)} 個日期／時段，預計建立 {len(selected_slots)} 張訂單。")
    confirm = st.checkbox(f"我確認要在{'正式機' if env == 'prod' else '測試機'}建立以上 {len(selected_slots)} 張訂單", key="batch_opt_confirm")

    if st.button("確認批次建立訂單", type="primary", width="stretch", disabled=not confirm or not selected_slots, key="batch_opt_execute"):
        def precheck(slot):
            available, staff = _check_one(lookup, env, payway, address, clean_type_id, slot.service_date, slot.period, person)
            return {"available": available, "staff": staff, "message": "執行前重查已無人力，跳過" if not available else ""}
        def executor(slot, _sequence):
            result = booking_service.create_order(env_name=env, payway=payway, region=region, lookup_result=lookup, address=address, clean_type_id=clean_type_id, date_s=slot.service_date, period_s=slot.period, hour=str(PERIOD_HOUR_MAP[slot.period]), person=str(person), allow_auto_lemon_shift=False)
            return {"success": True, "order_no": result.get("order_no", ""), "staff": result.get("staff", slot.staff), "message": "成功"}
        with st.spinner("逐張重新確認人力並建立訂單..."):
            summary = execute_batch(selected_slots, precheck=precheck, executor=executor, continue_after_error=True)
        st.session_state.batch_opt_results = [{"日期": r.get("service_date", ""), "時段": r.get("period", ""), "成功": bool(r.get("success")), "訂單編號": r.get("order_no", ""), "專員": r.get("staff", ""), "訊息": r.get("message", "")} for r in summary["results"]]
        st.success(f"完成：成功 {summary['success_count']} / {summary['target_count']} 張。") if not summary["fail_count"] else st.warning(f"完成：成功 {summary['success_count']}，失敗 {summary['fail_count']}。")
    results = st.session_state.get("batch_opt_results") or []
    if results: st.dataframe(pd.DataFrame(results), width="stretch", hide_index=True)
