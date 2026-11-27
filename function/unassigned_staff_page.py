# -*- coding: utf-8 -*-
"""未配班檢查頁：① 成立保留單 ② 記錄未配班人員（只剩 1 人的時段）。

變更紀錄
- 2026-11-27：① 保留單沒有「檸檬人勿動」時：只有檸檬人 → 取消；檸檬人＋專員 → 取消後就專員重建。
- 2026-11-27：② 可改範圍天數（主控表參數設定）；①② 可改排程時間（主控表排程設定 D 欄）。
- 2026-11-26：① 新增「自動排程設定」：保留單開始日／結束日／停止日改在頁面設定（存主控表「參數設定」）。
- 2026-11-22：① 專員全是檸檬人的保留單一併取消。
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


def _render_schedule_time(key: str, prefix: str) -> None:
    """排程時間（主控表「排程設定」D 欄）：區間每隔 N，或固定時間。存檔後下一個時段生效。"""
    from datetime import time as _time

    from shared import unassigned_settings as uset

    state_key = f"{prefix}_time_text"
    if state_key not in st.session_state:
        try:
            st.session_state[state_key] = uset.load_schedule_time(key)
        except Exception as exc:
            st.session_state[state_key] = ""
            st.warning(f"讀取排程設定失敗：{exc}")
    current = st.session_state[state_key]
    st.markdown(f"**排程時間**（目前：{current or '未設定'}）")
    m = uset._RANGE_RE.match(current or "")
    mode = st.radio("方式", ["區間", "固定時間"], index=0 if (m or not current) else 1, horizontal=True,
                    key=f"{prefix}_mode")
    every_opts = ["每小時", "每2小時", "每3小時", "每30分鐘"]
    if mode == "區間":
        c1, c2, c3 = st.columns(3)
        start = _time(int(m.group(1)), int(m.group(2))) if m else _time(8, 30)
        end = _time(int(m.group(3)), int(m.group(4))) if m else _time(17, 30)
        cur_every = (f"每{m.group(5)}{m.group(6)}" if m and m.group(5) else (f"每{m.group(6)}" if m else "每小時"))
        with c1:
            t1 = st.time_input("開始", value=start, step=600, key=f"{prefix}_t1")
        with c2:
            t2 = st.time_input("結束", value=end, step=600, key=f"{prefix}_t2")
        with c3:
            every = st.selectbox("間隔", every_opts, index=every_opts.index(cur_every) if cur_every in every_opts else 0,
                                 key=f"{prefix}_every")
        text = uset.build_time_text("區間", f"{t1:%H:%M}", f"{t2:%H:%M}", every)
    else:
        raw = st.text_input("時間（多個用逗號，例 08:30,13:30）", value=current if not m else "", key=f"{prefix}_times")
        text = ",".join(x.strip() for x in raw.replace("，", ",").split(",") if x.strip())
    if st.button("儲存排程時間", key=f"{prefix}_time_save"):
        try:
            uset.save_schedule_time(key, text)
            st.session_state[state_key] = text
            st.success(f"已儲存：{text}（下一個時段起生效）")
        except Exception as exc:
            st.error(f"儲存失敗：{exc}")


def _render_schedule_settings(rs, parse_day, default_start: str, default_end: str) -> tuple[date, date]:
    """自動排程（每小時）的保留單區間與停止日；存主控表「參數設定」。回傳 (開始日, 結束日)。"""
    if "unassigned_reserve_settings" not in st.session_state:
        st.session_state.unassigned_reserve_settings = rs.load(log=lambda m: st.warning(m))
    saved = st.session_state.unassigned_reserve_settings

    def _day(item: str, default: str = "") -> date | None:
        try:
            return parse_day(saved.get(item) or default) if (saved.get(item) or default) else None
        except ValueError:
            return parse_day(default) if default else None

    start, end, stop = _day(rs.START_ITEM, default_start), _day(rs.END_ITEM, default_end), _day(rs.STOP_ITEM)
    with st.expander(f"⏰ 自動排程設定（目前 {rs.fmt(start)}～{rs.fmt(end)}"
                     f"{'，' + rs.fmt(stop) + ' 起停止' if stop else ''}）", expanded=False):
        st.caption("排程依這裡的區間自動成立保留單（排程時間在下方設定）；"
                   "設定「停止日」後，當天（含）起排程不再自動成立（頁面手動成立不受影響）。存在主控表「參數設定」。")
        c1, c2, c3 = st.columns(3)
        with c1:
            new_start = st.date_input("保留單開始日", value=start, key="urs_start")
        with c2:
            new_end = st.date_input("保留單結束日", value=end, key="urs_end")
        with c3:
            use_stop = st.checkbox("設定停止日", value=stop is not None, key="urs_use_stop")
            new_stop = st.date_input("自動成立停止日", value=stop or date.today(), key="urs_stop",
                                     disabled=not use_stop)
        if st.button("儲存區間與停止日", key="urs_save"):
            try:
                rs.save(new_start, new_end, new_stop if use_stop else None)
                st.session_state.unassigned_reserve_settings = {
                    rs.START_ITEM: rs.fmt(new_start), rs.END_ITEM: rs.fmt(new_end),
                    rs.STOP_ITEM: rs.fmt(new_stop) if use_stop else ""}
                st.success("已儲存，下一次排程起生效")
            except Exception as exc:
                st.error(f"儲存失敗：{exc}")
        st.divider()
        _render_schedule_time("unassigned_reserve_create", "urs")
    return start, end


def _render_reserve(env, lookup, get_region_by_address, backend_email: str = "", backend_password: str = "") -> None:
    from function.reserve_optimizer import member_addresses

    st.caption("日期區間內只要有未配班就成立保留單：同一天同一時段（上午／下午／全天）合成一張，"
               "人數＝人數、時數取最短（1人2小時＋1人3小時 → 2人2小時；1 人也成立 1人單）。"
               "後台查不到這麼多人時（例如有人不服務保留地址），人數減 1 再試。"
               "同一天同一時段已有 2 張以上 1 人保留單時，會先取消再合併成一張 N 人保留單；客服備註沒有「檸檬人勿動」的保留單：只有檸檬人會取消；檸檬人＋專員會先取消，再就專員重建保留單。")
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
    from shared import reserve_settings as rs
    from shared.unassigned_reserve_schedule import RESERVE_END, RESERVE_START, parse_day

    saved = _render_schedule_settings(rs, parse_day, RESERVE_START, RESERVE_END)
    # 預設＝自動排程的區間（頁面設定）
    with d1:
        start = st.date_input("開始日期", value=saved[0], key="unassigned_reserve_start")
    with d2:
        end = st.date_input("結束日期", value=saved[1], key="unassigned_reserve_end")
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
        st.dataframe(pd.DataFrame([{"結果": "✅" if r.get("success") else ("🗑️" if str(r.get("message", "")).startswith("已取消（") else "❌"), "日期": r.get("service_date", ""),
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
                 "message": ((f"已取消（{c['merge_group']}）" if c.get("merge_group") in ("檸檬人", "檸檬人＋專員") else "已取消（合併）") if c.get("ok")
                             else f"取消失敗：{c.get('message', '')}")}
                for c in out["cancelled"]
            ]
            from shared.execution_log_service import log_execution

            ok = sum(1 for r in out["created"] if r.get("success"))
            merged = sum(1 for c in out["cancelled"] if c.get("ok"))
            status.update(label=f"完成：成立 {ok} 張" + (f"、取消 {merged} 張（合併 1 人單／檸檬人單／檸檬人＋專員）" if merged else ""), state="complete", expanded=False)
            log_execution(function_name="未配班成立保留單", status="成功" if all(r.get("success") or str(r.get("message", "")).startswith("已取消（") for r in results) else "失敗",
                          area=region, target=address, message=f"{start}～{end}：成立 {ok} 張、取消 {merged} 張（合併／檸檬人）")
        except Exception as exc:
            results = [{"success": False, "message": f"執行失敗：{exc}"}]
            status.update(label="執行失敗", state="error", expanded=True)
        st.session_state.unassigned_reserve_result = results
        st.session_state.pop("unassigned_reserve_plan", None)
        st.rerun()


def _render_record(lookup, region: str) -> None:
    from shared import unassigned_settings as uset
    from shared.unassigned_staff_schedule import date_range, write_calendar

    if "unassigned_record_days" not in st.session_state:
        st.session_state.unassigned_record_days = uset.load_days(log=lambda m: st.warning(m))
    days = int(st.session_state.unassigned_record_days)
    st.caption(f"明天起 {days} 天內，某時段未配班只剩 1 位專員，記到排程行事曆。")
    with st.expander(f"⏰ 自動排程設定（範圍：明天起 {days} 天）", expanded=False):
        st.caption("存在主控表（範圍天數→參數設定、排程時間→排程設定），排程下一次執行起生效。")
        new_days = st.number_input("範圍天數（明天起幾天）", min_value=1, max_value=60, value=days, step=1,
                                   key="urr_days")
        if st.button("儲存範圍天數", key="urr_days_save"):
            try:
                uset.save_days(int(new_days))
                st.session_state.unassigned_record_days = int(new_days)
                st.session_state.pop("unassigned_record_rows", None)
                st.success(f"已儲存：明天起 {int(new_days)} 天")
                st.rerun()
            except Exception as exc:
                st.error(f"儲存失敗：{exc}")
        st.divider()
        _render_schedule_time("unassigned_staff_record", "urr")
    today = date.today()
    date_start, date_end = date_range(today, days)
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
