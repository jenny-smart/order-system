# -*- coding: utf-8 -*-
"""排程行事曆：所有排程／系統通知統一記到 SCHEDULE_NOTICE_CALENDAR_ID。

更新記錄：
2026-11-22
- 新增（Jenny）：原本記 jenny@hers.com.tw、jenny@lemonclean.com.tw、tpe@lemonclean.com.tw 的
  行事曆紀錄（ATM 對帳、客人備註、儲值金客服備註空白、官網評價、檸檬人待換專員、記錄未配班人員）
  全部改記這個行事曆。
- 優先順序：SCHEDULE_NOTICE_CALENDAR_ID → 各功能自己的舊變數（ATM_CALENDAR_ID 等，只在前者沒設定時用）。
- 都沒設定時回傳空 tuple：不再退回 tpe@／jenny@。
- 寫入憑證：行事曆 ID 不是 jenny@hers.com.tw 時用 GOOGLE_CALENDAR_REFRESH_TOKEN（jenny@lemonclean.com.tw 授權），
  所以這個行事曆要能讓 jenny@lemonclean.com.tw 編輯活動。
"""
from __future__ import annotations

import os

NOTICE_CALENDAR_ENV = "SCHEDULE_NOTICE_CALENDAR_ID"
MISSING_MESSAGE = f"⚠️ 尚未設定排程行事曆 {NOTICE_CALENDAR_ENV}，沒有記入行事曆"


def _split(value: str) -> tuple:
    return tuple(x.strip() for x in (value or "").split(",") if x.strip())


def notice_calendar_ids(*legacy_envs: str) -> tuple:
    """排程行事曆 ID；沒設定時才看各功能的舊變數；都沒有回傳 ()。"""
    ids = _split(os.getenv(NOTICE_CALENDAR_ENV, ""))
    for name in legacy_envs:
        if ids:
            break
        ids = _split(os.getenv(name, ""))
    return ids


def require_notice_calendar_ids(*legacy_envs: str) -> tuple:
    ids = notice_calendar_ids(*legacy_envs)
    if not ids:
        raise RuntimeError(f"尚未設定排程行事曆 {NOTICE_CALENDAR_ENV}（不再寫 tpe@／jenny@）")
    return ids
