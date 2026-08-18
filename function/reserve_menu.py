# -*- coding: utf-8 -*-
"""檸檬保留單建單／取消 UI。"""

from datetime import date

import pandas as pd
import streamlit as st

from accounts import ACCOUNTS
from orders import get_region_by_address
from function.ui_common import step, info_panel
from function.reserve_cancel import SYSTEM_RESERVE_MEMO, cancel_selected_reserve_orders, find_reserve_orders
from function.reserve_optimizer import (
    PERIOD_HOURS, RESERVE_PHONE_DEFAULT, ReserveRule, build_period_plan,
    create_reserve_orders_for_plan, login_reserve_member, member_addresses,
)


def _env_label(env): return "正式機 prod" if env == "prod" else "測試機 dev"


def _lookup(env, email, password, phone):
    key = f"reserve_lookup::{env}::{phone}"
    if st.session_state.get(key): return st.session_state[key]
    result = login_reserve_member(env, email.strip(), password.strip(), phone.strip())
    st.session_state[key] = result
    return result


def _header(env, email, password):
    phone = st.text_input("保留單會員手機", value=RESERVE_PHONE_DEFAULT, key="reserve_shared_phone")
    st.info(f"目前執行環境：{_env_label(env)}")
    if not email.strip() or not password.strip():
        st.warning("請先輸入上方後台帳號與密碼。")
        return phone, None
    try: return phone, _lookup(env, email, password, phone)
    except Exception as exc:
        st.error(f"讀取保留會員失敗：{exc}"); return phone, None


def render_create(email, password, env):
    step("3", "檸檬保留單建單")
    info_panel("功能說明", [
        "先分析指定期間每個日期／時段的未配班真人，再依 AM／PM 保留率計算建議保留張數。",
        "分析完成後不是整段自動建立；可直接在日期 × 時段表逐列勾選，並修改每列實際建立張數。",
        "每張保留單固定 2 位專員，建立前會重新讀取即時班表；不自動補檸檬人、不改其他客人班表。",
        f"系統建立的訂單會在客人備註寫『{SYSTEM_RESERVE_MEMO}』，供安全取消時再次辨識。",
        "支援正式機 prod 與測試機 dev；正式執行前必須再次勾選確認。",
    ])
    phone, lookup = _header(env, email, password)
    if not lookup: return
    addresses = member_addresses(lookup)
    if not addresses:
        st.error("保留會員沒有可用地址。"); return
    c1, c2 = st.columns(2)
    with c1: address = st.selectbox("保留單服務地址", addresses, key="reserve_create_address")
    with c2: payway = st.selectbox("付款類型", ["儲值金", "信用卡", "ATM"], key="reserve_create_payway")
    region = get_region_by_address(address, ACCOUNTS) or "台北"
    d1, d2 = st.columns(2)
    with d1: start = st.date_input("分析開始日期", value=date(2026, 9, 21), key="reserve_plan_start")
    with d2: end = st.date_input("分析結束日期", value=date(2026, 9, 30), key="reserve_plan_end")
    periods = st.multiselect("分析時段（可複選）", list(PERIOD_HOURS), default=["09:00-12:00", "14:00-17:00"], key="reserve_plan_periods")
    r1, r2 = st.columns(2)
    with r1: am_rate = st.slider("AM 保留率", 0, 100, 70, 5, key="reserve_am_rate") / 100
    with r2: pm_rate = st.slider("PM 保留率", 0, 100, 70, 5, key="reserve_pm_rate") / 100
    if st.button("統計班表並產生保留計畫", width="stretch", key="reserve_build_plan"):
        try:
            rules = [ReserveRule(start, end, am_rate, pm_rate)]
            plan = build_period_plan(lookup, start, end, rules, periods)
            st.session_state.reserve_plan_rows = [p.__dict__ for p in plan]
        except Exception as exc: st.error(str(exc))
    rows = st.session_state.get("reserve_plan_rows") or []
    if not rows: return
    editor_rows = []
    for r in rows:
        editor_rows.append({
            "執行": False, "日期": r["service_date"], "時段": r["period"],
            "未配班人數": r["unassigned_people"], "保留率": f"{int(r['reserve_rate']*100)}%",
            "建議保留張數": r["reserve_order_target"], "建立張數": r["reserve_order_target"],
            "預計留給市場": r["market_people_target"],
        })
    st.markdown("#### 選擇日期 × 時段與建立張數")
    st.caption("可任意跨日期、跨上午／下午複選；『建立張數』可低於建議值。")
    df = pd.DataFrame(editor_rows)
    edited = st.data_editor(
        df, width="stretch", hide_index=True,
        disabled=["日期", "時段", "未配班人數", "保留率", "建議保留張數", "預計留給市場"],
        column_config={
            "執行": st.column_config.CheckboxColumn("執行"),
            "建立張數": st.column_config.NumberColumn("建立張數", min_value=0, step=1),
        }, key="reserve_create_editor",
    )
    selected = []
    for item in edited.to_dict("records"):
        if not item.get("執行") or int(item.get("建立張數") or 0) <= 0: continue
        selected.append({"service_date": item["日期"], "period": item["時段"], "reserve_order_target": int(item["建立張數"])})
    total = sum(x["reserve_order_target"] for x in selected)
    st.info(f"目前選擇 {len(selected)} 個日期／時段，預計建立 {total} 張保留單。")
    confirm = st.checkbox(f"我確認要在{_env_label(env)}建立以上 {total} 張保留單", key="reserve_create_confirm")
    if st.button("確認建立檸檬保留單", type="primary", width="stretch", disabled=not confirm or total <= 0, key="reserve_create_execute"):
        try:
            with st.spinner("逐張重新確認班表並建立保留單..."):
                result = create_reserve_orders_for_plan(env_name=env, lookup_result=lookup, region=region, address=address, plan_rows=selected, payway=payway)
            st.session_state.reserve_last_create = result
            st.success(f"完成：成功 {result['success_count']} / {result['target_orders']} 張")
        except Exception as exc: st.error(str(exc))
    result = st.session_state.get("reserve_last_create")
    if result and result.get("results"): st.dataframe(pd.DataFrame(result["results"]), width="stretch", hide_index=True)


def render_cancel(email, password, env):
    step("3", "檸檬保留單取消")
    info_panel("功能說明", [
        "依日期區間、複選時段與客人備註條件搜尋保留單。",
        "搜尋後可逐筆勾選，或直接在表格一次選多筆；不再用『取消前 N 張』的方式。",
        "真正取消前會重新讀取最新客人備註；若已被人工改成其他客人保留內容，該張自動跳過。",
        f"安全條件只接受客人備註空白或含『{SYSTEM_RESERVE_MEMO}』；『全部』模式僅供查看。",
    ])
    phone, lookup = _header(env, email, password)
    if not lookup: return
    c1, c2 = st.columns(2)
    with c1: start = st.date_input("取消查詢開始日期", value=date(2026, 9, 21), key="reserve_cancel_start")
    with c2: end = st.date_input("取消查詢結束日期", value=date(2026, 9, 30), key="reserve_cancel_end")
    periods = st.multiselect("取消查詢時段（可複選；不選代表全部）", list(PERIOD_HOURS), key="reserve_cancel_periods")
    memo_filter = st.selectbox("客人備註篩選", ["僅系統保留單", "系統保留單或空白", "僅空白", "全部（僅供查看）"], key="reserve_cancel_filter")
    if st.button("查詢可取消保留單", width="stretch", key="reserve_cancel_search"):
        try:
            with st.spinner("查詢並確認客人備註..."):
                rows, debug = find_reserve_orders(env, email.strip(), password.strip(), phone.strip(), start.isoformat(), end.isoformat(), memo_filter=memo_filter, periods=periods, return_debug=True)
            st.session_state.reserve_cancel_rows = rows
            st.session_state.reserve_cancel_debug = debug
            st.success(f"查詢完成：{len(rows)} 張。")
        except Exception as exc: st.error(str(exc))
    rows = st.session_state.get("reserve_cancel_rows") or []
    if not rows: return
    editor = []
    for r in rows:
        editor.append({"取消": False, "日期": r.get("service_date"), "時段": r.get("period"), "訂單編號": r.get("order_no"), "客人備註": r.get("customer_memo", ""), "安全可取消": bool(r.get("cancel_eligible"))})
    df = pd.DataFrame(editor)
    edited = st.data_editor(df, width="stretch", hide_index=True, disabled=["日期", "時段", "訂單編號", "客人備註", "安全可取消"], column_config={"取消": st.column_config.CheckboxColumn("取消")}, key="reserve_cancel_editor")
    order_map = {str(r.get("order_no")): r for r in rows}
    selected = [order_map[str(x["訂單編號"])] for x in edited.to_dict("records") if x.get("取消") and x.get("安全可取消") and str(x.get("訂單編號")) in order_map]
    st.info(f"目前選擇 {len(selected)} 張安全可取消保留單。")
    if memo_filter == "全部（僅供查看）": st.warning("全部模式僅供查看，不開放取消。"); return
    confirm = st.checkbox(f"我確認要取消以上 {len(selected)} 張保留單", key="reserve_cancel_confirm")
    if st.button("確認取消選取保留單", type="primary", width="stretch", disabled=not confirm or not selected, key="reserve_cancel_execute"):
        try:
            with st.spinner("取消前重新確認最新客人備註..."):
                result = cancel_selected_reserve_orders(env, email.strip(), password.strip(), selected)
            st.session_state.reserve_cancel_result = result
            st.success("取消流程完成。")
        except Exception as exc: st.error(str(exc))
    result = st.session_state.get("reserve_cancel_result") or []
    if result: st.dataframe(pd.DataFrame(result), width="stretch", hide_index=True)
