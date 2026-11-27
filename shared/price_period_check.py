# -*- coding: utf-8 -*-
"""金額期間檢查：掃日期區間內的訂單，找出改期跨大掃除期間（或平日↔假日）後金額沒重算的訂單。

更新記錄：
2026-11-28（新增）
- scan 加 progress 回呼，頁面顯示逐日進度。
- 單筆金額對不上時，用電話查同一服務日期的其他已付款／待付款訂單（不限掃描區間），
  合計（總金額－車馬費）符合本期間價格就不列出（例：主單 9300＋補差價單 300＝9600）；
  合計仍不符才列出，並註明同日其他訂單與合計金額。
- 有退款的訂單（待退狀態：已部分退款／待退款）以後台訂單編輯頁的「退款金額」扣除後再比對
  （例：9000 已部分退款 1800 → 7200）；已全額退款視為 0。
- 有加收（加收狀態不是「無」）同理，讀「加收金額」加回後再比對。
- 計價依據改成兩欄「服務日計價」「目前金額計價」，各為「客戶等級＋期間＋平假日」
  （例：一般客非大掃除假日、一般客大掃除1平日）；期間顯示 非大掃除／大掃除1／大掃除2。
- 只檢查服務類型「居家清潔」的訂單（水洗等其他服務不依人時計價）。
- 結果改成分欄：異常類型／目前金額／應收金額／差額／客戶等級（推定）／目前金額是／服務日屬於／備註／處理。
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


def order_created_at(item: dict):
    """列表卡片「訂購資訊」的訂購時間（第一個 YYYY-MM-DD HH:MM:SS）；沒有回傳 None。"""
    import re

    m = re.search(r"(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2}(?::\d{2})?)", str(item.get("row_text", "") or ""))
    if not m:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(f"{m.group(1)} {m.group(2)}", fmt)
        except ValueError:
            continue
    return None


CHECKED_SERVICE = "居家清潔"


def is_home_cleaning(item: dict) -> bool:
    """卡片上的服務類型是「居家清潔」才檢查（服務金額設定只適用居家清潔；水洗等另計）。"""
    return any(line.strip() == CHECKED_SERVICE for line in str(item.get("row_text", "") or "").splitlines())


def _card_persons(text: str) -> str:
    import re

    m = re.search(r"(\d+)\s*人\s*\d+(?:\.\d+)?\s*(?:小時|時)", str(text or ""))
    return m.group(1) if m else ""


def check_item(item: dict, config=None) -> dict | None:
    """一筆列表卡片 → 有問題回傳結果 dict，沒問題（或無法判斷）回傳 None。"""
    import service_pricing

    text = str(item.get("row_text", "") or "")
    if not is_home_cleaning(item):  # 水洗等其他服務不是依人時計價，不檢查
        return None
    service_date, hour = str(item.get("service_date") or ""), item.get("hour")
    amount = _net_amount(item)
    if not amount or amount <= 0 or not service_date or not hour:
        return None
    known = _card_persons(text) or (str(item["staff_count"]) if item.get("staff_count") else "")
    if known:
        detail = service_pricing.price_detail(service_date, known, hour, amount, config, item.get("period"))
        person_note = f"{known}人"
    else:
        results = [(p, service_pricing.price_detail(service_date, p, hour, amount, config, item.get("period")))
                   for p in GUESS_PERSONS]
        if any(d["status"] == "ok" for _, d in results):
            return None
        hit = next(((p, d) for p, d in results if d["status"] == "other"), None)
        if not hit:
            return None
        known, detail = hit
        person_note = f"{known}人（人數推算）"
    if detail["status"] != "other":
        return None
    diff = detail["diff"]
    notes = ([f"已扣退款 {item['_refund']}"] if item.get("_refund") else []) + \
            ([f"已加加收 {item['_charge']}"] if item.get("_charge") else [])
    tier = service_pricing.TIER_LABELS[detail["tier"]]
    return {
        "服務日期": detail["service_day"],
        "服務日計價": f"{tier}{detail['service_period']}{detail['service_daytype']}",
        "人時": f"{person_note}{hour}小時",
        "異常類型": "平日／假日價格錯" if detail["kind"] == "day" else "期間價格錯（改期跨大掃除期間）",
        "目前金額": detail["amount"],
        "目前金額計價": f"{tier}{detail['charged_period']}{detail['charged_daytype']}",
        "應收金額": detail["expected"],
        "差額": f"{'少收' if diff > 0 else '多收'} {abs(diff)}",
        "備註": "；".join(notes),
        "處理": "重新成立訂單",
        "_person": known, "_hour": hour,
    }


_REFUND_RE = __import__("re").compile(r"待退狀態\s*[：:]\s*(已部[分份]退款|待退款|已全額退款)")
_CHARGE_RE = __import__("re").compile(r"加收狀態\s*[：:]\s*([^\s\n]+)")


def refund_state(item: dict) -> str:
    m = _REFUND_RE.search(str(item.get("row_text", "") or ""))
    return m.group(1) if m else ""


def charge_state(item: dict) -> str:
    """卡片「加收狀態」（已加收、待收款…）；「無」或沒有回傳空字串。"""
    m = _CHARGE_RE.search(str(item.get("row_text", "") or ""))
    return "" if not m or m.group(1) == "無" else m.group(1)


def _net_amount(item: dict):
    """總金額－車馬費－退款金額＋加收金額（退款、加收金額由 load_adjustments 讀後台補上）。"""
    text = str(item.get("row_text", "") or "")
    total = _money(text, "總金額")
    if total is None:
        return None
    if refund_state(item) == "已全額退款":
        return 0
    return (total - (_money(text, "車馬費") or 0)
            - int(item.get("_refund") or 0) + int(item.get("_charge") or 0))


def _int_amount(value) -> int:
    raw = str(value or "").replace(",", "").strip()
    try:
        return int(float(raw)) if raw else 0
    except ValueError:
        return 0


def load_adjustments(session, item: dict) -> bool:
    """有部分退款／待退款或加收時，到後台訂單編輯頁讀「退款金額」「加收金額」，
    存到 item["_refund"]、item["_charge"]；有讀到任一金額回傳 True。每筆只讀一次。"""
    if "_adjusted" in item:
        return False
    item["_adjusted"] = True
    need_refund = refund_state(item) in ("已部分退款", "已部份退款", "待退款")
    need_charge = bool(charge_state(item))
    if not need_refund and not need_charge:
        return False
    from memo_system import change_order
    from memo_system.change_order_fill import _purchase_state

    try:
        order = change_order.fetch_order_basic(item["order_no"], session=session, by="orderNo") or {}
        state = _purchase_state(session, order)
    except Exception:
        return False
    if need_refund:
        item["_refund"] = _int_amount(state.get("refundAmount"))
    if need_charge:
        item["_charge"] = _int_amount(state.get("chargeAmount"))
    return bool(item.get("_refund") or item.get("_charge"))


def _same_day_orders(session, item: dict) -> list[dict]:
    """同電話、同服務日期的其他已付款／待付款訂單（不限訂購日期）。"""
    from memo_system import memo

    phone, service_date = str(item.get("phone") or "").strip(), str(item.get("service_date") or "")
    if not phone or not service_date:
        return []
    day = service_date.replace("/", "-")
    found = {}
    for status_code, _ in STATUSES:
        params = memo.blank_list_params()
        params["phone"] = phone
        params["clean_date_s"] = params["clean_date_e"] = day
        params["purchase_status"] = status_code
        for other in _fetch_list(session, params):
            if other["order_no"] != item["order_no"] and str(other.get("service_date") or "") == service_date:
                found[other["order_no"]] = other
    return sorted(found.values(), key=lambda x: x["order_no"])


def group_check(item: dict, problem: dict, others: list[dict], config=None):
    """同日多筆合計檢查。回傳 (合計是否正確, 合計金額)。

    人時可能是重疊（訂單轉換、補差價單：同一批人時拆兩張單）或相加（主單＋補單），兩種都試。
    """
    import service_pricing

    amounts = [problem["目前金額"]] + [a for a in (_net_amount(o) for o in others) if a is not None]
    total = sum(amounts)
    p0 = problem["_person"]
    phs = [float(p0) * float(problem["_hour"])]
    for other in others:
        p = _card_persons(other.get("row_text", "")) or (str(other["staff_count"]) if other.get("staff_count") else p0)
        try:
            phs.append(float(p) * float(other.get("hour") or 0))
        except (TypeError, ValueError):
            pass
    candidates = {ph for ph in phs if ph > 0} | {sum(ph for ph in phs if ph > 0)}
    for ph in candidates:
        status, _ = service_pricing.price_status(item.get("service_date"), 1, ph, total, config)
        if status == "ok":
            return True, total
    return False, total


def scan(session, start: date, end: date, date_field: str = "訂購日期", log=None, config=None, progress=None,
         created_window=None) -> dict:
    """回傳 {"rows": 有問題的訂單, "scanned": 檢查筆數}。

    progress(已完成天數, 總天數, 當天, 已檢查筆數, 異常筆數)：每查完一天呼叫一次（開始前先以 0 呼叫）。
    created_window＝(起, 迄)（naive 台北時間）：只檢查訂購時間在 [起, 迄) 內的訂單（排程用）。
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
                if created_window:
                    created = order_created_at(item)
                    if created and not (created_window[0] <= created < created_window[1]):
                        continue
                seen.add(item["order_no"])
                day_total += 1
                problem = check_item(item, config)
                if problem and load_adjustments(session, item):
                    log(f"{item['order_no']} 退款 {item.get('_refund', 0)}／加收 {item.get('_charge', 0)}，調整後重新比對")
                    problem = check_item(item, config)
                if not problem:
                    continue
                others = _same_day_orders(session, item)
                for other in others:
                    load_adjustments(session, other)
                if others:
                    ok, total = group_check(item, problem, others, config)
                    listed = "、".join(o["order_no"] for o in others)
                    if ok:
                        log(f"{item['order_no']} 同日另有 {listed}，合計 {total} 正確，不列出")
                        continue
                    problem["備註"] = "；".join(x for x in (problem["備註"], f"同日另有 {listed}，合計 {total} 仍不符") if x)
                problem.pop("_person", None)
                problem.pop("_hour", None)
                day_bad += 1
                rows.append({
                    date_field: day.strftime("%Y/%m/%d"),
                    "訂單編號": item["order_no"],
                    "訂購人": customer_name(item.get("row_text", ""), item.get("name", "")) or item.get("name", ""),
                    "服務日期": problem.pop("服務日期"),
                    "服務時段": item.get("period", ""),
                    "服務日計價": problem.pop("服務日計價"),
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
        print(row["訂單編號"], row["服務日期"], row["人時"], f"目前 {row['目前金額']}", f"應收 {row['應收金額']}", row["差額"], row["異常類型"], row["備註"])


if __name__ == "__main__":
    main()
