# -*- coding: utf-8 -*-
import unittest
from datetime import datetime
from unittest.mock import MagicMock, Mock, patch

import shared.dev_sheet_copy as dsc


class _State(dict):
    __getattr__ = dict.__getitem__
    __setattr__ = dict.__setitem__


def _st():
    st = MagicMock()
    st.session_state = _State()
    return st


class DevSheetCopyTest(unittest.TestCase):
    def test_prod_uses_original_sheet_without_copy(self):
        st, creator = _st(), Mock()
        self.assertEqual(dsc.resolve_run_sheet(st, "prod", " 台北202610 ", creator), "台北202610")
        creator.assert_not_called()

    def test_dev_copies_once_and_reuses_copy(self):
        st, creator = _st(), Mock(side_effect=["台北202610_dev1022-0900", "x"])
        first = dsc.resolve_run_sheet(st, "dev", "台北202610", creator)
        second = dsc.resolve_run_sheet(st, "dev", "台北202610", creator)
        self.assertEqual(first, "台北202610_dev1022-0900")
        self.assertEqual(second, first)
        creator.assert_called_once_with("台北202610")
        self.assertEqual(dsc.read_sheet(st, "dev", "台北202610"), first)
        self.assertEqual(dsc.read_sheet(st, "prod", "台北202610"), "台北202610")

    def test_read_sheet_before_copy_reads_original(self):
        self.assertEqual(dsc.read_sheet(_st(), "dev", "台中202610"), "台中202610")

    def test_dev_actions_exclude_calendar(self):
        self.assertNotIn("改 Google 日曆", dsc.action_options("dev"))
        self.assertEqual(dsc.default_actions("dev"), ["建單"])
        self.assertIn("改 Google 日曆", dsc.action_options("prod"))

    def test_copy_title(self):
        self.assertEqual(dsc.copy_title("台北202610", datetime(2026, 10, 22, 9, 5, 7)), "台北202610_dev1022-090507")

    def test_create_dev_copy_duplicates_tab(self):
        sh = Mock()
        sh.worksheet.return_value = Mock(id=123)
        client = Mock()
        client.open_by_key.return_value = sh
        with patch("orders.build_gsheet_client", return_value=client):
            title = dsc.create_dev_copy("台北202610")
        self.assertTrue(title.startswith("台北202610_dev"))
        sh.duplicate_sheet.assert_called_once_with(123, new_sheet_name=title)


class CloudDevTest(unittest.TestCase):
    def test_cloud_run_dev_uses_dev_backend_and_only_creates_orders(self):
        import shared.cloud_batch_booking as cloud
        with patch.object(cloud, "load_pending", side_effect=lambda sheet, excluded=None, *a, **k: [] if excluded and 3 in excluded else [(3, "台北", "")]), \
             patch.object(cloud, "held_rows", return_value=[]), \
             patch.object(cloud, "Progress"), \
             patch.dict(cloud.ACCOUNTS, {"台北": {"email": "e", "password": "p"}}), \
             patch.object(cloud, "run_process_web_hybrid", return_value={"success_count": 1}) as runner:
            self.assertEqual(cloud.run("台北202610_dev", pause_seconds=0, env_name="dev"), 0)
        self.assertEqual(runner.call_args.kwargs["env_name"], "dev")
        self.assertEqual(runner.call_args.kwargs["selected_actions"], ["建單"])
        self.assertEqual(runner.call_args.kwargs["sheet_name"], "台北202610_dev")

    def test_dispatch_sends_env(self):
        import function.cloud_batch_booking as ui
        for env, expected in (("prod", "prod"), ("dev", "dev")):
            with self.subTest(env=env), patch.object(ui, "_token", return_value="t"), \
                 patch.object(ui, "_latest_run", return_value=None), \
                 patch.object(ui, "load_config", return_value={}), \
                 patch.object(ui.requests, "post", return_value=Mock(status_code=204)) as post:
                ui._dispatch("s", 50, 0, "all", "台北", False, env=env)
                self.assertEqual(post.call_args.kwargs["json"]["inputs"]["env"], expected)

    def test_cloud_ui_dev_dispatches_copy(self):
        import function.cloud_batch_booking as ui
        st = _st()
        cols = [Mock(), Mock(), Mock()]
        cols[0].selectbox.return_value = "台北"
        cols[1].text_input.return_value = "台北202610"
        cols[0].number_input.return_value = 50
        cols[1].number_input.return_value = 0
        cols[0].date_input.return_value = None
        cols[1].date_input.return_value = None
        st.columns.side_effect = [cols, cols[:2], cols[:2]]
        st.checkbox.side_effect = lambda *a, **kw: kw.get("key") == "optimized_cloud_confirm"
        st.button.side_effect = lambda *a, **kw: kw.get("key") == "optimized_cloud_start"
        st.multiselect.return_value = ["可約"]
        with patch.object(ui, "st", st), patch.object(ui, "_render_cloud_status"), \
             patch.object(dsc, "create_dev_copy", return_value="台北202610_devX"), \
             patch.object(ui, "_dispatch", return_value={}) as dispatch:
            ui.render("dev")
        self.assertEqual(dispatch.call_args.args[0], "台北202610_devX")
        self.assertEqual(dispatch.call_args.kwargs["env"], "dev")


if __name__ == "__main__":
    unittest.main()
