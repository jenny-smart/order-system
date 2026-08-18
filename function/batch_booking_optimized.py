# -*- coding: utf-8 -*-
"""批次建單優化：獨立於既有 Google Sheet 批次建單。

第一版先支援「既有會員／既有地址」的多日期 × 多時段批次建單。
每個時段先查人力，使用者再勾選真正要建立的時段；執行每一筆前再次查班表。
既有 render_batch 完全不修改。
"""

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from accounts import ACCOUNTS
from orders import get_region_by_address
from function.ui_common import step, info_panel
from shared.batch_booking_core import PERIOD_HOUR_MAP
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


def render(backend_email: str, backend_password: str, env: str) -> None:
    step("3", "批次建單優化")
    info_panel("功能說明", [
        "這是新增功能，不會取代或修改既有『批次建單（Google Sheet）』。",
        "同一會員／地址可一次選擇日期範圍與多個服務時段；系統逐一檢查哪些日期 × 時段有人力。",
        "查班後可任意勾選真正要建立的多個時段，不必一筆一筆重新輸入日期與時間。",
        "正式建立每一筆前會再次確認該日期／完整同時段仍有人力；人力已被使用就跳過該筆。",
        "第一版限定既有會員與既有地址；不自動補檸檬人、不改其他專員班表。",
    ])
    info_panel("建議流程", [
        "1. 輸入會員手機並讀取會員。",
        "2. 選地址、付款方式、人數、日期範圍與候選時段。",
        "3. 按『檢查日期 × 時段人力』，再勾選要建單的時段。",
        "4. 確認摘要後批次建立；結果逐筆列出訂單編號或失敗原因。",
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
        rows = []
        cur = start
        with st.spinner("逐日檢查完整同時段人力..."):
            while cur <= end:
                for period in periods:
                    try:
                        available, staff = _check_one(lookup, env, payway, address, clean_type_id, cur.isoformat(), period, person)
                        rows.append({"執行": False, "日期": cur.isoformat(), "時段": period, "有人力": available, "可用專員": staff})
                    except Exception as exc:
                        rows.append({"執行": False, "日期": cur.isoformat(), "時段": period, "有人力": False, "可用專員": "", "錯誤": str(exc)})
                cur += timedelta(days=1)
        st.session_state.batch_opt_slots = rows

    rows = st.session_state.get("batch_opt_slots") or []
    if not rows:
        return

    st.markdown("#### 選擇真正要建立的日期／時段")
    st.caption("只有『有人力』的列可以建單；可一次勾選不同日期、不同時段。")
    editor_df = pd.DataFrame(rows)
    edited = st.data_editor(
        editor_df,
        width="stretch",
        hide_index=True,
        disabled=[c for c in editor_df.columns if c != "執行"],
        column_config={"執行": st.column_config.CheckboxColumn("執行", help="勾選要建立的時段")},
        key="batch_opt_editor",
    )
    selected = edited[(edited["執行"] == True) & (edited["有人力"] == True)].to_dict("records")
    st.info(f"目前選擇 {len(selected)} 個日期／時段，預計建立 {len(selected)} 張訂單。")

    confirm = st.checkbox(
        f"我確認要在{'正式機' if env == 'prod' else '測試機'}建立以上 {len(selected)} 張訂單",
        key="batch_opt_confirm",
    )
    if st.button("確認批次建立訂單", type="primary", width="stretch", disabled=not confirm or not selected, key="batch_opt_execute"):
        results = []
        with st.spinner("逐筆重新確認人力並建立訂單..."):
            for row in selected:
                date_s, period = row["日期"], row["時段"]
                try:
                    available, staff = _check_one(lookup, env, payway, address, clean_type_id, date_s, period, person)
                    if not available:
                        results.append({"日期": date_s, "時段": period, "成功": False, "訂單編號": "", "訊息": "執行前重查已無人力，跳過"})
                        continue
                    result = qo.quick_create_order(
                        env_name=env, payway=payway, region=region, lookup_result=lookup,
                        address=address, clean_type_id=clean_type_id, date_s=date_s,
                        period_s=period, hour=str(PERIOD_HOUR_MAP[period]), person=str(person),
                        allow_auto_lemon_shift=False,
                    )
                    results.append({"日期": date_s, "時段": period, "成功": True, "訂單編號": result.get("order_no", ""), "專員": result.get("staff", staff), "訊息": "成功"})
                except Exception as exc:
                    results.append({"日期": date_s, "時段": period, "成功": False, "訂單編號": "", "訊息": str(exc)})
        st.session_state.batch_opt_results = results
        success_count = sum(1 for r in results if r.get("成功"))
        st.success(f"批次執行完成：成功 {success_count} / {len(results)} 張。")

    results = st.session_state.get("batch_opt_results") or []
    if results:
        st.dataframe(pd.DataFrame(results), width="stretch", hide_index=True)
