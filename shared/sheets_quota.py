# 移植自 orders-system sheets_quota.py（fbf485d）：Google Sheets 讀寫節流與 429 配額重試。
"""Pace Sheets reads/writes and retry only explicitly rejected quota requests."""
import threading
import time
from gspread.http_client import HTTPClient
from gspread.exceptions import APIError

_lock = threading.Lock()
_last = {}


def pace(method):
    category = 'read' if method.lower() == 'get' else 'write'
    with _lock:
        now = time.monotonic()
        delay = max(0, _last.get(category, now - 2) + 2 - now)
        if delay:
            time.sleep(delay)
        _last[category] = time.monotonic()


class QuotaHTTPClient(HTTPClient):
    def request(self, method, endpoint, *args, **kwargs):
        for attempt in range(7):
            pace(method)
            try:
                return super().request(method, endpoint, *args, **kwargs)
            except APIError as exc:
                if exc.response.status_code != 429 or attempt == 6:
                    raise
                # Never retry backend booking or uncertain network/5xx failures.
                time.sleep(min(2 ** (attempt + 1), 32))
