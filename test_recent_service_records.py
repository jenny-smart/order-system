import unittest
from unittest.mock import Mock

import orders


def _row(order_no, date, names):
    links = "".join(f'<a href="/schedule/edit?id={i}"><span>{n}</span>(3)</a>' for i, n in enumerate(names))
    return f"<tr><td>{order_no}</td><td>x</td><td>{date} {links}</td></tr>"


class RecentServiceRecordsTests(unittest.TestCase):
    def _session(self, rows):
        resp = Mock(status_code=200, text=f"<table>{''.join(rows)}</table>")
        session = Mock()
        session.get.return_value = resp
        return session

    def test_future_orders_excluded_and_based_on_query_day(self):
        session = self._session([
            _row("LC1", "2027-02-24", ["呂筠蓁"]),
            _row("LC2", "2027-02-17", ["黃柏維"]),
            _row("LC3", "2026-11-18", ["吳承軒"]),
            _row("LC4", "2026-11-10", ["蔡立娟"]),
            _row("LC5", "2026-10-01", ["陳蕙琪"]),
            _row("LC6", "2026-09-01", ["張三"]),
        ])
        recs = orders.fetch_recent_service_records(session, "0912", "張莉莉", n=3, today="2026-11-18")
        self.assertEqual([r["order_no"] for r in recs], ["LC3", "LC4", "LC5"])

    def test_default_today_is_taiwan_today(self):
        session = self._session([_row("LC1", "2999-01-01", ["未來"]), _row("LC2", "2000-01-01", ["過去"])])
        recs = orders.fetch_recent_service_records(session, "0912", "x", n=5)
        self.assertEqual([r["order_no"] for r in recs], ["LC2"])


if __name__ == "__main__":
    unittest.main()
