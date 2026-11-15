"""付款後5碼比對：依 J 欄對應 K:S、配不到寫 P 欄「待確認：原因」。"""
from unittest.mock import Mock, patch

from memo_system import payment_match as pm


def _bank(time="", income="", note="", j="", k="", l="", region="高雄"):
    row = [""] * 20
    if region == "高雄":
        row[0], row[6] = time, note
    else:
        row[1], row[5] = time, note
    row[4], row[9], row[10], row[11] = income, j, k, l
    return row


def _cand(month, order, name, amount, paid_at, last5="", date="2026-11-01"):
    row = [""] * 20
    row[10:19] = [month, order, name, date, str(amount), last5, "居家清潔", "清潔服務", paid_at]
    return row


def _run(region, sheet):
    ws = Mock()
    ws.get_all_values.return_value = sheet
    logs = []
    with patch.object(pm, "get_worksheet", return_value=ws), \
            patch.object(pm.memo, "with_retry", side_effect=lambda fn, *a, **k: fn(*a, **k)):
        result = pm.match_bank_rows(region, ui_logger=logs.append)
    updates = {}
    for call in ws.batch_update.call_args_list:
        for u in call.args[0]:
            updates[u["range"]] = u["values"][0]
    return result, updates, logs


def _sheet():
    t = "2026/10/08 11:53:51"
    return [
        _bank(),  # 標題
        _bank("2026/11/05 14:29:37", "18,900", "812-0020461000178537\n打掃", j="LC00219696", k="舊姓名", l="1"),
        _bank(t, "14,000", "韓耕柏 中信銀青年"),
        _bank(t, "", "韓耕柏 中信銀青年"),
        _bank(t, "", "韓耕柏 中信銀青年"),
        _bank(t, "", "韓耕柏 中信銀青年"),
        _bank(t, "", "韓耕柏 中信銀青年"),
        _bank("2026/11/9 23:02:12", "7,800", "017-0000000310768744"),          # 沒姓名／後5碼
        _bank("2026/11/10 10:00:00", "2,400", "王小明"),                          # 兩筆同額
        [""] * 20, [""] * 20,
        _cand("2026.11", "LC00219696", "黃裕玲", 18900, "2026-11-05 15:05"),
        _cand("2026.10", "LC00217199", "韓耕柏", 3600, "2026-10-08 12:00"),
        _cand("2026.10", "LC00217176", "韓耕柏", 3600, "2026-10-08 12:00"),
        _cand("2026.10", "LC00217058", "韓耕柏", 1800, "2026-10-08 12:00"),
        _cand("2026.10", "LC00217202", "韓耕柏", 3200, "2026-10-08 12:00"),
        _cand("2026.10", "LC00217177", "韓耕柏", 1800, "2026-10-08 12:00"),
        _cand("2027.01", "LC00220076", "陳惠卿", 7800, "2026-11-09 23:11"),
        _cand("2026.11", "LC00300001", "王小明", 2400, "2026-11-10 10:30"),
        _cand("2026.11", "LC00300002", "王小明", 2400, "2026-11-10 10:30"),
    ]


def test_existing_j_row_is_overwritten_from_ks_by_order_no():
    result, updates, _ = _run("高雄", _sheet())
    assert result["updated_by_order"] == 1
    assert updates["I2"] == ["2026.11"]
    assert updates["K2:O2"] == ["黃裕玲", 18900, "", "清潔", "服務費用"]  # 高雄維持清潔／服務費用
    assert updates["K12:S12"] == [""] * 9  # 已用的候選從 K:S 移除


def test_multi_order_sum_fills_continuation_rows():
    result, updates, _ = _run("高雄", _sheet())
    assert result["matched_bank_rows"] == 1 and result["matched_orders"] == 5
    assert {updates[f"J{r}"][0] for r in range(3, 8)} == {
        "LC00217199", "LC00217176", "LC00217058", "LC00217202", "LC00217177"}


def test_unmatched_rows_logged_and_marked_in_p():
    result, updates, logs = _run("高雄", _sheet())
    assert result["review"] == 2
    assert updates["P8"] == ["待確認：備註沒有姓名或後5碼"]
    assert updates["P9"] == ["待確認：多組金額相同"]
    assert any(line.startswith("第 8 列｜7,800｜017-0000000310768744｜備註沒有姓名或後5碼") for line in logs)
    assert "T8" not in updates


def test_taoyuan_layout_reads_b_time_and_f_note():
    sheet = [
        _bank(region="桃園"),
        _bank("2026/10/16 12:11:02", "9,600", "傅以如清潔費\n\n北中壢分行", region="桃園"),
        [""] * 20,
        _cand("2026.11", "LC00217496", "傅以如", 9600, "2026-10-16 13:00"),
    ]
    result, updates, _ = _run("桃園", sheet)
    assert result["matched_orders"] == 1 and updates["J2"] == ["LC00217496"]


def test_continuation_rows_missing_marks_review():
    sheet = _sheet()
    sheet[3] = _bank("2026/10/09 09:00:00", "500", "別人", region="高雄")  # 續列被別的銀行列佔用
    result, updates, _ = _run("高雄", sheet)
    assert updates["P3"][0].startswith("待確認：5 筆訂單加總，但下方列非空")


def test_taoyuan_keeps_backend_category_and_detail():
    sheet = [_bank(region="桃園"), _bank("2026/10/16 12:11:02", "9,600", "傅以如", region="桃園"),
             [""] * 20, _cand("2026.11", "LC00217496", "傅以如", 9600, "2026-10-16 13:00")]
    _, updates, _ = _run("桃園", sheet)
    assert updates["K2:O2"][3:] == ["居家清潔", "清潔服務"]
