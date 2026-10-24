import unittest
from unittest.mock import patch

import function.reserve_optimizer as ro


def _schedule(people):
    return {"09:00-12:00": {"unassigned_people": people}, "14:00-17:00": {"unassigned_people": people}}


class ReserveBatchTest(unittest.TestCase):
    def run_batch(self, plan_rows, outcomes, people=20):
        calls = []

        def fake_multi(env, region, lookup, address, clean_type_id, slots, hour, person="2", extra_fields=None):
            calls.append(list(slots))
            outcome = outcomes(len(calls), slots)
            return outcome

        lookup = {"session": object(), "base_url": "https://example.invalid"}
        with patch.object(ro, "fetch_schedule_html", return_value=""), \
             patch.object(ro, "parse_schedule_unassigned", side_effect=lambda html, d: _schedule(people)), \
             patch.object(ro.qo, "quick_create_stored_value_orders", side_effect=fake_multi), \
             patch.object(ro, "_finish_reserve_order", side_effect=lambda s, b, no, d, p, st, a, bid: {"success": True, "order_no": no, "customer_memo_ok": True}), \
             patch.object(ro, "_assert_supported_env"):
            result = ro.create_reserve_orders_batch(
                env_name="dev", lookup_result=lookup, region="台北", address="台北市大安區信義路四段210號4樓",
                plan_rows=plan_rows, sleep_seconds=0,
            )
        return calls, result

    def test_each_round_submits_all_remaining_slots_at_once(self):
        rows = [
            {"service_date": "2027-01-21", "period": "09:00-12:00", "reserve_order_target": 2},
            {"service_date": "2027-01-21", "period": "14:00-17:00", "reserve_order_target": 1},
            {"service_date": "2027-01-22", "period": "09:00-12:00", "reserve_order_target": 2},
        ]
        counter = iter(range(100))
        calls, result = self.run_batch(rows, lambda n, slots: {
            "orders": [{"order_no": f"TT{next(counter)}", "slot": s, "date": s.split("_")[0], "period_s": s.split("_")[1]} for s in slots],
            "unavailable": [], "not_created": [],
        })
        self.assertEqual(calls[0], ["2027-01-21_09:00-12:00", "2027-01-21_14:00-17:00", "2027-01-22_09:00-12:00"])
        self.assertEqual(calls[1], ["2027-01-21_09:00-12:00", "2027-01-22_09:00-12:00"])
        self.assertEqual(len(calls), 2)
        self.assertEqual(result["success_count"], 5)

    def test_slot_without_staff_stops_only_that_slot(self):
        rows = [
            {"service_date": "2027-01-21", "period": "09:00-12:00", "reserve_order_target": 2},
            {"service_date": "2027-01-21", "period": "14:00-17:00", "reserve_order_target": 2},
        ]
        counter = iter(range(100))
        calls, result = self.run_batch(rows, lambda n, slots: {
            "orders": [{"order_no": f"TT{next(counter)}", "slot": s, "date": s.split("_")[0], "period_s": s.split("_")[1]} for s in slots if "09:00" in s],
            "unavailable": [s for s in slots if "14:00" in s], "not_created": [],
        })
        self.assertEqual(calls[1], ["2027-01-21_09:00-12:00"])
        self.assertEqual(result["success_count"], 2)
        self.assertTrue(any("無可預約人力" in r.get("message", "") for r in result["results"]))

    def test_low_market_people_stops_before_submit(self):
        rows = [{"service_date": "2027-01-21", "period": "09:00-12:00", "reserve_order_target": 3, "market_people_target": 6}]
        calls, result = self.run_batch(rows, lambda n, slots: {"orders": [], "unavailable": [], "not_created": []}, people=7)
        self.assertEqual(calls, [])
        self.assertTrue(result["results"][0]["stopped"])


if __name__ == "__main__":
    unittest.main()
