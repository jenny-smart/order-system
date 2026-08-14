# -*- coding: utf-8 -*-
"""Second-stage VIP calendar patch.

- Fetch every Google Calendar page inside the selected month/date range.
- Present query results as two synchronized calendar-style columns:
  left = backend paid orders, right = Google Calendar.
"""


def _paginated_list_events(vcs, service, calendar_id, start_dt, end_dt):
    rows = []
    page_token = None
    page_count = 0
    while True:
        kwargs = {
            "calendarId": calendar_id,
            "timeMin": start_dt.isoformat(),
            "timeMax": end_dt.isoformat(),
            "singleEvents": True,
            "orderBy": "startTime",
            "maxResults": 250,
        }
        if page_token:
            kwargs["pageToken"] = page_token
        result = service.events().list(**kwargs).execute()
        rows.extend(result.get("items", []) or [])
        page_count += 1
        page_token = result.get("nextPageToken")
        if not page_token or page_count >= 20:
            break
    return rows


def _status_and_icon(vcs, vcp, row):
    event = row.get("event") or {}
    icon, color_name = vcp._color_meta(vcs, row.get("color_id"))
    status = vcp._confirmation_status(event)
    return icon, color_name, status


def _date_label(date_s):
    from datetime import datetime
    weekdays = "一二三四五六日"
    try:
        d = datetime.strptime(str(date_s), "%Y-%m-%d").date()
        return f"{d.month}/{d.day}（{weekdays[d.weekday()]}）"
    except Exception:
        return str(date_s or "")


def _render_backend_column(st, customer, source):
    st.markdown("### 🧾 後台已付款訂單")
    rows = sorted(
        customer.get("orders") or [],
        key=lambda x: (str(x.get("date") or ""), str(x.get("time") or "")),
    )
    if not rows:
        st.info("此範圍沒有後台已付款訂單")
        return

    for order in rows:
        marker = "⭐ " if order is source else ""
        date_s = str(order.get("date") or "")
        period = str(order.get("time") or "").replace(" ", "")
        with st.expander(
            f"{marker}📅 {_date_label(date_s)}｜{period or '未標時段'}｜{order.get('order_no', '')}",
            expanded=True,
        ):
            st.write(f"**訂單編號：** {order.get('order_no', '')}")
            st.write(f"**日期：** {date_s}")
            st.write(f"**時段：** {period}")
            st.write(f"**地址：** {order.get('address', '')}")
            st.write(f"**付款：** {order.get('payway', '')}")


def _render_calendar_column(vcs, vcp, st, customer, matched):
    st.markdown("### 📅 Google 日曆")
    if customer.get("calendar_lookup_error"):
        st.warning(f"Google 日曆查詢失敗：{customer.get('calendar_lookup_error')}")

    rows = sorted(
        customer.get("calendar_events") or [],
        key=lambda x: (str(x.get("date") or ""), str(x.get("period") or "")),
    )
    if not rows:
        if not customer.get("calendar_lookup_error"):
            st.info("此範圍沒有符合手機號碼的 Google 日曆事件")
        return

    for row in rows:
        event = row.get("event") or {}
        icon, color_name, status = _status_and_icon(vcs, vcp, row)
        marker = "⭐ " if row is matched else ""
        date_s = str(row.get("date") or "")
        period = str(row.get("period") or "").replace(" ", "")
        with st.expander(
            f"{marker}{icon} {_date_label(date_s)}｜{period or '未標時段'}｜{status}",
            expanded=True,
        ):
            st.write(f"**日期：** {date_s}")
            st.write(f"**時段：** {period}")
            st.write(f"**狀態：** {status}")
            st.write(f"**顏色：** {icon} {color_name}")
            st.write(f"**標題：** {row.get('summary', '')}")
            st.write(f"**Event ID：** `{event.get('id', '')}`")


def _side_by_side_renderer(vcs, vcp, customer, source):
    st = vcs.st
    st.divider()
    st.markdown("## 查詢結果")
    st.caption(
        f"{customer.get('query_date_s', '')} ～ {customer.get('query_date_e', '')}｜"
        "左邊看後台，右邊看 Google 日曆，方便直接對照日期與時段。"
    )

    matched = vcp._find_matching_calendar_row(vcs, customer, source)
    left, right = st.columns(2, gap="large")
    with left:
        _render_backend_column(st, customer, source)
    with right:
        _render_calendar_column(vcs, vcp, st, customer, matched)

    st.markdown("### 目前選取訂單比對")
    st.write(
        f"**後台：{source.get('order_no', '')}｜{source.get('date', '')} "
        f"{str(source.get('time') or '').replace(' ', '')}**"
    )
    if matched:
        event = matched.get("event") or {}
        icon, color_name, status = _status_and_icon(vcs, vcp, matched)
        st.write(
            f"**日曆：{matched.get('date', '')} {matched.get('period', '')}｜"
            f"{icon} {status}｜{color_name}**"
        )
        diffs = []
        if str(source.get("date") or "") != str(matched.get("date") or ""):
            diffs.append(f"日期：後台 {source.get('date', '')} / 日曆 {matched.get('date', '')}")
        backend_period = str(source.get("time") or "").replace(" ", "")
        if backend_period != str(matched.get("period") or "").replace(" ", ""):
            diffs.append(f"時段：後台 {backend_period} / 日曆 {matched.get('period', '')}")
        if diffs:
            st.warning("⚠️ 發現差異：" + "；".join(diffs))
        else:
            st.success("✅ 目前選取訂單與配對日曆日期、時段一致")
        if event.get("summary"):
            st.caption(event.get("summary"))
    else:
        st.warning("目前選取的後台訂單找不到可直接配對的 Google 日曆事件")

    return matched


def apply_patch(vcs, vcp):
    """Apply after vip_calendar_patch.apply_patch(vcs)."""
    vcs._list_events = lambda service, calendar_id, start_dt, end_dt: _paginated_list_events(
        vcs, service, calendar_id, start_dt, end_dt
    )
    vcp._render_query_results = lambda vcs_arg, customer, source: _side_by_side_renderer(
        vcs_arg, vcp, customer, source
    )
    return vcs
