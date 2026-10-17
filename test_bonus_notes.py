import html
import json
import unittest
from unittest.mock import Mock, patch

import orders


class BonusNotesTest(unittest.TestCase):
    def session(self, notice="", progress=0, embedded=True):
        state = {"notice": notice, "progress": progress, "isCharge": 0,
                 "isRefund": 0, "chargeNote": "原加收備註", "refundNote": "原待退備註"}
        session = Mock()

        def get(*args, **kwargs):
            textarea = "{{ purchase.notice }}" if embedded else html.escape(state["notice"])
            script = f'<script>const vm = {{purchase: {json.dumps(state)}, other: {{}}}};</script>' if embedded else ""
            return Mock(status_code=200, text=(
                '<meta name="csrf-token" content="token">'
                f'<textarea name="notice">{textarea}</textarea>'
                '<input name="email" value="test@example.invalid">'
                + script
            ))

        def post(*args, **kwargs):
            state.update(kwargs["data"])
            return Mock(status_code=200)

        session.get.side_effect = get
        session.post.side_effect = post
        return session, state

    def apply(self, session):
        return orders.add_bonus_note_to_order(
            session, "https://example.invalid", "LC00216889",
            ["胡偉勝", "黃麗玲"], edit_id="216889",
        )

    def test_repeated_apply_posts_once_and_preserves_other_fields(self):
        session, state = self.session("請先電話聯絡")
        self.assertTrue(self.apply(session)[0])
        self.assertTrue(self.apply(session)[0])
        session.post.assert_called_once()
        self.assertEqual(state["notice"], "請先電話聯絡\n獎金：胡偉勝X黃麗玲")
        self.assertEqual(state["progress"], "1")
        self.assertEqual(state["isCharge"], "0")
        self.assertEqual(state["isRefund"], "0")
        self.assertEqual(state["chargeNote"], "原加收備註")
        self.assertEqual(state["refundNote"], "原待退備註")
        self.assertEqual(state["email"], "test@example.invalid")

    def test_existing_duplicate_bonus_lines_are_merged_only_for_target(self):
        session, state = self.session(
            "請先聯絡\n獎金：胡偉勝X黃麗玲\n其他備註\n獎金 : 胡偉勝 Ｘ 黃麗玲\n獎金：李佩蓉", 1)
        self.assertTrue(self.apply(session)[0])
        self.assertEqual(state["notice"],
                         "請先聯絡\n獎金：胡偉勝X黃麗玲\n其他備註\n獎金：李佩蓉")
        self.assertTrue(self.apply(session)[0])
        session.post.assert_called_once()

    def test_existing_bonus_still_sets_processed_status(self):
        session, state = self.session("獎金：胡偉勝X黃麗玲", 0)
        self.assertTrue(self.apply(session)[0])
        self.assertEqual(state["notice"], "獎金：胡偉勝X黃麗玲")
        self.assertEqual(state["progress"], "1")
        session.post.assert_called_once()

    def test_search_reads_vue_notice_even_when_textarea_is_empty(self):
        source = '<textarea name="notice"></textarea><script>const vm = {purchase: ' + json.dumps(
            {"notice": "獎金：胡偉勝X黃麗玲", "nested": {"value": "}"}}
        ) + ', other: {}};</script>'
        session = Mock()
        session.get.return_value = Mock(status_code=200, text=source)
        self.assertEqual(orders._fetch_order_edit_notice(session, "LC00216889", "216889"),
                         "獎金：胡偉勝X黃麗玲")

    def test_json_null_notice_does_not_save_template_text(self):
        session, state = self.session(None)
        self.assertTrue(self.apply(session)[0])
        self.assertEqual(state["notice"], "獎金：胡偉勝X黃麗玲")

    def test_static_html_notice_preserves_decoded_entities(self):
        session, state = self.session("聯絡 A&B <提醒>", embedded=False)
        self.assertTrue(self.apply(session)[0])
        self.assertEqual(state["notice"], "聯絡 A&B <提醒>\n獎金：胡偉勝X黃麗玲")

    def test_unreadable_notice_does_not_submit(self):
        session = Mock()
        session.get.return_value = Mock(status_code=200, text=(
            '<meta name="csrf-token" content="token">'
            '<textarea name="notice">{{ purchase.notice }}</textarea>'
        ))
        self.assertFalse(self.apply(session)[0])
        session.post.assert_not_called()

    def test_duplicate_batch_rows_do_not_duplicate_note(self):
        session, state = self.session()
        item = {"order_no": "LC00216889", "cust_name": "測試客戶",
                "bonus_names": ["胡偉勝", "黃麗玲"], "edit_id": "216889"}
        with patch.object(orders.requests, "Session", return_value=session), patch.object(orders, "login", return_value=True):
            results = orders.apply_bonus_notes("dev", "test@example.invalid", "test", [item, item])
        self.assertTrue(all(r["ok"] for r in results))
        self.assertEqual(state["notice"], "獎金：胡偉勝X黃麗玲")
        session.post.assert_called_once()


if __name__ == "__main__":
    unittest.main()
