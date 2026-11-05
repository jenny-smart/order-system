"""ATM 待付款同步：整欄 J 去重，A 欄往下補資料後不重列已列過的訂單。"""
from unittest.mock import Mock, patch

from memo_system import atm


def _row(a="", j="", k="", l=""):
    row = [""] * 20
    row[0], row[9], row[10], row[11] = a, j, k, l
    return row


def _sheet():
    return [
        _row(a="日期"),
        _row(a="11/02", j="LC00219518", k="張美鳳", l="4800"),
        _row(j="LC00219397", k="黃妙禎", l="4800"),   # 11/02 列過、A 欄空
        _row(a="押金"),                              # A 欄最後一筆在這之後 → 上面都在分界線以上
        _row(), _row(), _row(), _row(),
        _row(j="LC00219736", k="王蘭香", l="4800"),   # 分界線以下
    ]


def _paste(values, rows):
    ws = Mock()
    ws.get_all_values.return_value = values
    ws.row_count = 100
    with patch.object(atm, "get_atm_worksheet", return_value=ws), \
            patch.object(atm.memo, "with_retry", side_effect=lambda fn, *a, **k: fn(*a, **k)):
        result = atm.paste_atm_unpaid_list("台北", rows)
    return result, ws


def _item(no, name):
    return {"year_month": "115.11", "order_no": no, "name": name, "net_amount": 4800, "line_url": ""}


def test_orders_above_bank_area_are_not_relisted():
    result, ws = _paste(_sheet(), [_item("LC00219397", "黃妙禎"), _item("LC00219518", "張美鳳"), _item("LC00219736", "王蘭香")])
    assert result["pasted"] == 0 and result["skipped_duplicates"] == 3
    ws.batch_update.assert_not_called()


def test_new_order_still_added_below_pending_rows():
    result, ws = _paste(_sheet(), [_item("LC00219397", "黃妙禎"), _item("LC00219999", "新客人")])
    assert result["pasted"] == 1 and result["skipped_duplicates"] == 1
    ranges = [u["range"] for u in ws.batch_update.call_args.args[0]]
    assert ranges[0] == "I10:L10"  # 王蘭香（第 9 列）下方
