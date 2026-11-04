import pandas as pd
from types import SimpleNamespace
from unittest.mock import Mock

from shared.line_notice_sheet import (
    build_source_writeback, filter_completed_address_groups, filter_groups_by_calendar, groups_from_dataframe,
    parse_row_spec, results_tsv, write_results_to_source,
)


def test_groups_existing_orders_by_customer_address_and_service():
    df = pd.DataFrame([
        {"__sheet_row__": 2, "姓名": "陳宜慧", "電話": "0912345678", "mail": "a@example.com", "LINE連結": "https://line.example/a", "地址": "新北市永和區A號", "購買項目": "居家清潔", "訂單編號": "LC1", "結果": "成功"},
        {"__sheet_row__": 3, "姓名": "陳宜慧", "地址": "新北市永和區A號", "購買項目": "居家清潔", "訂單編號": "LC2", "結果": "成功"},
        {"__sheet_row__": 4, "姓名": "陳宜慧", "地址": "台北市辦公路B號", "購買項目": "辦公室清潔", "訂單編號": "LC3", "結果": "成功"},
        {"__sheet_row__": 5, "姓名": "失敗客", "地址": "地址", "購買項目": "居家清潔", "訂單編號": "LC4", "結果": "失敗"},
    ])
    groups = groups_from_dataframe(df, "2-5")
    assert [group["order_nos"] for group in groups] == [["LC1", "LC2"], ["LC3"]]
    assert groups[0]["entries"][0]["phone"] == "0912345678"
    assert groups[0]["entries"][0]["email"] == "a@example.com"
    assert groups[0]["entries"][0]["line_url"] == "https://line.example/a"


def test_tsv_keeps_multiline_notice_in_one_cell():
    output = results_tsv([{
        "order_no": "LC1、LC2", "group": {"name": "陳宜慧", "address": "地址"},
        "text": "第一行\n第二行", "error": None,
    }])
    assert output.startswith("姓名\t地址\t訂單編號\tLINE預約完成通知\t日曆檢查\n")
    assert '"第一行\n第二行"' in output


def test_row_spec_accepts_commas_and_ranges():
    assert parse_row_spec("2,4-5") == {2, 4, 5}


def test_calendar_filter_keeps_only_orders_with_matching_event():
    groups = [{"order_nos": ["LC1", "LC2"], "entries": [
        {"order_no": "LC1", "address": "台北市A", "date": "2026-12-01", "start": "09:00", "end": "12:00", "proxy": False},
        {"order_no": "LC2", "address": "台北市A", "date": "2026-12-08", "start": "09:00", "end": "12:00", "proxy": False},
    ]}]
    fake_orders = SimpleNamespace(
        get_region_by_address=lambda _address, _accounts: "台北",
        find_matching_calendar_event=lambda _service, _calendar, _address, date, _start, _end: {"id": "event"} if date == "2026-12-01" else None,
    )
    updates = []
    kept, skipped = filter_groups_by_calendar(
        groups, fake_orders, Mock(), {"台北": "calendar"}, {},
        progress_callback=lambda checked, total, matched, skipped_count, entry: updates.append(
            (checked, total, matched, skipped_count, entry["order_no"])
        ),
    )
    assert kept[0]["order_nos"] == ["LC1"]
    assert [item["order_no"] for item in skipped] == ["LC2"]
    assert updates == [(1, 2, 1, 0, "LC1"), (2, 2, 1, 1, "LC2")]


def test_calendar_day_query_is_reused():
    calls = []
    class Request:
        def execute(self): calls.append("execute"); return {"items": [{"id": "event"}]}
    class Events:
        def list(self, **_kwargs): return Request()
    service = SimpleNamespace(events=lambda: Events())
    groups = [{"order_nos": ["LC1", "LC2"], "entries": [
        {"order_no": "LC1", "address": "台北市A", "date": "2026-12-01", "start": "09:00", "end": "12:00", "proxy": False},
        {"order_no": "LC2", "address": "台北市B", "date": "2026-12-01", "start": "13:00", "end": "16:00", "proxy": False},
    ]}]
    fake_orders = SimpleNamespace(
        get_region_by_address=lambda *_args: "台北",
        find_matching_calendar_event=lambda svc, cal, _addr, date, _start, _end: svc.events().list(calendarId=cal, timeMin=date, timeMax=date).execute()["items"][0],
    )
    kept, _ = filter_groups_by_calendar(groups, fake_orders, service, {"台北": "calendar"}, {})
    assert kept[0]["order_nos"] == ["LC1", "LC2"]
    assert calls == ["execute"]


def test_notice_is_written_to_first_source_row_and_reduction_is_flagged():
    group = {"name": "王小明", "address": "台北市A", "service": "居家清潔", "email": "", "line_url": "", "entries": [
        {"row": 2, "order_no": "LC1", "date": "2026-12-01", "start": "09:00", "end": "12:00"},
        {"row": 3, "order_no": "LC2", "date": "2026-12-08", "start": "09:00", "end": "12:00"},
    ]}
    result_group = {**group, "order_nos": ["LC1"], "entries": [group["entries"][0]]}
    results = [{"group": result_group, "text": "完整通知", "error": None, "result": {
        "email": "a@example.com", "line_url": "https://line.example/a",
        "orders_info": [{"order_no": "LC1", "service_date": "2026-12-01", "period_s": "09:00 - 12:00"}],
    }}]
    updates, insertions, reductions = build_source_writeback([group], results, [])
    assert updates[2]["通知內容"] == "完整通知"
    assert updates[2]["mail"] == "a@example.com"
    assert updates[3]["通知內容"] == ""
    assert updates[2]["異動檢查"].startswith("減少：")
    assert updates[2]["狀態"] == "安排減少"
    assert insertions == []
    assert reductions == [2]


def test_writer_adds_columns_and_batches_source_updates():
    group = {"name": "王小明", "address": "台北市A", "service": "居家清潔", "entries": [
        {"row": 2, "order_no": "LC1", "date": "2026-12-01", "start": "09:00", "end": "12:00"}
    ]}
    results = [{"group": group, "text": "完整通知", "error": None, "result": {
        "orders_info": [{"order_no": "LC1", "service_date": "2026-12-01", "period_s": "09:00-12:00"}]
    }}]
    class Worksheet:
        id = 99
        spreadsheet = SimpleNamespace(batch_update=Mock())
        def row_values(self, _row): return ["姓名", "地址", "日期", "開始時間", "結束時間", "狀態"]
        def update(self, **kwargs): self.header_update = kwargs
        def batch_update(self, *args, **kwargs): self.cells = (args, kwargs)
        def insert_rows(self, *args, **kwargs): raise AssertionError("不應新增列")
    ws = Worksheet()
    written, inserted, reduced = write_results_to_source(ws, [group], results, [])
    assert (written, inserted, reduced) == (1, 0, 0)
    assert ws.header_update["values"][0][-5:] == ["mail", "LINE連結", "通知內容", "異動檢查", "通知處理狀態"]
    assert any(item["range"] == "I2" and item["values"] == [["完整通知"]] for item in ws.cells[0][0])


def test_same_customer_address_only_first_row_keeps_notice():
    home = {"name": "王小明", "address": "台北市A", "service": "居家清潔", "entries": [{"row": 2, "order_no": "LC1", "date": "2026-12-01", "start": "09:00", "end": "12:00"}]}
    office = {"name": "王小明", "address": "台北市A", "service": "辦公室清潔", "entries": [{"row": 5, "order_no": "LC2", "date": "2026-12-08", "start": "09:00", "end": "12:00"}]}
    results = [
        {"group": home, "text": "第一份通知", "error": None, "result": {"orders_info": [{"service_date": "2026-12-01", "period_s": "09:00-12:00"}]}},
        {"group": office, "text": "第二份通知", "error": None, "result": {"orders_info": [{"service_date": "2026-12-08", "period_s": "09:00-12:00"}]}},
    ]
    updates, _, _ = build_source_writeback([home, office], results, [])
    assert updates[2]["通知內容"] == "第一份通知"
    assert updates[5]["通知內容"] == ""


def test_resume_skips_completed_customer_address():
    df = pd.DataFrame([
        {"姓名": "完成客", "地址": "台北市A", "通知處理狀態": "完成"},
        {"姓名": "待處理客", "地址": "台北市B", "通知處理狀態": "失敗（下次將自動續跑）"},
    ])
    groups = [{"name": "完成客", "address": "台北市A"}, {"name": "待處理客", "address": "台北市B"}]
    pending, completed = filter_completed_address_groups(groups, df)
    assert completed == 1
    assert [group["name"] for group in pending] == ["待處理客"]
