from types import SimpleNamespace

from memo_system import atm


def test_proxy_reserve_customer_name_supports_full_and_half_width_colons():
    assert atm._proxy_reserve_customer_name({"memo": "代客保留：王小明"}) == "王小明"
    assert atm._proxy_reserve_customer_name(
        {"service_notice": "請先聯絡；代客保留: 李小華"}
    ) == "李小華"


def test_proxy_reserve_customer_name_ignores_cancelled_or_unrelated_notes():
    assert atm._proxy_reserve_customer_name({"memo": "取消代客保留：王小明"}) == ""
    assert atm._proxy_reserve_customer_name({"memo": "系統保留單", "name": "檸檬保留"}) == ""


def test_unpaid_order_list_uses_proxy_name_without_changing_regular_name(monkeypatch):
    items = [
        {"date_clean": "2026-12-10", "order_no": "LC001", "name": "檸檬保留",
         "total": 3000, "fare": 0, "memo": "代客保留：王小明", "member": {"line": "reserve"}},
        {"date_clean": "2026-12-11", "order_no": "LC002", "name": "陳大文",
         "total": 2500, "fare": 200, "memo": "一般訂單", "member": {"line": "regular"}},
    ]
    response = SimpleNamespace(raise_for_status=lambda: None, text="ignored")
    monkeypatch.setattr(atm.memo, "session_get", lambda *args, **kwargs: response)
    monkeypatch.setattr(atm, "extract_purchase_list_json", lambda html: {"data": items})

    rows = atm.search_atm_unpaid_orders(object(), date_until="2026-12-31")

    assert rows[0]["name"] == "王小明"
    assert rows[0]["order_no"] == "LC001"
    assert rows[1]["name"] == "陳大文"
    assert rows[1]["net_amount"] == 2300
