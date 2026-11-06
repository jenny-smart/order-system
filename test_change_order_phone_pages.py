from datetime import date
from unittest.mock import Mock

from memo_system import change_order


def _page(order_nos):
    resp = Mock(text="<table><tbody>" + "".join(f"<tr><td>{n}</td></tr>" for n in order_nos) + "</tbody></table>")
    resp.raise_for_status = Mock()
    return resp


def test_phone_lookup_reads_all_pages_and_sorts(monkeypatch):
    pages = {"1": ["LC3", "LC2"], "2": ["LC1"], "3": []}
    dates = {"LC1": date(2099, 1, 1), "LC2": date(2099, 3, 1), "LC3": date(2099, 2, 1)}
    session = Mock()
    session.get.side_effect = lambda url, params, timeout: _page(pages[params["page"]])
    monkeypatch.setattr(change_order, "_parse_order_row",
                        lambda row: {"order_no": row.get_text(strip=True), "is_paid": True,
                                     "service_date": dates[row.get_text(strip=True)]})
    monkeypatch.setattr(change_order, "_fill_cleaner_count", lambda *a, **k: None)
    result = change_order.fetch_upcoming_paid_orders_by_phone("0912", session=session)
    assert [o["order_no"] for o in result] == ["LC1", "LC3", "LC2"]


def test_phone_lookup_stops_when_backend_ignores_page(monkeypatch):
    session = Mock()
    session.get.side_effect = lambda url, params, timeout: _page(["LC1"])
    monkeypatch.setattr(change_order, "_parse_order_row",
                        lambda row: {"order_no": "LC1", "is_paid": True, "service_date": date(2099, 1, 1)})
    monkeypatch.setattr(change_order, "_fill_cleaner_count", lambda *a, **k: None)
    assert len(change_order.fetch_upcoming_paid_orders_by_phone("0912", session=session)) == 1
    assert session.get.call_count == 2


def test_recent_done_sorted_before_upcoming():
    today = date(2026, 11, 6)
    parsed = [{"order_no": n, "is_paid": True, "service_date": d} for n, d in
              [("A", date(2026, 12, 1)), ("B", date(2026, 10, 1)), ("C", date(2026, 11, 1)), ("D", date(2026, 9, 1))]]
    assert [o["order_no"] for o in change_order._select_change_order_candidates(parsed, today)] == ["B", "C", "A"]
