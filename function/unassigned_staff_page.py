# -*- coding: utf-8 -*-
"""未配班檢查頁：① 成立保留單 ② 記錄未配班人員（只剩 1 人的時段）。

變更紀錄
- 2026-11-22：① 確定成立前後會合併單人保留單（同時段 2 張以上 1 人單 → 取消後成立 N 人單）。
- 2026-11-22：① 確認改成兩段按鈕（成立 N 張 → 確定成立／取消），取代勾選框（正式機勾不起來）。
- 2026-11-22：① 預設日期＝保留單排程區間（2027/01/22～02/04）；① 也有每小時排程（shared/unassigned_reserve_schedule.py）。
- 2026-11-21：新增。邏輯在 shared/unassigned_staff.py；
  ② 的每日排程在 shared/unassigned_staff_schedule.py。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st

from accounts import ACCOUNTS
from shared import unassigned_staff as us


def _env_label(env: str) -> str:
    return "正式機 prod" if str(env).lower() == "prod" else "測試機 dev"


def render(backend_email: str, backend_password: str, env: str) -> None:
    from function import reserve_menu
    from orders import get_region_by_address

    st.markdown("### 🔍 未配班檢查")
    st.caption("讀後台班表灰底「未配班」名單（不算檸檬人、晚上時段）。")
    if not reserve_menu._require_supported_env(env):
        return
    phone, lookup = reserve_menu._common_member_header(env, backend_email, backend_password)
    if not lookup:
        return
    tab1, tab2 = st.tabs(["① 成立保留單", "② 記錄未配班人員"])
    with tab1:
        _render_reserve(env, lookup, get_region_by_address, backend_email, backend_password)
    with tab2:
        from function.reserve_optimizer import member_addresses

        addresses = member_addresses(lookup)
        _render_record(lookup, (get_region_by_address(addresses[0], ACCOUNTS) if addresses else "") or "台北")


def _render_reserve(env, lookup, get_region_by_address, backend_email: str = "", backend_password: str = "") -> None:
    from function.reserve_optimizer import member_addresses

    st.caption("日期區間內只要有未配班就成立保留單：同一天同一時段（上午／下午／全天）合成一張，"
               "人數＝人數、時數取最短（1人2小時＋1人3小時 → 2人2小時；1 人也成立 1人單）。"
               "後台查不到這麼多人時（例如有人不服務保留地址），人數減 1 再試。"
               "同一天同一時段已有 2 張以上 1 人保留單時，會先取消再合併成一張 N 人保留單。")
    addresses = member_addresses(lookup)
    if not addresses:
        st.error("保留會員沒有可用地址。")
        return
    c1, c2 = st.columns(2)
    with c1:
        address = st.selectbox("保留單服務地址", addresses, key="unassigned_reserve_address")
    with c2:
        payway = st.selectbox("付款類型", ["儲值金", "信用卡", "ATM"], index=0, key="unassigned_reserve_payway")
    region = get_region_by_address(address, ACCOUNTS) or "台北"
    d1, d2 = st.columns(2)
    from shared.unassigned_reserve_schedule import RESERVE_END, RESERVE_START

    # 預設＝保留單排程的區間（暫訂 2027/01/22～02/04）
    with d1:
        start = st.date_input("開始日期", value=date.fromisoformat(RESERVE_START), key="unassigned_reserve_start")
    with d2:
        end = st.date_input("結束日期", value=date.fromisoformat(RESERVE_END), key="unassigned_reserve_end")
    if st.button("讀取未配班並產生保留計畫", width="stretch", key="unassigned_reserve_scan"):
        with st.spinner("讀取班表中…"):
            try:
                summary = us.scan_range(us._schedule_getter(lookup), start.isoformat(), end.isoformat())
                st.session_state.unassigned_reserve_plan = us.build_plan(summary)
                st.session_state.unassigned_reserve_armed = False
                st.session_state.pop("unassigned_reserve_result", None)
            except Exception as exc:
                st.error(f"讀取班表失敗：{exc}")
    result = st.session_state.get("unassigned_reserve_result")
    if result:
        st.markdown("**上次成立結果**")
        st.dataframe(pd.DataFrame([{"結果": "✅" if r.get("success") else ("🗑️" if r.get("message") == "已取消（合併）" else "❌"), "日期": r.get("service_date", ""),
                                    "時段": f"{r.get('group', '')} {r.get('period', '')}", "人數": r.get("person", 0),
                                    "訂單編號": r.get("order_no", ""), "專員": r.get("staff", ""),
                                    "說明": r.get("message", "")} for r in result]), width="stretch", hide_index=True)
    plan = st.session_state.get("unassigned_reserve_plan")
    if plan is None:
        return
    if not plan:
        st.success("這段期間沒有未配班專員。")
        return
    st.dataframe(pd.DataFrame([{"日期": p["service_date"], "時段": p["group"], "保留單": f"{p['period']} {p['person']}人{p['hours']}小時",
                                "未配班（勾班時數）": p["staff"]} for p in plan]), width="stretch", hide_index=True)
    total = len(plan)
    # 兩段按鈕確認（不用勾選框：正式機上勾選框勾不起來）
    if not st.session_state.get("unassigned_reserve_armed"):
        if st.button(f"成立以上 {total} 張檸檬保留單", type="primary", width="stretch", key="unassigned_reserve_arm"):
            st.session_state.unassigned_reserve_armed = True
            st.rerun()
        return
    st.warning(f"確定要在{_env_label(env)}成立以上 {total} 張檸檬保留單？")
    c_ok, c_cancel = st.columns(2)
    with c_cancel:
        if st.button("取消", width="stretch", key="unassigned_reserve_cancel"):
            st.session_state.unassigned_reserve_armed = False
            st.rerun()
    with c_ok:
        run_now = st.button("確定成立", type="primary", width="stretch", key="unassigned_reserve_run")
    if run_now:
        st.session_state.unassigned_reserve_armed = False
        status = st.status("成立保留單中（每輪先重讀班表）…", expanded=True)
        try:
            out = us.merge_and_create(env_name=env, backend_email=backend_email.strip(),
                                      backend_password=backend_password.strip(), lookup_result=lookup, region=region,
                                      address=address, date_start=start.isoformat(), date_end=end.isoformat(),
                                      payway=payway, log=status.write)
            results = out["created"] + [
                {"success": False, "service_date": c.get("service_date", ""), "group": c.get("merge_group", ""),
                 "period": c.get("period", ""), "order_no": c.get("order_no", ""),
                 "message": ("已取消（合併）" if c.get("ok") else f"合併取消失敗：{c.get('message', '')}")}
                for c in out["cancelled"]
            ]
            from shared.execution_log_service import log_execution

            ok = sum(1 for r in out["created"] if r.get("success"))
            merged = sum(1 for c in out["cancelled"] if c.get("ok"))
            status.update(label=f"完成：成立 {ok} 張" + (f"、合併取消 {merged} 張 1 人保留單" if merged else ""), state="complete", expanded=False)
            log_execution(function_name="未配班成立保留單", status="成功" if all(r.get("success") or r.get("message") == "已取消（合併）" for r in results) else "失敗",
                          area=region, target=address, message=f"{start}～{end}：成立 {ok} 張、合併取消 {merged} 張")
        except Exception as exc:
            results = [{"success": False, "message": f"執行失敗：{exc}"}]
            status.update(label="執行失敗", state="error", expanded=True)
        st.session_state.unassigned_reserve_result = results
        st.session_state.pop("unassigned_reserve_plan", None)
        st.rerun()


def _render_record(lookup, region: str) -> None:
    from shared.unassigned_staff_schedule import DEFAULT_DAYS, date_range, write_calendar

    st.caption("未來 2 週某時段未配班只剩 1 位專員，記到行事曆（每日排程：tool-system 排程設定 "
               "功能代號 unassigned_staff_record）。")
    today = date.today()
    date_start, date_end = date_range(today, DEFAULT_DAYS)
    st.info(f"範圍：{date_start}～{date_end}")
    if st.button("讀取只剩 1 人的時段", width="stretch", key="unassigned_record_scan"):
        with st.spinner("讀取班表中…"):
            try:
                st.session_state.unassigned_record_rows = us.single_left(
                    us.scan_range(us._schedule_getter(lookup), date_start, date_end))
            except Exception as exc:
                st.error(f"讀取班表失敗：{exc}")
    rows = st.session_state.get("unassigned_record_rows")
    if rows is None:
        return
    if not rows:
        st.success("沒有只剩 1 人的時段。")
    else:
        st.code("\n".join(r["text"] for r in rows), language=None)
        st.dataframe(pd.DataFrame([{"日期": r["date"], "時段": r["group"], "專員": r["name"], "勾班時數": r["hours"]}
                                   for r in rows]), width="stretch", hide_index=True)
    ids = us.notice_calendar_ids()
    if not ids:
        st.warning(f"尚未設定排程行事曆（Streamlit Secrets {us.NOTICE_CALENDAR_ENV}），無法記入行事曆。")
        return
    st.caption("記入排程行事曆：" + "、".join(ids))
    if st.button("記入行事曆", width="stretch", key="unassigned_record_write"):
        from zoneinfo import ZoneInfo

        event = us.build_calendar_event(region, rows, date_start, date_end, datetime.now(ZoneInfo("Asia/Taipei")))
        messages, ok = write_calendar(event, ids)
        (st.success if ok else st.error)("；".join(messages))
