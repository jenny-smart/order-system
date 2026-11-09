# -*- coding: utf-8 -*-
"""專員排班頁（/cleaner1/{id}/shift）共用解析與送出欄位組裝。

v2026.11.09-1：從 memo_system/shift.py「檸檬人批次勾班」抽出，不依賴 orders／memo，
排班管理與所有成單補檸檬人（shared/cleaner_shift.py）共用同一套解析，
避免兩邊判斷「已勾班」不一致。
"""


def parse_shift_page(html_text):
    """回傳 (token, existing, hidden_fields)。existing 例：{"2026-11-18_2": "1400-1800"}。"""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html_text or "", "html.parser")
    token_el = soup.select_one('input[name="_token"]')
    token = (token_el.get("value", "") if token_el is not None else "") or ""
    if not token:
        meta = soup.select_one('meta[name="csrf-token"]')
        token = (meta.get("content", "") if meta is not None else "") or ""
    hidden_fields = {}
    for el in soup.select('input[type="hidden"]'):
        name = el.get("name", "") or ""
        if name and name != "_token":
            hidden_fields[name] = el.get("value", "") or ""
    existing = {}
    for el in soup.select('input[name^="shift_"][checked]'):
        value = str(el.get("value", "") or "").strip()
        if value and value != "0":
            existing[el.get("name", "")[len("shift_"):]] = value
    return token, existing, hidden_fields


def build_shift_payload(token, merged, hidden_fields=None):
    payload = {f"shift_{k}": v for k, v in (merged or {}).items()}
    payload["_token"] = token
    if hidden_fields:
        payload.update(hidden_fields)
    return payload
