# -*- coding: utf-8 -*-
"""記錄未配班人員：自動排程。未來 2 週某時段未配班只剩 1 位專員，記到獨立行事曆。

更新記錄：
2026-11-22
- 只寫排程行事曆 SCHEDULE_NOTICE_CALENDAR_ID，不再預設 tpe@／jenny@。
2026-11-21
- 新增（Jenny）。由 tool-system 的 Cloud Schedule Router 依主控表「排程設定」
  （功能代號 unassigned_staff_record）派送 .github/workflows/unassigned-staff-record-schedule.yml。

規則（見 shared/unassigned_staff.py）：
- 範圍＝明天起 14 天；不算檸檬人與晚上時段。
- 一則行事曆：標題「【未配班剩1人】台北 N 個時段（MM/DD）」，內容每行「2026/11/24 下午-1」；
  同一天重跑只留最新一則。
- 只寫 SCHEDULE_NOTICE_CALENDAR_ID（排程行事曆）；沒設定時報錯，不寫 tpe@／jenny@。
- 只讀取、不修改後台。
"""
from __future__ import annotations

import argparse
import traceback
from datetime import date, datetime, timedelta
from typing import Callable
from zoneinfo import ZoneInfo

TOOL_NAME = "記錄未配班人員：自動排程"
TZ = ZoneInfo("Asia/Taipei")
REGIONS = ("台北",)
DEFAULT_DAYS = 14


def date_range(today: date, days: int = DEFAULT_DAYS) -> tuple[str, str]:
    return (today + timedelta(days=1)).isoformat(), (today + timedelta(days=days)).isoformat()


def _log(status: str, area: str, message: str, traceback_text: str = "") -> None:
    try:
        from shared.execution_log_service import log_execution

        log_execution(function_name=TOOL_NAME, status=status, run_type="排程", area=area,
                      message=message, traceback_text=traceback_text)
    except Exception as exc:
        print(f"WARN 執行 Log 寫入失敗：{exc}", flush=True)


def _scan_region(env: str, email: str, password: str, date_start: str, date_end: str) -> dict:
    from memo_system import memo
    from shared.unassigned_staff import scan_range

    memo.set_env(env)
    memo.set_runtime_credentials(email, password)
    session = memo.login(ui_logger=None)

    def get_html(day: str) -> str:
        r = memo.session_get(session, f"{memo.BASE_URL}/schedule", params={"date": day, "staffId": ""})
        r.raise_for_status()
        return r.text

    return scan_range(get_html, date_start, date_end)


def write_calendar(event: dict, calendar_ids, service_factory=None) -> tuple[list[str], int]:
    from shared.atm_match_reconcile_schedule import _calendar_service, _insert_event, service_for

    service_factory = service_factory or _calendar_service
    messages, ok = [], 0
    for calendar_id in calendar_ids:
        try:
            _insert_event(service_for(service_factory, calendar_id), calendar_id, **event)
            messages.append(f"已記入行事曆 {calendar_id}")
            ok += 1
        except Exception as exc:
            messages.append(f"⚠️ 記入行事曆 {calendar_id} 失敗：{type(exc).__name__}: {exc}")
    return messages, ok


def run(env: str = "prod", today: date | None = None, regions=REGIONS, days: int = DEFAULT_DAYS,
        scan=None, service_factory=None, calendar_ids=None, dry_run: bool = False,
        log: Callable[[str], None] = lambda t: print(t, flush=True)) -> dict:
    import orders  # noqa: F401  （與其他排程相同的載入順序）
    from accounts import ACCOUNTS
    from shared.unassigned_staff import build_calendar_event, require_notice_calendar_ids, single_left

    scan = scan or _scan_region
    now = datetime.now(TZ)
    today = today or now.date()
    date_start, date_end = date_range(today, days)
    if calendar_ids is not None:
        calendar_ids = tuple(calendar_ids)
    elif not dry_run:
        calendar_ids = require_notice_calendar_ids()
    log(f"RANGE {date_start} ～ {date_end}（{'、'.join(regions)}）")

    failed, out = [], {}
    for region in regions:
        account = ACCOUNTS.get(region) or {}
        email, password = str(account.get("email") or ""), str(account.get("password") or "")
        if not email or not password:
            log(f"{region}：略過（未設定後台帳密）")
            out[region] = {"skipped": True}
            continue
        try:
            rows = single_left(scan(env, email, password, date_start, date_end))
        except Exception as exc:
            msg = f"{type(exc).__name__}: {exc}"
            log(f"❌ {region} 讀取班表失敗：{msg}")
            _log("失敗", region, f"{date_start}～{date_end}：{msg}", traceback.format_exc())
            failed.append(region)
            out[region] = {"error": msg}
            continue
        event = build_calendar_event(region, rows, date_start, date_end, now)
        log(event["summary"])
        log(event["description"])
        messages, ok = (["（dry run：不寫行事曆）"], 1) if dry_run else write_calendar(event, calendar_ids, service_factory)
        for m in messages:
            log(m)
        _log("成功" if ok else "失敗", region, f"{date_start}～{date_end}：{event['summary']}；" + "；".join(messages))
        if not ok:
            failed.append(region)
        out[region] = {"rows": rows, "event": event, "calendar": messages}
    if failed:
        raise RuntimeError("記錄未配班人員失敗：" + "、".join(failed))
    return {"range": (date_start, date_end), "result": out}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--env", default="prod")
    parser.add_argument("--date", default="", help="以這天當作執行日（YYYY-MM-DD，測試用）")
    parser.add_argument("--regions", default=",".join(REGIONS), help="逗號分隔，預設台北")
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS, help="明天起幾天（預設 14）")
    parser.add_argument("--dry-run", action="store_true", help="只讀班表、不寫行事曆")
    args = parser.parse_args()
    today = date.fromisoformat(args.date) if args.date.strip() else None
    regions = tuple(r.strip() for r in args.regions.split(",") if r.strip()) or REGIONS
    try:
        run(env=args.env, today=today, regions=regions, days=args.days, dry_run=args.dry_run)
    except Exception as exc:
        _log("失敗", "、".join(regions), str(exc), traceback.format_exc())
        raise


if __name__ == "__main__":
    main()
