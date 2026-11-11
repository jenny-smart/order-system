# -*- coding: utf-8 -*-
"""儲值金訂單客服備註空白：每日 08:20（上班日）列出訂購人姓名，記入行事曆。

更新記錄：
2026-11-12
- 新增（Jenny）。由 tool-system 的 Cloud Schedule Router 依主控表「排程設定」
  （功能代號 stored_value_notice_daily）派送 .github/workflows/stored-value-notice-schedule.yml。

規則：
- 只在上班日執行（config/taiwan_work_calendar.json；週六日＋國定假日不跑，補班日照跑）。
- 查詢區間＝前一上班日 08:00 ～ 今天 08:00（依訂購時間；週一會涵蓋週五 08:00 起整個週末）。
- 台北／台中各用自己的後台帳號查：購買項目＝儲值金、付款狀態＝待付款＋已付款、客服備註空白
  （orders.find_pending_stored_value_orders，與「儲值獎金備註」搜尋相同）。
- 結果記一則 jenny@hers.com.tw 行事曆「【儲值金客服備註空白】台北 N 筆、台中 M 筆」
  （寫不進去改寫 jenny@lemonclean.com.tw；可用 STORED_VALUE_NOTICE_CALENDAR_ID 指定），
  內容逐區列出訂購人姓名（附訂單編號、付款狀態、訂購時間）。同一天重跑只留最新一則。
- 只查詢、記行事曆，不修改後台。

Actions 紀錄只印各區筆數，不印客戶姓名；逐筆明細寫進行事曆。
"""
from __future__ import annotations

import argparse
import contextlib
import io
import os
import traceback
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

TOOL_NAME = "儲值金訂單客服備註空白：自動排程"
TZ = ZoneInfo("Asia/Taipei")
CUTOFF = time(8, 0)
REGIONS = ("台北", "台中")
PURCHASE_STATUS = ["0", "1"]  # 待付款＋已付款（取消／退款不列）
CALENDAR_IDS = ("jenny@hers.com.tw", "jenny@lemonclean.com.tw")
CALENDAR_PREFIX = "【儲值金客服備註空白】"


def previous_workday(day: date, calendar: dict) -> date:
    from shared.weekend_reminder_schedule import is_off_day

    prev = day - timedelta(days=1)
    while is_off_day(prev, calendar):
        prev -= timedelta(days=1)
    return prev


def query_window(today: date, calendar: dict) -> tuple[datetime, datetime]:
    """前一上班日 08:00 ～ 今天 08:00（naive，台北時間）。"""
    return datetime.combine(previous_workday(today, calendar), CUTOFF), datetime.combine(today, CUTOFF)


def build_calendar_event(result: dict, window: tuple[datetime, datetime], now: datetime) -> dict:
    counts = "、".join(f"{region} {len(item.get('rows') or [])} 筆" for region, item in result.items())
    lines = [f"區間：{window[0]:%m/%d %H:%M} ～ {window[1]:%m/%d %H:%M}（訂購時間）",
             "條件：購買項目＝儲值金、待付款＋已付款、客服備註空白", ""]
    for region, item in result.items():
        rows = item.get("rows") or []
        lines.append(f"■ {region}：{len(rows)} 筆" + (f"（{item['error']}）" if item.get("error") else ""))
        if rows:
            lines.append("訂購人：" + "、".join(str(r.get("name") or "（無姓名）") for r in rows))
        for r in rows:
            lines.append(f"{r.get('name') or '（無姓名）'} {r.get('order_no', '')} {r.get('purchase_status', '')}"
                         f" {str(r.get('created_time', ''))[5:16]}")
        lines.append("")
    return dict(
        summary=f"{CALENDAR_PREFIX}{counts}（{now:%m/%d}）",
        description="\n".join(lines).strip(),
        start=now, reminder_minutes=[0], replace_prefix=CALENDAR_PREFIX,
    )


def write_calendar(result: dict, window, now: datetime, service_factory=None) -> list[str]:
    """寫行事曆；失敗只回報。"""
    from shared.atm_match_reconcile_schedule import _calendar_service, _insert_event, service_for

    service_factory = service_factory or _calendar_service
    preferred = os.getenv("STORED_VALUE_NOTICE_CALENDAR_ID", "").strip()
    calendar_ids = (preferred,) if preferred else CALENDAR_IDS
    event = build_calendar_event(result, window, now)
    last_error = None
    for calendar_id in calendar_ids:
        try:
            _insert_event(service_for(service_factory, calendar_id), calendar_id, **event)
            return [f"已記入行事曆 {calendar_id}"]
        except Exception as exc:
            last_error = exc
    return [f"⚠️ 記入行事曆失敗：{last_error}"]


def _log(status: str, message: str, traceback_text: str = "") -> None:
    try:
        from shared.execution_log_service import log_execution

        log_execution(function_name=TOOL_NAME, status=status, run_type="排程", area="台北／台中",
                      message=message, traceback_text=traceback_text)
    except Exception as exc:  # 記錄失敗不影響排程結果
        print(f"WARN 執行 Log 寫入失敗：{exc}", flush=True)


def _query_region(env: str, email: str, password: str, window) -> list[dict]:
    from orders import find_pending_stored_value_orders

    rows = find_pending_stored_value_orders(
        env_name=env, backend_email=email, backend_password=password,
        date_s=window[0].strftime("%Y-%m-%d"), date_e=window[1].strftime("%Y-%m-%d"),
        purchase_status=PURCHASE_STATUS, notice_status="blank",
        created_from=window[0], created_to=window[1],
    )
    return sorted(rows, key=lambda r: (str(r.get("created_time", "")), str(r.get("order_no", ""))))


def run(env: str = "prod", today: date | None = None, regions=REGIONS, dry_run: bool = False,
        calendar: dict | None = None, now: datetime | None = None, query=None) -> dict:
    import orders  # noqa: F401  （先載入 orders，與其他排程相同的載入順序）
    from accounts import ACCOUNTS
    from shared.weekend_reminder_schedule import is_off_day, load_work_calendar

    calendar = load_work_calendar() if calendar is None else calendar
    now = now or datetime.now(TZ)
    today = today or now.date()
    if is_off_day(today, calendar):
        print(f"SKIP {today} 不是上班日", flush=True)
        return {"due": False, "today": str(today)}

    window = query_window(today, calendar)
    print(f"WINDOW {window[0]:%Y-%m-%d %H:%M} ～ {window[1]:%Y-%m-%d %H:%M}", flush=True)
    query = query or _query_region

    result: dict = {}
    for region in regions:
        item = {"rows": [], "error": ""}
        result[region] = item
        try:
            account = ACCOUNTS.get(region) or {}
            email, password = str(account.get("email") or ""), str(account.get("password") or "")
            if not email or not password:
                raise RuntimeError(f"{region}未設定後台帳密（{region} EMAIL／PASSWORD Secrets）")
            with contextlib.redirect_stdout(io.StringIO()):  # 明細不印進 Actions 紀錄
                item["rows"] = query(env, email, password, window)
            print(f"QUERY {region} 儲值金訂單客服備註空白 {len(item['rows'])} 筆", flush=True)
        except Exception as exc:
            item["error"] = f"{type(exc).__name__}: {exc}"
            print(f"ERROR {region} {item['error']}", flush=True)

    messages = [] if dry_run else write_calendar(result, window, now)
    for line in messages:
        print(line, flush=True)

    errors = [f"{r}：{i['error']}" for r, i in result.items() if i["error"]]
    summary = "；".join(f"{r} {len(i['rows'])} 筆" for r, i in result.items())
    message = f"{window[0]:%m/%d %H:%M}～{window[1]:%m/%d %H:%M}：{summary}" + ("（試跑，未寫入）" if dry_run else "")
    if errors:
        message += "；錯誤 " + "；".join(errors)
    print(f"FINISH {message}", flush=True)
    if not dry_run:
        _log("失敗" if errors else "成功", message)
    if errors and len(errors) == len(result):
        raise RuntimeError("；".join(errors))
    return {"due": True, "window": window, "result": result}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--env", default="prod")
    parser.add_argument("--date", default="", help="以這天當作執行日（YYYY-MM-DD，測試用）")
    parser.add_argument("--regions", default="台北,台中", help="逗號分隔，預設台北,台中")
    parser.add_argument("--dry-run", action="store_true", help="只查詢不寫行事曆")
    args = parser.parse_args()
    today = date.fromisoformat(args.date) if args.date.strip() else None
    regions = tuple(r.strip() for r in args.regions.split(",") if r.strip()) or REGIONS
    try:
        run(env=args.env, today=today, regions=regions, dry_run=args.dry_run)
    except Exception as exc:
        _log("失敗", str(exc), traceback.format_exc())
        raise


if __name__ == "__main__":
    main()
