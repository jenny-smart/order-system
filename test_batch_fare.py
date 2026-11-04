"""批次成單車馬費：中斷復原改日曆不覆蓋車馬費、LINE 通知帶出車馬費、成單後核對前次車馬費。"""
from unittest.mock import Mock, patch

import orders
from shared import gsheet, hybrid_batch_runner
from shared.hybrid_batch_runner import _batch_line_messages, _fare_amount, _recovered_result


ADDRESS = "新北市新莊區福德三街30號10樓"


def _row(date, fare=""):
    return {
        "姓名": "王小明", "地址": ADDRESS, "購買項目": "居家清潔",
        "日期": date, "開始時間": "09:00", "結束時間": "12:00", "車馬費": fare,
    }


def test_line_notice_shows_order_fare():
    entries = [(_row("2026-12-01"), {"訂單編號": "LC00000001", "結果": "成功", "車馬費": "200"})]
    message = _batch_line_messages(entries, logger=lambda _m: None)[0]["通知內容"]
    assert "車馬費：200" in message


def test_line_notice_sums_fare_for_multiple_dates():
    entries = [
        (_row("2026-12-01"), {"訂單編號": "LC00000001", "結果": "成功", "車馬費": "200"}),
        (_row("2026-12-08"), {"訂單編號": "LC00000002", "結果": "成功", "車馬費": "200"}),
    ]
    message = _batch_line_messages(entries, logger=lambda _m: None)[0]["通知內容"]
    assert "車馬費：400" in message


def test_line_notice_without_fare_has_no_fare_line():
    entries = [(_row("2026-12-01"), {"訂單編號": "LC00000001", "結果": "成功", "車馬費": "0"})]
    message = _batch_line_messages(entries, logger=lambda _m: None)[0]["通知內容"]
    assert "車馬費" not in message


def test_fare_amount_takes_first_nonzero():
    assert _fare_amount("0", "200") == 200
    assert _fare_amount("", None, "nan") == 0
    assert _fare_amount("1,000") == 1000


def test_recovered_row_keeps_backfilled_fare_and_staff():
    row = {"訂單編號": "LC00000009", "服務人員": "王專員 X 李專員", "服務狀態": "未處理", "車馬費": "200"}
    result = _recovered_result(row)
    assert result["車馬費"] == "200"
    assert result["服務人員"] == "王專員 X 李專員"


def test_recovered_calendar_sync_writes_only_calendar_columns():
    row = {"訂單編號": "LC00000009", "服務人員": "王專員", "服務狀態": "未處理", "車馬費": "200"}
    calendar = {"日曆改色結果": "成功", "日曆改色原因": "", "日曆原色": "紫", "日曆新色": "黃", "狀態": "已安排"}
    with patch.object(hybrid_batch_runner, "_lazy_calendar_sync",
                      side_effect=lambda _row, result, *_a: {**result, **calendar}), \
            patch.object(hybrid_batch_runner._orders, "update_sheet_rows") as update:
        hybrid_batch_runner._recovered_calendar_sync(Mock(), 12, row, "台北", {}, print)
    written = update.call_args.args[1][12]
    assert written == calendar
    assert "車馬費" not in written and "結果" not in written


def test_update_sheet_rows_calendar_only_does_not_touch_fare():
    ws = Mock()
    ws.row_values.return_value = ["日曆改色結果", "狀態", "服務人員", "服務狀態", "車馬費"]
    with patch.object(gsheet, "ensure_columns_in_sheet", return_value=ws.row_values.return_value):
        gsheet.update_sheet_rows(ws, {5: {"日曆改色結果": "成功", "狀態": "已安排"}})
    ranges = [item["range"] for item in ws.batch_update.call_args.args[0]]
    assert ranges == ["A5", "B5"]


def test_update_sheet_rows_full_result_still_fills_fare():
    ws = Mock()
    headers = ["訂單編號", "服務人員", "服務狀態", "車馬費"]
    with patch.object(gsheet, "ensure_columns_in_sheet", return_value=headers):
        gsheet.update_sheet_rows(ws, {5: orders.build_row_result(order_no="LC1", result="成功", fare="")})
    values = {item["range"]: item["values"][0][0] for item in ws.batch_update.call_args.args[0]}
    assert values["D5"] == "0"


def test_fare_warning_when_previous_order_had_fare():
    warning = orders.fare_mismatch_warning("0", {"fare": "200"})
    assert "車馬費待確認" in warning and "200" in warning


def test_no_fare_warning_when_fare_present_or_never_charged():
    assert orders.fare_mismatch_warning("200", {"fare": "200"}) == ""
    assert orders.fare_mismatch_warning("0", {"fare": "0"}) == ""
    assert orders.fare_mismatch_warning("0", None) == ""
