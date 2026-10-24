import unittest
from unittest.mock import Mock, patch

import quick_order as q


class LazyDiscountCodeTest(unittest.TestCase):
    def _run(self, slot_error=None):
        coupon = Mock(return_value="C123")
        session = Mock()
        lookup = {"session": session, "phone": "", "member_payload": {"member": {"member_id": "1", "email": "m@example.com"}}}
        retry = Mock(side_effect=slot_error) if slot_error else Mock(return_value=("[]", "token", {}))
        with patch.object(q, "resolve_backend_booking_address", return_value=({"address": "新北市中和區測試路1號"}, {}, {})), \
             patch.object(q, "_configure_environment", return_value="https://example.invalid"), \
             patch.object(q, "_get_booking_token_for_payway", return_value="token"), \
             patch.object(q, "_fetch_csrf_from_url", return_value="token"), \
             patch.object(q, "calculate_hour", return_value={"data": {"hour": 4, "price": 8000, "fare": 0}}), \
             patch.object(q, "_query_booking_slot_with_lemon_retry", retry), \
             patch.object(q, "list_order_numbers_for_phone", side_effect=[set(), {"NEW"}, {"NEW"}, {"NEW"}, {"NEW"}]), \
             patch.object(q, "_fetch_purchase_blocks_for_phone", side_effect=[[]] + [[{"order_no": "NEW", "lines": ["新北市中和區測試路1號"]}]] * 5), \
             patch.object(q, "_parse_service_date_time_loose", return_value=("2026-10-25", "14:00-18:00")), \
             patch.object(q, "_extract_payway_line", return_value="信用卡"), \
             patch.object(q, "fetch_order_meta_by_order_no", return_value={}), \
             patch.object(q, "_fetch_purchase_block_for_order_no", return_value={"lines": ["總金額：0"]}), \
             patch.object(q, "_check_order_no_duplicate", return_value=(False, 1)), \
             patch.object(q.time, "sleep"):
            try:
                result = q.quick_create_order(
                    "dev", "信用卡", "", lookup, "新北市中和區測試路1號", "1",
                    "2026-10-25", "14:00-18:00", "4", discount_code=coupon,
                )
            except Exception as exc:
                result = exc
        return coupon, session, result

    def test_coupon_created_after_slot_found_and_submitted(self):
        coupon, session, result = self._run()
        coupon.assert_called_once()
        self.assertEqual(session.post.call_args.kwargs["data"]["discount_code"], "C123")
        self.assertEqual(result["discount_code"], "C123")

    def test_no_coupon_when_slot_missing(self):
        coupon, session, result = self._run(slot_error=Exception("後台未回傳可預約時段"))
        self.assertIsInstance(result, Exception)
        coupon.assert_not_called()
        session.post.assert_not_called()

    def test_sections_on_date_lists_backend_sections(self):
        raw = '[{"date":"2026-10-25","section":"08:30-12:30"},{"date":"2026-10-25","section":"14:00-18:00"},{"date":"2026-10-24","section":"09:00-12:00"}]'
        self.assertEqual(q._sections_on_date(raw, "2026-10-25"), "08:30-12:30；14:00-18:00")


class CouponTitleTest(unittest.TestCase):
    def test_title_is_customer_name(self):
        self.assertEqual(q._coupon_title({"member": {"name": "吳惠盟"}}, "LC00216063"), "吳惠盟6063")
        self.assertEqual(q._coupon_title({"member": {"name": "吳惠盟"}}, "LC00216063", amount=8400), "吳惠盟6063-8400")
        self.assertEqual(q._coupon_title({"name": "陳佳吟"}, "", "0910828425"), "陳佳吟8425")

    def test_title_without_name_uses_tail_only(self):
        self.assertEqual(q._coupon_title({"member": {}}, "TT00217663"), "7663")


if __name__ == "__main__":
    unittest.main()
