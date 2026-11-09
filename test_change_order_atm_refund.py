"""清潔異動 ATM 待退款 → ATM 工作表待配對區（負數、清潔／退款）。"""
from memo_system import atm, change_order


def test_is_atm_pending_refund():
    assert change_order._is_atm_pending_refund({"B": "待退款", "R": "ATM"})
    assert change_order._is_atm_pending_refund({"B": "待退款", "R": "藍新ATM"})
    assert not change_order._is_atm_pending_refund({"B": "待退款", "R": "信用卡"})
    assert not change_order._is_atm_pending_refund({"B": "待返儲值金", "R": "ATM"})
    assert not change_order._is_atm_pending_refund({"B": "待收款", "R": "ATM"})


class _WS:
    row_count = 50

    def __init__(self):
        self.updates = []

    def get_all_values(self):
        return [["銀行"]] + [[""] * 15 for _ in range(10)]

    def update(self, values=None, range_name=None, value_input_option=None):
        self.updates.append((range_name, values))


def test_append_refund_row_negative_and_refund_fee(monkeypatch):
    ws = _WS()
    monkeypatch.setattr(atm, "get_atm_worksheet", lambda region: ws)
    monkeypatch.setattr(atm, "ensure_candidate_row_format", lambda ws, rows, log=None: {})
    result = atm.append_change_order_charges("台北", [
        {"year_month": "2026.11", "order_no": "LC1", "name": "甲", "amount": 400, "change_text": "異動服務收款", "kind": "charge"},
        {"year_month": "2026.11", "order_no": "LC2", "name": "乙", "amount": -4800, "kind": "refund"},
    ])
    assert result == {"pasted": 2, "start_row": 6}
    data = dict(ws.updates)
    assert data["I6:L7"] == [["2026.11", "LC1", "甲", 400], ["2026.11", "LC2", "乙", -4800]]
    assert data["N6:O7"] == [["清潔", "異動費"], ["清潔", "退款"]]
