# -*- coding: utf-8 -*-
"""金額期間檢查：掃日期區間內的訂單，找出改期跨大掃除期間（或平日↔假日）後金額沒重算的訂單。

更新記錄：
2026-11-28（新增）
- scan 加 progress 回呼，頁面顯示逐日進度。
- 依「訂購日期」或「服務日期」逐日查後台訂單列表，付款狀態只查「已付款」「待付款」。
- 每筆用（總金額－車馬費）對服務日期所屬期間（非大掃除／大掃除 PART1／PART2）、平假日的
  VIP／一般客價格；金額剛好是其他期間或另一種平假日的價格 → 列為「應重新成立訂單」。
- 人數：卡片有「N人M小時」直接用；沒有用已配班專員人數；都沒有就試 1～6 人，
  只有沒有任何人數符合本期間價格、且有人數符合其他期間價格時才列出（標「人數推算」）。
- 優惠、折抵、合併、補單等對不上任何價格的訂單不列出。只讀後台，不修改後台。

手動執行：
    python -m shared.price_period_check --start 2026-11-11 --end 2026-11-28 --region 台北
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from shared.line_compare_sheet import _fetch_list, _money, customer_name, each_day

TZ = ZoneInfo("Asia/Taipei")
STATUSES = (("1", "已付款"), ("0", "待付款"))
MAX_DAYS = 92
DATE_FIELDS = {"訂購日期": ("date_s", "date_e"), "服務日期": ("clean_date_s", "clean_date_e")}
GUESS_PERSONS = range(1, 7)


def _card_persons(text: str) -> str:
    import re

    m = re.search(r"(\d+)\s*人\s*\d+(?:\.\d+)?\s*(?:小時|時)", str(text or ""))
    return m.group(1) if m else ""


def check_item(item: dict, config=None) -> dict | None:
    """一筆列表卡片 → 有問題回傳結果 dict，沒問題（或無法判斷）回傳 None。"""
    import service_pricing

    text = str(item.get("row_text", "") or "")
    total, fare = _money(text, "總金額"), _money(text, "車馬費") or 0
    service_date, hour = str(item.get("service_date") or ""), item.get("hour")
    if not total or not service_date or not hour:
        return None
    amount = total - fare
    known = _card_persons(text) or (str(item["staff_count"]) if item.get("staff_count") else "")
    if known:
        status, message = service_pricing.price_status(service_date, known, hour, amount, config, item.get("period"))
        person_note = f"{known}人"
    else:
        results = [(p, *service_pricing.price_status(service_date, p, hour, amount, config, item.get("period")))
                   for p in GUESS_PERSONS]
        if any(s == "ok" for _, s, _ in results):
            return None
        hit = next(((p, s, m) for p, s, m in results if s == "other"), None)
        if not hit:
            return None
        known, status, message = hit
        person_note = f"{known}人（人數推算）"
    if status != "other":
        return None
    return {"人時": f"{person_note}{hour}小時", "服務金額": amount, "問題": message}


def scan(session, start: date, end: date, date_field: str = "訂購日期", log=None, config=None, progress=None) -> dict:
    """回傳 {"rows": 有問題的訂單, "scanned": 檢查筆數}。

    progress(已完成天數, 總天數, 當天, 已檢查筆數, 異常筆數)：每查完一天呼叫一次（開始前先以 0 呼叫）。
    """
    from memo_system import memo
    import service_pricing

    log = log or (lambda m: None)
    if start > end:
        raise ValueError("開始日期不可晚於結束日期")
    if (end - start).days + 1 > MAX_DAYS:
        raise ValueError(f"一次最多查 {MAX_DAYS} 天")
    if date_field not in DATE_FIELDS:
        raise ValueError(f"日期種類只能是 {'、'.join(DATE_FIELDS)}")
    config = config if config is not None else service_pricing.load_config()
    if not config.get("enabled"):
        raise ValueError("「服務金額設定」尚未啟用，無法判斷各期間價格")
    key_s, key_e = DATE_FIELDS[date_field]
    seen, rows = set(), []
    total_days = (end - start).days + 1
    if progress:
        progress(0, total_days, start, 0, 0)
    for index, day in enumerate(each_day(start, end), 1):
        day_total = day_bad = 0
        for status_code, status_name in STATUSES:
            params = memo.blank_list_params()
            params[key_s] = params[key_e] = day.strftime("%Y-%m-%d")
            params["purchase_status"] = status_code
            for item in _fetch_list(session, params):
                if item["order_no"] in seen:
                    continue
                seen.add(item["order_no"])
                day_total += 1
                problem = check_item(item, config)
                if not problem:
                    continue
                day_bad += 1
                rows.append({
                    date_field: day.strftime("%Y/%m/%d"),
                    "訂單編號": item["order_no"],
                    "訂購人": customer_name(item.get("row_text", ""), item.get("name", "")) or item.get("name", ""),
                    "服務日期": item.get("service_date", ""),
                    "服務時段": item.get("period", ""),
                    "付款狀態": status_name,
                    **problem,
                    "LINE連結": item.get("line_url", ""),
                    "訂單連結": f"{memo.BASE_URL}/purchase?orderNo={item['order_no']}",
                })
        log(f"[{day:%m/%d}] 檢查 {day_total} 筆，金額異常 {day_bad} 筆")
        if progress:
            progress(index, total_days, day, len(seen), len(rows))
    return {"rows": rows, "scanned": len(seen)}


def main():
    parser = argparse.ArgumentParser(description="金額期間檢查")
    parser.add_argument("--env", default="prod")
    parser.add_argument("--region", default="台北")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", default="")
    parser.add_argument("--by", default="訂購日期", choices=list(DATE_FIELDS))
    args = parser.parse_args()
    from shared.customer_memo_schedule import _preload_modules

    _preload_modules()
    from accounts import ACCOUNTS
    from memo_system import memo

    account = ACCOUNTS.get(args.region) or {}
    memo.set_env(args.env)
    memo.set_runtime_credentials(str(account.get("email") or ""), str(account.get("password") or ""))
    session = memo.login()
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end) if args.end else datetime.now(TZ).date()
    result = scan(session, start, end, args.by, log=print)
    print(f"共檢查 {result['scanned']} 筆，金額異常 {len(result['rows'])} 筆")
    for row in result["rows"]:
        print(row["訂單編號"], row["服務日期"], row["人時"], row["服務金額"], row["問題"])


if __name__ == "__main__":
    main()
