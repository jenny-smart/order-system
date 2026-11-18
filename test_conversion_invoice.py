import orders  # noqa: F401
import quick_order as q

TRIPLE = ["LC00220571", "余先生", "發票：HR60355055", "三聯式：", "睦仁文化傳播股份有限公司", "90030357",
          "付款方式：信用卡", "付款狀態：已付款"]
CANCELLED_TRIPLE = ["發票：", "三聯式：", "睦仁文化傳播股份有限公司", "90030357", "付款方式：信用卡"]
MEMBER_CARRIER = ["發票：", "二聯式：會員載具", "付款方式：信用卡"]
MOBILE = ["發票：", "二聯式：手機載具 /HWHMPF6", "付款方式：信用卡"]
DONATE = ["發票：", "捐贈：8585", "付款方式：信用卡"]


def test_triple_invoice_is_kept():
    for lines in (TRIPLE, CANCELLED_TRIPLE):
        kw = q._invoice_kwargs_from_block(lines, "a@b.com")
        assert kw["invoice_type_override"] == "3"
        assert (kw["company_title"], kw["company_no"], kw["payment_type"]) == ("睦仁文化傳播股份有限公司", "90030357", "B2B")


def test_member_carrier_uses_member_email():
    kw = q._invoice_kwargs_from_block(MEMBER_CARRIER, "a@b.com")
    assert (kw["invoice_type_override"], kw["carrier_type_id_override"], kw["carrier_info"]) == ("2", "1", "a@b.com")


def test_mobile_carrier_and_donate():
    kw = q._invoice_kwargs_from_block(MOBILE, "a@b.com")
    assert (kw["carrier_type_id_override"], kw["carrier_info"]) == ("2", "/HWHMPF6")
    kw = q._invoice_kwargs_from_block(DONATE, "a@b.com")
    assert (kw["invoice_type_override"], kw["donate_code_override"]) == ("1", "8585")


def test_unparseable_or_incomplete_falls_back_to_default():
    assert q._invoice_kwargs_from_block(["發票：不開立發票"], "a@b.com") == {}
    assert q._invoice_kwargs_from_block(["三聯式：", "", ""], "a@b.com") == {}


def test_last_order_invoice_fallback_uses_previous_order(monkeypatch):
    q._LAST_INVOICE_CACHE.clear()
    info = {"invoice_type": "3", "carrier_type_id": "", "carrier_info": "",
            "company_title": "睦仁文化傳播股份有限公司", "company_no": "90030357", "donate_code": ""}
    monkeypatch.setattr(q, "_find_payway_invoice_source_for_stored_value", lambda s, p: ({"payway": "信用卡"}, info, {}))
    kw = q._last_order_invoice_kwargs(object(), "0965-182-387", "a@b.com")
    assert kw["invoice_type_override"] == "3" and kw["company_no"] == "90030357"


def test_last_order_invoice_fallback_errors_keep_default(monkeypatch):
    q._LAST_INVOICE_CACHE.clear()
    def boom(s, p):
        raise RuntimeError("x")
    monkeypatch.setattr(q, "_find_payway_invoice_source_for_stored_value", boom)
    assert q._last_order_invoice_kwargs(object(), "0965182387", "a@b.com") == {}
