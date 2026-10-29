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
                ("LC00215507", "2026-10-24"), ("LC00217404", "2026-10-24"),
            ],
        )
        self.assertEqual(positions, [2, 3])
        self.assertEqual(count, 3)

    def test_row_runs_groups_consecutive_positions(self):
        self.assertEqual(_row_runs([2, 3, 4, 7, 9, 10]), [(2, 3), (7, 1), (9, 2)])


if __name__ == "__main__":
    unittest.main()
