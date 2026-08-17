# -*- coding: utf-8 -*-
"""memo_system（客服備註搬移／ATM對帳／清潔異動／付款比對）共用的純文字/日期解析工具。

跟 shared/text_parsing.py（orders.py／quick_order.py 用）故意分開放：
兩邊的地址/電話正規化規則不完全相同（memo_system 的 normalize_address 會多做
臺→台、全形符號、"之"/"號-"等清洗），直接合併有改變比對行為的風險，所以先各自
歸位到 shared/ 底下，兩邊都在同一個頂層資料夾內方便之後視需要再統一。
"""

import re
from datetime import datetime


def normalize_phone(p: str) -> str:
    return re.sub(r"\D+", "", str(p or ""))


def parse_phone_list(text: str):
    raw = re.split(r"[,\n;、，]+", str(text or ""))
    phones = []
    for x in raw:
        p = normalize_phone(x)
        if p:
            phones.append(p)
    return list(dict.fromkeys(phones))


def normalize_text(t: str) -> str:
    return re.sub(r"\s+", "", str(t or ""))


def normalize_address(addr: str) -> str:
    s = str(addr or "").strip()
    s = normalize_text(s)
    s = s.replace("臺", "台")
    s = s.replace("，", ",")
    s = s.replace("（", "(").replace("）", ")")
    s = s.replace("－", "-").replace("–", "-").replace("—", "-")
    s = s.replace("之", "-")
    s = s.replace("號-", "號")
    s = s.replace("樓-", "樓")
    s = s.replace(",", "")
    s = s.replace("　", "")
    return s


def same_address(a: str, b: str) -> bool:
    na = normalize_address(a)
    nb = normalize_address(b)
    return bool(na and nb and na == nb)


def clip_text(text: str, limit: int = 50000) -> str:
    return str(text or "")[:limit]


def safe_cell(row, idx_1_based: int) -> str:
    i = idx_1_based - 1
    return str(row[i]).strip() if i < len(row) else ""


def parse_date(t: str):
    if not t:
        return None
    s = str(t).strip()
    for fmt in [
        "%Y/%m/%d",
        "%Y-%m-%d",
        "%Y/%m/%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
        "%Y-%m-%d %H:%M",
    ]:
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            pass
    m = re.search(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", s)
    if m:
        y, mo, d = map(int, m.groups())
        return datetime(y, mo, d)
    return None


def parse_row_spec(spec: str):
    rows = set()
    for p in str(spec).split(","):
        p = p.strip()
        if not p:
            continue
        if "-" in p:
            a, b = map(int, p.split("-", 1))
            if a > b:
                a, b = b, a
            rows.update(range(a, b + 1))
        else:
            rows.add(int(p))
    return sorted(x for x in rows if x >= 2)


def extract_name_from_text_block(text: str) -> str:
    lines = [x.strip() for x in str(text or "").splitlines() if x.strip()]
    for line in lines:
        if re.search(r"^[一-鿿]{2,4}$", line):
            return line
    return ""


def extract_service_date_from_page_text(page_text: str) -> str:
    text = str(page_text or "")
    m = re.search(r"(\d{4}[/-]\d{2}[/-]\d{2})\s*\([一二三四五六日]\)", text)
    if m:
        return m.group(1).replace("-", "/")
    m = re.search(r"(\d{4}[/-]\d{2}[/-]\d{2})", text)
    if m:
        return m.group(1).replace("-", "/")
    return ""


def extract_address_from_text_block(text: str) -> str:
    text = str(text or "")
    city_pattern = (
        r"(?:台北市|臺北市|新北市|桃園市|新竹市|新竹縣|台中市|臺中市|"
        r"彰化縣|南投縣|雲林縣|嘉義市|嘉義縣|台南市|臺南市|高雄市|"
        r"屏東縣|宜蘭縣|花蓮縣|台東縣|臺東縣|基隆市)"
    )
    patterns = [
        rf"({city_pattern}[^\n]*?號(?:之\d+)?(?:\d+樓)?(?:之\d+)?(?:\d+室)?)",
        rf"({city_pattern}[^\n]*?樓之\d+)",
        rf"({city_pattern}[^\n]*?\d+樓)",
        rf"({city_pattern}[^\n]*?號)",
    ]
    for p in patterns:
        m = re.search(p, text)
        if m:
            return m.group(1).strip()
    return ""


def get_purchase_id_from_edit_url(edit_url: str) -> str:
    m = re.search(r"/purchase/edit/(\d+)", edit_url or "")
    return m.group(1) if m else ""


def display_service_date(item) -> str:
    return item.get("service_date") or item.get("raw_date_str") or ""


def item_service_date_obj(item):
    return item.get("service_date_obj") or item.get("raw_date_obj")
