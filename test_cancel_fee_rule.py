"""異動費＋待退款＝取消服務：VIP 免收；一般客不分工作天數收服務費 5%。"""
from datetime import date
from unittest.mock import patch

import pytest

from memo_system import change_order as c

ORDER = {"order_no": "LC00300001", "customer_name": "測試", "payway": "信用卡", "period_text": "09:00-12:00",
         "service_hours": 3.0, "cleaner_count": 2, "total": 4200, "travel_fee": 200}
TODAY = date(2026, 11, 2)  # 週一


@pytest.mark.parametrize("service_date", [date(2026, 11, 3), date(2026, 11, 5), date(2026, 11, 20)])
def test_regular_cancel_always_five_percent(service_date):
    with patch.object(c, "pricing_tier", lambda order: "regular"):
        info = c.calc_cancel_fee(ORDER, service_date, today=TODAY)
        row = c.build_refund_row(ORDER, info, "", service_date=service_date, today=TODAY)
    assert info["change_fee"] == 200  # (4200-200) × 5%
    assert row["_refund_amount"] == 3800
    assert "收5%取消異動費$200，退款$3800" in row["J"]


@pytest.mark.parametrize("service_date", [date(2026, 11, 3), date(2026, 11, 20)])
def test_vip_cancel_free(service_date):
    with patch.object(c, "pricing_tier", lambda order: "vip"):
        info = c.calc_cancel_fee(ORDER, service_date, today=TODAY)
        row = c.build_refund_row(ORDER, info, "", service_date=service_date, today=TODAY)
    assert info["change_fee"] == 0
    assert row["_refund_amount"] == 4000
    assert "VIP免收異動費，退款$4000" in row["J"]


def test_reschedule_charge_still_uses_workday_fee():
    with patch.object(c, "pricing_tier", lambda order: "vip"):
        info = c.calc_change_fee(ORDER, date(2026, 11, 4), today=TODAY)
    assert info["change_fee"] > 0
