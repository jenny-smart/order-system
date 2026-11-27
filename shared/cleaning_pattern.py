# -*- coding: utf-8 -*-
"""清潔細項（坪數／空間數量／加購）：居家與辦公室欄位不同，並可從評估備註自動補填。

後台代客預訂表單（/booking/single）欄位：
- 坪數 ping：1=10以下、2=11~20、3=20以下（僅辦公室）、4=21~40、5=41~60、6=61~80、7=81以上
  居家／大掃除／裝修細清沒有 3；辦公室沒有 1、2。
- 居家（clean_type_id 1、4）：room 房間、bathroom 衛浴、balcony 陽台、livingroom 客廳、kitchen 廚房、
  window 窗戶、shutter 百葉窗；加購 clothes／dyson／refrigerator／disinfection／go_abord／home_move／
  storage／cabinet／quintuple；勾選 uncleaned 半年以上沒打掃、pet 家中有貓狗。
- 辦公室（clean_type_id 2）：office 辦公室、meetingroom 會議室、toilet 廁所、tearoom 茶水間、seat 座位、
  window 窗戶、shutter 百葉窗；加購 disinfection／go_abord／quintuple；勾選 uncleaned（沒有 pet）。

評估備註換算（客服規則）：書房＝房間＋1、餐廳＝客廳＋1、落地窗算窗戶；沒寫數字算 1。
"""
from __future__ import annotations

import re

HOME_COUNT_FIELDS = [("room", "房間"), ("bathroom", "衛浴"), ("balcony", "陽台"), ("livingroom", "客廳"),
                     ("kitchen", "廚房"), ("window", "窗戶"), ("shutter", "百葉窗")]
OFFICE_COUNT_FIELDS = [("office", "辦公室"), ("meetingroom", "會議室"), ("toilet", "廁所"), ("tearoom", "茶水間"),
                       ("seat", "座位"), ("window", "窗戶"), ("shutter", "百葉窗")]
HOME_FLAG_FIELDS = [("clothes", "衣物洗晾"), ("dyson", "DYSON除蟎"), ("refrigerator", "冰箱清理"),
                    ("disinfection", "簡易消毒"), ("go_abord", "30日內出國"), ("home_move", "搬家打包"),
                    ("storage", "收納整理"), ("cabinet", "櫥櫃清潔"), ("quintuple", "五倍券"),
                    ("uncleaned", "半年以上沒打掃"), ("pet", "家中有貓狗")]
OFFICE_FLAG_FIELDS = [("disinfection", "簡易消毒"), ("go_abord", "30日內出國"), ("quintuple", "五倍券"),
                      ("uncleaned", "半年以上沒打掃")]

ALL_COUNT_KEYS = sorted({k for k, _ in HOME_COUNT_FIELDS + OFFICE_COUNT_FIELDS})
ALL_FLAG_KEYS = sorted({k for k, _ in HOME_FLAG_FIELDS + OFFICE_FLAG_FIELDS})

HOME_PING_OPTIONS = [("1", "10以下"), ("2", "11~20"), ("4", "21~40"), ("5", "41~60"), ("6", "61~80"), ("7", "81以上")]
OFFICE_PING_OPTIONS = [("3", "20以下"), ("4", "21~40"), ("5", "41~60"), ("6", "61~80"), ("7", "81以上")]


def is_office(clean_type_id) -> bool:
    return str(clean_type_id).strip() == "2"


def count_fields(clean_type_id):
    return OFFICE_COUNT_FIELDS if is_office(clean_type_id) else HOME_COUNT_FIELDS


def flag_fields(clean_type_id):
    return OFFICE_FLAG_FIELDS if is_office(clean_type_id) else HOME_FLAG_FIELDS


def ping_options(clean_type_id):
    return OFFICE_PING_OPTIONS if is_office(clean_type_id) else HOME_PING_OPTIONS


def ping_code(ping_number, clean_type_id="1") -> str:
    """室內坪數（數字）→ 後台 ping 代號。查不到數字時回 "4"（21~40）。"""
    try:
        n = float(ping_number)
    except (TypeError, ValueError):
        return "4"
    if n <= 0:
        return "4"
    if is_office(clean_type_id):
        if n <= 20:
            return "3"
    else:
        if n <= 10:
            return "1"
        if n <= 20:
            return "2"
    if n <= 40:
        return "4"
    if n <= 60:
        return "5"
    if n <= 80:
        return "6"
    return "7"


def ping_label(code, clean_type_id="1") -> str:
    return dict(HOME_PING_OPTIONS + OFFICE_PING_OPTIONS).get(str(code), "")


# 關鍵字依序比對（長的／容易包含其他字的放前面）：(關鍵字, 居家欄位, 辦公室欄位)
_COUNT_KEYWORDS = [
    ("落地窗", "window", "window"),
    ("百葉", "shutter", "shutter"),
    ("窗", "window", "window"),
    ("書房", "room", None),
    ("廚房", "kitchen", "tearoom"),
    ("茶水", None, "tearoom"),
    ("會議", None, "meetingroom"),
    ("辦公", None, "office"),
    ("座位", None, "seat"),
    ("衛浴", "bathroom", "toilet"),
    ("浴室", "bathroom", "toilet"),
    ("廁所", "bathroom", "toilet"),
    ("陽台", "balcony", None),
    ("餐廳", "livingroom", None),
    ("客廳", "livingroom", None),
    ("臥", "room", None),
    ("房", "room", None),
]
_FLAG_KEYWORDS = [
    ("衣物", "clothes"), ("洗晾", "clothes"), ("除蟎", "dyson"), ("dyson", "dyson"), ("冰箱", "refrigerator"),
    ("消毒", "disinfection"), ("出國", "go_abord"), ("打包", "home_move"), ("收納", "storage"),
    ("櫥櫃", "cabinet"), ("五倍", "quintuple"), ("半年", "uncleaned"), ("沒打掃", "uncleaned"),
    ("未打掃", "uncleaned"), ("貓", "pet"), ("狗", "pet"), ("寵物", "pet"),
]
_PING_RANGE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*[-~～－到至]\s*(\d+(?:\.\d+)?)\s*(?:p|P|坪)")
_PING_SINGLE_RE = re.compile(r"(?:坪數\s*[：:]?\s*(\d+(?:\.\d+)?))|(?:(\d+(?:\.\d+)?)\s*(?:p|P|坪)(?![a-zA-Z]))")


def _line_number(line: str) -> int:
    m = re.search(r"(\d+)", line)
    return int(m.group(1)) if m else 1


def parse_assessment(text: str, clean_type_id="1") -> dict:
    """評估備註 → 細項。

    回傳 {"ping": 代號或 "", "ping_number": 坪數, "counts": {欄位: 數量}, "flags": {欄位: "1"},
          "unknown": [看不懂的行], "details": [(原文, 換算說明)]}
    """
    office = is_office(clean_type_id)
    flag_keys = {k for k, _ in flag_fields(clean_type_id)}
    counts, flags, unknown, details = {}, {}, [], []
    ping, ping_number = "", None
    for raw in str(text or "").splitlines():
        line = raw.strip().strip("-•・*　")
        if not line or re.fullmatch(r"評估(項目|內容|備註)?\s*[：:]?", line):
            continue
        m = _PING_RANGE_RE.search(line)
        if m:
            ping_number = max(float(m.group(1)), float(m.group(2)))
        else:
            m = _PING_SINGLE_RE.search(line)
            if m:
                ping_number = float(m.group(1) or m.group(2))
        if m:
            ping = ping_code(ping_number, clean_type_id)
            details.append((line, f"坪數 {ping_label(ping)}"))
            continue
        lower = line.lower()
        flag = next((key for kw, key in _FLAG_KEYWORDS if kw in lower), None)
        if flag:
            if flag in flag_keys:
                flags[flag] = "1"
                details.append((line, dict(flag_fields(clean_type_id))[flag]))
            else:
                unknown.append(line)
            continue
        hit = next(((home_key, office_key) for kw, home_key, office_key in _COUNT_KEYWORDS if kw in line), None)
        key = (hit[1] if office else hit[0]) if hit else None
        if not key:
            unknown.append(line)
            continue
        n = _line_number(line)
        counts[key] = counts.get(key, 0) + n
        label = dict(count_fields(clean_type_id))[key]
        details.append((line, f"{label} +{n}"))
    return {"ping": ping, "ping_number": ping_number, "counts": counts, "flags": flags,
            "unknown": unknown, "details": details}


def pattern_fields(clean_type_id, counts=None, flags=None, ping=None) -> dict:
    """送後台的細項欄位：本類別的欄位照填，另一類別的欄位一律歸零（避免沿用舊單的居家欄位算辦公室時數）。"""
    counts, flags = counts or {}, flags or {}
    own_counts = {k for k, _ in count_fields(clean_type_id)}
    own_flags = {k for k, _ in flag_fields(clean_type_id)}
    data = {}
    for k in ALL_COUNT_KEYS:
        v = int(counts.get(k) or 0) if k in own_counts else 0
        data[k] = str(v) if k not in ("window", "shutter") else (str(v) if v else "")
    for k in ALL_FLAG_KEYS:
        on = k in own_flags and str(flags.get(k) or "0") == "1"
        if k in ("uncleaned", "pet"):
            # 後台是勾選框：沒勾時表單不送這個欄位，這裡也不送。
            if on:
                data[k] = "1"
            continue
        data[k] = "1" if on else "0"
    if ping:
        data["ping"] = str(ping)
    return data
