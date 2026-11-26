# -*- coding: utf-8 -*-
"""服務異動：待處理發票情境與 VIP 退券原價反推。"""
from datetime import date, datetime

import pytest

from memo_system import invoice_change as ic

ORDER = {"order_no": "LC00000001", "customer_name": "王小明", "line_url": "https://chat.line.biz/x",
         "invoice_no": "HR60355358", "carrier_type": "二聯式", "total": 4800}
ORDER3 = {**ORDER, "order_no": "LC00000002", "invoice_no": "HR60355359", "carrier_type": "三聯式", "total": 3000}
ARGS = ("2026-11-25 (三) 09:00-13:00", "2026/11/25", "一般客")


def test_notify_page_by_tax_id():
    assert ic.notify_target(True) == ("買家發票補通知", ic.NOTIFY_URL_B2B)
    assert ic.notify_target(False) == ("發票補通知", ic.NOTIFY_URL_B2C)
    assert ic.notify_after(datetime(2026, 11, 25, 10, 40)) == datetime(2026, 11, 25, 16, 40)


def test_info_change_row_is_pending_invoice_and_notifies_b2b_for_triplicate():
    row = ic.build_info_change_row(ORDER3, {"買家地址": "新北市板橋區", "買家Email": ""}, *ARGS)
    assert row["B"] == "待處理發票" and row["C"] == "發票資料變更"
    assert "買家地址改為「新北市板橋區」" in row["J"] and "Email" not in row["J"]
    assert "買家發票補通知" in row["J"] and row["X"] == "HR60355359" and row["Y"] == "三聯"
    with pytest.raises(ValueError):
        ic.build_info_change_row(ORDER, {"買家地址": " "}, *ARGS)


def test_carrier_validation():
    assert ic.validate_carrier("手機條碼", "/VMVA4EV") == ""
    assert ic.validate_carrier("手機條碼", "VMVA4EV") != ""
    assert ic.validate_carrier("紙本發票", "") == ""
    assert ic.validate_carrier("會員載具", "a@gmail.com") == ""
    assert ic.validate_carrier("會員載具", "abc") != ""
    row = ic.build_carrier_change_row(ORDER, "手機條碼", "/VMVA4EV", *ARGS)
    assert "改為手機條碼 /VMVA4EV" in row["J"] and "折讓重開" in row["J"] and "「發票補通知」" in row["J"]
    member = ic.build_carrier_change_row(ORDER, "會員載具", "a@gmail.com", *ARGS)
    assert "改為會員載具 a@gmail.com" in member["J"]


def test_triplicate_row_matches_tool_system_executor():
    row = ic.build_reissue_row(ORDER, "二聯轉三聯", "12345678", "檸檬有限公司", *ARGS, service_note="客要報帳")
    # tool-system TRIPLICATE_DETAILS＋parse_requirements：C「二聯轉三聯」、K 第一行「統編 公司名稱」
    assert row["C"] == "二聯轉三聯" and row["K"].splitlines()[0] == "12345678 檸檬有限公司"
    assert "全額折讓 $4,800" in row["J"] and "作廢" not in row["J"] and "買家發票補通知" in row["J"]
    to_two = ic.build_reissue_row(ORDER3, "三聯轉二聯", "", "", *ARGS)
    assert "重開二聯" in to_two["J"] and "「發票補通知」" in to_two["J"] and "三聯" not in to_two["C"]
    with pytest.raises(ValueError):
        ic.build_reissue_row(ORDER, "更正統編", "1234567", "檸檬公司", *ARGS)


def test_tax_id_correction_does_not_issue_allowance():
    row = ic.build_reissue_row(ORDER3, "更正統編", "87654321", "檸檬公司", *ARGS)
    assert "改為統編87654321 檸檬公司" in row["J"] and "折讓" not in row["J"]
    assert row["_calc_amount"] == 0 and "買家發票補通知" in row["J"] and row["C"] == "發票更正統編"


def test_merge_writes_single_row_listing_all_orders():
    rows = ic.build_merge_rows([ORDER, ORDER3], "2026-11-25", "2026/11/25", "一般客")
    assert len(rows) == 1 and rows[0]["C"] == "合併開立發票" and rows[0]["G"] == "LC00000001"
    assert "LC00000001、LC00000002" in rows[0]["J"] and "共 $7,800" in rows[0]["J"]
    with pytest.raises(ValueError):
        ic.build_merge_rows([ORDER], "", "2026/11/25", "")


def test_credit_card_over_three_months_refunds_by_atm():
    today = date(2026, 11, 25)
    assert ic.refund_payway("信用卡", date(2026, 8, 25), today) == "信用卡"
    assert ic.refund_payway("信用卡", date(2026, 8, 24), today) == "ATM"
    assert ic.refund_payway("ATM", date(2026, 11, 1), today) == "ATM"


def test_original_price_normal_and_deep_clean():
    assert ic.original_price(date(2026, 11, 25), 2, 2)["amount"] == 2310   # 週三
    assert ic.original_price(date(2026, 11, 28), 2, 2)["amount"] == 2710   # 週六
    assert ic.original_price(date(2026, 12, 16), 2, 4)["amount"] == 6000   # 2026 PART1 平日
    assert ic.original_price(date(2027, 1, 23), 2, 4)["amount"] == 6400    # 2026 PART2 週末
    assert ic.original_price(date(2024, 12, 14), 2, 2)["amount"] == 2960   # 2024 週末
    assert ic.original_price(date(2021, 1, 4), 2, 4)["derived"] is True


def test_vip_refund_customer_initiated_converted_hours():
    used = [{"service_date": date(2026, 11, 25), "persons": 2, "hours": 2},
            {"service_date": date(2026, 11, 28), "persons": 2, "hours": 2}]
    refund = ic.calc_vip_refund("customer", paid_amount=10000, used_services=used,
                                converted_from_hours=True, shopping_credit_refund=999)
    assert refund["used_total"] == 5020 and refund["stored_refund"] == 4980
    assert refund["shopping_credit_refund"] == 0 and refund["total_refund"] == 4980
    row = ic.build_vip_refund_row(ORDER, refund, "customer", "ab12345678", "ATM", False,
                                  "", "2026/11/25")
    assert row["B"] == "VIP待退券" and row["S"] == 4980 and row["R"] == "ATM" and row["X"] == "AB12345678"
    assert "折讓 $4,980" in row["J"] and "購物金不返還" in row["J"]


def test_vip_refund_company_initiated_adds_negotiated_credit_without_allowance():
    refund = ic.calc_vip_refund("company", stored_balance=3000, shopping_credit_refund=500)
    assert refund["stored_refund"] == 3000 and refund["total_refund"] == 3500
    row = ic.build_vip_refund_row(ORDER, refund, "company", "AB12345678", "信用卡", True, "", "2026/11/25")
    assert "折讓 $3,000" in row["J"] and "買家發票補通知" in row["J"]


def test_vip_refund_never_negative():
    used = [{"service_date": date(2026, 11, 25), "persons": 2, "hours": 8}]
    refund = ic.calc_vip_refund("customer", paid_amount=5000, used_services=used, converted_from_hours=True)
    assert refund["stored_refund"] == 0
    row = ic.build_vip_refund_row(ORDER, refund, "customer", "", "ATM", False, "", "2026/11/25")
    assert "不需折讓" in row["J"]
