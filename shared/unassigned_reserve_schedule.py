# -*- coding: utf-8 -*-
"""未配班成立保留單：自動排程。區間內有未配班專員就成立檸檬保留單。

更新記錄：
2026-11-22
- 結果記到排程行事曆 SCHEDULE_NOTICE_CALENDAR_ID：標題「【未配班保留單】台北 成立 N 張…（MM/DD）」；
  內容跟今天最新一則一樣就不新增（留最早那則），有變才再新增一則。沒設定行事曆只略過、不算失敗。
- 加入合併單人保留單：同時段 2 張以上 1 人保留單先取消，再重新成立 N 人單。
- 區間日期接受 2027/01/22、2027/1/22 等寫法（repository variable 填斜線會失敗）。
- 新增（Jenny）。由 tool-system 的 Cloud Schedule Router 依主控表「排程設定」
  （功能代號 unassigned_reserve_create，08:30～17:30 每小時）派送
  .github/workflows/unassigned-reserve-schedule.yml。

規則（同「未配班檢查 → ① 成立保留單」，見 shared/unassigned_staff.py）：
- 範圍：在「未配班檢查 → ① 成立保留單」頁面設定（存主控表「參數設定」，2026-11-26 起）；
  沒設定時用 repository variable UNASSIGNED_RESERVE_START／END，再沒有用 2027/01/22～2027/02/04。
  頁面也可設「自動成立停止日」：當天（含）起排程不再成立。開始日早於明天時從明天起，
  過了結束日就略過。不算檸檬人、晚上時段。
- 同一天同一時段（上午／下午／全天）合成一張：人數＝人數、時數取最短；1 人也成立 1人單。
- 後台查不到這麼多人時人數減 1 再試。
- 保留會員 0939592628、儲值金；地址用該區的保留地址（台北：信義路四段210號4樓、台中：館前路19號4樓）。
- 備註、「保留單紀錄」工作表沿用檸檬保留單建單；結果寫執行 Log。
- 同一天同一時段有 2 張以上 1 人保留單：先取消，再重新成立 N 人保留單；專員全是檸檬人的保留單取消
  （shared/unassigned_staff.merge_and_create）。
"""
from __future__ import annotations

import argparse
import traceback
from datetime import date, datetime, timedelta
from typing import Callable
from zoneinfo import ZoneInfo

TOOL_NAME = "未配班成立保留單：自動排程"
TZ = ZoneInfo("Asia/Taipei")
REGIONS = ("台北",)
RESERVE_START, RESERVE_END = "2027-01-22", "2027-02-04"
CITY = {"台北": "台北市", "台中": "台中市"}
CALENDAR_PREFIX = "【未配班保留單】"


def build_calendar_event(region: str, results: list, date_start: str, date_end: str, now: datetime) -> dict:
    ok = [r for r in results if r.get("success")]
    bad = [r for r in results if not r.get("success") and r.get("message") != "已無未配班專員"]
    lines = []
    for r in ok:
        lines.append(f"✅ {r.get('service_date')} {r.get('group')} {r.get('period', '')} "
                     f"{r.get('person', 0)}人 {r.get('order_no', '')}".rstrip())
    for r in bad:
        lines.append(f"❌ {r.get('service_date')} {r.get('group')}：{r.get('message', '')}".rstrip())
    if not lines:
        lines = ["（沒有需要成立的保留單）"]
    lines += ["", f"範圍：{region} {date_start}～{date_end}（不含檸檬人、晚上時段）"]
    title = f"成立 {len(ok)} 張" + (f"、未成立 {len(bad)} 個時段" if bad else "")
    return dict(summary=f"{CALENDAR_PREFIX}{region} {title}（{now:%m/%d}）", description="\n".join(lines),
                start=now, reminder_minutes=[0], replace_prefix=f"{CALENDAR_PREFIX}{region}")


def write_calendar(event: dict, service_factory=None, calendar_ids=None) -> list:
    """記到排程行事曆（內容沒變不新增）；沒設定行事曆或寫失敗只回報，不影響保留單結果。"""
    from shared.notice_calendar import MISSING_MESSAGE, notice_calendar_ids, write_if_changed

    calendar_ids = tuple(calendar_ids) if calendar_ids is not None else notice_calendar_ids()
    if not calendar_ids:
        return [MISSING_MESSAGE]
    try:
        messages, _ok = write_if_changed(event, calendar_ids, service_factory)
    except Exception as exc:
        messages = [f"⚠️ 記入行事曆失敗：{type(exc).__name__}: {exc}"]
    return messages


def parse_day(value: str) -> date:
    """2027-01-22、2027/01/22、2027/1/22、2027.1.22 都可以（2026-11-22）。"""
    import re

    m = re.fullmatch(r"\s*(\d{4})\s*[-/.]\s*(\d{1,2})\s*[-/.]\s*(\d{1,2})\s*", str(value or ""))
    if not m:
        raise ValueError(f"日期格式看不懂：{value!r}（請填 2027/01/22 或 2027-01-22）")
    return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))


def date_range(today: date, start: str = "", end: str = "", settings: dict | None = None) -> tuple[str, str] | None:
    """保留單區間；開始日早於明天就從明天起，已經過了結束日回傳 None。
    順序：手動參數 → 主控表參數設定（頁面設定）→ repository variable → 程式預設。"""
    import os

    from shared.reserve_settings import END_ITEM, START_ITEM

    settings = settings or {}
    start = (start or settings.get(START_ITEM, "") or os.getenv("UNASSIGNED_RESERVE_START", "")
             or RESERVE_START).strip()
    end = (end or settings.get(END_ITEM, "") or os.getenv("UNASSIGNED_RESERVE_END", "") or RESERVE_END).strip()
    first = max(parse_day(start), today + timedelta(days=1))
    last = parse_day(end)
    return None if first > last else (first.isoformat(), last.isoformat())


def _log(status: str, area: str, message: str, traceback_text: str = "") -> None:
    try:
        from shared.execution_log_service import log_execution

        log_execution(function_name=TOOL_NAME, status=status, run_type="排程", area=area,
                      message=message, traceback_text=traceback_text)
    except Exception as exc:
        print(f"WARN 執行 Log 寫入失敗：{exc}", flush=True)


def pick_address(region: str, addresses: list[str]) -> str:
    """該區的保留地址；會員沒有這個地址時用同城市的第一個地址。"""
    from function.reserve_address import KEEP_ADDRESSES

    city = CITY.get(region, region)
    for keep in KEEP_ADDRESSES:
        if keep.startswith(city) and keep in addresses:
            return keep
    same_city = [a for a in addresses if a.startswith(city)]
    if same_city:
        return same_city[0]
    raise RuntimeError(f"保留會員沒有{region}的地址")


def _run_region(env: str, region: str, email: str, password: str, date_start: str, date_end: str,
                log: Callable[[str], None]) -> list[dict]:
    from function.reserve_optimizer import login_reserve_member, member_addresses
    from shared.unassigned_staff import merge_and_create

    lookup = login_reserve_member(env, email, password)
    address = pick_address(region, member_addresses(lookup))
    log(f"{region}：保留地址 {address}")
    out = merge_and_create(env_name=env, backend_email=email, backend_password=password, lookup_result=lookup,
                           region=region, address=address, date_start=date_start, date_end=date_end,
                           payway="儲值金", log=log)
    for c in out["cancelled"]:
        mark = "🗑️" if c.get("ok") else "❌"
        log(f"{mark} 取消 {c.get('service_date')} {c.get('period', '')} {c.get('order_no')} {c.get('message', '')}".rstrip())
    return out["created"] + [
        {"service_date": c.get("service_date"), "group": c.get("merge_group"), "period": c.get("period", ""),
         "success": False, "person": 0, "order_no": c.get("order_no", ""), "message": f"取消失敗（{c.get('merge_group')}）：{c.get('message', '')}"}
        for c in out["cancelled"] if not c.get("ok")
    ]


def run(env: str = "prod", today: date | None = None, regions=REGIONS, start: str = "", end: str = "",
        run_region=None, log: Callable[[str], None] = lambda t: print(t, flush=True),
        service_factory=None, calendar_ids=None, settings: dict | None = None) -> dict:
    import orders  # noqa: F401  （與其他排程相同的載入順序）
    from accounts import ACCOUNTS
    from shared import reserve_settings

    run_region = run_region or _run_region
    today = today or datetime.now(TZ).date()
    settings = reserve_settings.load(log=log) if settings is None else settings
    stop_day = reserve_settings.stopped(today, settings)
    if stop_day:
        log(f"已設定 {stop_day:%Y/%m/%d} 起停止自動成立保留單，略過")
        return {"range": None, "result": {}, "stopped": stop_day.isoformat()}
    window = date_range(today, start, end, settings)
    if window is None:
        log(f"已過保留單區間（{start or settings.get(reserve_settings.START_ITEM) or RESERVE_START}～"
            f"{end or settings.get(reserve_settings.END_ITEM) or RESERVE_END}），略過")
        return {"range": None, "result": {}}
    date_start, date_end = window
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
            results = run_region(env, region, email, password, date_start, date_end, log)
        except Exception as exc:
            msg = f"{type(exc).__name__}: {exc}"
            log(f"❌ {region} 失敗：{msg}")
            _log("失敗", region, f"{date_start}～{date_end}：{msg}", traceback.format_exc())
            failed.append(region)
            out[region] = {"error": msg}
            continue
        ok = [r for r in results if r.get("success")]
        bad = [r for r in results if not r.get("success") and r.get("message") != "已無未配班專員"]
        for r in results:
            mark = "✅" if r.get("success") else "❌"
            log(f"{mark} {r.get('service_date')} {r.get('group')} {r.get('period', '')} "
                f"{r.get('person', 0)}人 {r.get('order_no', '')} {r.get('message', '')}".rstrip())
        summary = f"{date_start}～{date_end}：成立 {len(ok)} 張" + (f"、未成立 {len(bad)} 個時段" if bad else "")
        log(f"{region}：{summary}")
        for m in write_calendar(build_calendar_event(region, results, date_start, date_end, datetime.now(TZ)),
                                service_factory=service_factory, calendar_ids=calendar_ids):
            log(m)
        _log("失敗" if bad else "成功", region, summary + ("；" + "；".join(
            f"{r.get('service_date')} {r.get('group')}：{r.get('message')}" for r in bad) if bad else ""))
        out[region] = {"results": results}
    if failed:
        raise RuntimeError("未配班成立保留單失敗：" + "、".join(failed))
    return {"range": (date_start, date_end), "result": out}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--env", default="prod")
    parser.add_argument("--date", default="", help="以這天當作執行日（YYYY-MM-DD，測試用）")
    parser.add_argument("--regions", default=",".join(REGIONS), help="逗號分隔，預設台北")
    parser.add_argument("--start", default="", help="保留單開始日（空白＝頁面設定／參數設定）")
    parser.add_argument("--end", default="", help="保留單結束日（空白＝頁面設定／參數設定）")
    args = parser.parse_args()
    today = parse_day(args.date) if args.date.strip() else None
    regions = tuple(r.strip() for r in args.regions.split(",") if r.strip()) or REGIONS
    try:
        run(env=args.env, today=today, regions=regions, start=args.start.strip(), end=args.end.strip())
    except Exception as exc:
        _log("失敗", "、".join(regions), str(exc), traceback.format_exc())
        raise


if __name__ == "__main__":
    main()
