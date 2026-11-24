import unittest
from unittest import mock

import function.order_creation as oc


class OldCustomerMultiLineMergeTest(unittest.TestCase):
    def _ok(self, order_no, session="S"):
        return {"ok": True, "result": {"order_no": order_no, "region": "台中", "session": session, "line_message": f"msg {order_no}"}}

    def test_single_success_keeps_single_message(self):
        with mock.patch.object(oc.qo, "build_combined_line_message_from_order_nos") as build:
            self.assertEqual(oc.combined_line_message_for_results([self._ok("LC1")], "prod"), "")
        build.assert_not_called()

    def test_successful_orders_are_merged_with_existing_session(self):
        results = [self._ok("LC1"), {"ok": False, "error": "x"}, self._ok("LC2"), self._ok("LC3")]
        with mock.patch.object(oc.qo, "build_combined_line_message_from_order_nos", return_value=({}, "合併訊息")) as build:
            message = oc.combined_line_message_for_results(results, "prod")
        self.assertEqual(message, "合併訊息")
        args, kwargs = build.call_args
        self.assertEqual(args[0], "prod")
        self.assertEqual(args[3], ["LC1", "LC2", "LC3"])
        self.assertEqual(kwargs["session"], "S")
        self.assertEqual(kwargs["fallback_region"], "台中")

    def test_merge_failure_returns_notice(self):
        with mock.patch.object(oc.qo, "build_combined_line_message_from_order_nos", side_effect=Exception("付款方式不同")):
            message = oc.combined_line_message_for_results([self._ok("LC1"), self._ok("LC2")], "prod")
        self.assertTrue(message.startswith("（合併 LINE 訊息產生失敗"))
        self.assertIn("付款方式不同", message)


if __name__ == "__main__":
    unittest.main()
