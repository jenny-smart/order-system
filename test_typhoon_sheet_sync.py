import re
import unittest
from unittest.mock import patch

import function.typhoon_sheet_sync as tss
from test_typhoon_transfer import _block


class _Worksheet:
    def __init__(self, values):
        self.values = [list(r) for r in values]
        self.batches = []
        self.updates = []
        self.appended = []

    def get_all_values(self):
        return [list(r) for r in self.values]

    title = "颱風"
    url = "https://docs.google.com/spreadsheets/d/abc123/edit#gid=1"
    drop_writes = False

    def batch_update(self, data, value_input_option=None):
        self.batches.append((data, value_input_option))
        if self.drop_writes:
            return
        for item in data:
            m = re.fullmatch(r"([A-Z]+)(\d+)", item["range"])
            col, row = tss.column_index(m.group(1)), int(m.group(2))
            while len(self.values) < row:
                self.values.append([])
            line = self.values[row - 1]
            line.extend([""] * (col + 1 - len(line)))
            line[col] = item["values"][0][0]

    def update(self, range_name=None, values=None):
        self.updates.append((range_name, values))

    def append_row(self, values, value_input_option=None):
        self.appended.append(values)


class _Client:
    def __init__(self, worksheet):
        self.ws = worksheet

    def open_by_key(self, key):
        client = self

        class Book:
            def worksheet(self, title):
                return client.ws
        return Book()


SETTINGS = {
    "spreadsheet_id": "https://docs.google.com/spreadsheets/d/abc123/edit#gid=0", "worksheet": "颱風",
    "order_col": "A", "orig_date_col": "F", "orig_period_col": "G", "orig_staff_col": "",
    "new_date_col": "I", "new_period_col": "J",
    "change_date_col": "L", "change_period_col": "M", "start_row": "2",
}
SHEET = [
    ["訂單編號", "姓名", "", "", "", "原日期", "原時段", "服務時數", "新日期", "新時段", "", "異動日期", "異動時段"],
    # 已改到 11/6 → 待填異動
    ["LC00215208", "王璿瑋", "", "", "", "2026-10-23", "08:30-12:30", "4", "2027-03-03", "08:30-12:30", "", "", ""],
    # 和新日期相同、異動欄空白 → 未變動
    ["LC00215218", "余葉菁", "", "", "", "2026-10-23", "14:00-18:00", "4", "2027/3/3", "14:00-18:00", "", "", ""],
    # 查不到 → 查詢失敗
    ["LC00217168", "李憶華", "", "", "", "2026-10-23", "09:00-11:00", "2", "2027-03-01", "09:00-11:00", "", "", ""],
    # 又改回新日期、異動欄還有舊值 → 待清除
    ["LC00217286", "陳世湟", "", "", "", "2026-10-23", "14:00-18:00", "4", "2027-03-01", "14:00-18:00", "", "2026/10/25", "14:00-18:00"],
    # 異動欄已是目前日期 → 已填異動（不寫）
    ["LC00216486", "陳沛希", "", "", "", "2026-10-23", "14:00-17:00", "3", "2027-03-02", "14:00-17:00", "", "2026/10/26", "14:00-17:00"],
    ["", "空白列"],
]


class SettingsTests(unittest.TestCase):
    def test_validate_accepts_url_and_rejects_bad_columns(self):
        settings = tss.validate_settings(SETTINGS)
        self.assertEqual(settings["spreadsheet_id"], "abc123")
        self.assertEqual(tss.column_index("AA"), 26)
        with self.assertRaises(ValueError):
            tss.validate_settings({**SETTINGS, "new_date_col": "1"})
        with self.assertRaises(ValueError):
            tss.validate_settings({**SETTINGS, "new_period_col": "I"})
        with self.assertRaises(ValueError):
            tss.validate_settings({**SETTINGS, "change_date_col": "I"})  # 不可寫到新日期欄
        with self.assertRaises(ValueError):
            tss.validate_settings({**SETTINGS, "change_period_col": "F"})  # 不可寫到原日期欄

    def test_save_then_load_per_account(self):
        ws = _Worksheet([tss.SETTINGS_HEADERS])
        client = _Client(ws)
        tss.save_settings("a@x", SETTINGS, client=client)
        ws.values.append(ws.appended[0])
        loaded = tss.load_settings("a@x", client=client)
        self.assertEqual((loaded["spreadsheet_id"], loaded["worksheet"], loaded["new_date_col"]), ("abc123", "颱風", "I"))
        self.assertEqual(tss.load_settings("b@x", client=client), tss.DEFAULT_SETTINGS)
        tss.save_settings("a@x", {**SETTINGS, "worksheet": "新"}, client=client)
        self.assertEqual(ws.updates[0][0], "A2")


class CompareAndApplyTests(unittest.TestCase):
    def setUp(self):
        self.ws = _Worksheet(SHEET)
        self.client = _Client(self.ws)
        current = {
            "LC00215208": ("2026-11-06", "14:00 - 18:00"),
            "LC00215218": ("2027-03-03", "14:00 - 18:00"),
            "LC00217286": ("2027-03-01", "14:00 - 18:00"),
            "LC00216486": ("2026-10-26", "14:00 - 17:00"),
        }

        def fetch(session, order_no):
            if order_no not in current:
                raise Exception(f"查無訂單：{order_no}")
            return _block(order_no, *current[order_no])

        self.patches = [
            patch.object(tss.tt, "_login", lambda *a: (None, "")),
            patch.object(tss.qo, "_fetch_purchase_block_for_order_no", fetch),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def test_compare_statuses(self):
        rows = tss.compare_sheet_orders("dev", "a", "b", SETTINGS, client=self.client)
        statuses = [(r["row"], r["status"]) for r in rows]
        self.assertEqual(statuses[0], (2, "待填異動"))
        self.assertEqual(statuses[1], (3, "未變動"))
        self.assertTrue(statuses[2][1].startswith("查詢失敗"))
        self.assertEqual(statuses[3:], [(5, "待清除異動欄"), (6, "已填異動")])
        self.assertEqual(self.ws.batches, [])

    def test_apply_fills_and_clears_only_change_columns(self):
        rows = tss.compare_sheet_orders("dev", "a", "b", SETTINGS, client=self.client)
        results = tss.apply_sheet_updates(SETTINGS, rows, client=self.client)
        self.assertEqual([(r["row"], r["status"]) for r in results], [(2, "已填異動"), (5, "已清除異動欄")])
        data, option = self.ws.batches[0]
        self.assertEqual(data, [
            {"range": "L2", "values": [["2026-11-06"]]}, {"range": "M2", "values": [["14:00-18:00"]]},
            {"range": "L5", "values": [[""]]}, {"range": "M5", "values": [[""]]},
        ])
        self.assertEqual(option, "USER_ENTERED")
        self.assertFalse(any(u["range"][0] in "IJ" for u in data))

    def test_apply_skips_change_cells_edited_after_compare(self):
        rows = tss.compare_sheet_orders("dev", "a", "b", SETTINGS, client=self.client)
        self.ws.values[1][11] = "2026-10-30"  # 客服比對後手動填了異動日期
        results = tss.apply_sheet_updates(SETTINGS, rows, client=self.client)
        self.assertEqual(results[0]["status"], "已跳過：比對後異動欄已被修改")
        self.assertEqual([u["range"] for u in self.ws.batches[0][0]], ["L5", "M5"])

    def test_old_settings_row_without_change_columns_still_loads(self):
        old_headers = ["後台帳號", "試算表ID", "工作表名稱", "訂單編號欄", "原日期欄", "原時段欄",
                       "新日期欄", "新時段欄", "起始列", "更新時間"]
        ws = _Worksheet([old_headers, ["a@x", "abc", "颱風", "A", "F", "G", "I", "J", "2", "2026-10-24 09:00"]])
        loaded = tss.load_settings("a@x", client=_Client(ws))
        self.assertEqual((loaded["start_row"], loaded["change_date_col"], loaded["change_period_col"]), ("2", "O", "P"))
        self.assertEqual(loaded["orig_staff_col"], "")  # 舊設定沒有原專員欄：留空避免和新日期欄 I 撞欄
        tss.save_settings("a@x", loaded, client=_Client(ws))
        self.assertEqual(ws.updates[0][1][0], tss.SETTINGS_HEADERS)

class VerifyTests(CompareAndApplyTests):
    def test_written_values_are_read_back(self):
        rows = tss.compare_sheet_orders("dev", "a", "b", SETTINGS, client=self.client)
        results = tss.apply_sheet_updates(SETTINGS, rows, client=self.client)
        self.assertEqual([r["status"] for r in results], ["已填異動", "已清除異動欄"])
        self.assertEqual(self.ws.values[1][11:13], ["2026-11-06", "14:00-18:00"])
        self.assertEqual(results[0]["written_to"], "颱風")

    def test_write_that_does_not_land_is_reported(self):
        self.ws.drop_writes = True
        rows = tss.compare_sheet_orders("dev", "a", "b", SETTINGS, client=self.client)
        results = tss.apply_sheet_updates(SETTINGS, rows, client=self.client)
        self.assertTrue(results[0]["status"].startswith("寫入後讀回不符"))


RESTORE_SETTINGS = {
    "spreadsheet_id": "abc123", "worksheet": "颱風", "order_col": "A", "orig_date_col": "F",
    "orig_period_col": "G", "orig_staff_col": "I", "new_date_col": "J", "new_period_col": "K",
    "change_date_col": "O", "change_period_col": "P", "start_row": "2",
}
RESTORE_SHEET = [
    ["訂單編號", "姓名", "", "", "", "原日期", "原時段", "服務時數", "原專員", "新日期", "新時段"],
    ["LC1", "甲", "", "", "", "2026-10-23", "09:00-12:00", "3", "宋芳儀、陳佩琪", "2027-03-01", "09:00-12:00"],
    ["LC2", "乙", "", "", "", "2026-10-23", "14:00-17:00", "3", "吳奐", "2027-03-01", "14:00-17:00"],
    ["LC3", "丙", "", "", "", "2026-10-23", "08:30-12:30", "4", "張靖、王宣婷", "2027-03-02", "08:30-12:30"],
    ["LC4", "丁", "", "", "", "2026-10-23", "09:00-11:00", "2", "", "2027-03-02", "09:00-11:00"],
]


class _Resp:
    status_code = 200


class _PostSession:
    def __init__(self):
        self.posts = []

    def post(self, url, params=None, data=None, **kwargs):
        self.posts.append((url, params, data))
        return _Resp()


class RestoreTests(unittest.TestCase):
    def setUp(self):
        self.ws = _Worksheet(RESTORE_SHEET)
        self.client = _Client(self.ws)
        # 後台目前狀態：LC1 在 3/1；LC2 已回原日期但專員不同；LC3 已在原班表
        self.state = {
            "LC1": ["2027-03-01", "09:00-12:00", ["檸檬人1", "檸檬人2"]],
            "LC2": ["2026-10-23", "14:00-17:00", ["李佩蓉"]],
            "LC3": ["2026-10-23", "08:30-12:30", ["張靖", "王宣婷"]],
        }
        self.session = _PostSession()

        def order_now(session, order_no):
            d, p, staff = self.state[order_no]
            return d, p, list(staff), ""

        self.patches = [
            patch.object(tss.tt, "_login", lambda *a: (self.session, "https://x")),
            patch.object(tss, "_order_now", order_now),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def test_plan_statuses(self):
        rows = tss.plan_restore("dev", "a", "b", RESTORE_SETTINGS, client=self.client)
        self.assertEqual([(r["order_no"], r["status"]) for r in rows], [
            ("LC1", "待返回"), ("LC2", "待配回原專員"), ("LC3", "已在原班表"), ("LC4", "缺原專員"),
        ])
        self.assertEqual(rows[0]["orig_staff"], ["宋芳儀", "陳佩琪"])

    def test_plan_requires_staff_column(self):
        with self.assertRaises(ValueError):
            tss.plan_restore("dev", "a", "b", {**RESTORE_SETTINGS, "orig_staff_col": ""}, client=self.client)

    def test_execute_moves_back_then_assigns_original_staff(self):
        rows = tss.plan_restore("dev", "a", "b", RESTORE_SETTINGS, client=self.client)
        calls = []

        def change_date(session, base_url, order_no, day, period, phone=""):
            calls.append(("date", order_no, day, period))
            self.state[order_no][0:2] = [day, period]
            return True, "HTTP 200"

        def assign(session, base_url, order_no, day, period, wanted, reserved=()):
            calls.append(("staff", order_no, day, tuple(wanted)))
            self.state[order_no][2] = list(wanted)
            return {"all_original": True, "missing": [], "message": ""}

        with patch.object(tss.tt, "_change_date_options",
                          lambda *a, **k: {"2026-10-23": {"09:00-12:00": [], "14:00-17:00": []}}), \
                patch.object(tss.qo, "_update_order_service_date", change_date), \
                patch.object(tss, "_assign_original_staff", assign):
            results = tss.execute_restore("dev", "a", "b", rows)
        self.assertEqual(calls, [
            ("date", "LC1", "2026-10-23", "09:00-12:00"),
            ("staff", "LC1", "2026-10-23", ("宋芳儀", "陳佩琪")),
            ("staff", "LC2", "2026-10-23", ("吳奐",)),
        ])
        self.assertEqual([r["status"] for r in results], ["已返回原班表", "已返回原班表"])
        lines = tss.restore_tsv(results).split("\n")
        self.assertEqual(lines[0].split("\t"), tss.RESTORE_COPY_HEADERS)
        cells = lines[1].split("\t")
        self.assertEqual(cells[:9], ["LC1", "", "2026-10-23", "09:00-12:00", "宋芳儀、陳佩琪",
                                     "2026-10-23", "09:00-12:00", "宋芳儀、陳佩琪", "已返回原班表"])
        self.assertRegex(cells[9], r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$")

    def test_final_check_catches_order_changed_after_it_finished(self):
        rows = tss.plan_restore("dev", "a", "b", RESTORE_SETTINGS, client=self.client)

        def change_date(session, base_url, order_no, day, period, phone=""):
            self.state[order_no][0:2] = [day, period]
            return True, ""

        def assign(session, base_url, order_no, day, period, wanted, reserved=()):
            self.state[order_no][2] = list(wanted)
            if order_no == "LC2":
                self.state["LC1"][2] = ["宋芳儀", "李佩蓉"]  # 處理 LC2 時 LC1 被動到
            return {"all_original": True, "missing": [], "message": ""}

        with patch.object(tss.tt, "_change_date_options",
                          lambda *a, **k: {"2026-10-23": {"09:00-12:00": [], "14:00-17:00": []}}), \
                patch.object(tss.qo, "_update_order_service_date", change_date), \
                patch.object(tss, "_assign_original_staff", assign):
            results = tss.execute_restore("dev", "a", "b", rows)
        self.assertTrue(results[0]["status"].startswith("最後核對不一致"), results[0]["status"])
        self.assertNotIn("restored_at", results[0])
        self.assertEqual(tss.check_mark(results[0]), "❌ 不一致")
        self.assertEqual(results[1]["status"], "已返回原班表")
        self.assertEqual(tss.check_mark(results[1]), "✅ 一致")

    def test_date_not_selectable_is_retried_after_others(self):
        rows = tss.plan_restore("dev", "a", "b", RESTORE_SETTINGS, client=self.client)
        calls = {"n": 0}

        def options(*a, **k):
            calls["n"] += 1
            # 第一次查 LC1 時選不到（被其他單占著），之後就選得到
            return {} if calls["n"] == 1 else {"2026-10-23": {"09:00-12:00": [], "14:00-17:00": []}}

        def change_date(session, base_url, order_no, day, period, phone=""):
            self.state[order_no][0:2] = [day, period]
            return True, ""

        def assign(session, base_url, order_no, day, period, wanted, reserved=()):
            self.state[order_no][2] = list(wanted)
            return {"all_original": True, "missing": [], "message": ""}

        with patch.object(tss.tt, "_change_date_options", options), \
                patch.object(tss.qo, "_update_order_service_date", change_date), \
                patch.object(tss, "_assign_original_staff", assign):
            results = tss.execute_restore("dev", "a", "b", rows)
        self.assertEqual([(r["order_no"], r["status"]) for r in results],
                         [("LC1", "已返回原班表"), ("LC2", "已返回原班表")])

    def test_execute_stops_when_original_date_not_selectable(self):
        rows = tss.plan_restore("dev", "a", "b", RESTORE_SETTINGS, client=self.client)
        lemon_calls = []
        with patch.object(tss.tt, "_change_date_options", lambda *a, **k: {}), \
                patch.object(tss.qo, "_update_order_service_date", lambda *a, **k: self.fail("不應送出")), \
                patch.object(tss.qo, "ensure_lemon_cleaner_shifts",
                             lambda *a: lemon_calls.append(a[2:]) or {"assigned": []}), \
                patch.object(tss, "_assign_original_staff", lambda *a, **k: {"all_original": True, "missing": [], "message": ""}):
            results = tss.execute_restore("dev", "a", "b", rows[:1])
        self.assertTrue(results[0]["status"].startswith("返回失敗：修改日期選不到"))
        self.assertEqual(len(lemon_calls), 1)  # 試過先勾檸檬人，仍選不到才停

    def test_lemon_shifts_opened_when_original_slot_full(self):
        rows = tss.plan_restore("dev", "a", "b", RESTORE_SETTINGS, client=self.client)
        opened = []

        def options(*a, **k):
            # 原日期時段要先替檸檬人勾班才選得到
            return {"2026-10-23": {"09:00-12:00": [], "14:00-17:00": []}} if opened else {}

        def add_lemon(session, base_url, day, period, count):
            opened.append((day, period, count))
            return {"assigned": [f"檸檬人{i}" for i in range(1, int(count) + 1)]}

        def change_date(session, base_url, order_no, day, period, phone=""):
            self.state[order_no][0:2] = [day, period]
            return True, ""

        def assign(session, base_url, order_no, day, period, wanted, reserved=()):
            self.state[order_no][2] = list(wanted)
            return {"all_original": True, "missing": [], "message": ""}

        with patch.object(tss.tt, "_change_date_options", options), \
                patch.object(tss.qo, "ensure_lemon_cleaner_shifts", add_lemon), \
                patch.object(tss.qo, "_update_order_service_date", change_date), \
                patch.object(tss, "_assign_original_staff", assign):
            results = tss.execute_restore("dev", "a", "b", rows[:1])
        self.assertTrue(results[0]["status"].startswith("已返回原班表"), results[0]["status"])
        self.assertEqual(opened, [(rows[0]["orig_date"], rows[0]["orig_period"], str(len(rows[0]["orig_staff"])))])
        self.assertIn("檸檬人1", results[0]["status"])
        self.assertEqual(tss.check_mark(results[0]), "✅ 一致")

    def test_assign_original_staff_picks_names_on_schedule_edit(self):
        slots = [{"宋芳儀\n (2)": "11", "李佩蓉 (4)": "12"}, {"陳佩琪 (3)": "21", "宋芳儀 (2)": "11"}]
        with patch.object(tss.qo, "_fetch_order_edit_id", lambda s, no: "999"), \
                patch.object(tss.qo, "_get_schedule_edit_info", lambda *a: ("tok", ["o1", "o2"], slots)), \
                patch.object(tss.qo, "_get_occupied_staff_for_period", lambda *a, **k: set()):
            out = tss._assign_original_staff(self.session, "https://x", "LC1", "2026-10-23", "09:00-12:00",
                                             ["宋芳儀", "陳佩琪"])
        self.assertTrue(out["all_original"], out)
        data = self.session.posts[0][2]
        self.assertIn(("shiftId[0]", "11"), data)
        self.assertIn(("shiftId[1]", "21"), data)

    def test_busy_original_gets_non_reserved_fallback(self):
        # 吳奐被別張單占用；目前位置上的人（張志豪）是其他待返回訂單的原專員，要換掉
        slots = [{"吳奐 (1)": "31", "張志豪 (2)": "32", "李佩蓉 (4)": "33"}]
        with patch.object(tss.qo, "_fetch_order_edit_id", lambda s, no: "999"), \
                patch.object(tss.qo, "_get_schedule_edit_info", lambda *a: ("tok", ["32"], slots)), \
                patch.object(tss.qo, "_get_occupied_staff_for_period", lambda *a, **k: {"吳奐"}):
            out = tss._assign_original_staff(self.session, "https://x", "LC2", "2026-10-23", "14:00-17:00",
                                             ["吳奐"], reserved={"張志豪"})
        self.assertFalse(out["all_original"])
        self.assertEqual(out["missing"], ["吳奐"])
        self.assertIn("已被同時段其他訂單安排", out["message"])
        self.assertIn(("shiftId[0]", "33"), self.session.posts[0][2])  # 改配李佩蓉，不占張志豪


class CascadeSimulationTests(unittest.TestCase):
    """模擬後台：改回原日期時後台會自動配人，可能配到其他待返回訂單的原專員。"""

    ROSTER = {"甲1": "1", "甲2": "2", "乙1": "3", "乙2": "4", "空1": "5", "空2": "6", "外1": "7"}

    def setUp(self):
        self.orders = {
            # A 先處理：改回時後台自動配到 B 的原專員乙1、乙2
            "LCA": {"date": "2027-04-12", "period": "09:00-12:00", "staff": ["檸1", "檸2"], "auto": ["乙1", "乙2"]},
            "LCB": {"date": "2027-04-12", "period": "09:00-12:00", "staff": ["檸3", "檸4"], "auto": ["空1", "空2"]},
            # 不在這次返回名單的外部訂單，占用 A 的原專員甲2
            "LCX": {"date": "2026-10-29", "period": "09:00-12:00", "staff": ["甲2"], "auto": []},
        }
        self.session = self

    # 假 session.post：依 shiftId 改專員
    def post(self, url, params=None, data=None, **kwargs):
        by_id = {v: k for k, v in self.ROSTER.items()}
        order_no = self._pid_to_no[params["purchase_id"]]
        self.orders[order_no]["staff"] = [by_id[sid] if sid in by_id else self.orders[order_no]["staff"][i]
                                          for i, (k, sid) in enumerate([x for x in data if x[0].startswith("shiftId")])]
        return _Resp()

    def _occupied(self, order_no):
        me = self.orders[order_no]
        return {n for no, o in self.orders.items() if no != order_no and o["date"] == me["date"] for n in o["staff"]}

    def test_failure_does_not_cascade(self):
        self._pid_to_no = {"A": "LCA", "B": "LCB"}
        rows = [
            {"row": 2, "order_no": "LCA", "name": "", "orig_date": "2026-10-29", "orig_period": "09:00-12:00",
             "orig_staff": ["甲1", "甲2"], "now_date": "2027-04-12", "now_period": "09:00-12:00", "now_staff": [], "status": "待返回"},
            {"row": 3, "order_no": "LCB", "name": "", "orig_date": "2026-10-29", "orig_period": "09:00-12:00",
             "orig_staff": ["乙1", "乙2"], "now_date": "2027-04-12", "now_period": "09:00-12:00", "now_staff": [], "status": "待返回"},
        ]

        def order_now(session, no):
            o = self.orders[no]
            return o["date"], o["period"], list(o["staff"]), ""

        def change_date(session, base_url, no, day, period, phone=""):
            o = self.orders[no]
            o["date"], o["period"], o["staff"] = day, period, list(o["auto"])
            return True, ""

        def edit_info(session, base_url, day, pid):
            no = self._pid_to_no[pid]
            current = [self.ROSTER[n] for n in self.orders[no]["staff"]]
            slot = {f"{n} (1)": sid for n, sid in self.ROSTER.items()}
            return "tok", current, [slot for _ in current]

        with patch.object(tss.tt, "_login", lambda *a: (self, "https://x")), \
                patch.object(tss, "_order_now", order_now), \
                patch.object(tss.tt, "_change_date_options", lambda *a, **k: {"2026-10-29": {"09:00-12:00": []}}), \
                patch.object(tss.qo, "_update_order_service_date", change_date), \
                patch.object(tss.qo, "_fetch_order_edit_id", lambda s, no: {"LCA": "A", "LCB": "B"}[no]), \
                patch.object(tss.qo, "_get_schedule_edit_info", edit_info), \
                patch.object(tss.qo, "_get_occupied_staff_for_period",
                             lambda s, b, d, p, exclude_purchase_id=None: self._occupied(self._pid_to_no[exclude_purchase_id])):
            results = tss.execute_restore("dev", "a", "b", rows)
        statuses = {r["order_no"]: r["status"] for r in results}
        # A 的甲2 被外部訂單占用 → A 只能部分配回，但不能占著 B 的原專員
        self.assertTrue(statuses["LCA"].startswith("已改回原日期，專員未全部配回"), statuses["LCA"])
        self.assertNotIn("乙1", self.orders["LCA"]["staff"])
        self.assertNotIn("乙2", self.orders["LCA"]["staff"])
        # B 不受 A 影響，完整返回
        self.assertEqual(statuses["LCB"], "已返回原班表")
        self.assertEqual(sorted(self.orders["LCB"]["staff"]), ["乙1", "乙2"])


class SwapDeadlockTests(unittest.TestCase):
    """兩組人員同時段對調，且沒有空閒人員：要借檸檬人暫時頂替才能各自換回。"""

    def setUp(self):
        self.roster = {"甲": "1", "乙": "2"}
        self.orders = {
            "LCA": {"date": "2026-10-29", "period": "09:00-12:00", "staff": ["乙"]},
            "LCB": {"date": "2026-10-29", "period": "09:00-12:00", "staff": ["甲"]},
        }
        self.pid = {"A": "LCA", "B": "LCB"}
        self.lemon_calls = []

    def post(self, url, params=None, data=None, **kwargs):
        by_id = {v: k for k, v in self.roster.items()}
        order = self.orders[self.pid[params["purchase_id"]]]
        ids = [v for k, v in data if k.startswith("shiftId")]
        order["staff"] = [by_id.get(sid, order["staff"][i]) for i, sid in enumerate(ids)]
        return type("R", (), {"status_code": 200})()

    def test_swapped_staff_are_restored_with_lemon_placeholder(self):
        rows = [
            {"row": 1, "order_no": "LCA", "name": "", "orig_date": "2026-10-29", "orig_period": "09:00-12:00",
             "orig_staff": ["甲"], "now_date": "2026-10-29", "now_period": "09:00-12:00", "now_staff": ["乙"],
             "status": "待配回原專員"},
            {"row": 2, "order_no": "LCB", "name": "", "orig_date": "2026-10-29", "orig_period": "09:00-12:00",
             "orig_staff": ["乙"], "now_date": "2026-10-29", "now_period": "09:00-12:00", "now_staff": ["甲"],
             "status": "待配回原專員"},
        ]

        def order_now(session, no):
            o = self.orders[no]
            return o["date"], o["period"], list(o["staff"]), ""

        def edit_info(session, base_url, day, pid):
            current = [self.roster[n] for n in self.orders[self.pid[pid]]["staff"]]
            slot = {f"{n} (1)": sid for n, sid in self.roster.items()}
            return "tok", current, [slot for _ in current]

        def occupied(session, base_url, day, period, exclude_purchase_id=None):
            me = self.pid[exclude_purchase_id]
            return {n for no, o in self.orders.items() if no != me for n in o["staff"]}

        def add_lemon(session, base_url, day, period, count):
            self.lemon_calls.append((day, period))
            self.roster["檸檬人1"] = "9"
            return {"assigned": ["檸檬人1"]}

        with patch.object(tss.tt, "_login", lambda *a: (self, "https://x")), \
                patch.object(tss, "_order_now", order_now), \
                patch.object(tss.qo, "_fetch_order_edit_id", lambda s, no: {"LCA": "A", "LCB": "B"}[no]), \
                patch.object(tss.qo, "_get_schedule_edit_info", edit_info), \
                patch.object(tss.qo, "_get_occupied_staff_for_period", occupied), \
                patch.object(tss.qo, "ensure_lemon_cleaner_shifts", add_lemon):
            results = tss.execute_restore("dev", "a", "b", rows)
        self.assertEqual(self.orders["LCA"]["staff"], ["甲"])
        self.assertEqual(self.orders["LCB"]["staff"], ["乙"])
        self.assertTrue(all(r["status"].startswith("已返回原班表") for r in results), [r["status"] for r in results])
        self.assertTrue(all(tss.check_mark(r) == "✅ 一致" for r in results))
        self.assertEqual(self.lemon_calls, [("2026-10-29", "09:00-12:00")])
        self.assertIn("檸檬人1 暫時頂替", results[0]["status"])


if __name__ == "__main__":
    unittest.main()
