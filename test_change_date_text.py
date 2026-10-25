from datetime import date, datetime
from unittest.mock import patch

from memo_system import change_order as c

ORDER = {"order_no": "LC00215801", "customer_name": "蔡傑仁", "payway": "儲值金", "period_text": "14:00-17:00",
         "service_hours": 3.0, "cleaner_count": 2, "total": 0, "travel_fee": 0}


def _workday(d):
    return d.weekday() < 5 and d != date(2026, 10, 26)  # 10/26 光復節補假


def test_change_date_text_shows_postponed_processing_day():
    with patch.object(c, "_is_workday", _workday):
        assert c.change_date_text(date(2026, 10, 25)) == "10/25(日)異動，順延至10/27(二)處理"
        assert c.change_date_text(datetime(2026, 10, 22, 17, 31)) == "10/22(四)異動，順延至10/23(五)處理"
        assert c.change_date_text(date(2026, 10, 22)) == "10/22(四)異動"


def test_charge_row_j_and_calc_note_start_with_change_date():
    with patch.object(c, "_is_workday", _workday), patch.object(c, "pricing_tier", lambda order: "vip"):
        info = c.calc_change_fee(ORDER, service_date=date(2026, 10, 27), today=date(2026, 10, 25))
        row = c.build_charge_row(ORDER, info, "", service_date=date(2026, 10, 27), today=date(2026, 10, 25))
    assert row["J"] == "10/25(日)異動，順延至10/27(二)處理：服務當天異動，收異動費$300*時數=$900"
    assert row["_calc_note"].startswith("10/25(日)異動，順延至10/27(二)處理：服務當天異動，儲值金客")


def test_time_change_and_manual_refund_rows_start_with_change_date():
    with patch.object(c, "_is_workday", _workday):
        fee = {"person": 2, "hours": 1, "amount": 1300, "calc_note": "平日"}
        add = c.build_addtime_row(ORDER, fee, "", service_date=date(2026, 10, 27), today=date(2026, 10, 22))
        refund = c.build_manual_refund_row(ORDER, 500, c.TYPE_COMPLAINT_REFUND, "", today=date(2026, 10, 22))
    assert add["J"].startswith("10/22(四)異動：")
    assert refund["J"].startswith("10/22(四)異動：")
