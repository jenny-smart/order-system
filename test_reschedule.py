import unittest
from unittest.mock import patch

import function.reschedule as rs
import function.typhoon_sheet_sync as tss


FOUND = [
    {"order_no": "LCA", "name": "甲", "phone": "0911", "service_date": "2026-10-29", "period": "09:00-12:00",
     "staff": "宋芳儀(2)X陳佩琪(3)"},
    {"order_no": "LCB", "name": "乙", "phone": "0922", "service_date": "2026-10-30", "period": "14:00-17:00",
     "staff": "張志豪(2)X吳承軒(1)"},
]


class _Worksheet:
    def __init__(self):
        self.values = [list(rs.SNAPSHOT_HEADERS)]

    def get_all_values(self):
        return [list(r) for r in self.values]

    def append_rows(self, rows, value_input_option=None):
        self.values.extend(list(r) for r in rows)


class _Client:
    def __init__(self, ws):
        self.ws = ws

    def open_by_key(self, key):
        ws = self.ws

        class Book:
            def worksheet(self, title):
                return ws
        return Book()


class SnapshotTests(unittest.TestCase):
    def test_record_save_list_and_load_with_date_filter(self):
        rows = rs.rows_from_orders(FOUND)
        self.assertEqual(rows[0]["orig_staff"], ["宋芳儀", "陳佩琪"])
        self.assertTrue(tss.restore_tsv(rows).split("\n")[1].startswith("LCA\t甲\t2026-10-29\t09:00-12:00\t宋芳儀、陳佩琪"))

        client = _Client(_Worksheet())
        snapshot_id = rs.save_snapshot("a@x", "2026-10-29～2026-10-30", rows, client=client)
        listed = rs.list_snapshots(client=client)
        self.assertEqual((listed[0]["id"], listed[0]["count"], listed[0]["range"]),
                         (snapshot_id, 2, "2026-10-29～2026-10-30"))

        items = rs.load_snapshot_items(snapshot_id, client=client)
        self.assertEqual([(i["order_no"], i["orig_date"], i["orig_period"], i["orig_staff"]) for i in items], [
            ("LCA", "2026-10-29", "09:00-12:00", "宋芳儀、陳佩琪"),
            ("LCB", "2026-10-30", "14:00-17:00", "張志豪、吳承軒"),
        ])
        only_30 = rs.load_snapshot_items(snapshot_id, "2026-10-30", "2026-10-30", client=client)
        self.assertEqual([i["order_no"] for i in only_30], ["LCB"])

    def test_plan_distinguishes_staff_only_and_date_changes(self):
        items = [
            {"row": 1, "order_no": "LCA", "name": "甲", "orig_date": "2026-10-29", "orig_period": "09:00-12:00",
             "orig_staff": "宋芳儀、陳佩琪"},
            {"row": 2, "order_no": "LCB", "name": "乙", "orig_date": "2026-10-30", "orig_period": "14:00-17:00",
             "orig_staff": "張志豪、吳承軒"},
            {"row": 3, "order_no": "LCC", "name": "丙", "orig_date": "2026-10-30", "orig_period": "09:00-11:00",
             "orig_staff": "吳奐"},
        ]
        now = {
            "LCA": ("2026-10-29", "09:00-12:00", ["宋芳儀", "李佩蓉"], ""),   # 同日期時段，只換了人
            "LCB": ("2026-11-02", "14:00-17:00", ["張志豪", "吳承軒"], ""),   # 日期被調整
            "LCC": ("2026-10-30", "09:00-11:00", ["吳奐"], ""),               # 沒變
        }
        with patch.object(tss.tt, "_login", lambda *a: (None, "")), \
                patch.object(tss, "_order_now", lambda s, no: now[no]):
            rows = rs.plan_return("dev", "a", "b", items)
        self.assertEqual([(r["order_no"], r["status"]) for r in rows],
                         [("LCA", "待配回原專員"), ("LCB", "待返回"), ("LCC", "已在原班表")])
        self.assertEqual(rows[0]["name"], "甲")


if __name__ == "__main__":
    unittest.main()
