"""ATM 對帳 ②＋③ 每日 08:10 排程（shared/atm_match_reconcile_schedule.py），以及待配對列 G／I／N／O 規則。"""
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from memo_system import atm

TZ = ZoneInfo("Asia/Taipei")


def _row(**cols):
    row = [""] * 21
    for letter, value in cols.items():
        row[ord(letter) - 65] = value
    return row


# ── N/O 規則 ─────────────────────────────────────────
@pytest.mark.parametrize("text,expected", [
    ("異動服務收款 11/05加時1小時", ("清潔", "異動費")),
    ("異動服務收款 更換日期", ("清潔", "異動費")),
    ("異動服務收款 工具組", ("清潔", "工具組")),
    ("", ("清潔", "異動費")),
])
def test_change_order_service_fee(text, expected):
    assert atm.change_order_service_fee(text) == expected


@pytest.mark.parametrize("amount,order_no,expected", [
    (2000, "", ("清潔", "新訓費")),
    ("2,000", "", ("清潔", "新訓費")),
    (2000, "LC00219084", ("清潔", "服務費用")),  # 有訂單的 2000 是服務費用
    (4800, "LC00219084", ("清潔", "服務費用")),
])
def test_default_service_fee_fallback(amount, order_no, expected):
    assert atm.default_service_fee(amount, order_no) == expected


# ── ② 未指定列號：近 3 個上班日 A:F 有資料、H:O 空白 ───────
@pytest.mark.parametrize("today,start", [
    ("2026-11-07", "2026-11-04"),  # 週六 → 週三、四、五
    ("2026-11-09", "2026-11-05"),  # 週一 → 上週四、五＋今天
    ("2026-11-05", "2026-11-03"),
    ("2027-02-11", "2027-02-02"),  # 春節連假後第一天：連假不算
])
def test_recent_workdays_start(today, start):
    assert str(atm.recent_workdays_start(date.fromisoformat(today))) == start


def test_recent_unmatched_bank_rows():
    rows = [
        _row(A="日期"),
        _row(A="2026/11/03", B="2026/11/03 10:00:00", E="4800"),          # 超過 3 個上班日
        _row(A="2026/11/04", B="2026/11/04 10:00:00", E="4800"),
        _row(A="2026/11/06", B="2026/11/06 14:02:46", E="4800", J="LC1", K="蘇慧芬"),  # 已配對
        _row(A="2026/11/06", B="2026/11/06 16:39:40", E="4800", F="檸檬家事"),
        _row(A="2026/11/07", B="2026/11/07 08:14:10", E="400", F="90344實"),
        _row(G="--,,"),                                                   # 只有 G 公式
        _row(I="2026.11", J="LC2", K="王蘭香", L="4800"),                 # 下方待配對區
        _row(B="2026/11/07 09:00:00", D="2400"),                          # A 空白看 B；支出列也算
    ]
    assert atm.recent_unmatched_bank_rows(rows, today=date(2026, 11, 7)) == [3, 5, 6, 9]


# ── 退款：清潔異動同日退款 ───────────────────────────
def test_match_refund():
    refunds = [
        {"date": date(2026, 11, 6), "order_no": "LC00219001", "name": "甲", "amounts": {2400}, "line_url": "", "year_month": "2026.11"},
        {"date": date(2026, 11, 6), "order_no": "LC00219002", "name": "乙", "amounts": {1200, 1300}, "line_url": "", "year_month": "2026.11"},
        {"date": date(2026, 11, 5), "order_no": "LC00219003", "name": "丙", "amounts": {800}, "line_url": "", "year_month": "2026.10"},
    ]
    assert atm.match_refund(refunds, date(2026, 11, 6), 2400) == (refunds[0], "退款")
    assert atm.match_refund(refunds, date(2026, 11, 6), 1300)[0]["order_no"] == "LC00219002"   # T 匯款金額或 S 退款金額
    assert atm.match_refund(refunds, date(2026, 11, 5), 900)[0] is None        # 金額不符 → 人工
    assert atm.match_refund(refunds, date(2026, 11, 6), 999)[0] is None
    assert atm.match_refund(refunds, date(2026, 11, 6), 2400, {"LC00219001"})[0] is None  # 已用過
    assert atm.match_refund(refunds, date(2026, 11, 7), 2400) == (None, "清潔異動找不到同日退款")


class _MatchWS:
    def __init__(self, rows):
        self.rows = rows
        self.writes = {}

    def get_all_values(self):
        return self.rows

    def update(self, a1, values, value_input_option=None):
        self.writes[a1] = values[0]

    def update_cell(self, r, c, v):
        self.writes[(r, c)] = v


def _run_match(monkeypatch, rows, refunds=()):
    ws = _MatchWS(rows)
    monkeypatch.setattr(atm, "get_atm_worksheet", lambda region: ws)
    monkeypatch.setattr(atm, "load_change_order_refunds", lambda region: list(refunds))
    for name in ("_clear_data_validation", "_copy_data_validation", "ensure_candidate_row_format", "normalize_atm_rows"):
        monkeypatch.setattr(atm, name, lambda *a, **k: None)
    result = atm.auto_match_bank_rows("台北", today=date(2026, 11, 7))
    return result, ws


def test_auto_match_refund_trainee_and_manual(monkeypatch):
    rows = [
        _row(A="日期"),
        _row(A="2026/11/06", B="2026/11/06 11:11:58", C="網路自轉", D="2,000", F="吳珍嫻新訓"),   # 2 支出 2000 → 新訓費
        _row(A="2026/11/06", B="2026/11/06 12:00:00", C="網路自轉", D="2,400", F="退款"),         # 3 支出 → 清潔異動退款
        _row(A="2026/11/06", B="2026/11/06 13:00:00", C="網路自轉", D="3,000", F="?"),            # 4 支出其他 → 人工
        _row(A="2026/11/06", B="2026/11/06 17:28:02", C="ＣＤ轉收", E="2,000", F="新訓費"),      # 5 收入 2000 沒訂單 → 新訓費
        _row(A="2026/11/06", B="2026/11/06 17:30:00", C="ＣＤ轉收", E="2,400", F="家事清潔"),    # 6 收入其他沒依據 → 人工
    ]
    refunds = [{"date": date(2026, 11, 6), "order_no": "LC00219084", "name": "許文菁", "amounts": {2400},
                "line_url": "https://line", "year_month": "2026.11"}]
    result, ws = _run_match(monkeypatch, rows, refunds)
    assert ws.writes["I2:O2"] == ["2026.11", "", "吳珍嫻", 2000, "", "清潔", "新訓費"]
    assert ws.writes[(2, atm.COL_RECON_STATUS)] == "新訓費"
    assert ws.writes["H3:O3"] == ["https://line", "2026.11", "LC00219084", "許文菁", 2400, "", "清潔", "退款"]
    assert ws.writes[(3, atm.COL_RECON_STATUS)] == "退款"
    assert not any(k for k in ws.writes if (isinstance(k, str) and k.endswith("4")) or k == (4, atm.COL_RECON_STATUS))
    assert ws.writes["I5:O5"][-2:] == ["清潔", "新訓費"]
    assert not any(k for k in ws.writes if (isinstance(k, str) and k.endswith("6")) or k == (6, atm.COL_RECON_STATUS))
    assert sorted(result["matched_rows"]) == [2, 3, 5]
    assert result["unmatched"] == 2
    # ③ 不會處理退款／新訓費列
    assert atm.rows_ready_for_reconcile(rows) == []


# ── ③ 只挑確定配對的列 ───────────────────────────────
def test_rows_ready_for_reconcile_only_confirmed_matches():
    b = "2026/11/06 09:28:58"
    rows = [
        _row(),  # 標題
        _row(B=b, E="4800", J="LC00219084", T="已配對"),
        _row(B=b, E="4800", J="LC00219085", T="需確認"),
        _row(B=b, E="2000", J="", T="已配對"),                       # 非訂單（新訓費）
        _row(B=b, E="4800", J="LC00219086", T="已更新系統"),
        _row(E="", J="LC00219087", T="已配對"),                      # 下方待配對區
        _row(B=b, E="4800", J="LC00219088", M="取消訂單", T="已配對"),
        _row(B=b, E="9600", J="LC00219089", T="已配對（多訂單加總）"),
    ]
    assert atm.rows_ready_for_reconcile(rows) == [2, 8]


def test_rows_before_1106_are_never_reconciled_by_schedule():
    rows = [
        _row(),
        _row(B="2026/11/05 19:22:28", E="1200", J="LC00218244", T="已配對"),
        _row(B="2026/11/06 00:00:01", E="4800", J="LC00219084", T="已配對"),
        _row(B="", E="4800", J="LC00219085", T="已配對"),           # 讀不到日期也不處理
        _row(B="2026-11-07 10:00", E="4800", J="LC00219086", T="已配對"),
    ]
    assert atm.rows_ready_for_reconcile(rows) == [3, 5]


# ── ③ 已付款不再發信、未開發票不發信並列出 ───────────
class _ReconWS:
    def __init__(self, rows):
        self.rows = rows
        self.cells = {}

    def get_all_values(self):
        return self.rows

    def update_cell(self, r, c, v):
        self.cells[(r, c)] = v


def _setup_reconcile(monkeypatch, status, invoice_after_issue, paid_at="2026-11-06 09:00:00"):
    ws = _ReconWS([_row(), _row(B="2026/11/06 09:00", E="4800", J="LC00219084", K="許文菁", L="4800", T="已配對")])
    state = {"status": status, "invoice": "", "mail": 0, "issued": 0, "paid_at": paid_at}
    monkeypatch.setattr(atm, "today_tw", lambda: date(2026, 11, 6))

    def find(session, order_no):
        return {"purchase_id": 9, "order_no": order_no, "total": 4800, "fare": 0, "payway": "2",
                "purchase_status": state["status"], "paid_at": state["paid_at"] if state["status"] == "1" else "",
                "invoice_no": state["invoice"]}

    def mark(session, pid):
        state["status"] = "1"
        return True

    def issue(session, pid):
        state["issued"] += 1
        state["invoice"] = invoice_after_issue
        return True

    def mail(session, order_no):
        state["mail"] += 1
        return {}

    monkeypatch.setattr(atm, "get_atm_worksheet", lambda region: ws)
    monkeypatch.setattr(atm, "find_purchase_by_order_no", find)
    monkeypatch.setattr(atm, "mark_paid", mark)
    monkeypatch.setattr(atm, "issue_invoice", issue)
    monkeypatch.setattr(atm, "send_confirmation_mail", mail)
    monkeypatch.setattr(atm, "_clear_data_validation", lambda *a, **k: None)
    return ws, state


def test_already_paid_order_never_gets_confirmation_mail(monkeypatch):
    ws, state = _setup_reconcile(monkeypatch, status="1", invoice_after_issue="AB12345678")
    result = atm.process_atm_rows("台北", "2", session=object())
    assert state["mail"] == 0
    assert result["success"] == 1 and result["completed"][0]["already_paid"] is True
    assert ws.cells[(2, atm.COL_MAIL_STATUS)] == "原已付款，未發信"
    assert ws.cells[(2, atm.COL_INVOICE_NO)] == "AB12345678"


def test_unpaid_order_gets_paid_invoice_and_mail(monkeypatch):
    ws, state = _setup_reconcile(monkeypatch, status="0", invoice_after_issue="AB12345678")
    result = atm.process_atm_rows("台北", "2", session=object())
    assert state["mail"] == 1 and result["no_invoice"] == []
    assert ws.cells[(2, atm.COL_RECON_STATUS)] == "已更新系統"


def test_invoice_not_issued_skips_mail_and_is_listed(monkeypatch):
    ws, state = _setup_reconcile(monkeypatch, status="0", invoice_after_issue="")
    result = atm.process_atm_rows("台北", "2", session=object())
    assert state["mail"] == 0 and state["issued"] == 1
    assert result["success"] == 1
    assert [d["order_no"] for d in result["no_invoice"]] == ["LC00219084"]
    assert ws.cells[(2, atm.COL_RECON_STATUS)] == "已更新系統（未開發票）"
    assert ws.cells[(2, atm.COL_PAID_AT)] == "2026-11-06 09:00:00"
    assert ws.cells[(2, atm.COL_MAIL_STATUS)] == "未開發票，未發信"


def test_mail_only_when_paid_today(monkeypatch):
    # 後台付款時間不是今天（例如補按已付款時後台帶入入帳日）→ 不發信
    ws, state = _setup_reconcile(monkeypatch, status="0", invoice_after_issue="AB12345678",
                                 paid_at="2026-11-05 17:00:00")
    result = atm.process_atm_rows("台北", "2", session=object())
    assert state["mail"] == 0 and result["success"] == 1
    assert ws.cells[(2, atm.COL_MAIL_STATUS)] == "非當日付款，未發信"


# ── 手動 ②＋③：只處理這次剛配對的列 ─────────────────
def test_match_and_reconcile_only_this_runs_matched_rows(monkeypatch):
    b = "2026/11/07 08:14:10"
    sheet = [
        _row(),
        _row(B=b, E="4800", J="LC00219001", K="甲", L="4800", T="已配對"),   # 以前配對、還沒 ③
        _row(B=b, E="4800", J="LC00219002", K="乙", L="4800", T="已配對"),   # 這次配對
        _row(B=b, E="2400", J="LC00219003", K="丙", L="2400", T="需確認"),   # 這次配對但需確認
    ]
    ws = type("W", (), {"get_all_values": lambda self: sheet})()
    calls = {}
    monkeypatch.setattr(atm, "auto_match_bank_rows", lambda **kw: calls.setdefault("match", kw) and {"matched_rows": [3, 4]})
    monkeypatch.setattr(atm, "get_atm_worksheet", lambda region: ws)

    def fake_process(**kw):
        calls["process"] = kw
        return {"success": 1}

    monkeypatch.setattr(atm, "process_atm_rows", fake_process)
    item = atm.match_and_reconcile("台北", session=object(), row_spec="")
    assert item["reconcile_rows"] == [3]
    assert calls["process"]["row_spec"] == "3"
    item = atm.match_and_reconcile("台北", session=object(), only_matched_rows=False)
    assert item["reconcile_rows"] == [2, 3]


# ── 行事曆 ───────────────────────────────────────────
def test_calendar_events_for_completed_and_missing_invoice():
    from shared import atm_match_reconcile_schedule as job

    done = {"region": "台北", "row": 5, "order_no": "LC1", "name": "甲", "amount": 4800,
            "invoice_no": "AB1", "already_paid": False, "mail_sent": True}
    miss = dict(done, order_no="LC2", invoice_no="", mail_sent=False, reason="後台尚未回覆發票號碼")
    result = {"台北": {"reconcile": {"completed": [done, miss], "no_invoice": [miss]}},
              "台中": {"reconcile": {}}}
    now = datetime(2026, 11, 6, 8, 12, tzinfo=TZ)
    events = job.build_calendar_events(result, now)
    assert events[0]["summary"].startswith("【ATM對帳】今日完成 2 筆")
    assert events[0]["start"] == now and events[0]["reminder_minutes"] == []
    assert "LC1" in events[0]["description"] and "已發確認信" in events[0]["description"]
    assert events[1]["summary"].startswith("【ATM對帳】未開立發票 1 筆")
    assert events[1]["reminder_minutes"] == [20, 10] and "LC2" in events[1]["description"]
    assert job.build_calendar_events({"台北": {"reconcile": {}}}, now) == []


# ── G 公式／下拉選單 ─────────────────────────────────
class FakeSpreadsheet:
    def __init__(self, validation_rows):
        self.validation_rows = validation_rows  # {col: {row,...}}
        self.requests = []

    def fetch_sheet_metadata(self, params=None):
        rows = []
        for r in range(1, 20):
            rows.append({"values": [
                {"dataValidation": {"condition": {}}} if r in self.validation_rows.get(c, set()) else {}
                for c in range(9, 16)
            ]})
        return {"sheets": [{"data": [{"startRow": 0, "startColumn": 8, "rowData": rows}]}]}

    def batch_update(self, body):
        self.requests.extend(body["requests"])


class FakeWorksheet:
    id = 42
    title = "ATM"

    def __init__(self, g_formulas, validation_rows):
        self.g = g_formulas
        self.spreadsheet = FakeSpreadsheet(validation_rows)
        self.updates = []

    month_values = {}

    def get(self, a1, value_render_option=None):
        if a1.startswith("I"):
            n = max(len(self.g), max(self.month_values, default=0))
            return [[self.month_values[r]] if r in self.month_values else [] for r in range(1, n + 1)]
        return [[v] if v else [] for v in self.g]

    def update(self, a1, values, value_input_option=None):
        self.updates.append((a1, values))

    def batch_update(self, updates, value_input_option=None):
        self.value_updates = getattr(self, "value_updates", []) + list(updates)


def _copies(ws, paste_type):
    return [(c["copyPaste"]["source"]["startRowIndex"] + 1, c["copyPaste"]["destination"]["startRowIndex"] + 1,
             c["copyPaste"]["destination"]["startColumnIndex"] + 1, c["copyPaste"]["destination"]["endColumnIndex"])
            for c in ws.spreadsheet.requests if "copyPaste" in c and c["copyPaste"]["pasteType"] == paste_type]


def test_month_text():
    assert atm._month_text(2026.11) == "2026.11"
    assert atm._month_text(2026.1) == "2026.10"
    assert atm._month_text(46327) == "2026.11"      # 日期序號 2026-11-01
    assert atm._month_text("2026.09") == "2026.09"


def _repeat_rows(ws):
    return [r["repeatCell"]["range"]["startRowIndex"] + 1 for r in ws.spreadsheet.requests if "repeatCell" in r]


def test_ensure_format_uses_single_template_row_not_chain():
    # 第 3 列 I 有下拉但 N/O 沒有；第 5 列 I/N/O 都有 → 範本＝第 5 列（不是「上方最近一列」）
    formula = '=I2&"-"&N2'
    ws = FakeWorksheet([""] + [formula] * 9 + ["", ""], {9: {2, 3, 5}, 14: {2, 5}, 15: {2, 5}})
    ws.month_values = {11: 2026.11, 12: "2026.11"}
    result = atm.ensure_candidate_row_format(ws, [3, 11, 12])
    assert _copies(ws, "PASTE_FORMAT") == [(5, 3, 7, 15), (5, 11, 7, 15), (5, 12, 7, 15)]
    assert _copies(ws, "PASTE_FORMULA") == [(5, 11, 7, 7), (5, 12, 7, 7)]
    assert _repeat_rows(ws) == [3, 11, 12]                          # I 欄固定文字格式
    assert ws.value_updates == [{"range": "I11", "values": [["2026.11"]]}]   # 數字改回文字
    assert result["month_fixed"] == 1 and result["g_filled"] == 2


def test_ensure_format_template_below_and_fallback_formula():
    ws = FakeWorksheet(["", "", "", "", '=I5&"-"'], {9: {5}, 14: {5}, 15: {5}})
    atm.ensure_candidate_row_format(ws, [2, 3])
    assert _copies(ws, "PASTE_FORMAT") == [(5, 2, 7, 15), (5, 3, 7, 15)]
    ws = FakeWorksheet(["", "", "已有值"], {})
    result = atm.ensure_candidate_row_format(ws, [2, 3])
    assert result["g_filled"] == 1 and result["format_copied"] == 0
    assert ws.updates == [("G2", [['=I2&"-"&N2&"-"&O2&","&J2&","&K2']])]


# ── 整理現有列（截圖那種 G 空白、I 沒下拉、N/O 空白）────────
def test_normalize_atm_rows_fills_no_and_formats(monkeypatch):
    from memo_system import change_order

    rows = [
        _row(A="日期"),
        _row(G="=…", I="2026.09", J="LC002148593", K="謝易辰", L="200", N="清潔", O="車馬費"),   # 已完整
        _row(I="2026.11", J="LC00219852", K="宋家駿", L="4,800"),
        _row(I="2026.11", J="LC00218376", K="曾璧霞", L="400"),      # 清潔異動收款 → 異動費
        _row(I="2026.11", J="", K="吳珍嫻", L="2,000"),               # 沒訂單 2000 → 新訓費
        _row(I="2026.11", J="", K="某人", L="900"),                   # 沒訂單其他 → 只填清潔
        _row(),
    ]
    writes = []
    ws = type("W", (), {"get_all_values": lambda self: rows,
                        "batch_update": lambda self, u, value_input_option=None: writes.extend(u)})()
    cws = type("C", (), {"get_all_values": lambda self: [
        [""] * 14,
        ["清潔", "待收款", "異動服務收款", "", "", "", "LC00218376", "曾璧霞", "", "加時 1 小時", "", "", "", "400"],
    ]})()
    monkeypatch.setattr(change_order, "get_worksheet", lambda region, tab_name="清潔異動": cws)
    formatted = []
    monkeypatch.setattr(atm, "ensure_candidate_row_format",
                        lambda w, r, log=None: formatted.extend(r) or {"g_filled": 4, "dropdown_copied": 4, "format_copied": 5})
    result = atm.normalize_atm_rows("台北", ws=ws)
    assert {w["range"]: w["values"][0] for w in writes} == {
        "N3:O3": ["清潔", "服務費用"],
        "N4:O4": ["清潔", "異動費"],
        "N5:O5": ["清潔", "新訓費"],
        "N6:O6": ["清潔", ""],
    }
    assert formatted == [2, 3, 4, 5, 6] and result["no_filled"] == 4


# ── 雲端入口 ─────────────────────────────────────────
def test_run_prints_counts_only(monkeypatch, capsys):
    from shared import atm_match_reconcile_schedule as job
    from memo_system import memo

    def fake():
        print("✅ 第5列：末碼+金額 → LC00219084 許文菁 $4800")
        return {"台北": {"match": {"success": 3}, "reconcile": {"success": 2, "failed": 0},
                         "reconcile_rows": [5, 6]},
                "台中": {"match": {}, "reconcile": {}, "reconcile_rows": []}}

    logged = []
    monkeypatch.setattr(atm, "run_scheduled_match_and_reconcile", fake)
    monkeypatch.setattr(job, "_log", lambda status, message: logged.append((status, message)))
    monkeypatch.setattr(job, "write_calendar", lambda result: [])
    assert job.run("prod") == 0
    out = capsys.readouterr().out
    assert "許文菁" not in out and "LC00219084" not in out
    assert "台北：② 配對成功 3" in out and "③ 更新系統 2／2 列" in out
    assert memo.BASE_URL.startswith("https://backend.lemonclean.com.tw")


def test_run_reports_partial_results_on_failure(monkeypatch, capsys):
    from shared import atm_match_reconcile_schedule as job

    def boom():
        exc = RuntimeError("台中：登入失敗")
        exc.results = {"台北": {"match": {"success": 1}, "reconcile": {}, "reconcile_rows": []}}
        raise exc

    monkeypatch.setattr(atm, "run_scheduled_match_and_reconcile", boom)
    monkeypatch.setattr(job, "_log", lambda *a: None)
    monkeypatch.setattr(job, "write_calendar", lambda result: [])
    assert job.run("prod") == 1
    out = capsys.readouterr().out
    assert "台中：登入失敗" in out and "台北：② 配對成功 1" in out




class _FakeEvents:
    def __init__(self, fail_ids=()):
        self.fail_ids = set(fail_ids)
        self.inserted = []

    def list(self, **kw):
        return type("R", (), {"execute": lambda s: {"items": []}})()

    def delete(self, **kw):
        return type("R", (), {"execute": lambda s: None})()

    def insert(self, calendarId, body, sendUpdates):
        if calendarId in self.fail_ids:
            raise PermissionError("403")
        self.inserted.append((calendarId, body["summary"]))
        return type("R", (), {"execute": lambda s: {}})()


def test_write_calendar_falls_back_to_lemonclean(monkeypatch):
    from shared import atm_match_reconcile_schedule as job

    monkeypatch.delenv("ATM_CALENDAR_ID", raising=False)
    events = _FakeEvents(fail_ids={"jenny@hers.com.tw"})
    service = type("S", (), {"events": lambda s: events})()
    done = {"region": "台北", "row": 5, "order_no": "LC1", "name": "甲", "amount": 4800}
    msgs = job.write_calendar({"台北": {"reconcile": {"completed": [done], "no_invoice": []}}},
                              now=datetime(2026, 11, 6, 8, 12, tzinfo=TZ), service_factory=lambda: service)
    assert events.inserted == [("jenny@lemonclean.com.tw", "【ATM對帳】今日完成 1 筆（11/06）")]
    assert msgs == ["已記入行事曆 jenny@lemonclean.com.tw：【ATM對帳】今日完成"]


def test_preview_lists_rows_for_confirmation(monkeypatch):
    sheet = [
        _row(A="日期"),
        _row(A="2026/11/06", B="2026/11/06 16:39:40", C="ＣＤ轉收", E="4800", F="檸檬家事"),
        _row(A="2026/11/06", B="2026/11/06 14:02:46", E="4800", J="LC00219865", K="蘇慧芬"),
    ]
    ws = type("W", (), {"get_all_values": lambda self: sheet})()
    monkeypatch.setattr(atm, "get_atm_worksheet", lambda region: ws)
    assert atm.preview_recent_unmatched_bank_rows("台北", today=date(2026, 11, 7)) == [{
        "列號": 2, "日期": "2026/11/06", "入帳時間": "2026/11/06 16:39:40",
        "摘要": "ＣＤ轉收", "收入": "4800", "備註": "檸檬家事",
    }]


# ── 公司匯款：F 欄像公司名稱 → 比對訂單發票抬頭 ─────────
@pytest.mark.parametrize("note,title,expected", [
    ("檸檬家事", "", False),
    ("康健診所", "康健診所", True),
    ("宏達國際電子股份", "宏達國際電子股份有限公司", True),     # 銀行備註截斷
    ("宏達國際", "宏達國際電子股份有限公司", True),
    ("宏達國際", "台積電股份有限公司", False),
    ("ＡＢＣ科技有限公司", "ABC科技有限公司", True),           # 全形半形
])
def test_company_name_matches(note, title, expected):
    assert atm.looks_like_company(note) is (note != "檸檬家事")
    assert atm.company_name_matches(note, title) is expected


def test_auto_match_company_transfer_uses_invoice_title(monkeypatch):
    rows = [
        _row(A="日期"),
        _row(A="2026/11/06", B="2026/11/06 10:00:00", C="跨行轉入", E="4,800", F="宏達國際電子股份"),
        _row(),
        _row(I="2026.11", J="LC00219101", K="王小明", L="4800"),
        _row(I="2026.11", J="LC00219102", K="陳大華", L="4800"),
    ]
    titles = {"LC00219101": {"company_title": "台積電股份有限公司"},
              "LC00219102": {"company_title": "宏達國際電子股份有限公司"}}
    monkeypatch.setattr(atm, "find_purchase_by_order_no", lambda session, no: titles.get(no))
    ws = _MatchWS(rows)
    monkeypatch.setattr(atm, "get_atm_worksheet", lambda region: ws)
    for name in ("_clear_data_validation", "_copy_data_validation", "ensure_candidate_row_format", "normalize_atm_rows"):
        monkeypatch.setattr(atm, name, lambda *a, **k: None)
    result = atm.auto_match_bank_rows("台北", today=date(2026, 11, 7), session=object())
    assert ws.writes["H2:O2"][2] == "LC00219102"
    assert ws.writes[(2, atm.COL_RECON_STATUS)] == "已配對"
    # 沒有 session（無法查抬頭）→ 不配對，留人工
    ws2 = _MatchWS([list(r) for r in rows])
    monkeypatch.setattr(atm, "get_atm_worksheet", lambda region: ws2)
    atm.auto_match_bank_rows("台北", today=date(2026, 11, 7))
    assert "H2:O2" not in ws2.writes


# ── 異動費配對後回填清潔異動已收款 ─────────────────────
class _ChangeWS:
    def __init__(self, rows):
        self.rows = rows
        self.batches = []

    def get_all_values(self):
        return self.rows

    def batch_update(self, updates, value_input_option=None):
        self.batches.append({u["range"]: u["values"][0][0] for u in updates})


def _change_row(**cols):
    row = [""] * 30
    for letter, value in cols.items():
        row[ord(letter) - 65] = value
    return row


def test_mark_change_order_collected(monkeypatch):
    from memo_system import change_order

    cws = _ChangeWS([
        _change_row(A="服務"),
        _change_row(A="清潔", B="待收款", C="異動服務收款", G="LC00219200", H="林小姐", N="600"),
        _change_row(A="清潔", B="待收款", C="異動服務收款", G="LC00219200", H="林小姐", N="1200", R="儲值金"),
        _change_row(A="清潔", B="已收款", C="異動服務收款", G="LC00219300", N="700"),
    ])
    monkeypatch.setattr(change_order, "get_worksheet", lambda region, tab_name="清潔異動": cws)
    msg = atm.mark_change_order_collected("台北", "LC00219200", 1200, "2026/11/06 14:02:46")
    assert msg == "已回填清潔異動第3列為已收款"
    assert cws.batches[-1] == {"B3": "已收款", "M3": "2026/11/06 14:02:46"}   # R 已有值不覆蓋
    atm.mark_change_order_collected("台北", "LC00219200", 600, "2026/11/06 10:00:00")
    assert cws.batches[-1] == {"B2": "已收款", "M2": "2026/11/06 10:00:00", "R2": "ATM"}
    # 清潔異動回填後台時只取日期
    assert change_order._normalize_date_value("2026/11/06 14:02:46") == "2026-11-06"
    assert atm.mark_change_order_collected("台北", "LC00219300", 700, None) == "清潔異動第4列已是已收款"
    assert "找不到" in atm.mark_change_order_collected("台北", "LC00219999", 700, None)


def test_auto_match_change_fee_backfills_change_order(monkeypatch):
    rows = [
        _row(A="日期"),
        _row(A="2026/11/06", B="2026/11/06 10:00:00", C="ＣＤ轉收", E="1,200", F="林小姐加時"),
        _row(A="2026/11/06", B="2026/11/06 11:00:00", C="ＣＤ轉收", E="4,800", F="王蘭香"),
        _row(),
        _row(I="2026.11", J="LC00219200", K="林小姐", L="1200", N="清潔", O="異動費"),
        _row(I="2026.11", J="LC00219736", K="王蘭香", L="4800", N="清潔", O="服務費用"),
    ]
    calls = []
    monkeypatch.setattr(atm, "mark_change_order_collected",
                        lambda region, no, amount, day: calls.append((no, amount, day)) or "已回填清潔異動第3列為已收款")
    result, ws = _run_match(monkeypatch, rows)
    assert calls == [("LC00219200", 1200, "2026/11/06 10:00:00")]   # B 欄日期時間；服務費用不回填
    assert result["change_order_collected"] == ["第2列 LC00219200：已回填清潔異動第3列為已收款"]
    # ③ 只會處理服務費用那列
    sheet = [list(r) for r in rows]
    for a1, vals in ws.writes.items():
        if isinstance(a1, str) and a1.startswith("H"):
            r = int(a1.split(":")[0][1:])
            sheet[r - 1][7:15] = vals
        elif isinstance(a1, tuple):
            sheet[a1[0] - 1][a1[1] - 1] = vals
    assert atm.rows_ready_for_reconcile(sheet) == [3]


# ── 需人工處理清單 ───────────────────────────────────
def test_review_list_covers_manual_cases(monkeypatch):
    rows = [
        _row(A="日期"),
        _row(A="2026/11/06", B="2026/11/06 13:00:00", D="3,000", F="不明轉出"),           # 2 支出找不到退款
        _row(A="2026/11/06", B="2026/11/06 17:30:00", E="2,400", F="家事清潔"),           # 3 未配對
        _row(A="2026/11/06", B="2026/11/06 10:00:00", E="1,200", F="林小姐"),             # 4 異動費，清潔異動找不到
        _row(),
        _row(I="2026.11", J="LC00219200", K="林小姐", L="1200", N="清潔", O="異動費"),
    ]
    monkeypatch.setattr(atm, "mark_change_order_collected", lambda *a: "清潔異動找不到 LC00219200 待收款 $1200")
    result, ws = _run_match(monkeypatch, rows)
    kinds = {(r["列號"], r["類型"]) for r in result["review"]}
    assert kinds == {(2, "支出／退款待確認"), (3, "未配對"), (4, "清潔異動未回填")}
    assert next(r for r in result["review"] if r["列號"] == 4)["訂單"] == "LC00219200"


def test_schedule_calendar_includes_review():
    from shared import atm_match_reconcile_schedule as job

    result = {"台北": {"match": {"review": [{"列號": 3, "類型": "需確認", "訂單": "LC1", "姓名": "甲", "金額": 4800, "說明": "已預填"}]},
                       "reconcile": {}}}
    events = job.build_calendar_events(result, datetime(2026, 11, 7, 8, 12, tzinfo=TZ))
    assert events[-1]["summary"] == "【ATM對帳】需人工處理 1 列"
    assert "台北 第3列【需確認】LC1 甲 $4800" in events[-1]["description"]
