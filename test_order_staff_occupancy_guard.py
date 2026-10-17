import unittest
from unittest.mock import Mock, patch

import quick_order as q


class _Response:
    def __init__(self, text, status_code=200, url="https://backend.lemonclean.com.tw/purchase"):
        self.text = text
        self.status_code = status_code
        self.url = url


class _Session:
    def __init__(self, html):
        self.html = html
        self.get_calls = []
        self.post_calls = []

    def get(self, url, **kwargs):
        self.get_calls.append((url, kwargs))
        return _Response(self.html)

    def post(self, url, **kwargs):
        self.post_calls.append((url, kwargs))
        return _Response("", status_code=200, url=url)


class OccupiedStaffLookupTests(unittest.TestCase):
    def test_parses_grey_unassigned_allowlist_for_exact_period(self):
        html = """
        <table>
          <tr><th>日期</th><th>09:00-16:00</th><th>14:00-17:00</th></tr>
          <tr><td>10-18（日）</td><td>
            <p style="background-color: #616161">
              <span>未配班 3 人</span>
              <span>6檸檬人40</span><span>48汪才開3</span><span>8×游宜璙2</span>
            </p>
          </td><td><p style="background:#616161"><span>未配班 1 人</span><span>4陳宜芝2</span></p></td></tr>
        </table>
        """
        parsed = q._parse_schedule_unassigned_staff(
            html, "2026-10-18", "09:00-16:00",
        )
        self.assertEqual(parsed["count"], 3)
        self.assertEqual(parsed["names"], {"檸檬人4", "汪才開", "游宜璙"})

    def test_finds_only_overlapping_other_order_staff(self):
        html = """
        <table>
          <tr><td>LC00217273</td><td>2026-10-18 (日) 09:00 - 16:00
            <a href="/schedule/edit?date=2026-10-18&purchase_id=17273">檸檬人2(0)</a>
            <a href="/schedule/edit?date=2026-10-18&purchase_id=17273">檸檬人1(0)</a>
          </td></tr>
          <tr><td>LC00217353</td><td>2026-10-18 (日) 09:00 - 16:00
            <a href="/schedule/edit?date=2026-10-18&purchase_id=17353">檸檬人3(0)</a>
          </td></tr>
          <tr><td>LC00218000</td><td>2026-10-18 (日) 16:00 - 18:00
            <a href="/schedule/edit?date=2026-10-18&purchase_id=18000">檸檬人4(0)</a>
          </td></tr>
        </table>
        """
        session = _Session(html)
        occupied = q._get_occupied_staff_for_period(
            session, "https://backend.lemonclean.com.tw",
            "2026-10-18", "09:00-16:00", exclude_purchase_id="17353",
        )
        self.assertEqual(occupied, {"檸檬人1", "檸檬人2"})

    def test_login_page_fails_closed(self):
        session = _Session('<form action="/login"><input type="password"></form>')
        session.get = Mock(return_value=_Response(
            '<input type="password">', url="https://backend.lemonclean.com.tw/login",
        ))
        with self.assertRaisesRegex(RuntimeError, "登入已失效"):
            q._get_occupied_staff_for_period(
                session, "https://backend.lemonclean.com.tw", "2026-10-18", "09:00-16:00",
            )

    def test_conversion_lookup_fails_closed_when_target_order_is_missing(self):
        html = """
        <table><tr><td>LC00217273</td><td>2026-10-18 (日) 09:00 - 16:00
          <a href="/schedule/edit?date=2026-10-18&purchase_id=17273">檸檬人2(0)</a>
        </td></tr></table>
        """
        with self.assertRaisesRegex(RuntimeError, "找不到目標訂單"):
            q._get_occupied_staff_for_period(
                _Session(html), "https://backend.lemonclean.com.tw",
                "2026-10-18", "09:00-16:00", exclude_purchase_id="99999",
            )


class AssignmentOccupancyGuardTests(unittest.TestCase):
    def test_conversion_skips_staff_owned_by_other_orders(self):
        session = _Session("")
        slots = [
            {"檸檬人1": "11", "檸檬人3": "13"},
            {"檸檬人2": "12", "檸檬人4": "14"},
        ]
        with patch.object(q, "_fetch_order_edit_id", return_value="999"), \
             patch.object(q, "_get_schedule_edit_info", return_value=("csrf", ["91", "92"], slots)), \
             patch.object(q, "_get_unassigned_staff_for_period", return_value={"count": 2, "names": {"檸檬人3", "檸檬人4"}}), \
             patch.object(q, "_get_occupied_staff_for_period", return_value={"檸檬人1", "檸檬人2"}):
            result = q.assign_lemon_cleaners_to_order(
                session, "https://backend.lemonclean.com.tw", "LC00999",
                "2026-10-18", "09:00-16:00", "2", allow_auto_lemon_shift=False,
            )
        self.assertTrue(result["success"])
        self.assertEqual(result["assigned"], ["檸檬人3", "檸檬人4"])
        posted = session.post_calls[0][1]["data"]
        self.assertIn(("shiftId[0]", "13"), posted)
        self.assertIn(("shiftId[1]", "14"), posted)
        self.assertNotIn(("shiftId[0]", "11"), posted)

    def test_conversion_stops_if_candidate_becomes_occupied_before_post(self):
        session = _Session("")
        slots = [{"檸檬人3": "13"}]
        with patch.object(q, "_fetch_order_edit_id", return_value="999"), \
             patch.object(q, "_get_schedule_edit_info", return_value=("csrf", ["91"], slots)), \
             patch.object(q, "_get_unassigned_staff_for_period", return_value={"count": 1, "names": {"檸檬人3"}}), \
             patch.object(q, "_get_occupied_staff_for_period", side_effect=[set(), {"檸檬人3"}]):
            result = q.assign_lemon_cleaners_to_order(
                session, "https://backend.lemonclean.com.tw", "LC00999",
                "2026-10-18", "09:00-16:00", "1", allow_auto_lemon_shift=False,
            )
        self.assertFalse(result["success"])
        self.assertIn("已被其他重疊訂單占用", result["message"])
        self.assertEqual(session.post_calls, [])

    def test_booking_stops_before_submit_when_returned_staff_is_occupied(self):
        with patch.object(q, "_get_unassigned_staff_for_period", return_value={"count": 2, "names": {"檸檬人2", "檸檬人5"}}), \
             patch.object(q, "_get_occupied_staff_for_period", return_value={"檸檬人2"}):
            with self.assertRaisesRegex(Exception, "已停止成立訂單"):
                q._assert_booking_staff_unassigned(
                    object(), "https://backend.lemonclean.com.tw",
                    "2026-10-18", "09:00-16:00", ["檸檬人2", "檸檬人5"],
                )

    def test_booking_rejects_candidate_not_in_grey_unassigned_list(self):
        with patch.object(q, "_get_unassigned_staff_for_period", return_value={"count": 2, "names": {"檸檬人3", "檸檬人4"}}):
            with self.assertRaisesRegex(Exception, "不在灰底"):
                q._assert_booking_staff_unassigned(
                    object(), "https://backend.lemonclean.com.tw",
                    "2026-10-18", "09:00-16:00", ["檸檬人1", "檸檬人3"], needed_people=2,
                )


if __name__ == "__main__":
    unittest.main()
