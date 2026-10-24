import unittest

from function.weekend_reminders import build_reminder_message


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


if __name__ == "__main__":
    unittest.main()
