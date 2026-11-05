"""週末提醒：同一人多筆合併成一則；同地址時間重疊時以沒有檸檬人的那筆為主。"""
from function.weekend_reminders import (
    build_reminder_message, combine_customer_reminders, find_paid_weekend_orders, merge_tracking_rows,
    plan_tracking_rows,
)
import function.weekend_reminders as wr

BEITOU = "台北市北投區三合街一段82巷119號"
NANGANG = "台北市南港區經貿二路157巷36弄1號"


def _item(no, date, time, name="林佳宜", phone="0920273745", address=BEITOU, lemon=False):
    row = {"order_no": no, "service_date": date, "service_time": time, "name": name, "phone": phone,
           "address": address, "line_url": "https://chat.line.biz/x/" + no, "order_status": "已付款",
           "has_lemon": lemon}
    row["message"] = build_reminder_message(row)
    return row


def _merged(items, existing=()):
    rows = merge_tracking_rows(items, list(existing))
    return {row["訂單編號"]: row for row in rows}


def test_two_dates_same_address_combined_into_first_order():
    rows = _merged([_item("LC00219772", "2026-11-08", "14:00-17:00"), _item("LC00215256", "2026-11-07", "09:00-12:00")])
    first, second = rows["LC00215256"], rows["LC00219772"]
    assert "服務時間：\n11/7（六） 09:00-12:00\n11/8（日） 14:00-17:00\n服務地址：" + BEITOU in first["通知內容"]
    assert first["回覆備註"] == "合併 2 筆：LC00215256、LC00219772"
    assert second["通知內容"] == "" and second["回覆備註"] == "併入 LC00215256"


def test_different_addresses_list_time_and_address_each():
    rows = _merged([_item("LC1", "2026-11-07", "09:00-12:00"), _item("LC2", "2026-11-07", "14:00-17:00", address=NANGANG)])
    message = rows["LC1"]["通知內容"]
    assert "服務時間及地址：\n11/7（六） 09:00-12:00　" + BEITOU + "\n11/7（六） 14:00-17:00　" + NANGANG in message
    assert rows["LC2"]["通知內容"] == ""


def test_overlap_uses_order_without_lemon():
    rows = _merged([
        _item("LC00217922", "2026-11-07", "09:00-18:00", name="Joanne", phone="0930265126", address=NANGANG, lemon=True),
        _item("LC00217923", "2026-11-07", "14:00-18:00", name="Joanne", phone="0930265126", address=NANGANG),
    ])
    winner, loser = rows["LC00217923"], rows["LC00217922"]
    assert "11/7（六） 14:00-18:00" in winner["通知內容"] and "09:00-18:00" not in winner["通知內容"]
    assert winner["回覆備註"] == ""
    assert loser["通知內容"] == "" and loser["回覆備註"].startswith("時段重疊不另發：與 LC00217923")


def test_overlap_without_lemon_difference_lists_both_and_flags():
    rows = _merged([
        _item("LC1", "2026-11-07", "09:00-18:00", address=NANGANG),
        _item("LC2", "2026-11-07", "14:00-18:00", address=NANGANG),
    ])
    assert "09:00-18:00" in rows["LC1"]["通知內容"] and "14:00-18:00" in rows["LC1"]["通知內容"]
    assert rows["LC1"]["回覆備註"] == "時段重疊待確認：LC1、LC2"
    assert rows["LC2"]["回覆備註"] == "併入 LC1"


def test_back_to_back_slots_are_not_overlap():
    rows = _merged([
        _item("LC1", "2026-11-07", "09:00-12:00", lemon=True),
        _item("LC2", "2026-11-07", "12:00-15:00"),
    ])
    assert "09:00-12:00" in rows["LC1"]["通知內容"] and "12:00-15:00" in rows["LC1"]["通知內容"]


def test_different_customers_not_combined():
    rows = _merged([_item("LC1", "2026-11-07", "09:00-12:00"), _item("LC2", "2026-11-07", "09:00-12:00", phone="0911111111")])
    assert rows["LC1"]["通知內容"] == build_reminder_message(_item("LC1", "2026-11-07", "09:00-12:00"))
    assert rows["LC2"]["通知內容"] and rows["LC2"]["回覆備註"] == ""


def test_new_order_not_merged_into_already_tracked_row():
    existing = [{"訂單編號": "LC1", "服務日期": "2026-11-07", "通知內容": "舊提醒", "通知狀態": "已排程", "訂單狀態": "已付款"}]
    rows = _merged([_item("LC1", "2026-11-07", "09:00-12:00"), _item("LC2", "2026-11-08", "09:00-12:00")], existing)
    assert rows["LC1"]["通知內容"] == "舊提醒"
    assert rows["LC2"]["通知內容"] == build_reminder_message(_item("LC2", "2026-11-08", "09:00-12:00"))


def test_new_lemon_overlapping_tracked_order_not_sent():
    existing = [{"訂單編號": "LC1", "服務日期": "2026-11-07", "通知內容": "舊提醒", "通知狀態": "已排程", "訂單狀態": "已付款"}]
    rows = _merged([_item("LC1", "2026-11-07", "14:00-18:00"), _item("LC2", "2026-11-07", "09:00-18:00", lemon=True)], existing)
    assert rows["LC2"]["通知內容"] == "" and rows["LC2"]["回覆備註"].startswith("時段重疊不另發")


def test_save_does_not_regenerate_message_for_merged_rows():
    rows = list(_merged([_item("LC1", "2026-11-07", "09:00-12:00"), _item("LC2", "2026-11-08", "09:00-12:00")]).values())
    planned, _positions, _count = plan_tracking_rows([], rows, "2026-11-05 12:00")
    by_no = {row["訂單編號"]: row for row in planned}
    assert by_no["LC2"]["通知內容"] == "" and by_no["LC2"]["回覆備註"] == "併入 LC1"
    assert "11/8" in by_no["LC1"]["通知內容"]


def test_typhoon_flag_carries_into_combined_message():
    items = [_item("LC1", "2026-11-07", "09:00-12:00"), _item("LC2", "2026-11-08", "09:00-12:00")]
    for item in items:
        item["typhoon_reminder"] = True
    assert "人事行政局" in _merged(items)["LC1"]["通知內容"]


def test_combine_ignores_unpaid_and_single_orders():
    single = _item("LC1", "2026-11-07", "09:00-12:00")
    cancelled = dict(_item("LC2", "2026-11-08", "09:00-12:00"), order_status="已退款")
    assert combine_customer_reminders([single, cancelled]) == {}


def test_lemon_detected_from_backend_card(monkeypatch):
    html = """<table><tr><td>LC00217922</td><td><div>Joanne</div><div>0930265126</div>
<div>台北市南港區經貿二路157巷36弄1號</div><div>2026-11-01 10:00:00</div><div>居家清潔</div></td><td><div>2026-11-07 (六)</div><div>09:00 - 18:00</div>
<div>檸檬人3(1) X 王小明(2)</div></td><td><div>付款狀態：已付款</div></td></tr></table>"""

    class Response:
        status_code = 200
        text = html

    class Session:
        def get(self, *_a, **_k):
            return Response()

    monkeypatch.setattr(wr.orders.requests, "Session", Session)
    monkeypatch.setattr(wr.orders, "login", lambda *_a: True)
    monkeypatch.setattr(wr, "_configure_backend", lambda _env: None)
    rows, _ = find_paid_weekend_orders("dev", "a", "b", "2026-11-07", "2026-11-08")
    assert rows[0]["has_lemon"] is True and rows[0]["service_time"] == "09:00-18:00"


def test_same_slot_different_addresses_combined_not_treated_as_overlap():
    rows = _merged([
        _item("LC1", "2026-11-07", "09:00-12:00", lemon=True),
        _item("LC2", "2026-11-07", "09:00-12:00", address=NANGANG),
    ])
    message = rows["LC1"]["通知內容"]
    assert "服務時間及地址：\n11/7（六） 09:00-12:00　" + BEITOU + "\n11/7（六） 09:00-12:00　" + NANGANG in message
    assert rows["LC1"]["回覆備註"] == "合併 2 筆：LC1、LC2"
    assert rows["LC2"]["通知內容"] == "" and rows["LC2"]["回覆備註"] == "併入 LC1"
