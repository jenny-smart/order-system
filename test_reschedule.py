import unittest
from unittest.mock import patch

import function.reschedule as rs
import function.typhoon_sheet_sync as tss


class _Resp:
    status_code = 200


FOUND = [
    {"order_no": "LCA", "name": "甲", "phone": "0911", "service_date": "2027-04-12", "period": "09:00-12:00",
     "staff": "宋芳儀(2)X陳佩琪(3)"},
    {"order_no": "LCB", "name": "乙", "phone": "0922", "service_date": "2027-04-12", "period": "09:00-12:00",
     "staff": "張志豪(2)X吳承軒(1)"},
]


class RowsTests(unittest.TestCase):
    def test_rows_keep_original_date_period_staff(self):
        rows = rs.rows_from_orders(FOUND)
        self.assertEqual(rows[0]["orig_staff"], ["宋芳儀", "陳佩琪"])
        self.assertEqual((rows[0]["orig_date"], rows[0]["orig_period"], rows[0]["status"]),
                         ("2027-04-12", "09:00-12:00", "待調班"))
        header, first = tss.restore_tsv(rows).split("\n")[:2]
        self.assertEqual(header.split("\t"), tss.RESTORE_COPY_HEADERS)
        self.assertTrue(first.startswith("LCA\t甲\t2027-04-12\t09:00-12:00\t宋芳儀、陳佩琪"))


class ExecuteTests(unittest.TestCase):
    """模擬後台：修改日期時後台會自動配人，可能配到另一張待調班訂單的原專員。"""

    ROSTER = {"宋芳儀": "1", "陳佩琪": "2", "張志豪": "3", "吳承軒": "4", "空1": "5", "空2": "6"}

    def setUp(self):
        self.orders = {
            "LCA": {"date": "2027-04-12", "period": "09:00-12:00", "staff": ["宋芳儀", "陳佩琪"], "auto": ["張志豪", "吳承軒"]},
            "LCB": {"date": "2027-04-12", "period": "09:00-12:00", "staff": ["張志豪", "吳承軒"], "auto": ["空1", "空2"]},
        }
        self.pid = {"A": "LCA", "B": "LCB"}

    def post(self, url, params=None, data=None, **kwargs):
        by_id = {v: k for k, v in self.ROSTER.items()}
        order = self.orders[self.pid[params["purchase_id"]]]
        shift_ids = [v for k, v in data if k.startswith("shiftId")]
        order["staff"] = [by_id.get(sid, order["staff"][i]) for i, sid in enumerate(shift_ids)]
        return _Resp()

    def run_execute(self, transfer_ok=True):
        rows = rs.rows_from_orders(FOUND)

        def transfer_one(session, base_url, env, row, dates):
            if not transfer_ok:
                return {"success": False, "message": "移轉區間內都無法安排，訂單未修改", "attempts": ["2026-10-29 無 09:00-12:00 時段"]}
            o = self.orders[row["order_no"]]
            o["date"], o["staff"] = dates[0], list(o["auto"])
            return {"success": True, "new_date": dates[0], "message": "", "attempts": []}

        def order_now(session, no):
            o = self.orders[no]
            return o["date"], o["period"], list(o["staff"]), ""

        def edit_info(session, base_url, day, pid):
            current = [self.ROSTER[n] for n in self.orders[self.pid[pid]]["staff"]]
            slot = {f"{n} (1)": sid for n, sid in self.ROSTER.items()}
            return "tok", current, [slot for _ in current]

        def occupied(session, base_url, day, period, exclude_purchase_id=None):
            me = self.pid[exclude_purchase_id]
            return {n for no, o in self.orders.items() if no != me and o["date"] == day for n in o["staff"]}

        with patch.object(rs.tt, "_login", lambda *a: (self, "https://x")), \
                patch.object(rs.tt, "transfer_one_order", transfer_one), \
                patch.object(tss, "_order_now", order_now), \
                patch.object(tss.qo, "_fetch_order_edit_id", lambda s, no: {"LCA": "A", "LCB": "B"}[no]), \
                patch.object(tss.qo, "_get_schedule_edit_info", edit_info), \
                patch.object(tss.qo, "_get_occupied_staff_for_period", occupied):
            return rs.execute_reschedule("dev", "a", "b", rows, {"2027-04-12": ["2026-10-29"]})

    def test_moves_and_keeps_original_staff_without_cascade(self):
        results = self.run_execute()
        self.assertEqual([r["status"] for r in results], ["已調班並配回原專員", "已調班並配回原專員"])
        self.assertEqual(sorted(self.orders["LCA"]["staff"]), ["宋芳儀", "陳佩琪"])
        self.assertEqual(sorted(self.orders["LCB"]["staff"]), ["吳承軒", "張志豪"])
        self.assertEqual(results[0]["now_date"], "2026-10-29")
        self.assertTrue(results[0]["restored_at"])
        after = tss.restore_tsv(results).split("\n")[1].split("\t")
        self.assertEqual(after[5:9], ["2026-10-29", "09:00-12:00", "宋芳儀、陳佩琪", "已調班並配回原專員"])

    def test_failed_move_reports_reason_and_keeps_order(self):
        results = self.run_execute(transfer_ok=False)
        self.assertTrue(results[0]["status"].startswith("調班失敗：移轉區間內都無法安排"))
        self.assertEqual(results[0]["now_date"], "2027-04-12")


if __name__ == "__main__":
    unittest.main()
