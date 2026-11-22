# -*- coding: utf-8 -*-
"""排程行事曆：所有排程／系統通知統一記到 SCHEDULE_NOTICE_CALENDAR_ID。

更新記錄：
2026-11-22
- 新增 insert_event_if_changed：同一天內容沒變就不新增（留最早那則），內容有變才再新增一則、舊的保留
  （記錄未配班人員、未配班成立保留單使用）。
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
    from shared.atm_match_reconcile_schedule import _secret

    ids = _split(_secret(NOTICE_CALENDAR_ENV))
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


def insert_event_if_changed(service, calendar_id: str, summary: str, description: str, start,
                            reminder_minutes: list, replace_prefix: str) -> str:
    """同一天同一種紀錄：跟當天最新一則內容（標題＋內容）一樣就不新增，回傳 "unchanged"；
    不一樣才新增一則（舊的都保留），回傳 "inserted"。"""
    from datetime import timedelta
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("Asia/Taipei")
    day_start = start.astimezone(tz).replace(hour=0, minute=0, second=0, microsecond=0)
    items = service.events().list(calendarId=calendar_id, timeMin=day_start.isoformat(),
                                  timeMax=(day_start + timedelta(days=1)).isoformat(), q=replace_prefix,
                                  singleEvents=True, orderBy="startTime", maxResults=100).execute().get("items", [])
    same_kind = [e for e in items if str(e.get("summary", "")).startswith(replace_prefix)]
    if same_kind:
        latest = same_kind[-1]
        if (latest.get("summary") or "") == summary and (latest.get("description") or "").strip() == description.strip():
            return "unchanged"
    body = {
        "summary": summary,
        "description": description,
        "start": {"dateTime": start.isoformat(), "timeZone": "Asia/Taipei"},
        "end": {"dateTime": (start + timedelta(minutes=30)).isoformat(), "timeZone": "Asia/Taipei"},
        "reminders": {"useDefault": False,
                      "overrides": [{"method": "popup", "minutes": m} for m in reminder_minutes]},
    }
    service.events().insert(calendarId=calendar_id, body=body, sendUpdates="none").execute()
    return "inserted"


def write_if_changed(event: dict, calendar_ids, service_factory=None) -> tuple[list, int]:
    """每個行事曆各寫一次（內容沒變就不新增）；回傳（訊息, 成功數）。"""
    from shared.atm_match_reconcile_schedule import _calendar_service, calendar_auth_label, service_for

    service_factory = service_factory or _calendar_service
    messages, ok = [], 0
    for calendar_id in calendar_ids:
        try:
            status = insert_event_if_changed(service_for(service_factory, calendar_id), calendar_id, **event)
            messages.append(f"內容沒變，沿用今天較早那則 {calendar_id}" if status == "unchanged"
                            else f"已記入行事曆 {calendar_id}")
            ok += 1
        except Exception as exc:
            hint = ""
            try:
                hint = f"（{calendar_auth_label(calendar_id)}）"
            except Exception:
                pass
            messages.append(f"⚠️ 記入行事曆 {calendar_id} 失敗{hint}：{type(exc).__name__}: {exc}")
    return messages, ok
