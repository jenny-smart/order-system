import unittest
from unittest.mock import Mock

import shared.booking_flow as flow


class BookingFlowContractTest(unittest.TestCase):
    def paid_payload(self):
        return {
            "date_s": "2027-01-02",
            "payway": "",
            "invoice_type": "2",
            "carrier_type_id": "2",
            "carrier_info": "/1P06KYP",
            "company_title": "",
            "company_no": "",
            "donate_code": "8585",
        }

    def test_payment_method_is_the_route_difference(self):
        self.assertEqual(flow.route_for("信用卡").path, "/booking/single")
        self.assertEqual(flow.route_for("ATM").path, "/booking/single")
        self.assertEqual(flow.route_for("儲值金").path, "/booking/stored_value_routine")

    def test_paid_order_uses_one_radio_and_keeps_invoice(self):
        data = flow.build_submit_data(self.paid_payload(), "token", "信用卡", "2027-01-02_08:30-12:30")
        self.assertEqual(data["datePeriod"], "2027-01-02_08:30-12:30")
        self.assertEqual(data["payway"], "1")
        self.assertEqual(data["carrier_info"], "/1P06KYP")
        with self.assertRaisesRegex(ValueError, "一次只能"):
            flow.build_submit_data(self.paid_payload(), "token", "ATM", ["a", "b"])

    def test_stored_value_uses_multiple_checkboxes_without_invoice(self):
        pairs = flow.build_submit_pairs(self.paid_payload(), "token", "儲值金", ["a", "b"])
        self.assertEqual([value for key, value in pairs if key == "date_list[]"], ["a", "b"])
        sent = dict(pairs)
        self.assertEqual(sent["payway"], "4")
        self.assertNotIn("invoice_type", sent)
        self.assertNotIn("carrier_info", sent)

    def test_invoice_rules_cover_donation_carriers_paper_and_company(self):
        cases = [
            {"invoice_type": "1", "donate_code": "8585"},
            {"invoice_type": "2", "carrier_type_id": "1", "carrier_info": "a@example.com"},
            {"invoice_type": "2", "carrier_type_id": "2", "carrier_info": "/1P06KYP"},
            {"invoice_type": "2", "carrier_type_id": "4", "carrier_info": ""},
            {"invoice_type": "3", "company_title": "測試公司", "company_no": "12345678"},
        ]
        for invoice in cases:
            with self.subTest(invoice=invoice):
                payload = {**self.paid_payload(), **invoice}
                flow.build_submit_data(payload, "token", "ATM", "slot")

    def test_stored_value_count_means_failed_orders(self):
        response = Mock()
        response.json.return_value = {"count": 0}
        self.assertEqual(flow.stored_value_failed_count(response), 0)
        response.json.return_value = {"count": 2}
        self.assertEqual(flow.stored_value_failed_count(response), 2)


if __name__ == "__main__":
    unittest.main()
