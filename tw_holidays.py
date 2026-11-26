"""台灣國定假日：依年份自動抓政府辦公日曆，抓不到時退回內建清單。

抓不到時先讀 config/taiwan_work_calendar.json（每年 12/25 自動補上隔年），再退回內建清單。

資料來源：TaiwanCalendar（依行政院人事行政總處公布之「政府行政機關辦公日曆表」整理），
每年一個 JSON：[{"date": "20270101", "week": "五", "isHoliday": true, "description": "開國紀念日"}, …]
isHoliday=true 且不是週六日的日子視為國定假日（含彈性放假）。
工作天規則維持原本：週六日一律不算工作日（補班日也不算）。
"""

from __future__ import annotations

import json
import urllib.request
from datetime import date
from pathlib import Path
from typing import Dict, Iterable, Optional, Set, Tuple

CALENDAR_URL = "https://cdn.jsdelivr.net/gh/ruyut/TaiwanCalendar/data/{year}.json"
# 本機辦公日曆（每年 12/25 由 .github/workflows/work-calendar-yearly.yml 自動補上隔年）
CALENDAR_FILE = Path(__file__).resolve().parent / "config" / "taiwan_work_calendar.json"

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


def local_calendar(year: int, path: Path = CALENDAR_FILE) -> Optional[Tuple[Set[date], Set[date]]]:
    """config/taiwan_work_calendar.json 的 year 年：{日期: 是否放假} → (平日放假日, 週末補班日)；沒有該年回傳 None。"""
    try:
        days = json.loads(Path(path).read_text(encoding="utf-8")).get("days", {})
    except (OSError, ValueError):
        return None
    rows = [{"date": key, "isHoliday": bool(off)} for key, off in days.items() if key.startswith(f"{year}-")]
    return parse_calendar(rows) if rows else None


def year_days(rows: Iterable[dict]) -> Dict[str, bool]:
    """TaiwanCalendar 一年的資料 → {"YYYY-MM-DD": 是否放假}（含週六日），給 taiwan_work_calendar.json 用。"""
    out = {}
    for row in rows:
        text = str(row.get("date", "")).replace("-", "").replace("/", "")
        if len(text) != 8 or not text.isdigit():
            continue
        off = row.get("isHoliday")
        if isinstance(off, str):
            off = off.strip().lower() in ("true", "1", "2", "是")
        out[f"{text[:4]}-{text[4:6]}-{text[6:]}"] = bool(off)
    return out


def update_calendar_file(year: int, path: Path = CALENDAR_FILE, rows: Optional[list] = None) -> bool:
    """把 year 年辦公日曆寫進 json（已有完整一年就不動）。回傳是否有改檔；抓不到官方日曆丟錯。"""
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"days": {}}
    days = data.setdefault("days", {})
    first, last = date(year, 1, 1), date(year, 12, 31)
    expected = (last - first).days + 1
    if sum(1 for key in days if key.startswith(f"{year}-")) >= expected:
        return False
    rows = rows if rows is not None else _fetch(year, timeout=30)
    if not rows:
        raise RuntimeError(f"抓不到 {year} 年政府辦公日曆（{CALENDAR_URL.format(year=year)}）")
    new_days = year_days(rows)
    if len(new_days) < expected:
        raise RuntimeError(f"{year} 年辦公日曆只有 {len(new_days)} 天，不完整，先不更新")
    days.update(new_days)
    data["days"] = dict(sorted(days.items()))
    data["source"] = "TaiwanCalendar / 政府行政機關辦公日曆表（每年 12/25 自動更新）"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return True


def calendar_for(year: int, fallback: Iterable[date] = ()) -> Tuple[Set[date], Set[date], bool]:
    """回傳 (假日, 補班日, 是否取得官方日曆)。
    依序：線上政府辦公日曆 → config/taiwan_work_calendar.json → fallback 裡同年份的日子。"""
    if year not in _CACHE:
        rows = _fetch(year)
        if rows:
            _CACHE[year] = parse_calendar(rows)
        else:
            local = local_calendar(year)
            if local:
                _CACHE[year] = local
    if year in _CACHE:
        holidays, makeup = _CACHE[year]
        return holidays, makeup, True
    return {d for d in fallback if d.year == year}, set(), False


def is_workday(day: date, fallback: Iterable[date] = (), warn=None) -> bool:
    holidays, _makeup, official = calendar_for(day.year, fallback)
    if not official and warn and not any(d.year == day.year for d in fallback):
        warn(f"⚠ 未取得 {day.year} 年辦公日曆，工作天只排除週六日")
    return day.weekday() < 5 and day not in holidays
