"""訂單編號查詢取不到會員電話時的備援：+886 手機、會員頁 keyword 查詢。"""
from unittest.mock import MagicMock

import pytest

from memo_system import change_order as c


@pytest.mark.parametrize("text,expected", [
    ("王小明\n0912-345-678", "0912345678"),
    ("+886 912 345 678", "0912345678"),
    ("886912345678", "0912345678"),
    ("市話 02-2345-6789", ""),
    ("", ""),
])
def test_normalize_mobile(text, expected):
    assert c.normalize_mobile(text) == expected


def _session_with_members(members_json):
    resp = MagicMock()
    resp.text = f"<script>new Vue({{ data: {{ memberList: {members_json}, x: 1 }} }})</script>"
    resp.raise_for_status = lambda: None
    session = MagicMock()
    session.get.return_value = resp
    return session


def test_member_keyword_lookup_single_member():
    session = _session_with_members('[{"id": 1, "name": "王小明", "phone": "0912345678"}]')
    assert c.lookup_phone_by_member_keyword("a@b.com", session) == "0912345678"
    assert session.get.call_args.kwargs["params"] == {"keyword": "a@b.com"}


def test_member_keyword_lookup_ambiguous_returns_empty():
    session = _session_with_members(
        '[{"id": 1, "name": "王", "phone": "0912345678"}, {"id": 2, "name": "王", "phone": "0922345678"}]')
    assert c.lookup_phone_by_member_keyword("王", session) == ""


def test_member_keyword_lookup_no_keyword():
    session = MagicMock()
    assert c.lookup_phone_by_member_keyword("", session) == ""
    session.get.assert_not_called()


def test_missing_phone_error_points_to_manual_input(monkeypatch):
    import service_pricing
    monkeypatch.setattr(service_pricing, "load_config", lambda: {"enabled": True})
    with pytest.raises(ValueError, match="手動輸入"):
        c.refresh_pricing_balance({"order_no": "LC001", "phone": ""}, session=None)
