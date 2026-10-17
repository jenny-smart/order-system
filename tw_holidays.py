"""台灣國定假日：依年份自動抓政府辦公日曆，抓不到時退回內建清單。

資料來源：TaiwanCalendar（依行政院人事行政總處公布之「政府行政機關辦公日曆表」整理），
每年一個 JSON：[{"date": "20270101", "week": "五", "isHoliday": true, "description": "開國紀念日"}, …]
isHoliday=true 且不是週六日的日子視為國定假日（含彈性放假）。
工作天規則維持原本：週六日一律不算工作日（補班日也不算）。
"""

from __future__ import annotations

import json
import urllib.request
from datetime import date
from typing import Dict, Iterable, Optional, Set, Tuple

CALENDAR_URL = "https://cdn.jsdelivr.net/gh/ruyut/TaiwanCalendar/data/{year}.json"

_CACHE: Dict[int, Tuple[Set[date], Set[date]]] = {}


def _fetch(year: int, timeout: float = 10) -> Optional[list]:
    try:
        with urllib.request.urlopen(CALENDAR_URL.format(year=year), timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def parse_calendar(rows: Iterable[dict]) -> Tuple[Set[date], Set[date]]:
    """回傳 (平日放假日, 週末補班日)。"""
    holidays, makeup = set(), set()
    for row in rows:
        text = str(row.get("date", "")).replace("-", "").replace("/", "")
        if len(text) != 8 or not text.isdigit():
            continue
        day = date(int(text[:4]), int(text[4:6]), int(text[6:]))
        off = row.get("isHoliday")
        if isinstance(off, str):
            off = off.strip().lower() in ("true", "1", "2", "是")
        if off and day.weekday() < 5:
            holidays.add(day)
        elif not off and day.weekday() >= 5:
            makeup.add(day)
    return holidays, makeup


def calendar_for(year: int, fallback: Iterable[date] = ()) -> Tuple[Set[date], Set[date], bool]:
    """回傳 (假日, 補班日, 是否取得官方日曆)。抓不到時用 fallback 裡同年份的日子。"""
    if year not in _CACHE:
        rows = _fetch(year)
        if rows:
            _CACHE[year] = parse_calendar(rows)
    if year in _CACHE:
        holidays, makeup = _CACHE[year]
        return holidays, makeup, True
    return {d for d in fallback if d.year == year}, set(), False


def is_workday(day: date, fallback: Iterable[date] = (), warn=None) -> bool:
    holidays, _makeup, official = calendar_for(day.year, fallback)
    if not official and warn and not any(d.year == day.year for d in fallback):
        warn(f"⚠ 未取得 {day.year} 年辦公日曆，工作天只排除週六日")
    return day.weekday() < 5 and day not in holidays
