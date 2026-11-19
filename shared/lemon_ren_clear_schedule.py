# -*- coding: utf-8 -*-
"""排班管理「清空檸檬人」自動排程：每日 12:30、18:00 清空未配班清單中的檸檬人。

更新記錄：
2026-11-20
- 新增（Jenny）。由 tool-system 的 Cloud Schedule Router 依主控表「排程設定」
  （功能代號 lemon_ren_clear）派送 .github/workflows/lemon-ren-clear-schedule.yml。

規則：
- 等同 ordersapp【排班管理】→ 清空排班 →「掃描並清空未配班清單」：
  memo_system.shift.find_unassigned_lemon_bookings_range → clear_unassigned_lemon_bookings（同一套程式）。
- 清空範圍＝當月 1 日～＋4 個月的月底（例：11/20 執行 → 11/01～隔年 03/31）。
- 五區各用自己的後台帳號（accounts.ACCOUNTS）；沒設帳密的地區略過，不擋其他地區。
- 有地區失敗時 exit 1（tool-system 行事曆紀錄會標 ❌）；每區結果寫執行 Log。
"""
from __future__ import annotations

import argparse
import calendar
import traceback
from datetime import date, datetime
from typing import Callable
from zoneinfo import ZoneInfo

TOOL_NAME = "清空未配班檸檬人：自動排程"
TZ = ZoneInfo("Asia/Taipei")
REGIONS = ("台北", "台中", "桃園", "新竹", "高雄")
DEFAULT_MONTHS = 4


def date_range(today: date, months: int = DEFAULT_MONTHS) -> tuple[str, str]:
    """當月 1 日～＋months 個月的月底（含）。"""
    total = today.year * 12 + (today.month - 1) + months
    year, month = divmod(total, 12)
    month += 1
    end = date(year, month, calendar.monthrange(year, month)[1])
    return today.replace(day=1).isoformat(), end.isoformat()


def _log(status: str, area: str, message: str, traceback_text: str = "") -> None:
    try:
        from shared.execution_log_service import log_execution

        log_execution(function_name=TOOL_NAME, status=status, run_type="排程", area=area,
                      message=message, traceback_text=traceback_text)
    except Exception as exc:  # 記錄失敗不影響排程結果
        print(f"WARN 執行 Log 寫入失敗：{exc}", flush=True)


def _clear_region(env: str, email: str, password: str, date_start: str, date_end: str,
                  log: Callable[[str], None]) -> dict:
    from memo_system import memo, shift

    memo.set_env(env)
    memo.set_runtime_credentials(email, password)
    session = memo.login(ui_logger=log)
    entries = shift.find_unassigned_lemon_bookings_range(
        session=session, date_start=date_start, date_end=date_end, ui_logger=log)
    results = shift.clear_unassigned_lemon_bookings(session=session, entries=entries, ui_logger=log) if entries else []
    return {
        "found": len(entries),
        "people": len(results),
        "cleared_days": sum(len(r.get("cleared_dates") or []) for r in results),
        "slots": sum(int(r.get("cleared_slot_count") or 0) for r in results),
        "errors": [f"{r.get('name', '')}：{e}" for r in results for e in (r.get("errors") or [])],
    }


def summary(region: str, item: dict) -> str:
    if item.get("skipped"):
        return f"{region}／清空檸檬人：略過（未設定後台帳密）"
    if item.get("error"):
        return f"{region}／清空檸檬人：錯誤 {item['error']}"
    if not item["found"]:
        return f"{region}／清空檸檬人：未配班清單沒有檸檬人"
    text = (f"{region}／清空檸檬人：{item['people']} 人，{item['cleared_days']} 天有清到資料，"
            f"移除 {item['slots']} 筆勾選")
    if item["errors"]:
        text += "；失敗 " + "；".join(item["errors"])
    return text


def run(env: str = "prod", today: date | None = None, regions=REGIONS, months: int = DEFAULT_MONTHS,
        clear=None, log: Callable[[str], None] | None = None) -> dict:
    import orders  # noqa: F401  （先載入 orders，與其他排程相同的載入順序）
    from accounts import ACCOUNTS

    log = log or (lambda text: print(text, flush=True))
    clear = clear or _clear_region
    today = today or datetime.now(TZ).date()
    date_start, date_end = date_range(today, months)
    log(f"RANGE {date_start} ～ {date_end}（{'、'.join(regions)}）")

    result: dict = {}
    for region in regions:
        account = ACCOUNTS.get(region) or {}
        email, password = str(account.get("email") or ""), str(account.get("password") or "")
        if not email or not password:
            item = {"skipped": True}
        else:
            log(f"\n===== 【{region}】=====")
            try:
                item = clear(env, email, password, date_start, date_end, log)
            except Exception as exc:
                item = {"error": f"{type(exc).__name__}: {exc}"}
        result[region] = item
        line = summary(region, item)
        failed = bool(item.get("error") or item.get("errors"))
        if not item.get("skipped"):
            _log("失敗" if failed else "成功", region, f"{date_start}～{date_end}：{line}")

    log("\n===== 結果 =====")
    for region, item in result.items():  # 每區一行
        log(summary(region, item))
    failed = [r for r, i in result.items() if i.get("error") or i.get("errors")]
    if failed:
        raise RuntimeError("清空檸檬人失敗：" + "、".join(failed))
    return {"range": (date_start, date_end), "result": result}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--env", default="prod")
    parser.add_argument("--date", default="", help="以這天當作執行日（YYYY-MM-DD，測試用）")
    parser.add_argument("--regions", default=",".join(REGIONS), help="逗號分隔，預設五區")
    parser.add_argument("--months", type=int, default=DEFAULT_MONTHS, help="清空到當月＋幾個月的月底（預設 4）")
    args = parser.parse_args()
    today = date.fromisoformat(args.date) if args.date.strip() else None
    regions = tuple(r.strip() for r in args.regions.split(",") if r.strip()) or REGIONS
    try:
        run(env=args.env, today=today, regions=regions, months=args.months)
    except Exception as exc:
        _log("失敗", "、".join(regions), str(exc), traceback.format_exc())
        raise


if __name__ == "__main__":
    main()
