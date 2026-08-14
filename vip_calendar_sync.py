# ============================================================
# File: vip_calendar_sync.py
# Module: VIP order / Google Calendar synchronization
# Created: 2026-08-07
# Updated: 2026-08-08
# v8.75: UI help is provided by ordersapp.py; core VIP/calendar sync logic unchanged.
#
# Standalone module. Do NOT add new business logic to quick_order.py.
# ordersapp.py can import render_vip_calendar_sync later.
# ============================================================
# -*- coding: utf-8 -*-

import copy
import re
from datetime import date, datetime, time, timedelta, timezone

import streamlit as st

import orders
import quick_order as qo
from accounts import ACCOUNTS
from cancel_order import cancel_orders
from env import GOOGLE_CALENDAR_MAP, COLOR_PURPLE, COLOR_YELLOW


TAIPEI_TZ = timezone(timedelta(hours=8))
COLOR_GREEN = "10"  # Google Calendar: 羅勒綠
STANDARD_PERIODS = [
    "08:30-12:30", "09:00-11:00", "09:00-12:00",
    "14:00-16:00", "14:00-17:00", "14:00-18:00",
    "09:00-16:00", "09:00-18:00",
]
CLEAN_TYPE_ID_MAP = {"居家清潔": "1", "辦公室清潔": "2", "裝修細清": "3"}


def _period_hours(period_s: str) -> int:
    start_s, end_s = str(period_s).replace(" ", "").split("-", 1)
    sh, sm = [int(x) for x in start_s.split(":")]
    eh, em = [int(x) for x in end_s.split(":")]
    minutes = (eh * 60 + em) - (sh * 60 + sm)
    hours = minutes / 60
    if hours >= 7:
        hours -= 1
    return int(hours)


def _event_datetime(date_s: str, hm: str) -> datetime:
    hh, mm = [int(x) for x in hm.split(":")]
    d = datetime.strptime(date_s, "%Y-%m-%d").date()
    return datetime.combine(d, time(hh, mm), tzinfo=TAIPEI_TZ)


def _event_range(date_s: str, period_s: str):
    start_s, end_s = str(period_s).replace(" ", "").split("-", 1)
    return _event_datetime(date_s, start_s), _event_datetime(date_s, end_s)


def _normalize(value):
    return re.sub(r"\s+", "", str(value or ""))


def _next_month_ym(today_value=None):
    today_value = today_value or date.today()
    first = today_value.replace(day=1)
    next_month = (first + timedelta(days=32)).replace(day=1)
    return next_month.strftime("%Y-%m")


def can_calendar_only_prebook(target_date: str, today_value=None):
    """Rule requested by operations: after the 5th, calendar-only may prebook next month."""
    today_value = today_value or date.today()
    return today_value.day >= 5 and str(target_date)[:7] == _next_month_ym(today_value)


def _region_from_order(order_row: dict) -> str:
    address = str(order_row.get("address") or "")
    region = orders.get_region_by_address(address, ACCOUNTS) if address else ""
    return region or "台北"


def load_vip_customer(env_name, backend_email, backend_password, phone, clean_type_id="1"):
    """Login once, load member and paid service orders as templates for VIP operations."""
    lookup = qo.quick_lookup_member(env_name, backend_email, backend_password, phone, clean_type_id)
    if not lookup.get("member_payload"):
        raise ValueError("此電話查無會員資料")
    member = lookup["member_payload"].get("member", {}) or {}
    known_addresses = []
    for item in member.get("memberAddressList", []) or []:
        addr = str(item.get("address") or "").strip()
        if addr and addr not in known_addresses:
            known_addresses.append(addr)
    name = str(member.get("name") or "")
    paid_orders = qo.get_customer_paid_orders(
        lookup["session"], lookup["phone"], known_addresses, name=name
    )
    return {
        "lookup": lookup,
        "member": member,
        "name": name,
        "phone": lookup["phone"],
        "addresses": known_addresses,
        "orders": paid_orders,
    }


def check_backend_change_slot(customer_data, source_order: dict, new_date_s: str, new_period_s: str):
    """Check backend availability BEFORE changing an existing order."""
    payway = source_order.get("payway") or "儲值金"
    address = source_order.get("address") or ""
    clean_label = source_order.get("clean_type") or "居家清潔"
    clean_type_id = CLEAN_TYPE_ID_MAP.get(clean_label, "1")
    person = str(source_order.get("person") or "2")
    hour = str(source_order.get("hour") or _period_hours(new_period_s))
    rows = qo.quick_check_available_slots(
        env_name=customer_data["lookup"]["env_name"],
        payway=payway,
        lookup_result=customer_data["lookup"],
        address=address,
        clean_type_id=clean_type_id,
        date_s=new_date_s,
        hour=hour,
        person=person,
        periods=[new_period_s],
        period_hours={new_period_s: _period_hours(new_period_s)},
    )
    result = rows[0] if rows else {"available": False, "staff": ""}
    return {
        "available": bool(result.get("available")),
        "staff": result.get("staff") or "",
        "raw": result,
    }


def change_backend_order_date(customer_data, source_order: dict, new_date_s: str, new_period_s: str):
    """
    Safe sequence:
    1. check backend target date/period;
    2. only if available, POST /purchase/change_date/{id};
    3. return result for calendar sync caller.
    """
    check = check_backend_change_slot(customer_data, source_order, new_date_s, new_period_s)
    if not check["available"]:
        return {"ok": False, "stage": "availability", "message": "後台該日期／時段目前無可用班表", **check}

    lookup = customer_data["lookup"]
    ok, msg = qo._update_order_service_date(
        lookup["session"], lookup["base_url"], source_order["order_no"],
        new_date_s, new_period_s, phone=customer_data["phone"],
    )
    return {
        "ok": bool(ok), "stage": "change_date", "message": msg,
        "staff": check.get("staff", ""), "available": True,
    }


def create_backend_order_from_template(customer_data, source_order: dict, new_date_s: str, new_period_s: str):
    """Create a new service order first, then caller may add yellow calendar event."""
    payway = source_order.get("payway") or "儲值金"
    address = source_order.get("address") or ""
    clean_label = source_order.get("clean_type") or "居家清潔"
    clean_type_id = CLEAN_TYPE_ID_MAP.get(clean_label, "1")
    person = str(source_order.get("person") or "2")
    hour = str(source_order.get("hour") or _period_hours(new_period_s))
    region = _region_from_order(source_order)

    availability = qo.quick_check_available_slots(
        env_name=customer_data["lookup"]["env_name"], payway=payway,
        lookup_result=customer_data["lookup"], address=address,
        clean_type_id=clean_type_id, date_s=new_date_s, hour=hour, person=person,
        periods=[new_period_s], period_hours={new_period_s: _period_hours(new_period_s)},
    )
    if not availability or not availability[0].get("available"):
        raise RuntimeError("後台該日期／時段目前無可用班表，未建立訂單")

    result = qo.quick_create_order(
        env_name=customer_data["lookup"]["env_name"],
        payway=payway,
        region=region,
        lookup_result=customer_data["lookup"],
        address=address,
        clean_type_id=clean_type_id,
        date_s=new_date_s,
        period_s=new_period_s,
        hour=hour,
        person=person,
        allow_auto_lemon_shift=False,
    )
    return result


def build_calendar_service():
    service = orders.build_gcal_service()
    if service is None:
        raise RuntimeError("Google Calendar 同步目前未啟用")
    return service


def _calendar_id(region: str):
    calendar_id = GOOGLE_CALENDAR_MAP.get(region)
    if not calendar_id:
        raise ValueError(f"{region} 尚未設定 Google Calendar ID")
    return calendar_id


def _list_events(service, calendar_id, start_dt, end_dt):
    return service.events().list(
        calendarId=calendar_id,
        timeMin=start_dt.isoformat(),
        timeMax=end_dt.isoformat(),
        singleEvents=True,
        orderBy="startTime",
        maxResults=250,
    ).execute().get("items", [])


def find_calendar_event(service, calendar_id, order_no="", phone="", address="", date_s="", period_s=""):
    """Find exact event by order no first; otherwise address/phone + date/time."""
    if date_s:
        d = datetime.strptime(date_s, "%Y-%m-%d").date()
        day_start = datetime.combine(d, time.min, tzinfo=TAIPEI_TZ)
        day_end = day_start + timedelta(days=1)
    else:
        day_start = datetime.now(TAIPEI_TZ) - timedelta(days=370)
        day_end = datetime.now(TAIPEI_TZ) + timedelta(days=370)
    events = _list_events(service, calendar_id, day_start, day_end)

    target_order = _normalize(order_no)
    target_phone = _normalize(phone)
    target_addr = _normalize(address)
    target_start = target_end = None
    if date_s and period_s:
        target_start, target_end = _event_range(date_s, period_s)

    fallback = None
    for event in events:
        blob = _normalize(" ".join([
            event.get("summary", ""), event.get("description", ""), event.get("location", ""),
        ]))
        if target_order and target_order in blob:
            return event
        if target_phone and target_phone not in blob and target_addr and target_addr not in blob:
            continue
        if target_start and target_end:
            start_raw = event.get("start", {}).get("dateTime")
            end_raw = event.get("end", {}).get("dateTime")
            start_dt = orders.parse_event_time(start_raw)
            end_dt = orders.parse_event_time(end_raw)
            if start_dt and end_dt:
                if start_dt.astimezone(TAIPEI_TZ).replace(second=0, microsecond=0) == target_start.replace(second=0, microsecond=0) and end_dt.astimezone(TAIPEI_TZ).replace(second=0, microsecond=0) == target_end.replace(second=0, microsecond=0):
                    return event
        if fallback is None and ((target_phone and target_phone in blob) or (target_addr and target_addr in blob)):
            fallback = event
    return fallback


def find_reference_calendar_event(service, calendar_id, phone="", address="", anchor_date=None):
    anchor_date = anchor_date or date.today()
    start_dt = datetime.combine(anchor_date - timedelta(days=240), time.min, tzinfo=TAIPEI_TZ)
    end_dt = datetime.combine(anchor_date + timedelta(days=240), time.max, tzinfo=TAIPEI_TZ)
    events = _list_events(service, calendar_id, start_dt, end_dt)
    phone_n = _normalize(phone)
    addr_n = _normalize(address)
    matched = []
    for event in events:
        blob = _normalize(" ".join([event.get("summary", ""), event.get("description", ""), event.get("location", "")]))
        if (phone_n and phone_n in blob) or (addr_n and addr_n in blob):
            matched.append(event)
    matched.sort(key=lambda e: str(e.get("start", {}).get("dateTime") or e.get("start", {}).get("date") or ""), reverse=True)
    return matched[0] if matched else None


def _safe_event_copy(event: dict):
    allowed = ["summary", "description", "location", "attendees", "reminders", "visibility", "transparency"]
    body = {k: copy.deepcopy(event[k]) for k in allowed if k in event}
    return body


def _append_status(description: str, status_line: str):
    lines = [x for x in str(description or "").splitlines() if not x.startswith("VIP同步狀態：")]
    lines.append(f"VIP同步狀態：{status_line}")
    return "\n".join(lines).strip()


def create_or_copy_calendar_event(
    region: str, phone: str, address: str, new_date_s: str, new_period_s: str,
    color_id: str, order_no: str = "", name: str = "", reference_event=None,
):
    service = build_calendar_service()
    calendar_id = _calendar_id(region)
    if reference_event is None:
        reference_event = find_reference_calendar_event(service, calendar_id, phone=phone, address=address)

    if reference_event:
        body = _safe_event_copy(reference_event)
    else:
        body = {
            "summary": f"VIP {name or phone}",
            "description": "",
            "location": address,
        }

    start_dt, end_dt = _event_range(new_date_s, new_period_s)
    body["start"] = {"dateTime": start_dt.isoformat(), "timeZone": "Asia/Taipei"}
    body["end"] = {"dateTime": end_dt.isoformat(), "timeZone": "Asia/Taipei"}
    body["colorId"] = str(color_id)
    body["description"] = _append_status(
        body.get("description", ""),
        (f"已成單 {order_no}" if order_no else "VIP預排／尚未成單"),
    )
    if order_no and order_no not in _normalize(body.get("description", "")):
        body["description"] = (body.get("description", "") + f"\n訂單編號：{order_no}").strip()
    if phone and phone not in _normalize(body.get("description", "")):
        body["description"] = (body.get("description", "") + f"\n電話：{phone}").strip()
    if address and not body.get("location"):
        body["location"] = address

    return service.events().insert(calendarId=calendar_id, body=body).execute()


def move_calendar_event_after_backend_change(
    region: str, source_order: dict, phone: str, new_date_s: str, new_period_s: str,
):
    service = build_calendar_service()
    calendar_id = _calendar_id(region)
    event = find_calendar_event(
        service, calendar_id,
        order_no=source_order.get("order_no", ""), phone=phone,
        address=source_order.get("address", ""), date_s=source_order.get("date", ""),
        period_s=str(source_order.get("time") or "").replace(" ", ""),
    )
    if not event:
        raise RuntimeError("找不到原日期／時段的 Google 日曆事件，後台已異動但日曆尚未同步")
    start_dt, end_dt = _event_range(new_date_s, new_period_s)
    body = {
        "start": {"dateTime": start_dt.isoformat(), "timeZone": "Asia/Taipei"},
        "end": {"dateTime": end_dt.isoformat(), "timeZone": "Asia/Taipei"},
        "colorId": COLOR_YELLOW,
        "description": _append_status(event.get("description", ""), f"已異動／已成單 {source_order.get('order_no', '')}"),
    }
    return service.events().patch(calendarId=calendar_id, eventId=event["id"], body=body).execute()


def mark_calendar_cancelled(region: str, source_order: dict, phone: str):
    service = build_calendar_service()
    calendar_id = _calendar_id(region)
    event = find_calendar_event(
        service, calendar_id,
        order_no=source_order.get("order_no", ""), phone=phone,
        address=source_order.get("address", ""), date_s=source_order.get("date", ""),
        period_s=str(source_order.get("time") or "").replace(" ", ""),
    )
    if not event:
        raise RuntimeError("後台已取消，但找不到原 Google 日曆事件")
    body = {
        "colorId": COLOR_GREEN,
        "description": _append_status(event.get("description", ""), f"取消／暫停 {source_order.get('order_no', '')}"),
    }
    return service.events().patch(calendarId=calendar_id, eventId=event["id"], body=body).execute()


def execute_change_and_calendar(customer_data, source_order, new_date_s, new_period_s):
    """Atomic-ish workflow: backend first; calendar only after backend success."""
    backend = change_backend_order_date(customer_data, source_order, new_date_s, new_period_s)
    if not backend.get("ok"):
        return {"ok": False, "backend": backend, "calendar": None}
    region = _region_from_order(source_order)
    try:
        cal = move_calendar_event_after_backend_change(region, source_order, customer_data["phone"], new_date_s, new_period_s)
        return {"ok": True, "backend": backend, "calendar": cal}
    except Exception as exc:
        return {"ok": False, "backend": backend, "calendar": None, "calendar_error": str(exc), "backend_already_changed": True}


def execute_cancel_and_calendar(
    customer_data, source_order, cancel_status="不需退款", customer_memo="", charge_note="", refund_note="",
):
    """Backend cancel first; calendar turns green only after backend success."""
    result = cancel_orders(
        customer_data["lookup"]["env_name"],
        customer_data["lookup"].get("backend_email", ""),
        customer_data["lookup"].get("backend_password", ""),
        [{
            "purchase_id": re.sub(r"\D", "", source_order.get("order_no", "")),
            "order_no": source_order.get("order_no", ""),
            "phone": customer_data["phone"],
            "service_date": source_order.get("date", ""),
            "period": source_order.get("time", ""),
        }],
        cancel_status, customer_memo, charge_note, refund_note,
    )
    row = result[0] if result else {"ok": False, "message": "取消沒有回傳結果"}
    if not row.get("ok"):
        return {"ok": False, "backend": row, "calendar": None}
    region = _region_from_order(source_order)
    try:
        cal = mark_calendar_cancelled(region, source_order, customer_data["phone"])
        return {"ok": True, "backend": row, "calendar": cal}
    except Exception as exc:
        return {"ok": False, "backend": row, "calendar_error": str(exc), "backend_already_cancelled": True}


def execute_calendar_only(customer_data, source_order, new_date_s, new_period_s):
    if not can_calendar_only_prebook(new_date_s):
        raise ValueError("僅新增日曆只開放：每月 5 日後預排『隔月』服務")
    region = _region_from_order(source_order)
    return create_or_copy_calendar_event(
        region=region, phone=customer_data["phone"], address=source_order.get("address", ""),
        new_date_s=new_date_s, new_period_s=new_period_s, color_id=COLOR_PURPLE,
        order_no="", name=customer_data.get("name", ""),
    )


def execute_book_then_calendar(customer_data, source_order, new_date_s, new_period_s):
    order_result = create_backend_order_from_template(customer_data, source_order, new_date_s, new_period_s)
    region = order_result.get("region") or _region_from_order(source_order)
    try:
        event = create_or_copy_calendar_event(
            region=region, phone=customer_data["phone"], address=source_order.get("address", ""),
            new_date_s=new_date_s, new_period_s=new_period_s, color_id=COLOR_YELLOW,
            order_no=order_result.get("order_no", ""), name=customer_data.get("name", ""),
        )
        return {"ok": True, "order": order_result, "calendar": event}
    except Exception as exc:
        return {"ok": False, "order": order_result, "calendar_error": str(exc), "backend_order_already_created": True}


def _order_label(o):
    return f"{o.get('order_no')}｜{o.get('date')} {o.get('time')}｜{o.get('address')}｜{o.get('person')}人{o.get('hour')}小時｜{o.get('payway')}"


def render_vip_calendar_sync(backend_email: str, backend_password: str, env_name: str):
    """Streamlit renderer; ordersapp.py integration intentionally deferred."""
    st.markdown("### VIP 訂單／Google 日曆同步")
    st.caption("後台優先：異動與取消都先完成後台，成功後才同步 Google 日曆。紫色＝未安排、黃色＝已安排、綠色＝暫停；既有日曆事件由使用者自行選擇，不由系統自動決定。")

    phone = st.text_input("VIP 客戶手機號碼", key="vipcal_phone", placeholder="09xxxxxxxx")
    if st.button("🔎 查詢 VIP 訂單", key="vipcal_lookup", type="primary", use_container_width=True):
        if not backend_email or not backend_password:
            st.error("請先輸入後台帳號與密碼")
        else:
            try:
                data = load_vip_customer(env_name, backend_email, backend_password, phone)
                # cancel_order needs credentials later; keep only in Streamlit session, not calendar event.
                data["lookup"]["backend_email"] = backend_email
                data["lookup"]["backend_password"] = backend_password
                st.session_state.vipcal_customer = data
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

    labels = [_order_label(o) for o in orders_list]
    selected_label = st.selectbox("選擇原訂單／範本", labels, key="vipcal_source_order")
    source = orders_list[labels.index(selected_label)]
    st.info(f"客戶：{customer.get('name')}　電話：{customer.get('phone')}　原訂單：{source.get('order_no')}")

    action = st.radio(
        "功能",
        ["異動日期／時段", "取消／暫停", "僅新增日曆", "先預約再新增日曆"],
        horizontal=True,
        key="vipcal_action",
    )

    if action == "取消／暫停":
        cancel_status = st.radio("取消處理方式", ["不需退款", "待退款", "待收異動"], horizontal=True, key="vipcal_cancel_status")
        memo = st.text_area("客人備註", key="vipcal_cancel_memo")
        charge_note = st.text_area("加收備註", key="vipcal_charge_note")
        refund_note = st.text_area("待退備註", key="vipcal_refund_note")
        if st.button("🛑 後台取消並同步日曆為綠色", key="vipcal_cancel_exec", type="primary", use_container_width=True):
            with st.spinner("先取消後台訂單，再同步日曆…"):
                result = execute_cancel_and_calendar(customer, source, cancel_status, memo, charge_note, refund_note)
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
        period_index = STANDARD_PERIODS.index(default_period) if default_period in STANDARD_PERIODS else 0
        new_period = st.selectbox("新服務時段", STANDARD_PERIODS, index=period_index, key="vipcal_new_period")
    new_date_s = new_date.isoformat()

    if action == "異動日期／時段":
        if st.button("🔎 先確認後台可異動", key="vipcal_check_change", use_container_width=True):
            try:
                check = check_backend_change_slot(customer, source, new_date_s, new_period)
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
                        result = execute_change_and_calendar(customer, source, new_date_s, new_period)
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
        allowed = can_calendar_only_prebook(new_date_s)
        st.caption(f"規則：每月 5 日後可先預排隔月服務。目前 {'符合' if allowed else '不符合'} 僅新增日曆條件。")
        if st.button("🟣 僅新增／複製紫色日曆", key="vipcal_calendar_only", type="primary", disabled=not allowed, use_container_width=True):
            try:
                with st.spinner("新增 VIP 預排日曆…"):
                    event = execute_calendar_only(customer, source, new_date_s, new_period)
                st.success(f"✅ 已新增紫色 VIP 預排日曆：{event.get('summary', '')}")
            except Exception as exc:
                st.error(str(exc))
        return

    if action == "先預約再新增日曆":
        if st.button("🔎 先確認後台可預約", key="vipcal_check_book", use_container_width=True):
            try:
                check = check_backend_change_slot(customer, source, new_date_s, new_period)
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
                            result = execute_book_then_calendar(customer, source, new_date_s, new_period)
                        if result.get("ok"):
                            st.success(f"✅ 訂單 {result['order'].get('order_no')} 已成立，黃色日曆已新增")
                        else:
                            st.error(f"⚠️ 訂單 {result['order'].get('order_no')} 已成立，但日曆新增失敗：{result.get('calendar_error')}")
                    except Exception as exc:
                        st.error(str(exc))