# -*- coding: utf-8 -*-
"""
Runtime patch for vip_calendar_sync.py.

Adds the newer VIP calendar behavior without touching the large ordersapp.py / quick_order.py files:
1. VIP lookup uses the query range selected by the UI, and shows only backend
   orders + Google Calendar events inside that range.
2. A newly-created yellow VIP order reuses a nearby purple prebook event when
   possible, moving it to the confirmed date/time instead of creating a duplicate.
3. VIP UI is compare-first: query -> compare backend/calendar -> choose action.
4. Existing Google Calendar events can update confirmation text and actual colorId.
"""

from datetime import datetime, time, timedelta


def _norm(value):
    import re
    return re.sub(r"\s+", "", str(value or ""))


def _event_dt(vcs, event):
    raw = (event.get("start") or {}).get("dateTime")
    if not raw:
        return None
    try:
        dt = vcs.orders.parse_event_time(raw)
        return dt.astimezone(vcs.TAIPEI_TZ) if dt else None
    except Exception:
        return None


def _event_end_dt(vcs, event):
    raw = (event.get("end") or {}).get("dateTime")
    if not raw:
        return None
    try:
        dt = vcs.orders.parse_event_time(raw)
        return dt.astimezone(vcs.TAIPEI_TZ) if dt else None
    except Exception:
        return None


def _replace_confirm_status(text):
    text = str(text or "")
    replacements = [
        ("<每月確認/自行預約>", "<已確認/自行預約>"),
        ("＜每月確認/自行預約＞", "＜已確認/自行預約＞"),
        ("每月確認/自行預約", "已確認/自行預約"),
    ]
    for old, new in replacements:
        if old in text:
            return text.replace(old, new)
    return text


def _query_range(vcs):
    """Read YYYY-MM-DD query range selected by the Streamlit UI."""
    today = datetime.now(vcs.TAIPEI_TZ).date()
    default_s = today.replace(day=1)
    default_e = default_s + timedelta(days=62)
    try:
        date_s = str(vcs.st.session_state.get("vipcal_query_date_s") or default_s.isoformat())
        date_e = str(vcs.st.session_state.get("vipcal_query_date_e") or default_e.isoformat())
        start_d = datetime.strptime(date_s, "%Y-%m-%d").date()
        end_d = datetime.strptime(date_e, "%Y-%m-%d").date()
        if start_d > end_d:
            start_d, end_d = end_d, start_d
        return start_d, end_d
    except Exception:
        return default_s, default_e


def find_nearby_prebook_event(vcs, service, calendar_id, phone, address, new_date_s, new_period_s, window_days=14):
    """Return best nearby purple/prebook calendar event for this VIP customer."""
    target_date = datetime.strptime(new_date_s, "%Y-%m-%d").date()
    start_dt = datetime.combine(target_date - timedelta(days=window_days), time.min, tzinfo=vcs.TAIPEI_TZ)
    end_dt = datetime.combine(target_date + timedelta(days=window_days + 1), time.min, tzinfo=vcs.TAIPEI_TZ)
    events = vcs._list_events(service, calendar_id, start_dt, end_dt)

    phone_n = _norm(phone)
    addr_n = _norm(address)
    p_start, p_end = str(new_period_s).replace(" ", "").split("-", 1)

    scored = []
    for event in events:
        summary = str(event.get("summary") or "")
        description = str(event.get("description") or "")
        location = str(event.get("location") or "")
        blob = _norm(" ".join([summary, description, location]))
        if phone_n and phone_n not in blob:
            continue

        start = _event_dt(vcs, event)
        end = _event_end_dt(vcs, event)
        if not start or not end:
            continue
        date_diff = abs((start.date() - target_date).days)
        if date_diff > window_days:
            continue

        event_period = f"{start.strftime('%H:%M')}-{end.strftime('%H:%M')}"
        same_period = event_period == f"{p_start}-{p_end}"
        same_addr = bool(addr_n and addr_n in blob)
        is_purple = str(event.get("colorId") or "") == str(vcs.COLOR_PURPLE)
        is_prebook = (
            "每月確認/自行預約" in summary
            or "每月確認/自行預約" in description
            or "VIP預排" in description
        )

        score = 0
        if is_prebook:
            score += 100
        if is_purple:
            score += 60
        if same_period:
            score += 40
        if same_addr:
            score += 20
        score += max(0, 20 - date_diff)
        scored.append((score, date_diff, start, event))

    if not scored:
        return None
    scored.sort(key=lambda x: (-x[0], x[1], x[2]))
    best = scored[0]
    return best[3] if best[0] >= 40 else None


def update_prebook_to_confirmed(vcs, service, calendar_id, event, phone, address, new_date_s, new_period_s, order_no):
    start_dt, end_dt = vcs._event_range(new_date_s, new_period_s)
    summary = _replace_confirm_status(event.get("summary", ""))
    description = _replace_confirm_status(event.get("description", ""))
    description = vcs._append_status(description, f"已成單 {order_no}")
    if order_no and order_no not in _norm(description):
        description = (description + f"\n訂單編號：{order_no}").strip()
    if phone and phone not in _norm(description):
        description = (description + f"\n電話：{phone}").strip()

    body = {
        "start": {"dateTime": start_dt.isoformat(), "timeZone": "Asia/Taipei"},
        "end": {"dateTime": end_dt.isoformat(), "timeZone": "Asia/Taipei"},
        "colorId": str(vcs.COLOR_YELLOW),
        "summary": summary,
        "description": description,
    }
    if address and not event.get("location"):
        body["location"] = address

    return service.events().patch(
        calendarId=calendar_id,
        eventId=event["id"],
        body=body,
    ).execute()


def _confirmation_status(event):
    text = " ".join([
        str(event.get("summary") or ""),
        str(event.get("description") or ""),
    ])
    if "已確認/自行預約" in text or "已確認" in text:
        return "已確認"
    if "每月確認/自行預約" in text or "每月確認" in text:
        return "每月確認"
    return "未標示"


def _set_confirmation_text(text, target):
    text = str(text or "")
    if target not in ("每月確認", "已確認"):
        return text

    pairs = [
        ("<每月確認/自行預約>", f"<{target}/自行預約>"),
        ("＜每月確認/自行預約＞", f"＜{target}/自行預約＞"),
        ("每月確認/自行預約", f"{target}/自行預約"),
        ("<已確認/自行預約>", f"<{target}/自行預約>"),
        ("＜已確認/自行預約＞", f"＜{target}/自行預約＞"),
        ("已確認/自行預約", f"{target}/自行預約"),
    ]
    changed = False
    for old, new in pairs:
        if old in text:
            text = text.replace(old, new)
            changed = True
    if not changed:
        prefix = f"＜{target}/自行預約＞"
        text = f"{prefix} {text}".strip()
    return text


def _color_meta(vcs, color_id):
    color_id = str(color_id or "")
    mapping = {
        str(vcs.COLOR_PURPLE): ("🟣", "紫色／預排"),
        str(vcs.COLOR_YELLOW): ("🟡", "黃色／已確認"),
        str(vcs.COLOR_GREEN): ("🟢", "綠色／取消暫停"),
        "": ("⚪", "預設色／未指定 colorId"),
    }
    return mapping.get(color_id, ("🔵", f"其他顏色／colorId={color_id}"))


def _calendar_row_label(vcs, row):
    icon, color_name = _color_meta(vcs, row.get("color_id"))
    event = row.get("event") or {}
    status = _confirmation_status(event)
    return (
        f"{row.get('date', '')} {row.get('period', '')}｜{icon} {color_name}｜"
        f"{status}｜{row.get('summary', '')}"
    )


def _find_matching_calendar_row(vcs, customer, source):
    rows = customer.get("calendar_events") or []
    order_no = _norm(source.get("order_no"))
    address = _norm(source.get("address"))
    phone = _norm(customer.get("phone"))
    source_date = str(source.get("date") or "")
    source_period = str(source.get("time") or "").replace(" ", "")

    best = None
    best_score = -1
    for row in rows:
        event = row.get("event") or {}
        blob = _norm(" ".join([
            event.get("summary", ""), event.get("description", ""), event.get("location", "")
        ]))
        score = 0
        if order_no and order_no in blob:
            score += 200
        if source_date and row.get("date") == source_date:
            score += 60
        if source_period and row.get("period") == source_period:
            score += 40
        if address and address in blob:
            score += 30
        if phone and phone in blob:
            score += 20
        if score > best_score:
            best_score = score
            best = row
    return best if best_score >= 40 else None


def update_calendar_event_fields(vcs, calendar_row, confirmation="保持不變", color_choice="保持不變"):
    event = calendar_row.get("event") or {}
    calendar_id = calendar_row.get("calendar_id")
    event_id = event.get("id") or calendar_row.get("event_id")
    if not calendar_id or not event_id:
        raise ValueError("此日曆事件缺少 calendarId 或 eventId，無法修改")

    body = {}
    if confirmation != "保持不變":
        body["summary"] = _set_confirmation_text(event.get("summary", ""), confirmation)
        body["description"] = _set_confirmation_text(event.get("description", ""), confirmation)

    color_map = {
        "紫色／預排": str(vcs.COLOR_PURPLE),
        "黃色／已確認": str(vcs.COLOR_YELLOW),
        "綠色／取消暫停": str(vcs.COLOR_GREEN),
    }
    if color_choice != "保持不變":
        body["colorId"] = color_map[color_choice]

    if not body:
        return event

    service = vcs.build_calendar_service()
    return service.events().patch(
        calendarId=calendar_id,
        eventId=event_id,
        body=body,
    ).execute()


def _render_query_results(vcs, customer, source):
    vcs.st.divider()
    vcs.st.markdown("## 同步查詢結果")
    vcs.st.caption(
        f"查詢範圍：{customer.get('query_date_s', '')} ～ {customer.get('query_date_e', '')}。"
        "先確認後台與 Google 日曆，再選擇下方處理方式。"
    )

    matched = _find_matching_calendar_row(vcs, customer, source)
    left, right = vcs.st.columns(2)
    with left:
        vcs.st.markdown("### 後台已付款訂單")
        vcs.st.write(f"**訂單編號：** {source.get('order_no', '')}")
        vcs.st.write(f"**日期：** {source.get('date', '')}")
        vcs.st.write(f"**時段：** {source.get('time', '')}")
        vcs.st.write(f"**地址：** {source.get('address', '')}")
        vcs.st.write(f"**付款：** {source.get('payway', '')}")

    with right:
        vcs.st.markdown("### Google 日曆")
        if matched:
            event = matched.get("event") or {}
            icon, color_name = _color_meta(vcs, matched.get("color_id"))
            vcs.st.write(f"**日期：** {matched.get('date', '')}")
            vcs.st.write(f"**時段：** {matched.get('period', '')}")
            vcs.st.write(f"**確認狀態：** {_confirmation_status(event)}")
            vcs.st.write(f"**實際顏色：** {icon} {color_name}")
            vcs.st.write(f"**Event ID：** `{event.get('id', '')}`")
            vcs.st.write(f"**標題：** {event.get('summary', '')}")
        else:
            vcs.st.warning("沒有找到可與此訂單直接配對的 Google 日曆事件")

    if matched:
        diffs = []
        backend_period = str(source.get("time") or "").replace(" ", "")
        if str(source.get("date") or "") != str(matched.get("date") or ""):
            diffs.append(f"日期不同：後台 {source.get('date', '')} / 日曆 {matched.get('date', '')}")
        if backend_period != str(matched.get("period") or "").replace(" ", ""):
            diffs.append(f"時段不同：後台 {backend_period} / 日曆 {matched.get('period', '')}")
        if _confirmation_status(matched.get("event") or {}) == "每月確認":
            diffs.append("日曆仍是『每月確認』，可改為『已確認』")
        if not matched.get("color_id"):
            diffs.append("日曆未指定實際 colorId，可設定為紫／黃／綠")

        if diffs:
            vcs.st.warning("⚠️ 發現差異\n\n" + "\n\n".join(f"- {x}" for x in diffs))
        else:
            vcs.st.success("✅ 後台與配對日曆的日期、時段目前一致")

    rows = customer.get("calendar_events") or []
    if rows:
        with vcs.st.expander("查看本次查詢到的全部 Google 日曆事件", expanded=False):
            for row in rows:
                vcs.st.write(_calendar_row_label(vcs, row))

    return matched


def _render_compare_first_ui(vcs, backend_email, backend_password, env_name):
    st = vcs.st
    st.markdown("### VIP 訂單／Google 日曆同步")
    st.caption("流程：先查詢 → 比對後台與日曆 → 再決定異動、取消、預排或修改日曆。")

    phone = st.text_input("VIP 客戶手機號碼", key="vipcal_phone", placeholder="09xxxxxxxx")
    if st.button("🔎 查詢 VIP 訂單＋Google 日曆", key="vipcal_lookup", type="primary", use_container_width=True):
        if not backend_email or not backend_password:
            st.error("請先輸入後台帳號與密碼")
        else:
            try:
                data = vcs.load_vip_customer(env_name, backend_email, backend_password, phone)
                data["lookup"]["backend_email"] = backend_email
                data["lookup"]["backend_password"] = backend_password
                st.session_state.vipcal_customer = data
                st.session_state.pop("vipcal_change_check", None)
                st.session_state.pop("vipcal_book_check", None)
            except Exception as exc:
                st.session_state.vipcal_customer = None
                st.error(str(exc))

    customer = st.session_state.get("vipcal_customer")
    if not customer:
        return

    orders_list = customer.get("orders") or []
    if not orders_list:
        st.warning("查無已付款服務訂單，無法取得 VIP 服務範本")
        return

    labels = [vcs._order_label(o) for o in orders_list]
    selected_label = st.selectbox("選擇原訂單／範本", labels, key="vipcal_source_order")
    source = orders_list[labels.index(selected_label)]
    st.info(f"客戶：{customer.get('name')}　電話：{customer.get('phone')}　原訂單：{source.get('order_no')}")

    matched = _render_query_results(vcs, customer, source)

    st.divider()
    st.markdown("## 選擇處理方式")
    action = st.radio(
        "功能",
        ["異動日期／時段", "取消／暫停", "僅新增日曆", "先預約再新增日曆", "修改日曆資訊"],
        horizontal=True,
        key="vipcal_action",
    )

    if action == "修改日曆資訊":
        rows = customer.get("calendar_events") or []
        if not rows:
            st.warning("本次查詢沒有 Google 日曆事件可修改")
            return
        labels = [_calendar_row_label(vcs, row) for row in rows]
        default_idx = rows.index(matched) if matched in rows else 0
        selected_event_label = st.selectbox("選擇要修改的 Google 日曆事件", labels, index=default_idx, key="vipcal_edit_event")
        calendar_row = rows[labels.index(selected_event_label)]
        event = calendar_row.get("event") or {}
        icon, color_name = _color_meta(vcs, calendar_row.get("color_id"))
        st.info(
            f"目前：{_confirmation_status(event)}｜{icon} {color_name}｜"
            f"Event ID：{event.get('id', '')}"
        )
        c1, c2 = st.columns(2)
        with c1:
            confirmation = st.selectbox("確認狀態", ["保持不變", "每月確認", "已確認"], key="vipcal_edit_confirmation")
        with c2:
            color_choice = st.selectbox(
                "日曆顏色",
                ["保持不變", "紫色／預排", "黃色／已確認", "綠色／取消暫停"],
                key="vipcal_edit_color",
            )
        if st.button("✅ 套用修改到 Google 日曆", key="vipcal_edit_exec", type="primary", use_container_width=True):
            try:
                updated = update_calendar_event_fields(vcs, calendar_row, confirmation, color_choice)
                st.success(f"✅ Google 日曆已更新：{updated.get('summary', '')}")
                st.session_state.vipcal_customer = vcs.load_vip_customer(
                    env_name, backend_email, backend_password, customer.get("phone", "")
                )
                st.session_state.vipcal_customer["lookup"]["backend_email"] = backend_email
                st.session_state.vipcal_customer["lookup"]["backend_password"] = backend_password
                st.rerun()
            except Exception as exc:
                st.error(f"日曆修改失敗：{exc}")
        return

    if action == "取消／暫停":
        cancel_status = st.radio("取消處理方式", ["不需退款", "待退款", "待收異動"], horizontal=True, key="vipcal_cancel_status")
        memo = st.text_area("客人備註", key="vipcal_cancel_memo")
        charge_note = st.text_area("加收備註", key="vipcal_charge_note")
        refund_note = st.text_area("待退備註", key="vipcal_refund_note")
        if st.button("🛑 後台取消並同步日曆為綠色", key="vipcal_cancel_exec", type="primary", use_container_width=True):
            with st.spinner("先取消後台訂單，再同步日曆…"):
                result = vcs.execute_cancel_and_calendar(customer, source, cancel_status, memo, charge_note, refund_note)
            if result.get("ok"):
                st.success("✅ 後台已取消，Google 日曆已改為綠色（取消／暫停）")
            elif result.get("backend_already_cancelled"):
                st.error(f"⚠️ 後台已取消，但日曆同步失敗：{result.get('calendar_error')}")
            else:
                st.error(f"取消失敗：{result.get('backend', {}).get('message', result)}")
        return

    c1, c2 = st.columns(2)
    with c1:
        new_date = st.date_input("新服務日期", key="vipcal_new_date")
    with c2:
        default_period = str(source.get("time") or "").replace(" ", "")
        period_index = vcs.STANDARD_PERIODS.index(default_period) if default_period in vcs.STANDARD_PERIODS else 0
        new_period = st.selectbox("新服務時段", vcs.STANDARD_PERIODS, index=period_index, key="vipcal_new_period")
    new_date_s = new_date.isoformat()

    if action == "異動日期／時段":
        if st.button("🔎 先確認後台可異動", key="vipcal_check_change", use_container_width=True):
            try:
                check = vcs.check_backend_change_slot(customer, source, new_date_s, new_period)
                st.session_state.vipcal_change_check = {"date": new_date_s, "period": new_period, **check}
            except Exception as exc:
                st.session_state.vipcal_change_check = None
                st.error(str(exc))
        checked = st.session_state.get("vipcal_change_check")
        if checked and checked.get("date") == new_date_s and checked.get("period") == new_period:
            if checked.get("available"):
                st.success(f"✅ 後台可異動；可用專員：{checked.get('staff') or '後台有可用時段'}")
                if st.button("✅ 確定異動後台＋同步日曆", key="vipcal_change_exec", type="primary", use_container_width=True):
                    with st.spinner("先修改後台日期／時段，再移動 Google 日曆…"):
                        result = vcs.execute_change_and_calendar(customer, source, new_date_s, new_period)
                    if result.get("ok"):
                        st.success("✅ 後台異動成功，原 Google 日曆事件已移到新日期／時段並設為黃色")
                    elif result.get("backend_already_changed"):
                        st.error(f"⚠️ 後台已異動，但日曆同步失敗：{result.get('calendar_error')}")
                    else:
                        st.error(result.get("backend", {}).get("message", "異動失敗"))
            else:
                st.error("❌ 後台目前沒有該日期／時段可供異動，不會修改日曆")
        return

    if action == "僅新增日曆":
        allowed = vcs.can_calendar_only_prebook(new_date_s)
        st.caption(f"規則：每月 5 日後可先預排隔月服務。目前 {'符合' if allowed else '不符合'} 僅新增日曆條件。")
        if st.button("🟣 僅新增／複製紫色日曆", key="vipcal_calendar_only", type="primary", disabled=not allowed, use_container_width=True):
            try:
                with st.spinner("新增 VIP 預排日曆…"):
                    event = vcs.execute_calendar_only(customer, source, new_date_s, new_period)
                st.success(f"✅ 已新增紫色 VIP 預排日曆：{event.get('summary', '')}")
            except Exception as exc:
                st.error(str(exc))
        return

    if action == "先預約再新增日曆":
        if st.button("🔎 先確認後台可預約", key="vipcal_check_book", use_container_width=True):
            try:
                check = vcs.check_backend_change_slot(customer, source, new_date_s, new_period)
                st.session_state.vipcal_book_check = {"date": new_date_s, "period": new_period, **check}
            except Exception as exc:
                st.session_state.vipcal_book_check = None
                st.error(str(exc))
        checked = st.session_state.get("vipcal_book_check")
        if checked and checked.get("date") == new_date_s and checked.get("period") == new_period:
            if not checked.get("available"):
                st.error("❌ 後台目前沒有該日期／時段可預約，不會新增日曆")
            else:
                st.success(f"✅ 後台可預約；可用專員：{checked.get('staff') or '後台有可用時段'}")
                if st.button("🟡 成立後台訂單＋新增黃色日曆", key="vipcal_book_exec", type="primary", use_container_width=True):
                    try:
                        with st.spinner("先成立後台訂單，再新增 Google 日曆…"):
                            result = vcs.execute_book_then_calendar(customer, source, new_date_s, new_period)
                        if result.get("ok"):
                            st.success(f"✅ 訂單 {result['order'].get('order_no')} 已成立，黃色日曆已新增")
                        else:
                            st.error(f"⚠️ 訂單 {result['order'].get('order_no')} 已成立，但日曆新增失敗：{result.get('calendar_error')}")
                    except Exception as exc:
                        st.error(str(exc))


def apply_patch(vcs):
    """Patch functions inside imported vip_calendar_sync module."""
    original_create = vcs.create_or_copy_calendar_event
    original_load = vcs.load_vip_customer

    def load_vip_customer_with_calendar(env_name, backend_email, backend_password, phone, clean_type_id="1"):
        data = original_load(env_name, backend_email, backend_password, phone, clean_type_id)
        start_d, end_d = _query_range(vcs)
        start_s, end_s = start_d.isoformat(), end_d.isoformat()

        data["orders"] = [
            row for row in (data.get("orders") or [])
            if row.get("date") and start_s <= str(row.get("date")) <= end_s
        ]
        data["query_date_s"] = start_s
        data["query_date_e"] = end_s

        try:
            service = vcs.build_calendar_service()
            all_events = []
            seen = set()
            range_start = datetime.combine(start_d, time.min, tzinfo=vcs.TAIPEI_TZ)
            range_end = datetime.combine(end_d + timedelta(days=1), time.min, tzinfo=vcs.TAIPEI_TZ)
            for addr in data.get("addresses") or [""]:
                region = vcs.orders.get_region_by_address(addr, vcs.ACCOUNTS) if addr else "台北"
                region = region or "台北"
                calendar_id = vcs._calendar_id(region)
                events = vcs._list_events(service, calendar_id, range_start, range_end)
                for ev in events:
                    blob = _norm(" ".join([
                        ev.get("summary", ""), ev.get("description", ""), ev.get("location", "")
                    ]))
                    if data.get("phone") and _norm(data["phone"]) not in blob:
                        continue
                    key = (calendar_id, ev.get("id"))
                    if key in seen:
                        continue
                    seen.add(key)
                    start = _event_dt(vcs, ev)
                    end = _event_end_dt(vcs, ev)
                    all_events.append({
                        "calendar_id": calendar_id,
                        "event_id": ev.get("id", ""),
                        "event": ev,
                        "date": start.strftime("%Y-%m-%d") if start else "",
                        "period": f"{start.strftime('%H:%M')}-{end.strftime('%H:%M')}" if start and end else "",
                        "summary": ev.get("summary", ""),
                        "color_id": str(ev.get("colorId") or ""),
                        "confirmation_status": _confirmation_status(ev),
                    })
            all_events.sort(key=lambda x: (x.get("date", ""), x.get("period", "")))
            data["calendar_events"] = all_events
            data["calendar_lookup_error"] = ""
        except Exception as exc:
            data["calendar_events"] = []
            data["calendar_lookup_error"] = str(exc)
        return data

    def create_or_update_calendar_event(region, phone, address, new_date_s, new_period_s, color_id, order_no="", name="", reference_event=None):
        service = vcs.build_calendar_service()
        calendar_id = vcs._calendar_id(region)

        if str(color_id) == str(vcs.COLOR_YELLOW) and order_no:
            candidate = find_nearby_prebook_event(
                vcs, service, calendar_id, phone, address, new_date_s, new_period_s
            )
            if candidate:
                updated = update_prebook_to_confirmed(
                    vcs, service, calendar_id, candidate, phone, address,
                    new_date_s, new_period_s, order_no,
                )
                updated["_vip_sync_action"] = "updated_existing_prebook"
                original_dt = _event_dt(vcs, candidate)
                updated["_vip_original_date"] = original_dt.strftime("%Y-%m-%d") if original_dt else ""
                return updated

        created = original_create(
            region=region, phone=phone, address=address,
            new_date_s=new_date_s, new_period_s=new_period_s,
            color_id=color_id, order_no=order_no, name=name,
            reference_event=reference_event,
        )
        if isinstance(created, dict):
            created["_vip_sync_action"] = "created_new_event"
        return created

    vcs.load_vip_customer = load_vip_customer_with_calendar
    vcs.create_or_copy_calendar_event = create_or_update_calendar_event
    vcs.render_vip_calendar_sync = lambda backend_email, backend_password, env_name: _render_compare_first_ui(
        vcs, backend_email, backend_password, env_name
    )
    return vcs
