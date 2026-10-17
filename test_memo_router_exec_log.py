import importlib
import unittest
from unittest.mock import patch

from function import memo_router


class MemoRouterExecLogTest(unittest.TestCase):
    def test_wrapper_survives_reload_and_logs_once(self):
        from memo_system import atm
        memo_router.install_execution_log()
        atm = importlib.reload(atm)  # memo_system/ui.py 每次畫面都會 reload
        self.assertTrue(getattr(atm.paste_atm_unpaid_list, "_order_system_exec_log", False))
        with patch.object(memo_router, "log_execution") as log:
            self.assertEqual(atm.paste_atm_unpaid_list("台北", [])["pasted"], 0)
        log.assert_called_once()
        self.assertEqual(log.call_args.kwargs["function_name"], "ATM 待付款清單貼上工作表")
        self.assertEqual(log.call_args.kwargs["area"], "台北")

    def test_failure_is_logged_and_reraised(self):
        memo_router.install_execution_log()
        from memo_system import change_order
        with patch.object(memo_router, "log_execution") as log:
            wrapped = memo_router._wrap(lambda region, rows, ui_logger=None: (_ for _ in ()).throw(RuntimeError("boom")),
                                        memo_router._co_append)
            with self.assertRaisesRegex(RuntimeError, "boom"):
                wrapped("台北", [{"G": "A1"}])
        self.assertEqual(log.call_args.kwargs["status"], "失敗")
        self.assertEqual(log.call_args.kwargs["target"], "A1")
        self.assertTrue(getattr(change_order.append_rows_to_sheet, "_order_system_exec_log", False))

    def test_dry_run_import_is_not_logged(self):
        with patch.object(memo_router, "log_execution") as log:
            wrapped = memo_router._wrap(lambda rows, dry_run=True, ui_logger=None, session=None: {"saved": 0},
                                        memo_router._shift_import)
            wrapped([], dry_run=True)
        log.assert_not_called()

    def test_legacy_pages_route_to_memo_system(self):
        from function import (atm_reconciliation, change_order_page, memo_customer_service,
                              payment_match_page, shift_management, assessment_tool)
        expected = {
            atm_reconciliation: "💰 財務對帳", change_order_page: "🔄 服務異動",
            memo_customer_service: "📋 客服作業", payment_match_page: "💳 付款後5碼及星和診所比對",
            shift_management: "📅 排班管理", assessment_tool: "📐 評估文字工具",
        }
        for module, section in expected.items():
            with patch("memo_system.ui.render_memo_system") as render, \
                    patch.object(memo_router, "install_execution_log"):
                module.render("a@b", "pw", "dev")
            render.assert_called_once_with(forced_main_section=section, shared_backend_email="a@b",
                                           shared_backend_password="pw", shared_env="dev")
        from memo_system.change_order import TAIWAN_PUBLIC_HOLIDAYS
        self.assertIs(change_order_page.TAIWAN_PUBLIC_HOLIDAYS, TAIWAN_PUBLIC_HOLIDAYS)


if __name__ == "__main__":
    unittest.main()
