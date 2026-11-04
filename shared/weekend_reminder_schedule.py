# -*- coding: utf-8 -*-
"""週末／例假日服務提醒排程：休假前 2 天 11:00 自動產生提醒名單。

規則：
- 休假區段＝連續的非上班日（週六日＋國定假日；補班日算上班日），
  依 config/taiwan_work_calendar.json（政府行政機關辦公日曆表）判斷。
- 執行日＝區段第一天往前 2 天（一般週末是週四）；若那天本身是休假日，
  再往前推到最近的上班日，讓客服在上班時間處理。
- 名單範圍＝整個休假區段（例：週五國定假日＋週末 → 週三執行，查週五～週日）。

GitHub Actions 每天台北時間 11:00 呼叫一次（.github/workflows/weekend-reminder-schedule.yml），
不是執行日就直接結束。只把已付款訂單寫入「週末服務提醒」追蹤表（含內勤工作表單插列），
不發送 LINE，與「週末服務 LINE 提醒」頁面手動儲存的結果相同。
"""
from __future__ import annotations

import argparse
import json
import traceback
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

CALENDAR_FILE = Path(__file__).resolve().parents[1] / "config" / "taiwan_work_calendar.json"
LEAD_DAYS = 2
LOOKAHEAD_DAYS = 21
TAIPEI = ZoneInfo("Asia/Taipei")


def load_work_calendar(path=CALENDAR_FILE):
    """回傳 {date: 是否放假}；檔案讀不到時回傳空 dict（改用週六日判斷）。"""
    try:
        days = json.loads(Path(path).read_text(encoding="utf-8")).get("days", {})
    except (OSError, ValueError):
        return {}
    return {date.fromisoformat(key): bool(value) for key, value in days.items()}


def is_off_day(day, calendar):
    if day in calendar:
        return calendar[day]
    return day.weekday() >= 5


def calendar_covers(day, calendar):
    return day in calendar


def off_block_from(start, calendar):
    """start 是休假區段第一天時回傳 (start, end)，否則 None。"""
    if not is_off_day(start, calendar) or is_off_day(start - timedelta(days=1), calendar):
        return None
    end = start
    while is_off_day(end + timedelta(days=1), calendar):
        end += timedelta(days=1)
    return start, end


def run_day_for(block_start, calendar):
    run_day = block_start - timedelta(days=LEAD_DAYS)
    while is_off_day(run_day, calendar):
        run_day -= timedelta(days=1)
    return run_day


def blocks_due(today, calendar, lookahead=LOOKAHEAD_DAYS):
    """today 需要執行提醒的休假區段清單 [(起, 迄)]。"""
    due = []
    for offset in range(1, lookahead + 1):
        block = off_block_from(today + timedelta(days=offset), calendar)
        if block and run_day_for(block[0], calendar) == today:
            due.append(block)
    return due


def next_run(today, calendar, lookahead=LOOKAHEAD_DAYS):
    """下一個執行日與其休假區段（含 today），找不到時回傳 None。"""
    for offset in range(0, lookahead + 1):
        day = today + timedelta(days=offset)
        blocks = blocks_due(day, calendar, lookahead)
        if blocks:
            return day, blocks
    return None


def _log(status, area, date_text, message, traceback_text=""):
    try:
        from shared.execution_log_service import log_execution

        log_execution(
            function_name="週末服務提醒：自動排程", status=status, run_type="排程",
            area=area, date=date_text, message=message, traceback_text=traceback_text,
        )
    except Exception as exc:  # 記錄失敗不影響排程結果
        print(f"WARN 執行 Log 寫入失敗：{exc}", flush=True)


def run(env="prod", today=None, regions=("台北",), dry_run=False, calendar=None):
    from accounts import ACCOUNTS
    from function.weekend_reminders import (
        find_paid_weekend_orders, load_tracking_rows, merge_tracking_rows, save_tracking_rows,
    )

    calendar = load_work_calendar() if calendar is None else calendar
    today = today or datetime.now(TAIPEI).date()
    if not calendar_covers(today + timedelta(days=LEAD_DAYS), calendar):
        print(f"WARN 辦公日曆沒有 {today.year} 年資料，只依週六日判斷；請更新 config/taiwan_work_calendar.json", flush=True)

    blocks = blocks_due(today, calendar)
    if not blocks:
        upcoming = next_run(today + timedelta(days=1), calendar)
        hint = f"；下次執行日 {upcoming[0]}（服務 {upcoming[1][0][0]}～{upcoming[1][0][1]}）" if upcoming else ""
        print(f"SKIP {today} 不是休假前 {LEAD_DAYS} 天的執行日{hint}", flush=True)
        return {"due": False, "today": str(today)}

    order_rows, warnings = [], []
    for start, end in blocks:
        for region in regions:
            account = ACCOUNTS.get(region) or {}
            email, password = str(account.get("email") or ""), str(account.get("password") or "")
            if not email or not password:
                raise RuntimeError(f"{region}未設定後台帳密（{region} EMAIL／PASSWORD Secrets）")
            rows, debug = find_paid_weekend_orders(env, email, password, str(start), str(end))
            if debug.get("hit_page_limit"):
                warnings.append(f"{region} {start}～{end} 查詢達 20 頁上限，可能漏單")
            order_rows.extend(rows)
            print(f"QUERY {region} {start}～{end} 已付款 {debug.get('paid', 0)} 筆", flush=True)

    merged = merge_tracking_rows(order_rows, load_tracking_rows())
    new_rows = [row for row in merged if row.get("資料狀態") == "新增"]
    saved = 0 if dry_run or not new_rows else save_tracking_rows(new_rows)
    date_text = "、".join(f"{start}～{end}" for start, end in blocks)
    message = (
        f"服務 {date_text}：已付款 {len(merged)} 筆，新增 {len(new_rows)} 筆"
        + ("（試跑，未寫入）" if dry_run else f"，已寫入 {saved} 筆")
        + ("；" + "；".join(warnings) if warnings else "")
    )
    print(f"FINISH {message}", flush=True)
    if not dry_run:
        _log("警告" if warnings else "成功", "、".join(regions), date_text, message)
    return {"due": True, "blocks": blocks, "paid": len(merged), "new": len(new_rows), "saved": saved}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--env", default="prod")
    parser.add_argument("--date", default="", help="以這天當作執行日（YYYY-MM-DD，測試用）")
    parser.add_argument("--regions", default="台北", help="逗號分隔，預設台北")
    parser.add_argument("--dry-run", action="store_true", help="只查詢不寫入追蹤表")
    args = parser.parse_args()
    today = date.fromisoformat(args.date) if args.date.strip() else None
    regions = tuple(r.strip() for r in args.regions.split(",") if r.strip()) or ("台北",)
    try:
        run(env=args.env, today=today, regions=regions, dry_run=args.dry_run)
    except Exception as exc:
        _log("失敗", "、".join(regions), args.date or str(datetime.now(TAIPEI).date()), str(exc), traceback.format_exc())
        raise


if __name__ == "__main__":
    main()
