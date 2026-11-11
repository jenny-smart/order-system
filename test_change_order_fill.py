# -*- coding: utf-8 -*-
"""服務異動階段 C：自後台補齊＋同步 ATM 工作表。"""
from unittest.mock import MagicMock, patch

from memo_system import change_order_fill as cof

LETTERS = "A B C D E F G H I J K L M N O P Q R S T U V W X Y Z AA AB AC AD AE".split()
ORDER = {"purchase_id": "9", "order_no": "LC00000001", "customer_name": "王小明", "line_url": "https://chat.line.biz/x",
         "invoice_no": "AB12345678", "carrier_type": "二聯式", "payway": "ATM", "travel_fee": 300}


def row(**cells):
    values = [""] * len(LETTERS)
    cells.setdefault("E", "2026/10/16")
    cells.setdefault("G", "LC00000001")
    for key, value in cells.items():
        values[LETTERS.index(key)] = value
    return values


def test_refund_fill_only_blanks_and_never_bank():
    fills = cof.backend_fill_values(row(B="待退款", H="手打"), ORDER, {"refundAmount": "1,000"}, "一般客", "2026-11-20 (五)")
    assert fills == {"D": "https://chat.line.biz/x", "F": "一般客", "I": "2026-11-20 (五)", "R": "ATM", "S": 1000,
                     "X": "AB12345678", "Y": "二聯"}
    assert "P" not in fills and "Q" not in fills


def test_out_of_scope_rows_not_filled():
    assert cof.wanted_letters(row(B="已退款")) == set()
    assert cof.wanted_letters(row(B="待退款", E="2026/10/15")) == set()
    assert cof.wanted_letters(row(B="待退款", G="")) == set()


def test_charge_m_needs_backend_paid_flag():
    base = dict(B="待收款", D="x", F="x", H="x", I="x")
    assert cof.backend_fill_values(row(**base), ORDER, {"isCharge": "1", "chargeDate": "2026-11-10", "chargeAmount": "600",
                                                         "chargePayment": "ATM"}) == {"N": 600, "R": "ATM"}
    assert cof.backend_fill_values(row(**base), ORDER, {"isCharge": "2", "chargeDate": "2026-11-10"}) == {"M": "2026/11/10"}


def test_unknown_backend_values_not_guessed():
    order = {**ORDER, "invoice_no": "儲值金", "payway": "非儲值金"}
    assert cof.backend_fill_values(row(B="待退款", D="x", F="x", H="x", I="x"), order, {}) == {}


def test_fill_from_backend_dry_run_does_not_write():
    ws = MagicMock()
    session = MagicMock()
    session.get.return_value = MagicMock(text="", raise_for_status=lambda: None)
    values = [["h"], row(B="待退款")]
    logs = []
    with patch.object(cof.change_order, "fetch_order_basic", return_value=ORDER), \
            patch.object(cof.change_order, "_extract_purchase_state", return_value={"refundAmount": "1000"}), \
            patch.object(cof.change_order, "_customer_type_from_order", return_value="一般客"), \
            patch.object(cof.change_order, "_format_service_datetime", return_value="2026-11-20 (五)"):
        planned = cof.fill_from_backend("台北", ws, values, session, log=logs.append, dry_run=True)
    ws.batch_update.assert_not_called()
    assert planned[0]["fills"]["S"] == 1000 and cof._cell(values[1], "R") == "ATM"  # 預覽時同步看得到補完的值
    assert any("〔預覽〕會補" in line for line in logs)


def test_atm_candidates_and_dedupe():
    values = [["h"],
              row(B="待退款", R="ATM", S="1000", H="王", I="2026-11-20 (五)"),
              row(B="待收款", R="ATM", N="600", G="LC2", I="2026/12/01", J="加購工具組"),
              row(B="待退款", R="信用卡", S="500", G="LC3"),
              row(B="待退款", R="ATM", S="500", G="LC4", AC="2026/11/11"),
              row(B="待收款", R="ATM", N="600", G="LC5", M="2026/11/11")]
    rows = cof.atm_candidates(values)
    assert [(r["order_no"], r["amount"], r["kind"], r["year_month"]) for r in rows] == [
        ("LC00000001", -1000, "refund", "2026.11"), ("LC2", 600, "charge", "2026.12")]
    assert cof.service_fee(rows[0]) == ("清潔", "退款") and cof.service_fee(rows[1]) == ("清潔", "工具組")
    atm_values = [[""] * 12]
    atm_values[0][9], atm_values[0][11] = "LC00000001", "-1,000"
    assert [r["order_no"] for r in cof.new_atm_rows(rows, atm_values)] == ["LC2"]


def test_sync_atm_sheet_dry_run_does_not_write():
    ws = MagicMock(row_count=100)
    ws.get_all_values.return_value = [["銀行"] + [""] * 11]
    with patch.object(cof.atm, "get_atm_worksheet", return_value=ws):
        rows = cof.sync_atm_sheet("台北", [["h"], row(B="待退款", R="ATM", S="200")], log=lambda *_: None, dry_run=True)
    assert len(rows) == 1 and not ws.update.called
