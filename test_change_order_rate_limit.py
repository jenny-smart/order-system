from unittest.mock import patch

from memo_system import change_order, memo


class RateLimited(Exception):
    def __str__(self):
        return "APIError: [429]: Quota exceeded for quota metric 'Read requests'"


class FakeWorksheet:
    title = "清潔異動"
    row_count = 10

    def __init__(self):
        self.col_calls = 0
        self.updates = []

    def col_values(self, col):
        self.col_calls += 1
        if self.col_calls == 1:
            raise RateLimited()
        return ["狀態", "待收款", "", ""]

    def batch_update(self, data, value_input_option=None):
        for item in data:
            assert "!" not in item["range"]
            item["range"] = f"'清潔異動'!{item['range']}"  # gspread 會改寫傳入的 dict
        if not self.updates and not getattr(self, "write_failed", False):
            self.write_failed = True
            raise RateLimited()  # 寫入也可能遇到 429；重試時 range 不可帶兩次分頁名稱
        self.updates.append((list(data), value_input_option))


def test_with_retry_waits_for_quota_then_succeeds():
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise RateLimited()
        return "ok"

    with patch.object(memo.time, "sleep") as sleep:
        assert memo.with_retry(flaky) == "ok"
    assert [c.args[0] for c in sleep.call_args_list] == list(memo.RATE_LIMIT_WAITS[:2])


def test_with_retry_gives_up_after_rate_limit_waits():
    def always():
        raise RateLimited()

    with patch.object(memo.time, "sleep"):
        try:
            memo.with_retry(always)
        except RateLimited:
            pass
        else:
            raise AssertionError("should raise")


def test_append_rows_retries_quota_and_writes_each_row_in_one_request():
    ws = FakeWorksheet()
    row = {"B": "待收款", "C": "異動服務收款", "G": "LC00217997", "H": "林冠君", "J": "異動費$180", "K": "公式", "N": 180, "_calc_note": "x"}
    with patch.object(change_order, "get_worksheet", return_value=ws), \
         patch.object(memo.time, "sleep"), \
         patch("memo_system.atm.append_change_order_charges", return_value={"pasted": 1, "start_row": 5}):
        result = change_order.append_rows_to_sheet("台北", [row])
    assert result["errors"] == [] and result["written"] == 1 and result["start_row"] == 3
    assert len(ws.updates) == 1
    data, option = ws.updates[0]
    assert option == "USER_ENTERED"
    ranges = [d["range"].split("!")[1] for d in data]
    assert ranges == ["B3", "C3", "G3", "H3", "J3", "N3", "AD3", "AE3"]  # 不覆蓋 K 欄公式
