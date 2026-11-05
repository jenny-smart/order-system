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


def test_previous_workday_skips_weekends_and_holidays():
    assert str(atm.previous_workday("2026-11-05")) == "2026-11-04"   # 週四 → 週三
    assert str(atm.previous_workday("2026-11-09")) == "2026-11-06"   # 週一 → 上週五
    assert str(atm.previous_workday("2027-02-11")) == "2027-02-03"   # 春節連假後 → 連假前


def test_scheduled_sync_limits_order_date_range():
    calls = {}

    def search(session, date_until=None, ui_logger=None, date_since=None):
        calls[date_until] = date_since
        return []

    session = Mock()
    with patch.object(atm, "search_atm_unpaid_orders", side_effect=search), \
            patch.object(atm, "flag_cancelled_pending_orders", return_value={}), \
            patch.object(atm, "paste_atm_unpaid_list", return_value={"pasted": 0}), \
            patch.object(atm.memo, "set_runtime_credentials"), \
            patch.object(atm.memo, "login", return_value=session), \
            patch.dict("accounts.ACCOUNTS", {"台北": {"email": "a", "password": "b"}, "台中": {"email": "c", "password": "d"}}):
        atm.run_scheduled_unpaid_sync(date_until="2026-11-09")
    assert calls == {"2026-11-09": "2026-11-06"}


def test_search_sends_order_date_start():
    session = Mock()
    response = Mock(text="<html></html>")
    with patch.object(atm.memo, "session_get", return_value=response) as get:
        atm.search_atm_unpaid_orders(session, date_until="2026-11-05", date_since="2026-11-04")
    params = get.call_args.kwargs["params"]
    assert params["date_s"] == "2026-11-04" and params["date_e"] == "2026-11-05"
