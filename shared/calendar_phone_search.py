# -*- coding: utf-8 -*-
"""VIP 客人用電話查 Google 日曆：有行程才給日曆搜尋連結，沒有就顯示「無日曆」。

給 LINE 通知產生器、服務異動、建立舊客訂單共用。
日曆事件標題慣例是「姓名-地址標籤,電話」，所以用電話做全文搜尋，
再用數字比對確認事件內真的有這支電話，避免模糊比對誤判。
"""
from __future__ import annotations

import re
from decimal import Decimal
from urllib.parse import quote

CALENDAR_SEARCH_URL = "https://calendar.google.com/calendar/r/search?q="
_EVENT_FIELDS = ("summary", "description", "location")


def normalize_phone(phone) -> str:
    digits = re.sub(r"\D", "", str(phone or ""))
    if digits.startswith("886") and len(digits) == 12:
        digits = "0" + digits[3:]
    return digits


def calendar_search_url(phone) -> str:
    digits = normalize_phone(phone)
    return CALENDAR_SEARCH_URL + quote(digits) if digits else ""


def is_vip_balance(balance) -> bool:
    """VIP＝會員儲值金（含購物金）餘額 > 0，與服務單價分級同一規則。"""
    if balance in (None, ""):
        return False
    try:
        return Decimal(str(balance).replace(",", "")) > 0
    except Exception:
        return False


def member_balance(member_payload):
    """從後台 get_member 回傳取餘額；查不到回傳 None（不猜）。"""
    if not member_payload:
        return None
    try:
        from service_pricing import account_balance
        return account_balance(member_payload)
    except Exception:
        return None


def _event_has_phone(event, digits) -> bool:
    text = "\n".join(str(event.get(field) or "") for field in _EVENT_FIELDS)
    return digits in re.sub(r"\D", "", text)


def find_events_by_phone(service, calendar_ids, phone, max_results=10):
    """在各地區日曆用電話搜尋，回傳真的含這支電話的事件。"""
    digits = normalize_phone(phone)
    if len(digits) < 8:
        return []
    found = []
    for calendar_id in dict.fromkeys(cid for cid in calendar_ids if cid):
        payload = service.events().list(
            calendarId=calendar_id, q=digits, maxResults=max_results, singleEvents=False,
        ).execute()
        for event in payload.get("items", []) or []:
            if _event_has_phone(event, digits):
                found.append({**event, "_calendar_id": calendar_id})
    return found


def lookup_calendar_by_phone(phone, service=None, calendar_map=None):
    """回傳 {"phone", "count", "url", "error"}；count=0 代表無日曆。"""
    digits = normalize_phone(phone)
    result = {"phone": digits, "count": 0, "url": "", "error": ""}
    if not digits:
        result["error"] = "無電話"
        return result
    try:
        if service is None or calendar_map is None:
            import orders
            service = service or orders.build_gcal_service()
            calendar_map = calendar_map if calendar_map is not None else orders.GOOGLE_CALENDAR_MAP
        events = find_events_by_phone(service, list(calendar_map.values()), digits)
    except Exception as exc:
        result["error"] = str(exc)
        return result
    result["count"] = len(events)
    if events:
        result["url"] = calendar_search_url(digits)
    return result


def render_calendar_link(st, info, key):
    """畫面顯示：有行程給連結，沒有顯示「無日曆」。info 為 lookup_calendar_by_phone 結果。"""
    if not info:
        return
    if info.get("error"):
        st.caption(f"📅 日曆查詢失敗：{info['error']}")
    elif info.get("count"):
        st.link_button(f"📅 日曆查詢結果（{info['phone']}，{info['count']} 筆）", info["url"], key=key)
    else:
        st.caption(f"📅 無日曆（{info.get('phone')}）")
