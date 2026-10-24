import unittest
from unittest.mock import patch

import function.typhoon_transfer as tt


def _block(order_no, date_s, period, name="王小明", phone="0912345678", staff="宋芳儀(2)X陳佩琪(3)", status="已付款"):
    return {
        "order_no": order_no,
        "lines": [
            order_no, name, phone, "台北市大安區復興南路一段1號",
            "2026-10-01 10:00:00", "居家清潔",
            f"{date_s} (五)", period, staff,
            "付款方式：儲值金", f"付款狀態：{status}",
        ],
    }


class ParsingTests(unittest.TestCase):
    def test_parse_date_range(self):
        start, end = tt.parse_date_range("2027/03/01-2027/03/05")
        self.assertEqual((start.isoformat(), end.isoformat()), ("2027-03-01", "2027-03-05"))
        with self.assertRaises(ValueError):
            tt.parse_date_range("2027/03/05-2027/03/01")
        with self.assertRaises(ValueError):
            tt.parse_date_range("2026/10/23")
        start, end = tt.parse_date_range("2026/10/23", allow_single=True)
        self.assertEqual((start.isoformat(), end.isoformat()), ("2026-10-23", "2026-10-23"))

    def test_target_dates_weekdays_only(self):
        # 3/1 為補假但價格算平日，仍要排入
        days = tt.target_dates("2027-02-26", "2027-03-02", "與颱風假相同（平日／週末）", "2026-10-23")
        self.assertEqual(days, ["2027-02-26", "2027-03-01", "2027-03-02"])
        weekend = tt.target_dates("2027-02-26", "2027-03-02", "與颱風假相同（平日／週末）", "2026-10-24")
        self.assertEqual(weekend, ["2027-02-27", "2027-02-28"])

    def test_order_row_skips_cancelled_and_other_dates(self):
        row = tt._order_row_from_block(_block("LC1", "2026-10-23", "08:30 - 12:30"), "2026-10-23")
        self.assertEqual((row["period"], row["person"], row["clean_type_id"]), ("08:30-12:30", 2, "1"))
        self.assertIsNone(tt._order_row_from_block(_block("LC2", "2026-10-23", "08:30 - 12:30", status="取消訂單"), "2026-10-23"))
        self.assertIsNone(tt._order_row_from_block(_block("LC3", "2026-10-24", "08:30 - 12:30"), "2026-10-23"))
        ranged = tt._order_row_from_block(_block("LC4", "2026-10-24", "08:30 - 12:30"), "2026-10-23", "2026-10-24")
        self.assertEqual(ranged["service_date"], "2026-10-24")

    def test_candidate_dates_follow_each_typhoon_day_type(self):
        # 10/23（五）排平日、10/24（六）排週末
        by_day = tt.candidate_dates_by_day(
            ["2026-10-23", "2026-10-24", "2026-10-23"], "2027-02-26", "2027-03-01", "與颱風假相同（平日／週末）",
        )
        self.assertEqual(by_day, {
            "2026-10-23": ["2027-02-26", "2027-03-01"],
            "2026-10-24": ["2027-02-27", "2027-02-28"],
        })

    def test_parse_change_date_page_reads_embedded_list(self):
        html = """
        <select id="date" name="date"><option value="">日期</option></select>
        <script>
            var json = '[{"date":"2027-03-01","section":"09:00-12:00","cleaner":["\\u5b8b\\u54c1"],"week":"\\u4e00"},{"date":"2027-03-01","section":"14:00-17:00","cleaner":[],"week":"\\u4e00"}]';
            section_list = $.parseJSON(json);
        </script>
        """
        options = tt.parse_change_date_page(html)
        self.assertEqual(options, {"2027-03-01": {"09:00-12:00": ["宋品"], "14:00-17:00": []}})

    def test_parse_change_date_page_without_list_fails_closed(self):
        with self.assertRaises(RuntimeError):
            tt.parse_change_date_page('<select name="date"><option value="">日期</option></select>')


class FindOrdersTests(unittest.TestCase):
    def test_paid_search_keeps_backend_top_to_bottom_order(self):
        blocks = [
            _block("LC9", "2026-10-23", "09:00 - 12:00"),
            _block("LC3", "2026-10-23", "08:30 - 12:30"),
            _block("LC5", "2026-10-23", "08:30 - 12:30", status="待付款"),
            _block("LC1", "2026-10-23", "08:30 - 12:30"),
        ]
        calls = []

        class Session:
            def get(self, url, params=None, **kwargs):
                calls.append(params)
                html = '<table><tr><td>LC3</td><td><a href="https://chat.line.biz/Uabc/chat/U3">LINE</a></td></tr></table>'
                return type("R", (), {"status_code": 200, "text": html})()

        with patch.object(tt, "_login", lambda *a: (Session(), "https://x")), \
                patch.object(tt.orders, "extract_order_cards_from_purchase_html", lambda html: blocks):
            rows, _ = tt.find_typhoon_orders("dev", "a", "b", "2026/10/23", "2026/10/24")
        self.assertEqual([r["order_no"] for r in rows], ["LC9", "LC3", "LC1"])
        self.assertEqual([r["line_url"] for r in rows], ["", "https://chat.line.biz/Uabc/chat/U3", ""])
        self.assertEqual(calls[0]["purchase_status"], "1")
        self.assertEqual((calls[0]["clean_date_s"], calls[0]["clean_date_e"]), ("2026-10-23", "2026-10-24"))


class TransferTests(unittest.TestCase):
    def setUp(self):
        self.row = {
            "order_no": "LC1", "period": "08:30-12:30", "phone": "0912345678",
            "name": "王小明", "person": 2, "service_date_before": "2026-10-23",
        }
        self.state = {"date": "2026-10-23", "period": "08:30 - 12:30"}
        self.posted = []

        def update(session, base_url, order_no, day, period, phone=""):
            self.posted.append((day, period))
            self.state.update(date=day, period=period)
            return True, "HTTP 200"

        self.patches = [
            patch.object(tt, "_change_date_options", lambda *a, **k: {
                "2027-03-01": {"09:00-12:00": ["甲"]},
                "2027-03-02": {"08:30-12:30": ["甲", "乙"]},
                "2027-03-03": {"09:00-12:00": ["甲", "乙"]},
            }),
            patch.object(tt.qo, "_update_order_service_date", update),
            patch.object(tt.qo, "_fetch_purchase_block_for_order_no",
                         lambda s, no: _block(no, self.state["date"], self.state["period"])),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def test_moves_to_first_available_date_with_same_period(self):
        result = tt.transfer_one_order(None, "", "dev", self.row, ["2027-02-27", "2027-03-01", "2027-03-02"])
        self.assertTrue(result["success"])
        self.assertEqual(result["new_date"], "2027-03-02")
        self.assertRegex(result["transferred_at"], r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$")
        self.assertEqual(self.posted, [("2027-03-02", "08:30-12:30")])
        self.assertIn("2027-02-27 不在修改日期選單", result["attempts"])
        self.assertIn("2027-03-01 無 08:30-12:30 時段（可選：09:00-12:00）", result["attempts"])

    def test_no_change_when_range_full(self):
        result = tt.transfer_one_order(None, "", "dev", self.row, ["2027-03-01", "2027-03-03", "2027-03-04"])
        self.assertFalse(result["success"])
        self.assertEqual(self.posted, [])

    def test_backend_rejects_change_tries_next_day(self):
        def reject_first(session, base_url, order_no, day, period, phone=""):
            self.posted.append((day, period))
            if day != "2027-03-01":
                self.state.update(date=day, period=period)
            return True, "HTTP 200"

        options = {"2027-03-01": {"08:30-12:30": []}, "2027-03-02": {"08:30-12:30": []}}
        with patch.object(tt.qo, "_update_order_service_date", reject_first), \
                patch.object(tt, "_change_date_options", lambda *a, **k: options):
            result = tt.transfer_one_order(None, "", "dev", self.row, ["2027-03-01", "2027-03-02"])
        self.assertEqual(result["new_date"], "2027-03-02")
        self.assertEqual(len(self.posted), 2)


class TransferManyTests(unittest.TestCase):
    def test_each_order_uses_its_own_day_candidates(self):
        seen = []

        def fake_one(session, base_url, env, row, dates):
            seen.append((row["order_no"], row["service_date_before"], dates))
            return {"success": True, "new_date": dates[0], "message": "", "attempts": []}

        rows = [
            {"order_no": "LC1", "service_date": "2026-10-23", "period": "08:30-12:30", "phone": ""},
            {"order_no": "LC2", "service_date": "2026-10-24", "period": "09:00-12:00", "phone": ""},
        ]
        by_day = {"2026-10-23": ["2027-03-01"], "2026-10-24": ["2027-03-06"]}
        with patch.object(tt, "_login", lambda *a: (None, "")), patch.object(tt, "transfer_one_order", fake_one):
            results = tt.transfer_typhoon_orders("dev", "a", "b", rows, by_day)
        self.assertEqual(seen, [("LC1", "2026-10-23", ["2027-03-01"]), ("LC2", "2026-10-24", ["2027-03-06"])])
        self.assertEqual([r["原日期"] for r in tt.result_copy_rows(results)], ["2026-10-23", "2026-10-24"])


class CopyResultsTests(unittest.TestCase):
    def test_tsv_has_original_and_new_date_period(self):
        results = [
            {"order_no": "LC1", "name": "王小明", "phone": "0912345678", "service_date_before": "2026-10-23",
             "line_url": "https://chat.line.biz/Uabc/chat/U123", "address": "台北市大安區復興南路一段1號",
             "period": "08:30-12:30", "success": True, "new_date": "2027-03-02", "message": "已移到",
             "transferred_at": "2026-10-23 14:32", "staff": "宋芳儀(2)X陳佩琪(3)"},
            {"order_no": "LC2", "name": "李\t大", "phone": "", "service_date_before": "2026-10-23",
             "period": "09:00-12:00", "success": False, "new_date": "", "message": "無法安排"},
        ]
        lines = tt.results_tsv(results).split("\n")
        self.assertEqual(lines[0].split("\t"), [
            "訂單編號", "姓名", "LINE@連結", "電話", "客戶地址", "原日期", "原時段", "服務時數", "原專員",
            "新日期", "新時段", "結果", "說明", "移轉時間",
        ])
        self.assertEqual(lines[1].split("\t")[:12], [
            "LC1", "王小明", "https://chat.line.biz/Uabc/chat/U123", "0912345678", "台北市大安區復興南路一段1號",
            "2026-10-23", "08:30-12:30", "4", "宋芳儀、陳佩琪", "2027-03-02", "08:30-12:30", "成功",
        ])
        self.assertEqual(lines[2].split("\t")[5:12], ["2026-10-23", "09:00-12:00", "3", "", "", "", "失敗"])
        self.assertEqual(lines[1].split("\t")[-1], "2026-10-23 14:32")
        self.assertEqual(lines[2].split("\t")[-1], "")

    def test_service_hours_deducts_break_for_full_day(self):
        self.assertEqual(
            [tt.service_hours(p) for p in ["09:00-11:00", "08:30-12:30", "09:00-16:00", "09:00-18:00"]],
            ["2", "4", "6", "8"],
        )


class TrackingTests(unittest.TestCase):
    SHEET = (
        "訂單編號\t姓名\tLINE@連結\t電話\t客戶地址\t原日期\t原時段\t服務時數\t新日期\t新時段\t結果\t說明\n"
        "LC00215208\t王璿瑋\thttps://chat.line.biz/x\t912021679\t台北市\t2026-10-23\t08:30-12:30\t4\t2027-03-03\t08:30-12:30\t成功\t已移到\n"
        "LC00215959\t王騏三\t\t932003793\t台北市\t2026-10-23\t14:00-18:00\t4\t2027/3/3\t14:00-18:00\t成功\t已移到\n"
        "LC00215208\t重複\t\t\t\t\t\t\t\t\t\t\n"
    )

    def test_parse_sheet_with_header(self):
        items = tt.parse_tracking_input(self.SHEET)
        self.assertEqual(items, [
            {"order_no": "LC00215208", "name": "王璿瑋", "expected_date": "2027-03-03", "expected_period": "08:30-12:30"},
            {"order_no": "LC00215959", "name": "王騏三", "expected_date": "2027-03-03", "expected_period": "14:00-18:00"},
        ])

    def test_parse_headerless_rows_with_one_date(self):
        items = tt.parse_tracking_input(
            "LC00217286\t陳世湟\t2027-03-01\t14:00-18:00\n"
            "LC002169001\t創盟電子\t2027/3/2\t14:00-16:00\n"
            "LC00217080\t簡驪蓉\t2026-10-23\t09:00-11:00\t2027-03-01\t09:00-11:00\n"
        )
        self.assertEqual(items[0], {"order_no": "LC00217286", "name": "陳世湟",
                                    "expected_date": "2027-03-01", "expected_period": "14:00-18:00"})
        self.assertEqual((items[1]["expected_date"], items[1]["expected_period"]), ("2027-03-02", "14:00-16:00"))
        # 兩個日期無法判斷哪個是新日期
        self.assertEqual(items[2]["expected_date"], "")

    def test_parse_previous_tracking_result(self):
        rows = [{"訂單編號": "LC00217286", "姓名": "陳世湟", "表單新日期": "2027-03-01", "表單新時段": "14:00-18:00",
                 "目前日期": "2026-10-30", "目前時段": "14:00-18:00", "付款狀態": "已付款", "狀態": "已變動",
                 "查詢時間": "2026-10-23 10:00"}]
        items = tt.parse_tracking_input(tt.tracking_tsv(rows))
        self.assertEqual((items[0]["expected_date"], items[0]["expected_period"]), ("2027-03-01", "14:00-18:00"))

    def test_parse_plain_order_numbers(self):
        items = tt.parse_tracking_input("LC00215208\n 訂單 LC00215959 \n無單號")
        self.assertEqual([i["order_no"] for i in items], ["LC00215208", "LC00215959"])
        self.assertEqual(items[0]["expected_date"], "")

    def test_track_flags_orders_changed_back(self):
        current = {"LC00215208": ("2027-03-03", "08:30 - 12:30"), "LC00215959": ("2026-10-30", "14:00 - 18:00")}

        def fetch(session, order_no):
            if order_no not in current:
                raise Exception(f"查無訂單：{order_no}")
            return _block(order_no, *current[order_no])

        items = tt.parse_tracking_input(self.SHEET) + [{"order_no": "LC1", "name": "", "expected_date": "", "expected_period": ""}]
        with patch.object(tt, "_login", lambda *a: (None, "")), \
                patch.object(tt.qo, "_fetch_purchase_block_for_order_no", fetch):
            rows = tt.track_orders("dev", "a", "b", items)
        self.assertEqual([r["狀態"] for r in rows[:2]], ["未變動", "已變動"])
        self.assertEqual((rows[1]["目前日期"], rows[1]["目前時段"], rows[1]["付款狀態"]), ("2026-10-30", "14:00-18:00", "已付款"))
        self.assertTrue(rows[2]["狀態"].startswith("查詢失敗"))
        self.assertEqual(tt.tracking_tsv(rows).split("\n")[0].split("\t"), tt.TRACK_HEADERS)


class LemonShiftTests(unittest.TestCase):
    def test_defaults(self):
        self.assertEqual(tt.parse_lemon_names(tt.DEFAULT_LEMON_NAMES), [f"檸檬人{i}" for i in range(1, 13)])
        self.assertEqual(tt.DEFAULT_LEMON_SHIFT_TYPES, ["全8", "上4"])
        self.assertEqual(tt.parse_lemon_names("檸檬人1，檸檬人2、 檸檬人3"), ["檸檬人1", "檸檬人2", "檸檬人3"])

    def test_shift_dates_modes(self):
        transfer_dates = ["2027-03-01", "2027-03-02"]
        args = ("2027-02-26", "2027-03-02")
        self.assertEqual(tt.shift_dates(*args, "與移轉日期相同（依移轉日別）", transfer_dates), transfer_dates)
        self.assertEqual(tt.shift_dates(*args, "僅平日"), ["2027-02-26", "2027-03-01", "2027-03-02"])
        self.assertEqual(tt.shift_dates(*args, "僅週末"), ["2027-02-27", "2027-02-28"])
        self.assertEqual(len(tt.shift_dates(*args, "平日＋週末")), 5)

    def test_assign_uses_shift_tool_with_only_dates(self):
        from memo_system import memo, shift
        calls = {}

        def fake_assign(**kwargs):
            calls.update(kwargs)
            return {"errors": [], "saved": 1}

        with patch.object(memo, "login", lambda ui_logger=None: "SESSION"), \
                patch.object(shift, "assign_person_shift_range", fake_assign):
            tt.assign_lemon_shifts("dev", "a@x", "pw", ["檸檬人1"], ["全8", "上4"], ["2027-03-02", "2027-03-01"])
        self.assertEqual(memo.BASE_URL.endswith("dev.lemonclean.com.tw"), True)
        self.assertEqual((calls["session"], calls["date_start"], calls["date_end"]), ("SESSION", "2027-03-01", "2027-03-02"))
        self.assertEqual(calls["only_dates"], ["2027-03-02", "2027-03-01"])
        self.assertEqual(calls["type_values"], ["全8", "上4"])


class AttentionTests(unittest.TestCase):
    def test_flags_same_customer_and_lemon_staff(self):
        rows = [
            {"order_no": "LC00217516", "name": "柯宗育", "phone": "0911975612", "service_date": "2026-10-28",
             "period": "14:00-18:00", "staff": "吳珍嫻X魏思遠X胡偉勝"},
            {"order_no": "LC00217507", "name": "柯宗育", "phone": "0911975612", "service_date": "2026-10-28",
             "period": "09:00-16:00", "staff": "檸檬人1(0)X檸檬人2(0)"},
            {"order_no": "LC00217399", "name": "吳昭潔", "phone": "0928989191", "service_date": "2026-10-28",
             "period": "09:00-12:00", "staff": "李心媛X謝孟諭"},
        ]
        notes = tt.attention_notes(rows)
        self.assertEqual(set(notes), {"LC00217516", "LC00217507"})
        self.assertIn("同客人 2 筆", notes["LC00217516"])
        self.assertIn("LC00217507（2026-10-28 09:00-16:00）", notes["LC00217516"])
        self.assertIn("專員含檸檬人", notes["LC00217507"])
        self.assertNotIn("專員含檸檬人", notes["LC00217516"])

    def test_same_name_without_phone(self):
        rows = [{"order_no": "LC1", "name": "王", "phone": "", "staff": ""},
                {"order_no": "LC2", "name": "王", "phone": "", "staff": ""}]
        self.assertEqual(set(tt.attention_notes(rows)), {"LC1", "LC2"})


class NoticeCopyTests(unittest.TestCase):
    def test_notice_row_matches_result_first_columns(self):
        rows = [{"order_no": "LC00217763", "name": "邱秀美",
                 "line_url": "https://chat.line.biz/U70866032f75cbfed9c32ce87366562ce/chat/Ub6ccb2bade49e71d15f65c4b968721a6",
                 "phone": "0928244622", "address": "台北市萬華區萬大路344巷22號3樓",
                 "service_date": "2026-10-28", "period": "09:00-12:00", "staff": "鄭淵涼 X 吳奐"}]
        self.assertEqual(tt.NOTICE_COPY_HEADERS, tt.RESULT_COPY_HEADERS[:9])
        lines = tt.notice_tsv(rows).split("\n")
        self.assertEqual(lines[0].split("\t"), tt.NOTICE_COPY_HEADERS)
        self.assertEqual(lines[1], "\t".join([
            "LC00217763", "邱秀美",
            "https://chat.line.biz/U70866032f75cbfed9c32ce87366562ce/chat/Ub6ccb2bade49e71d15f65c4b968721a6",
            "0928244622", "台北市萬華區萬大路344巷22號3樓", "2026-10-28", "09:00-12:00", "3", "鄭淵涼、吳奐",
        ]))

    def test_staff_text_round_trip(self):
        self.assertEqual(tt.staff_text("宋芳儀(2)X陳佩琪(3)"), "宋芳儀、陳佩琪")
        self.assertEqual(tt.staff_text("檸檬人2 X 檸檬人11"), "檸檬人2、檸檬人11")
        self.assertEqual(tt.parse_staff_text("宋芳儀、陳佩琪"), ["宋芳儀", "陳佩琪"])
        self.assertEqual(tt.parse_staff_text("宋芳儀(2) X 陳佩琪(3)"), ["宋芳儀", "陳佩琪"])


if __name__ == "__main__":
    unittest.main()
