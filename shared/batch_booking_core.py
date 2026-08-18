# -*- coding: utf-8 -*-
"""共用多日期／多時段批次建單核心。

這一層刻意不依賴 Streamlit，也不直接知道「一般批次建單」或「檸檬保留單」。
功能頁只要提供 availability_checker / executor，就可以共用：
1. 日期 × 時段展開
2. 可用人力結果正規化
3. 選取／全選／上午／下午策略
4. 執行前再次檢查
5. 批次逐筆執行與結果彙整

現有舊版「批次建單（Google Sheet）」不會改動；新功能以此核心獨立運作。
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date, timedelta
from typing import Callable, Iterable, List, Optional, Sequence

PERIOD_HOUR_MAP = {
    "08:30-12:30": 4,
    "09:00-11:00": 2,
    "09:00-12:00": 3,
    "14:00-16:00": 2,
    "14:00-17:00": 3,
    "14:00-18:00": 4,
    "09:00-16:00": 6,
    "09:00-18:00": 8,
}

AM_PERIODS = {"08:30-12:30", "09:00-11:00", "09:00-12:00", "09:00-16:00", "09:00-18:00"}
PM_PERIODS = {"14:00-16:00", "14:00-17:00", "14:00-18:00"}


@dataclass
class SlotPlan:
    service_date: str
    period: str
    available: bool = False
    staff: str = ""
    available_people: int = 0
    selected: bool = False
    quantity: int = 1
    note: str = ""

    @property
    def hour(self) -> int:
        return int(PERIOD_HOUR_MAP.get(self.period, 0))

    @property
    def daypart(self) -> str:
        return "AM" if self.period in AM_PERIODS else "PM"

    def to_dict(self) -> dict:
        row = asdict(self)
        row["hour"] = self.hour
        row["daypart"] = self.daypart
        return row


def daterange(start: date, end: date) -> Iterable[date]:
    if end < start:
        raise ValueError("結束日期不可早於開始日期")
    cur = start
    while cur <= end:
        yield cur
        cur += timedelta(days=1)


def build_grid(start: date, end: date, periods: Sequence[str]) -> List[SlotPlan]:
    invalid = [p for p in periods if p not in PERIOD_HOUR_MAP]
    if invalid:
        raise ValueError(f"不支援時段：{', '.join(invalid)}")
    return [SlotPlan(d.isoformat(), p) for d in daterange(start, end) for p in periods]


def merge_availability(grid: Sequence[SlotPlan], availability_rows: Sequence[dict]) -> List[SlotPlan]:
    lookup = {
        (str(r.get("date") or r.get("service_date") or ""), str(r.get("period") or "")): r
        for r in availability_rows or []
    }
    merged: List[SlotPlan] = []
    for slot in grid:
        raw = lookup.get((slot.service_date, slot.period), {})
        available = bool(raw.get("available", False))
        staff = str(raw.get("staff") or "")
        available_people = raw.get("available_people")
        if available_people in (None, ""):
            available_people = raw.get("people")
        try:
            people = int(available_people or 0)
        except Exception:
            people = 0
        merged.append(SlotPlan(
            service_date=slot.service_date,
            period=slot.period,
            available=available,
            staff=staff,
            available_people=people,
            selected=bool(slot.selected and available),
            quantity=max(0, int(slot.quantity or 0)),
            note=str(raw.get("note") or slot.note or ""),
        ))
    return merged


def apply_selection(slots: Sequence[SlotPlan], mode: str) -> List[SlotPlan]:
    """回傳新清單，不原地修改。

    mode: all / none / am / pm / available
    """
    result: List[SlotPlan] = []
    for src in slots:
        slot = SlotPlan(**asdict(src))
        if mode in {"all", "available"}:
            slot.selected = bool(slot.available)
        elif mode == "none":
            slot.selected = False
        elif mode == "am":
            slot.selected = bool(slot.available and slot.period in AM_PERIODS)
        elif mode == "pm":
            slot.selected = bool(slot.available and slot.period in PM_PERIODS)
        else:
            raise ValueError(f"未知選取模式：{mode}")
        result.append(slot)
    return result


def from_editor_rows(rows: Sequence[dict], *, selected_key="執行", quantity_key="建立張數") -> List[SlotPlan]:
    result: List[SlotPlan] = []
    for row in rows or []:
        service_date = str(row.get("日期") or row.get("service_date") or "")
        period = str(row.get("時段") or row.get("period") or "")
        available = bool(row.get("可用", row.get("available", False)))
        selected = bool(row.get(selected_key, row.get("selected", False))) and available
        try:
            qty = int(row.get(quantity_key, row.get("quantity", 1)) or 0)
        except Exception:
            qty = 0
        result.append(SlotPlan(
            service_date=service_date,
            period=period,
            available=available,
            staff=str(row.get("可用專員") or row.get("staff") or ""),
            available_people=int(row.get("可用人數") or row.get("available_people") or 0),
            selected=selected,
            quantity=max(0, qty),
            note=str(row.get("說明") or row.get("note") or ""),
        ))
    return result


def selected_units(slots: Sequence[SlotPlan]) -> int:
    return sum(max(0, int(s.quantity or 0)) for s in slots if s.selected and s.available)


def selected_slot_count(slots: Sequence[SlotPlan]) -> int:
    return sum(1 for s in slots if s.selected and s.available and int(s.quantity or 0) > 0)


def execute_batch(
    slots: Sequence[SlotPlan],
    *,
    precheck: Optional[Callable[[SlotPlan], dict]] = None,
    executor: Callable[[SlotPlan, int], dict],
    continue_after_error: bool = True,
) -> dict:
    """逐時段、逐張執行；每張前可再做一次即時檢查。

    executor(slot, sequence_in_slot) 應回傳 dict；成功時 success=True。
    precheck(slot) 可回傳 {available: bool, message: str, ...}。
    """
    results = []
    target_units = selected_units(slots)
    for slot in slots:
        if not slot.selected or not slot.available or int(slot.quantity or 0) <= 0:
            continue
        for seq in range(1, int(slot.quantity) + 1):
            if precheck is not None:
                try:
                    check = precheck(slot) or {}
                except Exception as exc:
                    check = {"available": False, "message": f"執行前檢查失敗：{exc}"}
                if not bool(check.get("available")):
                    results.append({
                        "success": False,
                        "service_date": slot.service_date,
                        "period": slot.period,
                        "sequence": seq,
                        "message": str(check.get("message") or "執行前即時人力不足"),
                    })
                    if not continue_after_error:
                        return _summary(target_units, results)
                    break
            try:
                row = dict(executor(slot, seq) or {})
                row.setdefault("service_date", slot.service_date)
                row.setdefault("period", slot.period)
                row.setdefault("sequence", seq)
                row.setdefault("success", True)
                results.append(row)
                if row.get("success") is False and not continue_after_error:
                    return _summary(target_units, results)
            except Exception as exc:
                results.append({
                    "success": False,
                    "service_date": slot.service_date,
                    "period": slot.period,
                    "sequence": seq,
                    "message": str(exc),
                })
                if not continue_after_error:
                    return _summary(target_units, results)
                break
    return _summary(target_units, results)


def _summary(target_units: int, results: Sequence[dict]) -> dict:
    success_count = sum(1 for r in results if r.get("success"))
    fail_count = sum(1 for r in results if not r.get("success"))
    return {
        "target_count": int(target_units),
        "success_count": success_count,
        "fail_count": fail_count,
        "results": list(results),
    }
