# -*- coding: utf-8 -*-
"""週末提醒「確認收到」連結：產生連結、向 line-lemonsystem Worker 查詢確認結果。

更新記錄：
2026-11-12（新增）
- 提醒訊息附上每張訂單專屬連結 {Worker 網址}/c/{訂單編號}/{YYYYMMDD}/{簽章}；客人點開後按「確認收到」，
  Worker 記錄確認時間。客服照常在 chat.line.biz 發訊息，不需要 LINE Webhook，也不需要客人的 LINE user ID
  （對話連結上的 ID 與 Webhook 的 user ID 不同，無法用來對應文字回覆）。
- 簽章＝HMAC-SHA256(LINE_REMINDER_API_KEY, "confirm|訂單編號|YYYY-MM-DD") 十六進位前 16 碼，
  與 Worker（worker/src/confirm.js）相同算法；金鑰要和 Worker 的 REMINDER_API_KEY 相同。
- 沒有設定 LINE_REMINDER_API_KEY 時不產生連結，提醒訊息維持原樣（只請客人回覆「已收到」）。
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re

DEFAULT_API_URL = "https://line-lemon-webhook.jenny-74e.workers.dev"
_ORDER_NO_RE = re.compile(r"^[A-Z]{2}\d{6,12}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _setting(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value is not None and str(value).strip():
        return str(value).strip()
    try:
        import streamlit as st

        value = st.secrets.get(name, "")
        if value is not None and str(value).strip():
            return str(value).strip()
    except Exception:
        pass
    return default


def api_url() -> str:
    return _setting("LINE_REMINDER_API_URL", DEFAULT_API_URL).rstrip("/")


def api_key() -> str:
    return _setting("LINE_REMINDER_API_KEY")


def signature(key: str, order_no: str, service_date: str) -> str:
    message = f"confirm|{order_no}|{service_date}".encode("utf-8")
    return hmac.new(str(key).encode("utf-8"), message, hashlib.sha256).hexdigest()[:16]


def confirm_url(order_no, service_date, url: str | None = None, key: str | None = None) -> str:
    """訂單的確認連結；沒有金鑰或訂單編號／日期格式不對時回傳空字串。"""
    order_no, service_date = str(order_no or "").strip(), str(service_date or "").strip()
    key = api_key() if key is None else key
    if not key or not _ORDER_NO_RE.match(order_no) or not _DATE_RE.match(service_date):
        return ""
    base = (api_url() if url is None else url).rstrip("/")
    return f"{base}/c/{order_no}/{service_date.replace('-', '')}/{signature(key, order_no, service_date)}"


def fetch_confirmations(keys, url: str | None = None, key: str | None = None, timeout: int = 20) -> dict:
    """查詢已確認的提醒；回傳 {"訂單編號|YYYY-MM-DD": 確認時間 ISO 字串}。"""
    import requests

    keys = sorted({str(k).strip() for k in keys if str(k).strip()})
    if not keys:
        return {}
    key = api_key() if key is None else key
    if not key:
        raise RuntimeError("尚未設定 LINE_REMINDER_API_KEY")
    base = (api_url() if url is None else url).rstrip("/")
    found = {}
    for start in range(0, len(keys), 200):
        response = requests.post(
            f"{base}/api/confirmations/status",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"keys": keys[start:start + 200]},
            timeout=timeout,
        )
        try:
            data = response.json()
        except ValueError:
            data = {}
        if not response.ok:
            raise RuntimeError(data.get("error") or f"確認查詢回傳 HTTP {response.status_code}")
        for item in data.get("confirmations", []):
            if item.get("reminder_key") and item.get("confirmed_at"):
                found[str(item["reminder_key"])] = str(item["confirmed_at"])
    return found
