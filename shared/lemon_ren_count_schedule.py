# -*- coding: utf-8 -*-
"""檸檬人統計（待換專員進度）自動排程：每日 11:00 統計台北訂單裡的檸檬人，記入行事曆。

更新記錄：
2026-11-22
- 除了排程行事曆 SCHEDULE_NOTICE_CALENDAR_ID，也記一份到 tpe@lemonclean.com.tw（EXTRA_CALENDAR_IDS）；
  兩個各自回報，有一個寫成功就不算失敗。
2026-11-22
- 只寫排程行事曆 SCHEDULE_NOTICE_CALENDAR_ID，拿掉 tpe@／jenny@ 預設；沒設定時報錯。
2026-11-21
- 行事曆改寫到獨立行事曆 SCHEDULE_NOTICE_CALENDAR_ID（與「記錄未配班人員」共用），
  不再寫 tpe@／jenny@，避免干擾；尚未設定時才沿用 tpe@、jenny@。
2026-11-22
- 統計範圍改為今天～＋3 個月月底（日期不小於當日，含今天）。
2026-11-20
- 統計範圍改為明天～＋3 個月月底；執行紀錄不再每行印兩次。
- 新增（Jenny）。由 tool-system 的 Cloud Schedule Router 依主控表「排程設定」
  （功能代號 lemon_ren_count）派送 .github/workflows/lemon-ren-count-schedule.yml。

規則：
- 等同 ordersapp【檸檬人統計】：memo_system.shift.count_order_lemons_range（同一套程式）。
  不算檸檬保留單、灰底未配班名單、合併訂單（同一客人當天多張單且客服備註有「檸檬人勿動」）。
- 統計範圍＝今天～＋3 個月的月底（例：11/22 執行 → 11/22～隔年 02/28）；日期不小於今天。
- 預設只跑台北（台北後台帳號 accounts.ACCOUNTS）。
- 結果記一則行事曆到排程行事曆 SCHEDULE_NOTICE_CALENDAR_ID 與 tpe@lemonclean.com.tw：
  標題「【檸檬人待換專員】台北 N 天 M 人次（MM/DD）」，內容＝「檸檬人待換專員進度：」文字；
  同一天重跑只留最新一則。SCHEDULE_NOTICE_CALENDAR_ID 優先，沒設定才看 LEMON_REN_COUNT_CALENDAR_IDS。
- 只讀取、不修改後台；統計失敗或行事曆全部寫不進去時 exit 1。
"""
from __future__ import annotations

import argparse
import calendar
import os
import traceback
from datetime import date, datetime, timedelta
from typing import Callable
from zoneinfo import ZoneInfo

TOOL_NAME = "檸檬人統計：自動排程"
TZ = ZoneInfo("Asia/Taipei")
REGIONS = ("台北",)
DEFAULT_MONTHS = 3
# 行事曆：shared/notice_calendar.py（SCHEDULE_NOTICE_CALENDAR_ID）
CALENDAR_PREFIX = "【檸檬人待換專員】"
# 2026-11-22 Jenny：除了排程行事曆，也要記 tpe@lemonclean.com.tw（需共用給 jenny@lemonclean.com.tw「變更活動」）
EXTRA_CALENDAR_IDS = ("tpe@lemonclean.com.tw",)


def date_range(today: date, months: int = DEFAULT_MONTHS) -> tuple[str, str]:
    """今天～＋months 個月的月底（含）。"""
    total = today.year * 12 + (today.month - 1) + months
    year, month = divmod(total, 12)
    month += 1
    end = date(year, month, calendar.monthrange(year, month)[1])
    return today.isoformat(), end.isoformat()


def _log(status: str, area: str, message: str, traceback_text: str = "") -> None:
    try:
        from shared.execution_log_service import log_execution

        log_execution(function_name=TOOL_NAME, status=status, run_type="排程", area=area,
                      message=message, traceback_text=traceback_text)
    except Exception as exc:  # 記錄失敗不影響排程結果
        print(f"WARN 執行 Log 寫入失敗：{exc}", flush=True)


def _count_region(env: str, email: str, password: str, date_start: str, date_end: str,
                  log: Callable[[str], None]) -> dict:
    from memo_system import memo, shift

    memo.set_env(env)
    memo.set_runtime_credentials(email, password)
    quiet = None if log is print or getattr(log, "_prints", False) else log  # shift／memo 本身會 print，避免每行印兩次
    session = memo.login(ui_logger=quiet)
    return shift.count_order_lemons_range(session=session, date_start=date_start, date_end=date_end, ui_logger=quiet)


def build_calendar_event(region: str, result: dict, date_start: str, date_end: str, now: datetime) -> dict:
    from memo_system.shift import format_lemon_progress

    days = [d for d in result.get("days") or [] if d.get("合計")]
    total = sum(int(d.get("合計") or 0) for d in days)
    lines = [format_lemon_progress(result.get("days") or [])]
    if not days:
        lines.append("（沒有待換專員的檸檬人）")
    lines += ["", f"統計範圍：{region} {date_start}～{date_end}（今天起；不含檸檬保留單、未配班名單、合併訂單）"]
    return dict(
        summary=f"{CALENDAR_PREFIX}{region} {len(days)} 天 {total} 人次（{now:%m/%d}）",
        description="\n".join(lines),
        start=now, reminder_minutes=[0], replace_prefix=CALENDAR_PREFIX,
    )


def write_calendar(event: dict, service_factory=None, calendar_ids=None) -> tuple[list[str], int]:
    """每個行事曆都寫；回傳（訊息, 成功數）。"""
    from shared.atm_match_reconcile_schedule import _calendar_service, _insert_event, service_for

    service_factory = service_factory or _calendar_service
    if calendar_ids is None:
        from shared.notice_calendar import MISSING_MESSAGE, notice_calendar_ids

        notice_ids = notice_calendar_ids("LEMON_REN_COUNT_CALENDAR_IDS")
        calendar_ids = tuple(dict.fromkeys(notice_ids + EXTRA_CALENDAR_IDS))  # 排程行事曆＋tpe@，去重
        if not notice_ids:
            print(MISSING_MESSAGE, flush=True)
    messages, ok = [], 0
    for calendar_id in calendar_ids:
        try:
            _insert_event(service_for(service_factory, calendar_id), calendar_id, **event)
            messages.append(f"已記入行事曆 {calendar_id}")
            ok += 1
        except Exception as exc:
            messages.append(f"⚠️ 記入行事曆 {calendar_id} 失敗：{type(exc).__name__}: {exc}")
    return messages, ok


def run(env: str = "prod", today: date | None = None, regions=REGIONS, months: int = DEFAULT_MONTHS,
        count=None, service_factory=None, dry_run: bool = False,
        log: Callable[[str], None] | None = None) -> dict:
    import orders  # noqa: F401  （先載入 orders，與其他排程相同的載入順序）
    from accounts import ACCOUNTS

    if log is None:
        def log(text):
            print(text, flush=True)
        log._prints = True
    count = count or _count_region
    now = datetime.now(TZ)
    today = today or now.date()
    date_start, date_end = date_range(today, months)
    log(f"RANGE {date_start} ～ {date_end}（{'、'.join(regions)}）")

    failed = []
    out: dict = {}
    for region in regions:
        account = ACCOUNTS.get(region) or {}
        email, password = str(account.get("email") or ""), str(account.get("password") or "")
        if not email or not password:
            log(f"{region}：略過（未設定後台帳密）")
            out[region] = {"skipped": True}
            continue
        log(f"\n===== 【{region}】=====")
        try:
            result = count(env, email, password, date_start, date_end, log)
        except Exception as exc:
            msg = f"{type(exc).__name__}: {exc}"
            log(f"❌ {region} 統計失敗：{msg}")
            _log("失敗", region, f"{date_start}～{date_end}：{msg}", traceback.format_exc())
            failed.append(region)
            out[region] = {"error": msg}
            continue
        event = build_calendar_event(region, result, date_start, date_end, now)
        log(event["summary"])
        log(event["description"])
        if dry_run:
            messages, ok = ["（dry run：不寫行事曆）"], 1
        else:
            messages, ok = write_calendar(event, service_factory=service_factory)
        for m in messages:
            log(m)
        status = "成功" if ok else "失敗"
        _log(status, region, f"{date_start}～{date_end}：{event['summary']}；" + "；".join(messages))
        if not ok:
            failed.append(region)
        out[region] = {"result": result, "event": event, "calendar": messages}

    if failed:
        raise RuntimeError("檸檬人統計失敗：" + "、".join(failed))
    return {"range": (date_start, date_end), "result": out}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--env", default="prod")
    parser.add_argument("--date", default="", help="以這天當作執行日（YYYY-MM-DD，測試用）")
    parser.add_argument("--regions", default=",".join(REGIONS), help="逗號分隔，預設台北")
    parser.add_argument("--months", type=int, default=DEFAULT_MONTHS, help="統計到當月＋幾個月的月底（預設 3）")
    parser.add_argument("--dry-run", action="store_true", help="只統計、不寫行事曆")
    args = parser.parse_args()
    today = date.fromisoformat(args.date) if args.date.strip() else None
    regions = tuple(r.strip() for r in args.regions.split(",") if r.strip()) or REGIONS
    try:
        run(env=args.env, today=today, regions=regions, months=args.months, dry_run=args.dry_run)
    except Exception as exc:
        _log("失敗", "、".join(regions), str(exc), traceback.format_exc())
        raise


if __name__ == "__main__":
    main()
