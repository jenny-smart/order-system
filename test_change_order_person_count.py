from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

from memo_system import change_order


def _session(html, status=200):
    session = MagicMock()
    session.get.return_value = SimpleNamespace(status_code=status, text=html)
    return session


def test_person_count_falls_back_to_schedule_edit_slots():
    """訂單列表沒有專員連結（未配班或檸檬人）時，人數改讀排班修改頁的人員位置數。"""
    html = '<input type="hidden" name="originShiftId[]" value="11"><input type="hidden" name="originShiftId[]" value="12">'
    order = {"order_no": "LC00217671", "purchase_id": "217671", "service_date": date(2026, 10, 27), "cleaner_count": 0}
    session = _session(html)
    change_order._fill_cleaner_count(order, session)
    assert order["cleaner_count"] == 2
    assert session.get.call_args.kwargs["params"] == {"date": "2026-10-27", "purchase_id": "217671"}


def test_person_count_kept_when_staff_links_exist_or_page_unreadable():
    order = {"purchase_id": "1", "service_date": date(2026, 10, 27), "cleaner_count": 3}
    session = _session("")
    change_order._fill_cleaner_count(order, session)
    assert order["cleaner_count"] == 3 and not session.get.called
    order = {"purchase_id": "1", "service_date": date(2026, 10, 27), "cleaner_count": 0}
    change_order._fill_cleaner_count(order, _session("", status=500))
    assert order["cleaner_count"] == 0
