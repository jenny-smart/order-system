import unittest
from types import SimpleNamespace
from unittest.mock import patch

import function.cancel_order as co


def _run(pages, **kwargs):
    calls = []

    def get(url, params=None, **kw):
        calls.append(dict(params))
        return SimpleNamespace(status_code=200, text=params["page"])

    def cards(text):
        page = int(text)
        return [{"order_no": f"LC{i}", "info": info} for i, info in enumerate(pages[page - 1] if page <= len(pages) else [])]

    def item(block):
        date, status, name, phone = block["info"]
        return {"purchase_id": block["order_no"], "order_no": block["order_no"], "name": name, "phone": phone,
                "service_date": date, "period": "09:00-12:00", "payment_status": status}

    with patch.object(co, "_new_logged_in_session", return_value=(SimpleNamespace(get=get), "https://x")), \
            patch.object(co.orders, "extract_order_cards_from_purchase_html", side_effect=cards), \
            patch.object(co, "_order_from_block", side_effect=item):
        rows = co.find_orders_for_cancel("dev", "e", "p", kwargs.pop("phone", ""), "2026-12-01", "2027-02-28", **kwargs)
    return rows, calls


class CancelOrderSearchTest(unittest.TestCase):
    def test_blank_phone_searches_date_range_for_all_customers(self):
        page = [("2026-12-05", "已付款", "王小明", "0912345678"), ("2026-12-06", "待付款", "李小華", "0922333444"),
                ("2026-11-30", "已付款", "陳大文", "0933444555"), ("2027-01-10", "已付款", "王大明", "0944555666")]
        rows, calls = _run([page])
        self.assertEqual([r["name"] for r in rows], ["王小明", "王大明"])
        self.assertEqual((calls[0]["phone"], calls[0]["clean_date_s"], calls[0]["clean_date_e"]), ("", "2026-12-01", "2027-02-28"))
        named, _ = _run([page], name_keyword="王 小明")
        self.assertEqual([r["name"] for r in named], ["王小明"])

    def test_phone_search_keeps_phone_only_filter(self):
        rows, calls = _run([[("2026-12-05", "已付款", "王小明", "0912345678")]], phone="0912-345-678")
        self.assertEqual(len(rows), 1)
        self.assertEqual((calls[0]["phone"], calls[0]["clean_date_s"]), ("0912345678", ""))

    def test_bad_phone_is_rejected_and_too_many_orders_without_phone_stops(self):
        with self.assertRaises(ValueError):
            _run([[]], phone="12345")
        full = [("2026-12-05", "已付款", "王小明", "0912345678")] * 20
        with patch.object(co, "DATE_ONLY_MAX_PAGES", 2), self.assertRaises(ValueError):
            _run([full, full, full], max_pages=1)


class CancelOrdersProgressTest(unittest.TestCase):
    def test_progress_callback_reports_each_order_including_failures(self):
        posted = []

        def post(url, **kw):
            posted.append(url)
            return SimpleNamespace(status_code=500 if url.endswith("/2") else 200)

        session = SimpleNamespace(get=lambda *a, **k: SimpleNamespace(text=""), post=post)
        rows = [{"purchase_id": str(i), "order_no": f"TT{i}"} for i in (1, 2, 3)]
        seen = []
        with patch.object(co, "_new_logged_in_session", return_value=(session, "https://x")), \
                patch.object(co, "_csrf_from_html", return_value="tok"), \
                patch.object(co, "_update_cancel_notes", return_value=(True, "")):
            results = co.cancel_orders("dev", "e", "p", rows, "不需退款", "測試取消", "", "",
                                       progress_callback=lambda done, total, row: seen.append((done, total, row["ok"])))
        self.assertEqual(seen, [(1, 3, True), (2, 3, False), (3, 3, True)])
        self.assertEqual([r["ok"] for r in results], [True, False, True])


if __name__ == "__main__":
    unittest.main()
