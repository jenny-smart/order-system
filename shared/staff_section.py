# -*- coding: utf-8 -*-
"""專員/班別 section 的後台查詢與 HTML 解析、姓名格式化，供 orders.py／quick_order.py 共用。

純解析函式（clean_staff_name/normalize_staff_display/format_staff_from_cleaners/
extract_cleaners_from_section_response/slot_exists_in_section_response）不含網路
呼叫；get_section_raw 是唯一對後台發 request 的函式。
"""

import re
import json
import html

from bs4 import BeautifulSoup

import orders


def get_section_raw(session, order_data, token, date_slot):
    data = order_data.copy()
    data["_token"] = token
    data["date_list[]"] = date_slot

    resp = session.post(orders.GET_SECTION_URL, data=data, headers=orders.HEADERS, allow_redirects=True)
    return resp.text if resp.status_code == 200 else ""


def extract_cleaners_from_section_response(raw_text, date_slot):
    """
    從 get_section 回傳抓指定日期/時段的人員。
    支援 JSON list：
    [{"date":"2026-05-14","section":"14:00-18:00","cleaner":["胡偉勝"]}]
    """
    if not raw_text:
        return []

    date_part, period_part = date_slot.split("_", 1)
    raw = str(raw_text)

    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            data = data.get("data") or data.get("result") or data.get("sections") or []
        if isinstance(data, list):
            for item in data:
                if not isinstance(item, dict):
                    continue
                item_date = str(item.get("date", "")).strip()
                item_section = str(item.get("section", "")).strip().replace(" ", "")
                if item_date == date_part and item_section == period_part.replace(" ", ""):
                    cleaners = (
                        item.get("cleaner")
                        or item.get("cleaners")
                        or item.get("staff")
                        or item.get("staffs")
                        or item.get("cleaner_name")
                        or item.get("cleanerName")
                        or item.get("name")
                        or item.get("text")
                        or item.get("title")
                        or ""
                    )
                    if isinstance(cleaners, list):
                        return [str(x).strip().lstrip("＊*") for x in cleaners if str(x).strip()]
                    if isinstance(cleaners, str) and cleaners.strip():
                        m = re.search(r"[（(]([^）)]+)[）)]", cleaners)
                        text = m.group(1) if m else cleaners
                        return [x.strip().lstrip("＊*") for x in re.split(r"[,，、/]+", text) if x.strip()]
    except Exception:
        pass

    text = html.unescape(raw)
    try:
        text = BeautifulSoup(text, "html.parser").get_text(" ", strip=True)
    except Exception:
        pass

    compact = re.sub(r"\s+", "", text)
    d = date_part
    p = period_part.replace(" ", "")
    idx = compact.find(d)
    if idx >= 0:
        nearby = compact[idx:idx + 600]
        pidx = nearby.find(p)
        if pidx >= 0:
            nearby = nearby[pidx:pidx + 500]
            m = re.search(r"[（(]([^）)]+)[）)]", nearby)
            if m:
                return [x.strip().lstrip("＊*") for x in re.split(r"[,，、/]+", m.group(1)) if x.strip()]

    return []


def clean_staff_name(name):
    """
    將班表/訂單頁的人名清成純姓名。
    例：
    - 00洪暐智(4) -> 洪暐智
    - X蔡佩玲(1) -> 蔡佩玲
    - ＊黃惟芊 -> 黃惟芊
    - 吳豐閔 X X蔡佩玲 -> 會在 normalize_staff_display 再統一成 吳豐閔 X 蔡佩玲
    """
    text = html.unescape(str(name or "")).strip()
    if not text:
        return ""

    text = text.strip().lstrip("＊*").strip()
    text = re.sub(r"^[Xx×＊*\s]+", "", text).strip()
    text = re.sub(r"^\d+", "", text).strip()
    text = re.sub(r"[（(]\d+[）)]", "", text).strip()
    text = re.sub(r"^[Xx×\s]+", "", text).strip()
    text = re.sub(r"[Xx×\s]+$", "", text).strip()
    return text


def normalize_staff_display(value, limit=None):
    """
    X欄顯示規則：名字和名字中間只保留一個「 X 」。
    不管來源是 list、已經串好的字串、或含有 X姓名，都先拆開、清洗、再重組。
    """
    if value in (None, ""):
        return ""

    if isinstance(value, (list, tuple)):
        raw_parts = []
        for item in value:
            raw_parts.extend(re.split(r"\s*[Xx×]\s*|[,，、/]+", str(item or "")))
    else:
        raw_parts = re.split(r"\s*[Xx×]\s*|[,，、/]+", str(value or ""))

    cleaned = []
    seen = set()
    for part in raw_parts:
        name = clean_staff_name(part)
        if not name or name in seen:
            continue
        cleaned.append(name)
        seen.add(name)
        if limit and len(cleaned) >= int(limit):
            break

    return " X ".join(cleaned)


def format_staff_from_cleaners(cleaners, people=None):
    try:
        limit = int(people) if people not in (None, "") else None
    except Exception:
        limit = None

    staff = normalize_staff_display(cleaners or [], limit=limit)
    return staff if staff else "無人力"


def slot_exists_in_section_response(raw_text, date_slot):
    """只認指定日期／時段的完整 checkbox，不做跨項目的模糊比對。"""
    if not raw_text:
        return False

    date_part, period_part = date_slot.split("_", 1)
    raw = str(raw_text)
    unescaped = html.unescape(raw)

    def _matches_item(item):
        if not isinstance(item, dict):
            return False
        item_date = str(item.get("date", "")).strip()
        item_section = str(item.get("section", "")).strip().replace(" ", "")
        return item_date == date_part and item_section == period_part.replace(" ", "")

    def _contains_exact_checkbox(markup):
        try:
            soup = BeautifulSoup(html.unescape(str(markup or "")), "html.parser")
            return any(
                str(node.get("value", "")).strip().replace(" ", "")
                == date_slot.replace(" ", "")
                for node in soup.select('input[name="date_list[]"]')
            )
        except Exception:
            return False

    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            data = data.get("data") or data.get("result") or data.get("sections") or []
        if isinstance(data, list):
            for item in data:
                if _matches_item(item) or _contains_exact_checkbox(item):
                    return True
    except Exception:
        pass

    return _contains_exact_checkbox(unescaped)
