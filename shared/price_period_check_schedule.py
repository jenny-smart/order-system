# -*- coding: utf-8 -*-
"""金額期間檢查（雲端排程，每日 17:00）：前一天 17:00～今天 17:00 成立的訂單，檢查金額是否符合服務日期所屬期間。

更新記錄：
2026-11-28
- 新增（Jenny）。由 tool-system 的 Cloud Schedule Router 依主控表「排程設定」
  （功能代號 price_period_check）派送 .github/workflows/price-period-check-schedule.yml。

規則：
- 區間＝前一天 17:00 ～ 今天 17:00（依訂購時間；截止時間＝執行日 17:00）。每天都跑（含假日）。
- 台北／台中各用自己的後台帳號查：訂購日期＝前一天～今天、已付款／待付款，再依訂購時間篩區間。
- 檢查邏輯同 ordersapp【金額期間檢查】（shared/price_period_check.scan）：金額剛好是其他期間或
  另一種平假日的價格才列出；同日其他訂單合計、退款、加收都調整後仍不符才列出。
- 結果記一則到排程行事曆 SCHEDULE_NOTICE_CALENDAR_ID：
  標題「【金額期間檢查】台北 N 筆、台中 M 筆（MM/DD）」，內容逐筆列出訂單、目前／應收金額、差額、
  異常類型與訂單連結；同一天內容沒變不重複新增。沒有異常也記（0 筆）。
- 只讀取、不修改後台；全部地區失敗或行事曆寫不進去時 exit 1。
Actions 紀錄只印各區筆數與訂單編號，不印客戶姓名、電話。
"""
from __future__ import annotations

import argparse
import traceback
from datetime import date, datetime, time, timedelta
from typing import Callable
from zoneinfo import ZoneInfo

TOOL_NAME = "金額期間檢查：自動排程"
TZ = ZoneInfo("Asia/Taipei")
REGIONS = ("台北", "台中")
CUTOFF = time(17, 0)
CALENDAR_PREFIX = "【金額期間檢查】"


def query_window(today: date) -> tuple[datetime, datetime]:
    """前一天 17:00 ～ 今天 17:00（naive 台北時間）。"""
    end = datetime.combine(today, CUTOFF)
    return end - timedelta(days=1), end


def _log(status: str, area: str, message: str, traceback_text: str = "") -> None:
    try:
        from shared.execution_log_service import log_execution

        log_execution(function_name=TOOL_NAME, status=status, run_type="排程", area=area,
                      message=message, traceback_text=traceback_text)
    except Exception as exc:  # 記錄失敗不影響排程結果
        print(f"WARN 執行 Log 寫入失敗：{exc}", flush=True)


def _scan_region(env: str, email: str, password: str, window: tuple[datetime, datetime],
                 log: Callable[[str], None]) -> dict:
    from memo_system import memo
    from shared import price_period_check as ppc

    memo.set_env(env)
    memo.set_runtime_credentials(email, password)
    session = memo.login()
    return ppc.scan(session, window[0].date(), window[1].date(), "訂購日期", log=log, created_window=window)


def build_calendar_event(result: dict, window: tuple[datetime, datetime], now: datetime) -> dict:
    counts = "、".join(
        f"{region} 失敗" if item.get("error") else f"{region} {len(item.get('rows') or [])} 筆"
        for region, item in result.items() if not item.get("skipped")
    )
    lines = [f"區間：{window[0]:%m/%d %H:%M} ～ {window[1]:%m/%d %H:%M}（訂購時間）", ""]
    for region, item in result.items():
        if item.get("skipped"):
            continue
        if item.get("error"):
            lines += [f"■ {region}：檢查失敗（{item['error']}）", ""]
            continue
        rows = item.get("rows") or []
        lines.append(f"■ {region}：檢查 {item.get('scanned', 0)} 筆，需重新成立 {len(rows)} 筆")
        for r in rows:
            lines.append(f"{r['訂單編號']} {r['訂購人']}｜服務 {r['服務日期']} {r['服務時段']}｜{r['人時']}")
            lines.append(f"　目前 {r['目前金額']}（{r['目前金額計價']}）→ 應收 {r['應收金額']}（{r['服務日計價']}），{r['差額']}｜{r['異常類型']}"
                         + (f"｜{r['備註']}" if r.get("備註") else ""))
            lines.append(f"　{r['訂單連結']}")
        lines.append("")
    return dict(
        summary=f"{CALENDAR_PREFIX}{counts}（{now:%m/%d}）",
        description="\n".join(lines).strip(),
        start=now, reminder_minutes=[0], replace_prefix=CALENDAR_PREFIX,
    )


def run(env: str = "prod", today: date | None = None, regions=REGIONS, scan=None, service_factory=None,
        calendar_ids=None, dry_run: bool = False, log: Callable[[str], None] = print) -> dict:
    from shared.customer_memo_schedule import _preload_modules

    _preload_modules()
    from accounts import ACCOUNTS

    scan = scan or _scan_region
    now = datetime.now(TZ)
    today = today or now.date()
    window = query_window(today)
    log(f"RANGE {window[0]:%Y-%m-%d %H:%M} ～ {window[1]:%Y-%m-%d %H:%M}（{'、'.join(regions)}）")

    result: dict = {}
    for region in regions:
        account = ACCOUNTS.get(region) or {}
        email, password = str(account.get("email") or ""), str(account.get("password") or "")
        if not email or not password:
            log(f"{region}：略過（未設定後台帳密）")
            result[region] = {"skipped": True}
            continue
        try:
            found = scan(env, email, password, window, lambda m: None)
            result[region] = found
            nos = "、".join(r["訂單編號"] for r in found["rows"]) or "無"
            log(f"{region}：檢查 {found['scanned']} 筆，需重新成立 {len(found['rows'])} 筆（{nos}）")
            _log("成功", region, f"檢查 {found['scanned']} 筆，需重新成立 {len(found['rows'])} 筆")
        except Exception as exc:
            msg = f"{type(exc).__name__}: {exc}"
            result[region] = {"error": msg}
            log(f"❌ {region} 檢查失敗：{msg}")
            _log("失敗", region, msg, traceback.format_exc())

    active = [r for r, item in result.items() if not item.get("skipped")]
    if active and all(result[r].get("error") for r in active):
        raise RuntimeError("全部地區檢查失敗")
    if dry_run or not active:
        return result

    event = build_calendar_event(result, window, now)
    from shared.notice_calendar import notice_calendar_ids, write_if_changed

    messages, ok = write_if_changed(event, calendar_ids or notice_calendar_ids(), service_factory)
    for m in messages:
        log(m)
    if not ok:
        raise RuntimeError("行事曆寫入失敗")
    return result


def main():
    parser = argparse.ArgumentParser(description=TOOL_NAME)
    parser.add_argument("--env", default="prod")
    parser.add_argument("--date", default="", help="以這天當作執行日（YYYY-MM-DD，空白＝今天）")
    parser.add_argument("--regions", default=",".join(REGIONS))
    parser.add_argument("--dry-run", action="store_true", help="只檢查不寫行事曆")
    args = parser.parse_args()
    today = date.fromisoformat(args.date) if args.date.strip() else None
    regions = tuple(r.strip() for r in args.regions.split(",") if r.strip()) or REGIONS
    run(env=args.env, today=today, regions=regions, dry_run=args.dry_run, log=lambda m: print(m, flush=True))


if __name__ == "__main__":
    main()
