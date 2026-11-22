# -*- coding: utf-8 -*-
"""清空未配班檸檬人：同一天另一個時段排在訂單上（含檸檬保留單）時，只留訂單時段，不整天清空。"""
import unittest
from unittest.mock import MagicMock, patch

from memo_system import shift

GREY = '<p style="background:#616161"><span>未配班 1 人</span><br><span>{}</span></p>'
HEADER = ("<tr><td></td><td>08:30-12:30</td><td>09:00-12:00</td><td>09:00-11:00</td>"
          "<td>14:00-16:00</td><td>14:00-17:00</td><td>14:00-18:00</td></tr>")
WEEK = (
    '<input id="date" value="2027-02-01"><table>' + HEADER +
    # 2/1：檸檬人3 下午在檸檬保留單，上午兩個時段出現在未配班
    "<tr><td>02-01<br>(一)</td><td>11-02<br>李尚儒 V<br>48宋品鈞3 X<br>4傅俊峰2</td>"
    "<td>11-02<br>蘇玉珮 V<br>8黃婕茹3" + GREY.format("8檸檬人30") + "</td>"
    "<td>" + GREY.format("8檸檬人30") + "</td><td></td>"
    "<td>11-02<br>檸檬保留 V<br>8吳爽1 X<br>8張志豪3<br>11-02<br>檸檬保留 V<br>8檸檬人30 X<br>463李佳芸1</td>"
    "<td></td></tr>" + HEADER +
    # 2/3：檸檬人4 上午在姚竹音的單，下午三個時段出現在未配班
    "<tr><td>02-03<br>(三)</td><td></td><td>11-02<br>姚竹音 V<br>48檸檬人40 X<br>4李佳芸1 D</td><td></td>"
    "<td>" + GREY.format("48檸檬人40") + "</td><td>" + GREY.format("48檸檬人40") + "</td>"
    "<td>" + GREY.format("48檸檬人40") + "</td></tr>"
    # 2/5：檸檬人7 沒有任何訂單，照舊整天清空
    + HEADER + "<tr><td>02-05<br>(五)</td><td>" + GREY.format("4檸檬人70") + "</td><td></td><td></td><td></td><td></td><td></td></tr>"
    "</table>"
)


class KeepOrderSlotTest(unittest.TestCase):
    def test_period_to_slot(self):
        self.assertEqual(shift.period_to_slot("14:00-17:00"), ("2", "1400-1700"))
        self.assertEqual(shift.period_to_slot("08:30-12:30"), ("1", "0830-1230"))
        self.assertEqual(shift.period_to_slot("09:00-18:00"), ("all", "8"))
        self.assertEqual(shift.period_to_slot("09:00-16:00"), ("all", "6"))
        self.assertEqual(shift.keep_slots_for_periods(["09:00-12:00", "08:30-12:30"]), {"1": "0830-1230"})
        self.assertEqual(shift.keep_slots_for_periods(["09:00-12:00", "09:00-18:00"]), {"all": "8"})

    def test_entries_carry_order_periods(self):
        with patch.object(shift.memo, "session_get", return_value=MagicMock(text=WEEK)):
            entries = shift.find_unassigned_lemon_bookings(None, "2027-02-01")
        got = {(e["date"], e["name"]): e["order_periods"] for e in entries}
        self.assertEqual(got, {
            ("2027-02-01", "檸檬人3"): ["14:00-17:00"],
            ("2027-02-03", "檸檬人4"): ["09:00-12:00"],
            ("2027-02-05", "檸檬人7"): [],
        })

    def test_clear_keeps_order_slot_only(self):
        with patch.object(shift.memo, "session_get", return_value=MagicMock(text=WEEK)):
            entries = shift.find_unassigned_lemon_bookings(None, "2027-02-01")
        existing = {
            "檸檬人3": {"2027-02-01_all": "8", "2027-02-10_all": "8"},
            "檸檬人4": {"2027-02-03_1": "0900-1200", "2027-02-03_2": "1400-1800"},
            "檸檬人7": {"2027-02-05_all": "8"},
        }
        submitted = {}

        def fake_state(_s, cid, _month):
            return "tok", dict(existing[cid]), {"_method": "PUT"}

        def fake_submit(_s, cid, _tok, merged, month=None, hidden_fields=None):
            submitted[cid] = merged

        with patch.object(shift, "find_cleaner_id_by_name", side_effect=lambda _s, n: n), \
             patch.object(shift, "get_shift_page_state", side_effect=fake_state), \
             patch.object(shift, "submit_shift_payload", side_effect=fake_submit):
            results = shift.clear_unassigned_lemon_bookings(None, entries)

        self.assertEqual(submitted["檸檬人3"], {"2027-02-01_2": "1400-1700", "2027-02-10_all": "8"})
        self.assertEqual(submitted["檸檬人4"], {"2027-02-03_1": "0900-1200"})
        self.assertEqual(submitted["檸檬人7"], {})
        self.assertFalse(any(r["errors"] for r in results))


if __name__ == "__main__":
    unittest.main()
