"""已成單預約完成通知加速：後台區間清單、日曆整段查詢、表頭只處理一次、後台多出訂單偵測。"""
from types import SimpleNamespace
from unittest.mock import Mock, patch

import quick_order as q
from shared import notification_service
from shared.line_notice_sheet import (
    _CachedCalendarService, build_source_writeback, ensure_source_headers, filter_groups_by_calendar,
    sheet_order_numbers, write_results_to_source,
)

ADDRESS = "新北市新莊區福德三街30號10樓"


def _card(no, date="2026-12-17", period="14:00 - 17:00", status="已付款", phone="0920584222",
          address=ADDRESS, service="居家清潔"):
    return f"""<tr><td>{no}</td><td><div>代客預訂：Jenny</div><div>陳明芬</div><div>{phone}</div><div>a@b.tw</div>
<a href="https://chat.line.biz/x/{no}">LINE</a><div>{address}</div><div>2026-11-04 15:16:40</div><div>{service}</div></td>
<td><div>{date} (四)</div><div>{period}</div></td>
<td><div>總金額：0</div><div>付款方式：儲值金</div><div>付款狀態：{status}</div></td></tr>"""


def _page(*cards):
    return SimpleNamespace(status_code=200, text="<table>" + "".join(cards) + "</table>")


def _blocks(*cards):
    session = Mock()
    session.get.return_value = _page(*cards)
    return q.prefetch_purchase_blocks(session, "2026-12-01", "2026-12-31")


def test_prefetch_pages_until_short_page():
    session = Mock()
    first = [_card(f"LC{n:08d}") for n in range(20)]
    session.get.side_effect = [_page(*first), _page(_card("LC00000099"))]
    blocks = q.prefetch_purchase_blocks(session, "2026-12-01", "2026-12-31")
    assert len(blocks) == 21 and session.get.call_count == 2
    params = session.get.call_args_list[1].kwargs["params"]
    assert params["clean_date_s"] == "2026-12-01" and params["page"] == "2"
    assert blocks["LC00000099"]["line_url"] == "https://chat.line.biz/x/LC00000099"


def test_prefetch_stops_when_page_repeats():
    session = Mock()
    session.get.return_value = _page(*[_card(f"LC{n:08d}") for n in range(20)])
    q.prefetch_purchase_blocks(session, "2026-12-01", "2026-12-31")
    assert session.get.call_count == 2


def test_combined_message_uses_cache_without_backend_query():
    blocks = _blocks(_card("LC00219683"))
    session = Mock()
    with patch.object(q, "_fetch_purchase_block_for_order_no") as fetch:
        result, _text = q.build_combined_line_message_from_order_nos(
            "prod", "", "", ["LC00219683"], session=session, block_cache=blocks,
        )
    fetch.assert_not_called()
    assert result["orders_info"][0]["service_date"] == "2026-12-17"
    assert result["line_url"] == "https://chat.line.biz/x/LC00219683"


def test_combined_message_falls_back_for_orders_outside_list():
    blocks = _blocks(_card("LC00219683"))
    other = _blocks(_card("LC00000777", date="2027-01-07"))["LC00000777"]
    with patch.object(q, "_fetch_purchase_block_for_order_no", return_value=other) as fetch:
        result, _ = q.build_combined_line_message_from_order_nos(
            "prod", "", "", ["LC00219683", "LC00000777"], session=Mock(), block_cache=blocks,
        )
    assert [call.args[1] for call in fetch.call_args_list] == ["LC00000777"]
    assert len(result["orders_info"]) == 2


def test_extra_orders_same_customer_address_only():
    blocks = _blocks(
        _card("LC00000001"),                                   # 工作表已有
        _card("LC00000002", date="2026-12-24"),                # 後台多出 → 增加
        _card("LC00000003", status="已退款"),                    # 作廢不算
        _card("LC00000004", phone="0911111111"),               # 別的客人
        _card("LC00000005", address="新北市板橋區莊敬路13號17樓"),  # 別的地址
        _card("LC00000006", service="大掃除"),                    # 別的服務類型
        _card("LC00000007", date="2026-12-10"),                # 已在工作表其他列
    )
    group = {"name": "陳明芬", "phone": "0920584222", "address": ADDRESS, "service": "居家清潔", "order_nos": ["LC00000001"]}
    extras = q.extra_orders_for_group(group, blocks, known_order_nos={"LC00000001", "LC00000007"})
    assert extras == [{"order_no": "LC00000002", "service_date": "2026-12-24", "period_s": "14:00 - 17:00"}]


def test_extra_orders_become_inserted_rows():
    group = {"name": "陳明芬", "address": ADDRESS, "service": "居家清潔", "email": "", "line_url": "",
             "entries": [{"row": 5, "order_no": "LC1", "date": "2026-12-17", "start": "14:00", "end": "17:00"}]}
    backend = {"orders_info": [{"service_date": "2026-12-17", "period_s": "14:00-17:00"}],
               "extra_orders": [{"order_no": "LC2", "service_date": "2026-12-24", "period_s": "14:00-17:00"}]}
    results = [{"group": group, "result": backend, "text": "通知", "error": None}]
    updates, insertions, reductions = build_source_writeback([group], results, [])
    assert [item["order"]["order_no"] for item in insertions] == ["LC2"]
    assert insertions[0]["after_row"] == 5 and not reductions
    assert updates[5]["異動檢查"].startswith("增加：後台另有 1 筆未在工作表（LC2 2026/12/24")


def test_no_extras_keeps_consistent():
    group = {"name": "陳明芬", "address": ADDRESS, "service": "居家清潔", "email": "", "line_url": "",
             "entries": [{"row": 5, "order_no": "LC1", "date": "2026-12-17", "start": "14:00", "end": "17:00"}]}
    backend = {"orders_info": [{"service_date": "2026-12-17", "period_s": "14:00-17:00"}], "extra_orders": []}
    updates, insertions, _ = build_source_writeback([group], [{"group": group, "result": backend, "text": "x", "error": None}], [])
    assert insertions == [] and updates[5]["異動檢查"] == "一致"


def _event(start, end, summary="清潔"):
    return {"start": {"dateTime": start}, "end": {"dateTime": end}, "summary": summary}


def test_calendar_prefetch_serves_day_queries_with_one_call():
    events = [
        _event("2026-12-01T09:00:00+08:00", "2026-12-01T12:00:00+08:00", "A"),
        _event("2026-12-02T09:00:00+08:00", "2026-12-02T12:00:00+08:00", "B"),
    ]
    raw = Mock()
    raw.events.return_value.list.return_value.execute.return_value = {"items": events}
    service = _CachedCalendarService(raw)
    service.prefetch("cal", "2026-12-01", "2026-12-02")
    day = service.events().list(calendarId="cal", timeMin="2026-12-02T00:00:00+08:00",
                                timeMax="2026-12-03T00:00:00+08:00", singleEvents=True, orderBy="startTime").execute()
    assert [event["summary"] for event in day["items"]] == ["B"]
    assert raw.events.return_value.list.call_count == 1


def test_calendar_prefetch_follows_page_tokens():
    raw = Mock()
    raw.events.return_value.list.return_value.execute.side_effect = [
        {"items": [_event("2026-12-01T09:00:00+08:00", "2026-12-01T12:00:00+08:00")], "nextPageToken": "t"},
        {"items": [_event("2026-12-02T09:00:00+08:00", "2026-12-02T12:00:00+08:00")]},
    ]
    assert _CachedCalendarService(raw).prefetch("cal", "2026-12-01", "2026-12-02") == 2


def test_calendar_query_outside_prefetch_range_hits_api():
    raw = Mock()
    raw.events.return_value.list.return_value.execute.return_value = {"items": []}
    service = _CachedCalendarService(raw)
    service.prefetch("cal", "2026-12-01", "2026-12-02")
    service.events().list(calendarId="cal", timeMin="2026-12-05T00:00:00+08:00", timeMax="2026-12-06T00:00:00+08:00").execute()
    assert raw.events.return_value.list.call_count == 2


def test_filter_groups_by_calendar_queries_each_calendar_once():
    raw = Mock()
    raw.events.return_value.list.return_value.execute.return_value = {"items": [
        _event("2026-12-01T09:00:00+08:00", "2026-12-01T12:00:00+08:00", "台北市A"),
        _event("2026-12-08T13:00:00+08:00", "2026-12-08T16:00:00+08:00", "台北市B"),
    ]}
    import orders
    groups = [{"order_nos": ["LC1", "LC2"], "entries": [
        {"order_no": "LC1", "address": "台北市A", "date": "2026-12-01", "start": "09:00", "end": "12:00", "proxy": False},
        {"order_no": "LC2", "address": "台北市B", "date": "2026-12-08", "start": "13:00", "end": "16:00", "proxy": False},
    ]}]
    fake_orders = SimpleNamespace(
        get_region_by_address=lambda *_a: "台北", get_date_str=orders.get_date_str,
        find_matching_calendar_event=orders.find_matching_calendar_event,
    )
    kept, skipped = filter_groups_by_calendar(groups, fake_orders, raw, {"台北": "cal"}, {})
    assert kept[0]["order_nos"] == ["LC1", "LC2"] and not skipped
    assert raw.events.return_value.list.call_count == 1


def test_headers_written_only_when_missing():
    ws = Mock()
    ws.row_values.return_value = ["姓名", "mail", "LINE連結", "通知內容", "異動檢查", "通知處理狀態"]
    assert ensure_source_headers(ws)[-1] == "通知處理狀態"
    ws.update.assert_not_called()


def test_writer_with_headers_skips_header_round_trip():
    ws = Mock()
    group = {"name": "王", "address": "台北市A", "service": "居家清潔", "email": "", "line_url": "",
             "entries": [{"row": 2, "order_no": "LC1", "date": "2026-12-01", "start": "09:00", "end": "12:00"}]}
    write_results_to_source(ws, [group], [], [], headers=["姓名", "地址", "狀態", "mail", "LINE連結", "通知內容", "異動檢查", "通知處理狀態"])
    ws.row_values.assert_not_called()
    ws.update.assert_not_called()
    ws.batch_update.assert_called_once()


def test_sheet_order_numbers():
    import pandas as pd
    df = pd.DataFrame({"訂單編號": ["LC1", "", None, " LC2 "]})
    assert sheet_order_numbers(df) == {"LC1", "LC2"}


def test_prefetch_notice_blocks_falls_back_to_empty_on_error():
    groups = [{"entries": [{"date": "2026-12-17"}, {"date": "2026/12/3"}]}]
    with patch.object(q, "prepare_notification_session", side_effect=RuntimeError("登入失敗")):
        assert notification_service.prefetch_notice_blocks("prod", "", "", groups, logger=lambda _m: None) == {}
    with patch.object(q, "prepare_notification_session", return_value=Mock()), \
            patch.object(q, "prefetch_purchase_blocks", return_value={"LC1": {}}) as prefetch:
        assert notification_service.prefetch_notice_blocks("prod", "", "", groups, logger=lambda _m: None) == {"LC1": {}}
    assert prefetch.call_args.args[1:] == ("2026-12-03", "2026-12-17")
