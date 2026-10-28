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

    def test_dev_can_reuse_existing_copy_without_creating_another(self):
        st, creator = _st(), Mock()
        existing = "台北202610_dev1028-080000"
        self.assertEqual(dsc.use_existing_copy(st, "dev", "台北202610", existing), existing)
        self.assertEqual(dsc.read_sheet(st, "dev", "台北202610"), existing)
        self.assertEqual(dsc.resolve_run_sheet(st, "dev", "台北202610", creator), existing)
        creator.assert_not_called()

    def test_existing_copy_must_match_source_prefix(self):
        with self.assertRaisesRegex(ValueError, "台北202610_dev"):
            dsc.use_existing_copy(_st(), "dev", "台北202610", "台中202610_dev1028-080000")

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
        cols[0].multiselect.return_value = ['可約']
        cols[0].selectbox.return_value = "台北"
        cols[1].text_input.return_value = "台北202610"
        cols[0].number_input.return_value = 50
        cols[1].number_input.return_value = 0
        cols[0].date_input.return_value = None
        cols[1].date_input.return_value = None
        cols[2].date_input.return_value = None
        st.columns.side_effect = lambda spec, **kw: cols[:spec if isinstance(spec, int) else len(spec)]
        st.container.return_value = st
        st.checkbox.side_effect = lambda *a, **kw: kw.get("key") == "optimized_cloud_confirm"
        st.button.side_effect = lambda *a, **kw: kw.get("key") == "optimized_cloud_start"
        st.multiselect.return_value = ["可約"]
        for col in cols:
            col.checkbox.side_effect, col.button.side_effect = st.checkbox.side_effect, st.button.side_effect
        with patch.object(ui, "st", st), patch.object(ui, "_render_cloud_status"), \
             patch.object(dsc, "create_dev_copy", return_value="台北202610_devX"), \
             patch.object(ui, "_dispatch", return_value={}) as dispatch:
            ui.render("dev")
        self.assertEqual(dispatch.call_args.args[0], "台北202610_devX")
        self.assertEqual(dispatch.call_args.kwargs["env"], "dev")


if __name__ == "__main__":
    unittest.main()


def _row(name, date, start, order="", event="", status="未安排", result=""):
    row = [""] * 34
    row[2], row[3], row[4], row[5], row[6], row[7], row[8] = name, "0912345678", "台北市大安區", date, start, "12:00", status
    row[12], row[13], row[33] = order, result, event
    return row


def _header():
    return [""] * 33 + ["日曆事件ID"]


class RefreshDevCopyTest(unittest.TestCase):
    def test_booked_rows_carry_by_event_id_and_unmatched_go_to_bottom(self):
        old = [_header(),
               _row("王小明", "2026/12/05", "9:00", "TT1", "e1", "已安排", "成功"),
               _row("李曉微", "2027/01/04", "14:00", "TT2", "e2", "已安排", "成功"),
               _row("陳靜萱", "2026/12/30", "9:00", "", "e3", "未安排", "失敗")]
        new = [_header(),
               _row("王小明", "2026/12/05", "09:00", event="e1"),
               _row("李曉微", "2027/01/11", "14:00", event="e2"),
               _row("陳靜萱", "2026/12/30", "9:00", event="e3"),
               _row("新客人", "2026/12/20", "9:00", event="e4")]
        updates, appended, carried, dropped = dsc.carry_booked_rows(old, new)
        self.assertEqual((carried, dropped), (1, []))
        self.assertEqual(updates[0], {"range": "I2", "values": [["已安排"]]})
        self.assertEqual(updates[1]["range"], "K2:AG2")
        self.assertEqual(updates[1]["values"][0][2:4], ["TT1", "成功"])
        # 李曉微改了日期：測試訂單是舊日期，放到最下方保留；陳靜萱沒成單不帶。
        self.assertEqual([row[2] for row in appended], ["李曉微"])

    def test_rows_already_booked_in_new_schedule_are_not_overwritten(self):
        old = [_header(), _row("王小明", "2026/12/05", "9:00", "TT1", "e1", "已安排")]
        new = [_header(), _row("王小明", "2026/12/05", "9:00", "LC9", "e1", "已安排")]
        self.assertEqual(dsc.carry_booked_rows(old, new), ([], [], 0, []))

    def test_rows_without_event_id_match_by_customer_date_and_time(self):
        old = [[""] * 34, _row("王小明", "2026/12/5", "9:00", "TT1")]
        new = [[""] * 34, _row("王小明", "2026/12/05", "09:00")]
        self.assertEqual(dsc.carry_booked_rows(old, new)[2], 1)

    def test_refresh_replaces_copy_keeping_name_and_cleans_up_on_failure(self):
        old_ws = Mock(index=5)
        old_ws.get_values.return_value = [_header(), _row("王小明", "2026/12/05", "9:00", "TT1", "e1", "已安排")]
        fresh = Mock(row_count=200)
        fresh.get_values.return_value = [_header(), _row("王小明", "2026/12/05", "9:00", event="e1")]
        sh = Mock()
        sh.worksheet.side_effect = lambda name: {"台北202612-202702": Mock(id=1), "台北202612-202702_dev1028-0800": old_ws}[name]
        sh.duplicate_sheet.return_value = fresh
        client = Mock()
        client.open_by_key.return_value = sh
        with patch("orders.build_gsheet_client", return_value=client):
            result = dsc.refresh_dev_copy("台北202612-202702", "台北202612-202702_dev1028-0800")
        self.assertEqual(result, {"carried": 1, "appended": 0, "dropped": []})
        sh.duplicate_sheet.assert_called_once_with(1, insert_sheet_index=5, new_sheet_name="台北202612-202702_dev1028-0800_更新中")
        sh.del_worksheet.assert_called_once_with(old_ws)
        fresh.update_title.assert_called_once_with("台北202612-202702_dev1028-0800")

        fresh.batch_update.side_effect = RuntimeError("quota")
        sh.del_worksheet.reset_mock()
        with patch("orders.build_gsheet_client", return_value=client), self.assertRaises(RuntimeError):
            dsc.refresh_dev_copy("台北202612-202702", "台北202612-202702_dev1028-0800")
        sh.del_worksheet.assert_called_once_with(fresh)

    def test_refresh_refuses_non_dev_sheet(self):
        with self.assertRaisesRegex(ValueError, "_dev"):
            dsc.refresh_dev_copy("台北202612-202702", "台北202612-202702")

    def test_only_paid_orders_are_carried(self):
        old = [_header(),
               _row("王小明", "2026/12/05", "9:00", "TT1", "e1", "已安排"),
               _row("李曉微", "2026/12/06", "9:00", "TT2", "e2", "已安排"),
               _row("陳靜萱", "2026/12/07", "9:00", "TT3", "e3", "已安排"),
               _row("林大同", "2026/12/08", "9:00", "TT4", "e4", "已安排")]
        new = [_header()] + [_row(r[2], r[5], r[6], event=r[33]) for r in old[1:]]
        statuses = {"TT1": "已付款", "TT2": "取消訂單", "TT3": "待付款"}
        updates, appended, carried, dropped = dsc.carry_booked_rows(old, new, statuses)
        self.assertEqual(carried, 1)
        self.assertEqual(updates[0]["range"], "I2")
        self.assertEqual(dropped, [("TT2", "取消訂單"), ("TT3", "待付款"), ("TT4", "後台查無")])

    def test_status_lookup_runs_before_copy_so_failure_leaves_copy_untouched(self):
        old_ws = Mock(index=5)
        old_ws.get_values.return_value = [_header(), _row("王小明", "2026/12/05", "9:00", "TT1", "e1", "已安排")]
        sh = Mock()
        sh.worksheet.side_effect = lambda name: {"台北202612": Mock(id=1), "台北202612_dev1": old_ws}[name]
        client = Mock()
        client.open_by_key.return_value = sh
        lookup = Mock(side_effect=RuntimeError("測試機後台登入失敗"))
        with patch("orders.build_gsheet_client", return_value=client), self.assertRaises(RuntimeError):
            dsc.refresh_dev_copy("台北202612", "台北202612_dev1", lookup)
        lookup.assert_called_once_with(["TT1"])
        sh.duplicate_sheet.assert_not_called()
        sh.del_worksheet.assert_not_called()
