from unittest.mock import Mock

from shared import calendar_phone_search as cps


def _service(items_by_calendar):
    service = Mock()
    def list_(**kwargs):
        req = Mock()
        req.execute.return_value = {"items": items_by_calendar.get(kwargs["calendarId"], [])}
        return req
    service.events.return_value.list.side_effect = list_
    return service


def test_found_returns_search_link():
    service = _service({"tp": [{"summary": "王小明-大安區,0912345678"}]})
    info = cps.lookup_calendar_by_phone("0912-345-678", service, {"台北": "tp", "台中": "tc"})
    assert info["count"] == 1
    assert info["url"] == "https://calendar.google.com/calendar/r/search?q=0912345678"


def test_fuzzy_hit_without_phone_is_no_calendar():
    service = _service({"tp": [{"summary": "王小明-大安區,0912345679"}]})
    info = cps.lookup_calendar_by_phone("0912345678", service, {"台北": "tp"})
    assert info["count"] == 0 and info["url"] == ""


def test_calendar_error_is_reported_not_raised():
    service = Mock()
    service.events.side_effect = RuntimeError("boom")
    info = cps.lookup_calendar_by_phone("0912345678", service, {"台北": "tp"})
    assert info["error"] == "boom" and info["count"] == 0


def test_vip_rules():
    assert cps.is_vip_balance("1,200") and not cps.is_vip_balance("0") and not cps.is_vip_balance(None)
    assert cps.member_balance({"storedValue": "500", "shoppingValue": "100"}) == 600
    assert cps.member_balance(None) is None
    assert cps.normalize_phone("+886 912-345-678") == "0912345678"
