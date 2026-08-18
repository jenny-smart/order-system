# -*- coding: utf-8 -*-
"""批次建單優化：獨立於既有 Google Sheet 批次建單。

支援既有會員／既有地址的多日期 × 多時段批次建單。
既有 render_batch 完全不修改；此頁改用 shared.batch_booking_core 共用核心。
"""

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from accounts import ACCOUNTS
from orders import get_region_by_address
from function.ui_common import step, info_panel
from shared.batch_booking_core import (
    PERIOD_HOUR_MAP,
    SlotPlan,
    build_grid,
    execute_batch,
)
import quick_order as qo

PERIODS = list(PERIOD_HOUR_MAP.keys())


def _member_addresses(lookup_result):
    payload = lookup_result.get("member_payload") or {}
    member = payload.get("member") or {}
    rows = member.get("memberAddressList") or []
    result = []
    for row in rows:
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
    rows = qo.quick_check_available_slots(
        env, payway, lookup, address, clean_type_id,
        date_s, str(PERIOD_HOUR_MAP[period]), person=str(person),
        periods=[period], period_hours=PERIOD_HOUR_MAP,
    )
    row = rows[0] if rows else {}
    return bool(row.get("available")), str(row.get("staff") or "")


def _editor_rows(slots):
    return [
        {
            "執行": bool(slot.selected),
            "日期": slot.service_date,
            "時段": slot.period,
            "有人力": bool(slot.available),
            "可用專員": slot.staff,
        }
        for slot in slots
    ]


def render(backend_email: str, backend_password: str, env: str) -> None:
    step("3", "批次建單優化")
    info_panel("功能說明", [
        "這是新增功能，不會取代或修改既有『批次建單（Google Sheet）』。",
        "同一會員／地址可一次選擇日期範圍與多個服務時段；系統會建立完整日期 × 時段清單並檢查人力。",
        "有人力的日期／時段可一次全選，也可再個別取消，不必逐筆重新輸入。",
        "正式建立每一張訂單前都會重新確認該日期／完整同時段仍有人力；已被使用就跳過該張。",
        "同一位儲值金客人也可以一次選擇多個有人力時段，依選取清單逐張建立。",
        "第一版限定既有會員與既有地址；不自動補檸檬人、不改其他專員班表。",
    ])
    info_panel("效率設計", [
        "查班：一次規劃多日期 × 多時段，再集中選取。",
        "建單：使用共用 batch_booking_core 執行，不與舊批次建單程式互相影響。",
        "安全：每張訂單建立前重新查班，避免前面建單後人力已被占用仍繼續成立。",
        "Google Sheet：新的 Sheet 型批次流程可使用 10 筆 checkpoint 批次回寫核心；既有批次建單暫不改。",
    ])

    if not backend_email.strip() or not backend_password.strip():
        st.warning("請先輸入上方後台帳號與密碼。")
        return

    phone = st.text_input("會員手機", key="batch_opt_phone")
    if st.button("讀取會員", width="stretch", key="batch_opt_lookup"):
        try:
            with st.spinner("讀取會員中..."):
                st.session_state.batch_opt_lookup_result = qo.quick_lookup_member(
                    env, backend_email.strip(), backend_password.strip(), phone.strip(), clean_type_id="1"
                )
            st.session_state.pop("batch_opt_slots", None)
            st.session_state.pop("batch_opt_results", None)
            if not st.session_state.batch_opt_lookup_result.get("member_payload"):
                st.error("查無會員。批次建單優化第一版先不處理新客。")
            else:
                st.success("會員讀取完成。")
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
    with c1:
        address = st.selectbox("服務地址", addresses, key="batch_opt_address")
    with c2:
        payway = st.selectbox("付款方式", ["信用卡", "ATM", "儲值金"], key="batch_opt_payway")
    with c3:
        person = st.number_input("服務人數", min_value=1, max_value=10, value=2, step=1, key="batch_opt_person")

    region = get_region_by_address(address, ACCOUNTS) or "台北"
    clean_type_id = "1"
    st.caption(f"地址判斷區域：{region}｜目前環境：{'正式機 prod' if env == 'prod' else '測試機 dev'}")

    d1, d2 = st.columns(2)
    today = date.today()
    with d1:
        start = st.date_input("開始日期", value=today + timedelta(days=1), key="batch_opt_start")
    with d2:
        end = st.date_input("結束日期", value=today + timedelta(days=14), key="batch_opt_end")
    periods = st.multiselect(
        "候選服務時段（可複選）", PERIODS,
        default=["09:00-12:00", "14:00-17:00"], key="batch_opt_periods",
    )

    if st.button("檢查日期 × 時段人力", width="stretch", key="batch_opt_check"):
        if end < start:
            st.error("結束日期不可早於開始日期。")
            return
        if not periods:
            st.error("請至少選擇一個候選時段。")
            return
        slots = build_grid(start, end, periods)
        with st.spinner("逐日檢查完整同時段人力..."):
            for slot in slots:
                try:
                    available, staff = _check_one(
                        lookup, env, payway, address, clean_type_id,
                        slot.service_date, slot.period, person,
                    )
                    slot.available = available
                    slot.staff = staff
                    slot.selected = available
                except Exception as exc:
                    slot.available = False
                    slot.selected = False
                    slot.note = str(exc)
        st.session_state.batch_opt_slots = slots
        st.session_state.pop("batch_opt_results", None)

    slots = st.session_state.get("batch_opt_slots") or []
    if not slots:
        return

    available_count = sum(1 for slot in slots if slot.available)
    st.markdown("#### 選擇真正要建立的日期／時段")
    st.caption(f"共檢查 {len(slots)} 個日期／時段，其中 {available_count} 個有人力；預設勾選所有有人力時段，可再取消不要的項目。")

    editor_df = pd.DataFrame(_editor_rows(slots))
    edited = st.data_editor(
        editor_df,
        width="stretch",
        hide_index=True,
        disabled=[c for c in editor_df.columns if c != "執行"],
        column_config={"執行": st.column_config.CheckboxColumn("執行", help="勾選要建立的時段")},
        key="batch_opt_editor",
    )

    selected_slots = []
    for row in edited.to_dict("records"):
        if bool(row.get("執行")) and bool(row.get("有人力")):
            selected_slots.append(SlotPlan(
                service_date=str(row["日期"]), period=str(row["時段"]),
                available=True, selected=True, quantity=1,
                staff=str(row.get("可用專員") or ""),
            ))
    st.info(f"目前選擇 {len(selected_slots)} 個日期／時段，預計建立 {len(selected_slots)} 張訂單。")

    confirm = st.checkbox(
        f"我確認要在{'正式機' if env == 'prod' else '測試機'}建立以上 {len(selected_slots)} 張訂單",
        key="batch_opt_confirm",
    )
    if st.button("確認批次建立訂單", type="primary", width="stretch", disabled=not confirm or not selected_slots, key="batch_opt_execute"):
        def precheck(slot):
            available, staff = _check_one(
                lookup, env, payway, address, clean_type_id,
                slot.service_date, slot.period, person,
            )
            return {
                "available": available,
                "staff": staff,
                "message": "執行前重查已無人力，跳過" if not available else "",
            }

        def executor(slot, _sequence):
            result = qo.quick_create_order(
                env_name=env, payway=payway, region=region, lookup_result=lookup,
                address=address, clean_type_id=clean_type_id, date_s=slot.service_date,
                period_s=slot.period, hour=str(PERIOD_HOUR_MAP[slot.period]), person=str(person),
                allow_auto_lemon_shift=False,
            )
            return {
                "success": True,
                "order_no": result.get("order_no", ""),
                "staff": result.get("staff", slot.staff),
                "message": "成功",
            }

        with st.spinner("逐張重新確認人力並建立訂單..."):
            summary = execute_batch(
                selected_slots,
                precheck=precheck,
                executor=executor,
                continue_after_error=True,
            )
        display_results = []
        for row in summary["results"]:
            display_results.append({
                "日期": row.get("service_date", ""),
                "時段": row.get("period", ""),
                "成功": bool(row.get("success")),
                "訂單編號": row.get("order_no", ""),
                "專員": row.get("staff", ""),
                "訊息": row.get("message", ""),
            })
        st.session_state.batch_opt_results = display_results
        if summary["fail_count"]:
            st.warning(f"批次執行完成：成功 {summary['success_count']} / {summary['target_count']} 張，失敗 {summary['fail_count']} 張。")
        else:
            st.success(f"批次執行完成：成功 {summary['success_count']} / {summary['target_count']} 張。")

    results = st.session_state.get("batch_opt_results") or []
    if results:
        st.dataframe(pd.DataFrame(results), width="stretch", hide_index=True)
