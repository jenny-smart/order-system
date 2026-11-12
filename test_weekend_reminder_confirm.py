# -*- coding: utf-8 -*-
"""週末提醒「確認收到」連結：簽章、訊息、同步回追蹤表與內勤分頁。"""
import hashlib
import hmac
import unittest
from datetime import date
from unittest.mock import patch

from function import weekend_reminders as wr
from shared import reminder_confirm as rc
from shared import weekend_reminder_confirm_sync as sync

KEY = "test-secret"
URL = "https://w.example.dev"


def tracking(order_no, service_date="2026-11-15", **extra):
    row = {header: "" for header in wr.TRACKING_HEADERS}
    row.update({"訂單編號": order_no, "服務日期": service_date, "訂單狀態": "已付款", "回覆狀態": "未回覆"})
    row.update(extra)
    return row


class LinkTest(unittest.TestCase):
    def test_signature_and_url_match_worker_format(self):
        expected = hmac.new(KEY.encode(), b"confirm|LC002200072|2026-11-15", hashlib.sha256).hexdigest()[:16]
        self.assertEqual(rc.signature(KEY, "LC002200072", "2026-11-15"), expected)
        self.assertEqual(
            rc.confirm_url("LC002200072", "2026-11-15", url=URL + "/", key=KEY),
            f"{URL}/c/LC002200072/20261115/{expected}",
        )

    def test_no_link_without_key_or_with_bad_input(self):
        self.assertEqual(rc.confirm_url("LC002200072", "2026-11-15", url=URL, key=""), "")
        self.assertEqual(rc.confirm_url("", "2026-11-15", url=URL, key=KEY), "")
        self.assertEqual(rc.confirm_url("LC002200072", "11/15", url=URL, key=KEY), "")

    def test_message_keeps_reply_wording_and_adds_link_when_configured(self):
        row = {"order_no": "LC002200072", "service_date": "2026-11-15", "service_time": "14:00-18:00", "address": "台北市"}
        with patch.object(rc, "api_key", return_value=""):
            plain = wr.build_reminder_message(row)
        self.assertIn("為確認您已收到提醒，請回覆「已收到」，謝謝您。", plain)
        self.assertNotIn("/c/", plain)
        with patch.object(rc, "api_key", return_value=KEY), patch.object(rc, "api_url", return_value=URL):
            linked = wr.build_reminder_message(row)
            combined = wr.build_combined_reminder_message([
                dict(row, order_no="LC00220396", service_date="2026-11-15", service_time="09:00-12:00"),
                dict(row, order_no="LC002200072", service_date="2026-11-14"),
            ])
        link = rc.confirm_url("LC002200072", "2026-11-15", url=URL, key=KEY)
        self.assertIn(f"請回覆「已收到」，或點以下連結確認：\n{link}\n謝謝您。", linked)
        self.assertIn("專員會在服務前5-10分鐘", linked)
        # 合併提醒只附最早那筆（主單）的連結
        self.assertIn(rc.confirm_url("LC002200072", "2026-11-14", url=URL, key=KEY), combined)
        self.assertEqual(combined.count("/c/"), 1)


class SyncTest(unittest.TestCase):
    TODAY = date(2026, 11, 13)

    def test_candidates_only_unreplied_paid_rows_in_window(self):
        rows = [
            tracking("LC1"), tracking("LC2", 回覆狀態="已回覆"), tracking("LC3", 訂單狀態="已取消"),
            tracking("LC4", "2026-11-08"), tracking("LC5", "2026-12-20"), tracking("LC6", "不是日期"),
        ]
        self.assertEqual([r["訂單編號"] for r in sync.candidate_rows(rows, self.TODAY)], ["LC1"])

    def test_confirmed_rows_get_reply_time_in_taipei_and_note(self):
        rows = [tracking("LC00000001"), tracking("LC00000002", 回覆備註="合併 2 筆：LC00000002、LC00000003")]
        updated = sync.apply_confirmations(rows, rows, {
            "LC00000001|2026-11-15": "2026-11-13T02:21:00.000Z",
            "LC00000002|2026-11-15": "2026-11-13T03:05:00.000Z",
        })
        self.assertEqual([(r["回覆狀態"], r["回覆時間"], r["回覆備註"]) for r in updated], [
            ("已回覆", "2026-11-13 10:21", "連結確認"),
            ("已回覆", "2026-11-13 11:05", "合併 2 筆：LC00000002、LC00000003；連結確認"),
        ])

    def test_merged_and_overlap_rows_follow_the_primary_order(self):
        primary = tracking("LC00000002", "2026-11-14")
        merged = tracking("LC00000003", "2026-11-15", 回覆備註="併入 LC00000002")
        skipped = tracking("LC00000004", "2026-11-14",
                           回覆備註="時段重疊不另發：與 LC00000002 時段重疊（此筆為檸檬人），以 LC00000002 時間為準")
        other = tracking("LC00000005")
        rows = [primary, merged, skipped, other]
        self.assertEqual(sync.follow_key(merged, rows), "LC00000002|2026-11-14")
        self.assertEqual(sync.follow_key(skipped, rows), "LC00000002|2026-11-14")
        self.assertEqual(sync.follow_key(other, rows), "")
        updated = sync.apply_confirmations(rows, rows, {"LC00000002|2026-11-14": "2026-11-13T02:00:00Z"})
        self.assertEqual([r["訂單編號"] for r in updated], ["LC00000002", "LC00000003", "LC00000004"])

    def test_staff_sheet_fills_ok_only_when_blank_and_matches_by_order_and_date(self):
        staff = [
            ["訂單編號", "服務日期", "服務時間", "姓名", "電話", "地址", "LINE", "通知內容", "回覆狀態"],
            ["LC00000009", "2026-11-15"],
            ["LC00000001", "2026-11-15", "", "", "", "", "", "", "", "已排程 11/13 09:00"],
            ["LC00000002", "2026-11-15", "", "", "", "", "", "", "未接", "已排程 11/13 09:00"],
        ]
        updated = [tracking("LC00000001", 回覆時間="2026-11-13 10:21"), tracking("LC00000002", 回覆時間="2026-11-13 11:05")]
        cells = sync.plan_staff_updates(staff, updated)
        self.assertEqual(cells, [
            {"range": "K1", "values": [["連結確認"]]},
            {"range": "I3", "values": [["OK"]]},
            {"range": "K3", "values": [["連結確認 11/13 10:21"]]},
            {"range": "K4", "values": [["連結確認 11/13 11:05"]]},  # I4 已有「未接」不覆蓋
        ])
        self.assertEqual(sync.plan_staff_updates(staff, []), [])

    def test_run_skips_api_when_nothing_pending_and_saves_when_confirmed(self):
        with patch.object(wr, "load_tracking_rows", return_value=[tracking("LC1", 回覆狀態="已回覆")]), \
                patch.object(rc, "fetch_confirmations") as fetch:
            self.assertEqual(sync.run(today=self.TODAY), {"candidates": 0, "confirmed": 0})
        fetch.assert_not_called()

        rows = [tracking("LC00000001"), tracking("LC00000002")]
        with patch.object(wr, "load_tracking_rows", return_value=rows), \
                patch.object(rc, "fetch_confirmations", return_value={"LC00000001|2026-11-15": "2026-11-13T02:21:00Z"}) as fetch, \
                patch.object(wr, "save_tracking_rows") as save, \
                patch.object(sync, "write_staff_sheet", return_value=2) as staff, \
                patch.object(sync, "_log"):
            result = sync.run(today=self.TODAY)
        self.assertEqual(fetch.call_args.args[0], {"LC00000001|2026-11-15", "LC00000002|2026-11-15"})
        self.assertEqual(result, {"candidates": 2, "confirmed": 1, "staff_cells": 2})
        self.assertEqual([r["訂單編號"] for r in save.call_args.args[0]], ["LC00000001"])
        staff.assert_called_once()

    def test_dry_run_writes_nothing(self):
        with patch.object(wr, "load_tracking_rows", return_value=[tracking("LC00000001")]), \
                patch.object(rc, "fetch_confirmations", return_value={"LC00000001|2026-11-15": "2026-11-13T02:21:00Z"}), \
                patch.object(wr, "save_tracking_rows") as save, patch.object(sync, "write_staff_sheet") as staff:
            sync.run(today=self.TODAY, dry_run=True)
        save.assert_not_called()
        staff.assert_not_called()


if __name__ == "__main__":
    unittest.main()
