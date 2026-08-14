# -*- coding: utf-8 -*-
"""Third-stage VIP calendar patch.

Adds an improved Google Calendar editor for the VIP test page:
- date can be changed;
- period can be changed;
- confirmation text can be changed;
- color terminology follows operations:
  purple = 未安排, yellow = 已安排, green = 暫停.
"""


def _parse_event_dt(vcs, raw):
    if not raw:
        return None
    try:
        dt = vcs.orders.parse_event_time(raw)
        return dt.astimezone(vcs.TAIPEI_TZ) if dt else None
    except Exception:
        return None


def _event_label(vcs, vcp, row):
    event = row.get("event") or {}
    icon, color_name = vcp._color_meta(vcs, row.get("color_id"))
    return (
        f"{row.get('date', '')} {row.get('period', '')}｜{icon} {color_name}｜"
        f"{vcp._confirmation_status(event)}｜{row.get('summary', '')}"
    )


def _update_calendar_schedule(vcs, vcp, row, new_date, new_period, confirmation, color_choice):
    event = row.get("event") or {}
    calendar_id = row.get("calendar_id")
    event_id = event.get("id") or row.get("event_id")
    if not calendar_id or not event_id:
        raise ValueError("此日曆事件缺少 calendarId 或 eventId，無法修改")

    start_dt, end_dt = vcs._event_range(new_date.isoformat(), new_period)
    body = {
        "start": {"dateTime": start_dt.isoformat(), "timeZone": "Asia/Taipei"},
        "end": {"dateTime": end_dt.isoformat(), "timeZone": "Asia/Taipei"},
    }

    if confirmation != "保持不變":
        body["summary"] = vcp._set_confirmation_text(event.get("summary", ""), confirmation)
        body["description"] = vcp._set_confirmation_text(event.get("description", ""), confirmation)

    color_map = {
        "紫色／未安排": str(vcs.COLOR_PURPLE),
        "黃色／已安排": str(vcs.COLOR_YELLOW),
        "綠色／暫停": str(vcs.COLOR_GREEN),
    }
    if color_choice != "保持不變":
        body["colorId"] = color_map[color_choice]

    service = vcs.build_calendar_service()
    return service.events().patch(
        calendarId=calendar_id,
        eventId=event_id,
        body=body,
    ).execute()


def _render_complete_calendar_editor(vcs, vcp, backend_email, backend_password, env_name):
    st = vcs.st
    customer = st.session_state.get("vipcal_customer")
    if not customer or st.session_state.get("vipcal_action") != "修改日曆資訊":
        return

    rows = customer.get("calendar_events") or []
    if not rows:
        return

    st.divider()
    st.markdown("## 修改日曆日期／時段／狀態")
    st.caption("紫色＝未安排｜黃色＝已安排｜綠色＝暫停。可同時修改日期、時段、確認文字與顏色。")

    labels = [_event_label(vcs, vcp, row) for row in rows]
    selected_label = st.selectbox("選擇要修改的日曆事件", labels, key="vipcal_full_edit_event")
    row = rows[labels.index(selected_label)]
    event = row.get("event") or {}

    start = _parse_event_dt(vcs, (event.get("start") or {}).get("dateTime"))
    end = _parse_event_dt(vcs, (event.get("end") or {}).get("dateTime"))
    if not start or not end:
        st.error("此事件不是標準日期＋時間格式，目前無法用此編輯器修改")
        return

    current_period = f"{start.strftime('%H:%M')}-{end.strftime('%H:%M')}"
    periods = list(vcs.STANDARD_PERIODS)
    if current_period not in periods:
        periods.insert(0, current_period)

    c1, c2 = st.columns(2)
    with c1:
        new_date = st.date_input("日曆日期", value=start.date(), key=f"vipcal_full_edit_date_{event.get('id', '')}")
    with c2:
        new_period = st.selectbox("日曆時段", periods, index=periods.index(current_period), key=f"vipcal_full_edit_period_{event.get('id', '')}")

    c3, c4 = st.columns(2)
    with c3:
        confirmation = st.selectbox(
            "確認狀態文字",
            ["保持不變", "每月確認", "已確認"],
            index=0,
            key=f"vipcal_full_edit_confirm_{event.get('id', '')}",
            help=f"目前：{vcp._confirmation_status(event)}",
        )
    with c4:
        color_choice = st.selectbox(
            "日曆顏色／安排狀態",
            ["保持不變", "紫色／未安排", "黃色／已安排", "綠色／暫停"],
            key=f"vipcal_full_edit_color_{event.get('id', '')}",
        )

    icon, color_name = vcp._color_meta(vcs, row.get("color_id"))
    st.info(
        f"目前：{row.get('date', '')} {row.get('period', '')}｜{icon} {color_name}｜"
        f"{vcp._confirmation_status(event)}｜Event ID：{event.get('id', '')}"
    )

    if st.button("✅ 套用日期／時段／狀態到 Google 日曆", key="vipcal_full_edit_exec", type="primary", use_container_width=True):
        try:
            updated = _update_calendar_schedule(vcs, vcp, row, new_date, new_period, confirmation, color_choice)
            st.success(f"✅ Google 日曆已更新：{updated.get('summary', '')}")
            refreshed = vcs.load_vip_customer(env_name, backend_email, backend_password, customer.get("phone", ""))
            refreshed["lookup"]["backend_email"] = backend_email
            refreshed["lookup"]["backend_password"] = backend_password
            st.session_state.vipcal_customer = refreshed
            st.rerun()
        except Exception as exc:
            st.error(f"日曆修改失敗：{exc}")


def apply_patch(vcs, vcp):
    def color_meta(vcs_arg, color_id):
        color_id = str(color_id or "")
        mapping = {
            str(vcs_arg.COLOR_PURPLE): ("🟣", "紫色／未安排"),
            str(vcs_arg.COLOR_YELLOW): ("🟡", "黃色／已安排"),
            str(vcs_arg.COLOR_GREEN): ("🟢", "綠色／暫停"),
            "": ("⚪", "預設色／未指定"),
        }
        return mapping.get(color_id, ("🔵", f"其他顏色／colorId={color_id}"))

    vcp._color_meta = color_meta
    original_renderer = vcs.render_vip_calendar_sync

    def wrapped_renderer(backend_email, backend_password, env_name):
        result = original_renderer(backend_email, backend_password, env_name)
        _render_complete_calendar_editor(vcs, vcp, backend_email, backend_password, env_name)
        return result

    vcs.render_vip_calendar_sync = wrapped_renderer
    return vcs
