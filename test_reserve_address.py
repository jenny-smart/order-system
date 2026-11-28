import unittest
from unittest.mock import patch

import function.reserve_address as ra

HTML = """<table><tr><td>檸檬保留</td><td>0939592628</td><td>
台北轉換(3,229,150)LC00017658[2,920,400]2018-09-13<br>
台北市大安區信義路四段210號4樓<a>[備註]</a> <a><i class="fa fa-trash-o"></i></a><br>
台中市北區館前路19號4樓<a>[備註]</a> <a><i class="fa fa-trash-o"></i></a><br>
新北市板橋區文化路一段270巷4號2樓<a>[備註]</a> <a><i class="fa fa-trash-o"></i></a><br>
<a>新北市板橋區文化路一段270巷4號2樓 (0) [備註]</a>
</td></tr><tr><td>別人</td><td>0912000000</td><td>台北市某路1號<a>[備註]</a><a><i class="fa fa-trash-o"></i></a></td></tr></table>"""


class ReserveAddressTest(unittest.TestCase):
    def test_parse_only_this_member_trash_addresses(self):
        self.assertEqual(ra.parse_member_addresses(HTML, "0939592628"), [
            "台北市大安區信義路四段210號4樓", "台中市北區館前路19號4樓", "新北市板橋區文化路一段270巷4號2樓"])

    def test_plan_keeps_fixed_and_deletes_all_others(self):
        addresses = ["台北市大安區信義路四段210號4樓", "臺中市北區館前路19號4樓", "新北市A路1號", "新北市B路2號"]
        self.assertEqual([p["處理"] for p in ra.plan_cleanup(addresses)], ["保留", "保留", ra.DELETE, ra.DELETE])

    def test_delete_never_touches_fixed_addresses(self):
        result = ra.delete_member_addresses("dev", "e", "p", list(ra.KEEP_ADDRESSES))
        self.assertEqual([r["結果"] for r in result], ["未刪除", "未刪除"])

    def test_cleanup_after_cancel_deletes_every_non_fixed_address(self):
        cancelled = [{"ok": True, "phone": "0939592628", "address": "新北市A路1號"}]
        member = ["台北市大安區信義路四段210號4樓", "新北市A路1號", "新北市B路2號"]
        with patch.object(ra, "list_member_addresses", return_value=member), \
                patch.object(ra, "delete_member_addresses",
                             side_effect=lambda e, m, p, addrs, phone: [{"地址": a, "結果": "已刪除", "說明": ""} for a in addrs]) as deleter:
            result = ra.cleanup_after_cancel("dev", "e", "p", cancelled)
        self.assertEqual(deleter.call_args.args[3], ["新北市A路1號", "新北市B路2號"])
        self.assertEqual([r["結果"] for r in result], ["已刪除", "已刪除"])

    def test_no_proxy_rows_means_no_lookup(self):
        with patch.object(ra, "list_member_addresses") as lister:
            self.assertEqual(ra.cleanup_after_cancel("dev", "e", "p", [{"ok": True, "address": "x"}]), [])
        lister.assert_not_called()


class CancelPageCleanupTest(unittest.TestCase):
    def test_only_reserve_account_orders_trigger_cleanup(self):
        import function.cancel_order as co
        from contextlib import nullcontext
        area = nullcontext()
        with patch.object(ra, "cleanup_after_cancel", return_value=[{"地址": "x", "結果": "已刪除"}]) as cleanup, \
                patch.object(co.st, "spinner", return_value=nullcontext()):
            self.assertEqual(co._cleanup_reserve_addresses("dev", "e", "p", [{"ok": True, "phone": "0912345678"}], area), [])
            cleanup.assert_not_called()
            result = [{"ok": True, "phone": "0939592628", "address": "新北市A路1號"}]
            self.assertEqual(co._cleanup_reserve_addresses("dev", "e", "p", result, area), [{"地址": "x", "結果": "已刪除"}])
            cleanup.assert_called_once()

    def test_cleanup_after_cancel_needs_a_cancelled_reserve_order(self):
        with patch.object(ra, "list_member_addresses") as lister:
            self.assertEqual(ra.cleanup_after_cancel("dev", "e", "p", [{"ok": True, "phone": "0912345678"},
                                                                         {"ok": False, "phone": "0939592628"}]), [])
        lister.assert_not_called()


class FastListTest(unittest.TestCase):
    class Resp:
        def __init__(self, text):
            self.text, self.status_code, self.url = text, 200, "https://x/member?keyword=0939592628"

    class Sess:
        def __init__(self, text):
            self.text = text

        def get(self, url, timeout=None):
            return FastListTest.Resp(self.text)

    def run_list(self, html):
        with patch.object(ra.co, "_new_logged_in_session", return_value=(self.Sess(html), "https://x")):
            return ra.list_member_addresses("prod", "e", "p", "0939592628")

    def test_server_html_with_trash_no_browser(self):
        self.assertEqual(self.run_list(HTML)[:2], ["台北市大安區信義路四段210號4樓", "台中市北區館前路19號4樓"])

    def test_embedded_json_no_browser(self):
        html = '<script>var m = {"memberAddressList": [{"id": 1, "address": "台北市大安區信義路四段210號4樓"}, {"id": 2, "address": "新北市A路 1號"}]};</script>'
        self.assertEqual(self.run_list(html), ["台北市大安區信義路四段210號4樓", "新北市A路1號"])


class RouteFilterTest(unittest.TestCase):
    class Route:
        def __init__(self, url, rtype):
            self.request = type("R", (), {"url": url, "resource_type": rtype})()
            self.action = None

        def abort(self):
            self.action = "abort"

        def continue_(self):
            self.action = "continue"

    def test_blocks_maps_fonts_images_keeps_backend_scripts(self):
        cases = {("https://maps.googleapis.com/maps/api/js?key=x", "script"): "abort",
                 ("https://fonts.googleapis.com/css?family=x", "stylesheet"): "abort",
                 ("https://www.lemonclean.com.tw/img/a.png", "image"): "abort",
                 ("https://backend.lemonclean.com.tw/js/jquery.min.js", "script"): "continue",
                 ("https://cdnjs.cloudflare.com/ajax/libs/vue/2.6.12/vue.min.js", "script"): "continue",
                 ("https://backend.lemonclean.com.tw/member?keyword=1", "document"): "continue"}
        for (url, rtype), expected in cases.items():
            r = self.Route(url, rtype)
            ra._route_filter(r)
            self.assertEqual(r.action, expected, url)
