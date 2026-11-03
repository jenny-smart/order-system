from unittest.mock import Mock, patch

import orders
from shared import proxy_reserve
from shared.hybrid_batch_runner import _batch_line_messages, line_messages_tsv


ADDRESS = "新北市永和區環河西路一段19號17樓"


def test_blank_purchase_item_is_inferred_by_name_and_address():
    html = f"""
    <table><tbody><tr><td>
      LC00999999<br>陳宜慧<br>0912345678<br>{ADDRESS}<br>建立時間<br>居家清潔
    </td></tr></tbody></table>
    """
    session = Mock()
    session.get.return_value = Mock(status_code=200, text=html)
    assert orders.infer_purchase_item_by_name_address(session, "陳宜慧", ADDRESS) == "居家清潔"


def test_blank_purchase_item_does_not_take_same_name_other_address():
    html = """
    <table><tbody><tr><td>
      LC00999998<br>陳宜慧<br>台北市信義區辦公路1號<br>建立時間<br>辦公室清潔
    </td></tr></tbody></table>
    """
    session = Mock()
    session.get.return_value = Mock(status_code=200, text=html)
    assert orders.infer_purchase_item_by_name_address(session, "陳宜慧", ADDRESS) == ""


def test_saved_address_memo_is_kept_for_batch_service_notice():
    payload = {"member": {"memberAddressList": [{
        "id": 7, "address": ADDRESS, "memo": "請先電話聯絡", "purchase": {},
    }]}}
    assert orders.pick_best_address_info(payload, ADDRESS)["notice"] == "請先電話聯絡"


def test_proxy_booking_uses_reserve_calendar_color():
    row = {
        "地址": ADDRESS, "日期": "2026-12-01", "開始時間": "09:00", "結束時間": "12:00",
        proxy_reserve.FLAG_KEY: True, proxy_reserve.NAME_KEY: "陳宜慧",
    }
    service = Mock()
    service.events.return_value.list.return_value.execute.return_value = {
        "items": [{"id": "event-1", "summary": "陳宜慧 居家清潔", "colorId": orders.COLOR_PURPLE}],
    }
    result = orders.stage_calendar_color(row, service, "台北")
    assert result["日曆新色"] == "孔雀藍"
    assert service.events.return_value.patch.call_args.kwargs["body"] == {"colorId": orders.COLOR_RESERVE}


def test_proxy_booking_without_matching_name_skips_and_does_not_create_event():
    service = Mock()
    service.events.return_value.list.return_value.execute.return_value = {
        "items": [{"id": "event-1", "summary": "其他客人"}],
    }
    result = orders.sync_proxy_reserve_calendar_by_name(
        service, "calendar-id", "2026-12-01", "陳宜慧",
    )
    assert result["日曆改色結果"] == "未執行"
    service.events.return_value.patch.assert_not_called()
    assert not hasattr(service.events.return_value, "insert") or not service.events.return_value.insert.called


def test_proxy_notice_without_name_skips_calendar():
    assert orders.proxy_reserve_name_from_notice("代客保留-") == ""
    assert orders.proxy_reserve_name_from_notice("代客保留：陳宜慧") == "陳宜慧"


def test_successful_batch_builds_combined_line_notice():
    entries = []
    for index, date in enumerate(("2026-12-01", "2026-12-08"), 1):
        row = {
            "姓名": "陳宜慧", "地址": ADDRESS, "購買項目": "居家清潔",
            "日期": date, "開始時間": "09:00", "結束時間": "12:00",
        }
        entries.append((row, {"訂單編號": f"LC0000000{index}", "結果": "成功"}))
    messages = _batch_line_messages(entries, logger=lambda _message: None)
    assert len(messages) == 1
    assert "2026/12/01 09:00-12:00" in messages[0]["通知內容"]
    assert "2026/12/08 09:00-12:00" in messages[0]["通知內容"]
    pasted = line_messages_tsv(messages)
    assert pasted.startswith("姓名\t地址\t訂單編號\tLINE預約完成通知\n")
    assert '"感謝您預約' in pasted
