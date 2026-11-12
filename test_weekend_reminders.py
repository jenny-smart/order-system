import unittest

from function.weekend_reminders import (
    _row_runs, build_reminder_message, merge_tracking_rows, plan_tracking_rows,
)


class WeekendReminderMessageTest(unittest.TestCase):
    def setUp(self):
        self.row = {
            "service_date": "2026-10-24",
            "service_time": "09:00-11:00",
            "address": "台北市文山區辛亥路四段77巷14號11樓",
        }

    def test_default_message_includes_holiday_office_notice(self):
        message = build_reminder_message(self.row)

        self.assertEqual(message, (
            "您好，這是週末/例假日的清潔服務提醒：\n\n"
            "服務時間：10/24（六） 09:00-11:00\n"
            "服務地址：台北市文山區辛亥路四段77巷14號11樓\n\n"
            "專員會在服務前5-10分鐘，以電話／門鈴／透過管理員等方式與您聯繫，煩請留意聯繫訊息。\n\n"
            "為確認您已收到提醒，請回覆「已收到」，謝謝您。\n\n"
            "💡 貼心提醒：\n"
            "📅 例假日內勤人員休息通常不會處理訊息，您可以先留訊息待上班日上班時間處理喔，"
            "造成不便，尚請見諒，謝謝～"
        ))

    def test_typhoon_message_replaces_notice_and_adds_cancellation_policy(self):
        message = build_reminder_message(self.row, typhoon_reminder=True)

        self.assertEqual(message, (
            "您好，這是週末/例假日的清潔服務提醒：\n\n"
            "服務時間：10/24（六） 09:00-11:00\n"
            "服務地址：台北市文山區辛亥路四段77巷14號11樓\n\n"
            "專員會在服務前5-10分鐘，以電話／門鈴／透過管理員等方式與您聯繫，煩請留意聯繫訊息。\n\n"
            "為確認您已收到提醒，請回覆「已收到」，謝謝您。\n\n"
            "💡 貼心提醒：\n"
            "📅 例假日內勤人員休息通常不會處理訊息，建議您可以先留訊息待工作日上班時間處理喔，謝謝～\n"
            "🌀 若人事行政局公告放假，則該日服務取消，待工作日上班時間與您協調時間，"
            "造成不便，尚請見諒～"
        ))


def _tracked(order_no, service_date, service_time="09:00-12:00", reply=""):
    return {
        "訂單編號": order_no, "服務日期": service_date, "服務時間": service_time,
        "通知內容": "msg", "訂單狀態": "已付款", "通知狀態": "已通知", "回覆狀態": reply,
    }


class WeekendReminderTrackingTest(unittest.TestCase):
    def test_rescheduled_order_counts_as_new_for_new_date(self):
        existing = [_tracked("LC00217404", "2026-10-24", reply="已回覆")]
        orders = [{
            "order_no": "LC00217404", "service_date": "2026-10-31",
            "service_time": "09:00-12:00", "order_status": "已付款", "message": "new",
        }]

        merged = merge_tracking_rows(orders, existing)

        self.assertEqual(merged[0]["資料狀態"], "新增")
        self.assertEqual(merged[0]["通知狀態"], "待通知")
        self.assertEqual(merged[0]["回覆狀態"], "未回覆")
        self.assertEqual(merged[0]["通知內容"], "new")

    def test_same_order_and_date_is_existing(self):
        existing = [_tracked("LC00217404", "2026-10-31", reply="已回覆")]
        orders = [{
            "order_no": "LC00217404", "service_date": "2026-10-31",
            "order_status": "已付款", "message": "new",
        }]

        merged = merge_tracking_rows(orders, existing)

        self.assertEqual(merged[0]["資料狀態"], "已存在")
        self.assertEqual(merged[0]["回覆狀態"], "已回覆")

    def test_plan_keeps_old_date_row_and_reports_new_row_positions(self):
        existing = [
            _tracked("LC00217404", "2026-10-24"),
            _tracked("LC00215507", "2026-10-24", "14:00-17:00"),
        ]
        incoming = [
            _tracked("LC00217404", "2026-10-31"),
            _tracked("LC00218089", "2026-10-31", "08:30-12:30"),
            _tracked("LC00215507", "2026-10-24", "14:00-17:00"),
        ]

        all_rows, positions, count = plan_tracking_rows(existing, incoming, "2026-10-28 10:00")

        self.assertEqual(
            [(row["訂單編號"], row["服務日期"]) for row in all_rows],
            [
                ("LC00217404", "2026-10-31"), ("LC00218089", "2026-10-31"),
                ("LC00217404", "2026-10-24"), ("LC00215507", "2026-10-24"),  # 既有列維持原順序
            ],
        )
        self.assertEqual(positions, [2, 3])
        self.assertEqual(count, 3)

    def test_new_rows_go_to_bottom_of_their_day_sorted_by_name(self):
        def row(no, day, name):
            r = _tracked(no, day)
            r["姓名"] = name
            return r
        existing = [row("LC9", "2026-11-15", "王"), row("LC8", "2026-11-15", "林"), row("LC7", "2026-11-14", "陳")]
        incoming = [row("LC5", "2026-11-15", "B"), row("LC6", "2026-11-15", "A"), row("LC4", "2026-11-14", "A")]
        all_rows, positions, _ = plan_tracking_rows(existing, incoming, "now")
        self.assertEqual([r["訂單編號"] for r in all_rows], ["LC9", "LC8", "LC6", "LC5", "LC7", "LC4"])
        self.assertEqual(positions, [4, 5, 7])

    def test_first_switch_resorts_by_name(self):
        def row(no, name):
            r = _tracked(no, "2026-11-15")
            r["姓名"] = name
            return r
        all_rows, _, _ = plan_tracking_rows([row("LC2", "B"), row("LC1", "A")], [row("LC3", "C")], "now", resort=True)
        self.assertEqual([r["訂單編號"] for r in all_rows], ["LC1", "LC2", "LC3"])

    def test_pending_orders_are_listed_with_payment_status(self):
        orders = [{"order_no": "LC1", "service_date": "2026-11-15", "order_status": "待付款", "message": "m"},
                  {"order_no": "LC2", "service_date": "2026-11-15", "order_status": "取消訂單", "message": ""}]
        merged = merge_tracking_rows(orders, [])
        self.assertEqual([(r["訂單編號"], r["訂單狀態"]) for r in merged], [("LC1", "待付款")])


class StaffSheetTest(unittest.TestCase):
    def test_links_and_manual_columns_follow_key(self):
        from function.weekend_reminders import plan_staff_sheet
        formatted = [
            ["訂單編號", "服務日期", "服務時間", "姓名", "電話", "地址", "LINE", "通知內容", "回覆狀態", "", "連結確認"],
            ["LC1", "2026-11-15", "", "", "", "", "", "", "OK", "", "已確認"],
            ["LC2", "2026-11-15", "", "", "", "", "", "", "", "已排程 11/13 09:00", ""],
            ["", "", "", "", "", "", "", "", "手動列", "", ""],
        ]
        raw = [["=importrange(\"x\",\"週末服務提醒!A:H\")"] + formatted[0][1:]] + formatted[1:]
        tracking = [
            {"訂單編號": "LC2", "服務日期": "2026-11-15", "姓名": "王", "LINE": "https://chat.line.biz/u",
             "電話": "0912345678", "訂單狀態": "待付款", "通知內容": "msg"},
            {"訂單編號": "LC1", "服務日期": "2026-11-15", "姓名": "林", "電話": "", "訂單狀態": "已付款"},
        ]
        m = plan_staff_sheet(formatted, raw, tracking, "https://b")
        self.assertEqual(m[0][:8], ["訂單編號", "服務日期", "服務時間", "訂購人", "電話", "地址", "付款狀態", "通知內容"])
        self.assertEqual(m[0][8:], ["'回覆狀態", "", "'連結確認"])
        self.assertEqual(m[1][:2], ["'LC2", "'2026-11-15"])
        self.assertEqual(m[1][3], '=HYPERLINK("https://chat.line.biz/u","王")')
        self.assertTrue(m[1][4].startswith('=HYPERLINK("https://b/purchase?') and m[1][4].endswith(',"0912345678")'))
        self.assertEqual(m[1][6], "'待付款")
        self.assertEqual(m[1][8:], ["", "'已排程 11/13 09:00", ""])
        self.assertEqual(m[2][3], "'林")
        self.assertEqual(m[2][8:], ["'OK", "", "'已確認"])
        self.assertEqual(m[3][8], "'手動列")  # 追蹤表沒有的手動列保留

    def test_row_runs_groups_consecutive_positions(self):
        self.assertEqual(_row_runs([2, 3, 4, 7, 9, 10]), [(2, 3), (7, 1), (9, 2)])


if __name__ == "__main__":
    unittest.main()
