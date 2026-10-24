# -*- coding: utf-8 -*-
"""三種批次成單共用的建單條件（批次建單／批次建單優化／雲端批次成單）。

可建單＝訂單編號空白＋狀態「未安排」＋「預約條件」空白或屬於本次預約對象。
「預約條件」由 tool-system 更新排程時依主控試算表「排程預約條件」寫入階段：
改加、人時不足、已確認、可約、未回覆（例如年節大掃除）；狀態本身不改。
本次預約對象由批次畫面勾選，預設只有「可約」。
"""
from __future__ import annotations

import re
from contextlib import contextmanager
from contextvars import ContextVar

HOLD_COLUMN = "預約條件"
STAGE_READY, STAGE_CHANGE, STAGE_SHORT, STAGE_CONFIRMED, STAGE_NO_REPLY = "可約", "改加", "人時不足", "已確認", "未回覆"
# 畫面顯示順序＝建議預約順序。
STAGES = (STAGE_READY, STAGE_CHANGE, STAGE_SHORT, STAGE_CONFIRMED, STAGE_NO_REPLY)
DEFAULT_STAGES = (STAGE_READY,)

# 每個 Streamlit 工作階段在自己的執行緒執行，ContextVar 不會互相影響。
_allowed_stages = ContextVar("allowed_booking_stages", default=DEFAULT_STAGES)


def set_booking_stages(stages) -> None:
    _allowed_stages.set(tuple(stages))


@contextmanager
def booking_stages(stages):
    token = _allowed_stages.set(tuple(stages))
    try:
        yield
    finally:
        _allowed_stages.reset(token)


def current_booking_stages() -> tuple:
    return _allowed_stages.get()


def _scalar(value):
    if hasattr(value, "iloc"):
        return value.iloc[0] if len(value) else ""
    if isinstance(value, (list, tuple)):
        return value[0] if value else ""
    return value


def _text(value) -> str:
    text = str(_scalar(value) if value is not None else "").strip()
    return "" if text in ("nan", "None") else text


def normalize_status(value) -> str:
    text = _text(value).replace(" ", " ").replace("﻿", "").replace("​", "")
    return re.sub(r"\s+", "", text)


def booking_stage(row) -> str:
    return _text(row.get(HOLD_COLUMN, ""))


def hold_reason(row) -> str:
    """預約條件不在本次預約對象內時回傳原因；空白（平常月份）一律可約。"""
    stage = booking_stage(row)
    if not stage or stage in current_booking_stages():
        return ""
    return f"預約條件「{stage}」不在本次預約對象"


def create_block_reason(row) -> str:
    """回傳不能建單的原因；空字串代表可建單。"""
    if _text(row.get("訂單編號", "")):
        return "已有訂單編號"
    status = normalize_status(row.get("狀態", ""))
    if status != "未安排":
        return f"狀態為「{status or '空白'}」，非未安排"
    return hold_reason(row)


def can_create_order(row) -> bool:
    return not create_block_reason(row)


def can_process_row(row) -> bool:
    """已有單號（寄信／改日曆）或可建單的列才進批次。"""
    return bool(_text(row.get("訂單編號", ""))) or can_create_order(row)
