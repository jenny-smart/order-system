# -*- coding: utf-8 -*-
"""未配班檢查：讀 /schedule 灰底「未配班」名單，成立檸檬保留單／記錄只剩 1 人的時段。

更新記錄：
2026-11-21
- 新增（Jenny）。
  功能1 成立保留單：日期區間內只要有未配班專員（不管是不是新增），同一天同一時段
  （上午／下午／全天）的人合成一張保留單，人數＝人數、時數取最短（1人2小時＋1人3小時
  → 2人2小時；只有 1 人就成立 1人單）。後台查不到這麼多人（例如有人不服務保留地址）時，
  人數減 1 再試，直到 1 人。
  功能2 記錄未配班人員：未來 2 週某天某時段未配班只剩 1 位專員，記「YYYY/MM/DD 下午-1」，
  寫到獨立行事曆（SCHEDULE_NOTICE_CALENDAR_ID）；還沒設定時先寫 tpe@、jenny@lemonclean.com.tw。

規則：
- 檸檬人是占位用的，不算專員（不建保留單、也不算進只剩 1 人）。
- 同一人出現在同一組多個時段欄位時只算一次，時數取最長。
- 晚上時段不處理。
- 保留單備註沿用檸檬保留單建單：客人備註「系統保留單」、客服備註「大掃除檸檬保留單」，
  成立紀錄寫「保留單紀錄」工作表。
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Callable, Dict, List, Optional

from bs4 import BeautifulSoup

GROUPS = ("上午", "下午", "全天")
# 各組依時數對應的時段欄位（與 shared/cleaner_shift.PERIOD_TO_SHIFT_CODE 相同）
GROUP_PERIODS: Dict[str, Dict[int, str]] = {
    "上午": {2: "09:00-11:00", 3: "09:00-12:00", 4: "08:30-12:30"},
    "下午": {2: "14:00-16:00", 3: "14:00-17:00", 4: "14:00-18:00"},
    "全天": {6: "09:00-16:00", 8: "09:00-18:00"},
}
PERIOD_INFO = {p: (g, h) for g, m in GROUP_PERIODS.items() for h, p in m.items()}
CALENDAR_PREFIX = "【未配班剩1人】"
# 排程紀錄專用的獨立行事曆（未配班、檸檬人待換專員共用），避免寫進 tpe@／jenny@ 干擾
NOTICE_CALENDAR_ENV = "SCHEDULE_NOTICE_CALENDAR_ID"


# 獨立行事曆還沒建之前，先記在原本的行事曆（與檸檬人待換專員相同）
DEFAULT_CALENDAR_IDS = ("tpe@lemonclean.com.tw", "jenny@lemonclean.com.tw")


def notice_calendar_ids(default: tuple = DEFAULT_CALENDAR_IDS) -> tuple:
    """SCHEDULE_NOTICE_CALENDAR_ID（逗號分隔）；沒設定時用 default。"""
    import os

    ids = tuple(x.strip() for x in os.getenv(NOTICE_CALENDAR_ENV, "").split(",") if x.strip())
    return ids or tuple(default)
_PERIOD_RE = re.compile(r"\d{1,2}:\d{2}-\d{1,2}:\d{2}")
_COUNT_RE = re.compile(r"未配班\s*(\d+)\s*人")


def _label_name(label: str) -> str:
    from quick_order import _unassigned_label_staff_name

    return _unassigned_label_staff_name(label)


def _row_date(label: str, query_date: str) -> Optional[str]:
    from memo_system.shift import _row_label_to_date

    return _row_label_to_date(label, query_date)


def parse_week_unassigned(html: str, query_date: str) -> List[Dict]:
    """一週班表 → [{date, period, group, hours, name, lemon}]（每個未配班人員一筆）。"""
    soup = BeautifulSoup(html or "", "html.parser")
    out: List[Dict] = []
    for table in soup.find_all("table"):
        periods: List[str] = []
        for tr in table.find_all("tr"):
            cells = tr.find_all(["td", "th"], recursive=False)
            if not cells:
                continue
            texts = [re.sub(r"\s+", "", c.get_text(" ", strip=True)) for c in cells]
            if any(_PERIOD_RE.fullmatch(t) for t in texts[1:]):
                periods = [t if _PERIOD_RE.fullmatch(t) else "" for t in texts]
                continue
            if not periods:
                continue
            day = _row_date(cells[0].get_text(" ", strip=True), query_date)
            if not day:
                continue
            for idx, cell in enumerate(cells[1:], start=1):
                period = periods[idx] if idx < len(periods) else ""
                if period not in PERIOD_INFO:
                    continue
                group, hours = PERIOD_INFO[period]
                blocks = cell.select('p[style*="616161"], div[style*="616161"]') or [
                    d for d in cell.find_all(["div", "p"]) if _COUNT_RE.search(d.get_text(" ", strip=True))
                ]
                if not blocks and _COUNT_RE.search(cell.get_text(" ", strip=True)):
                    blocks = [cell]
                for block in blocks:
                    text = block.get_text("\n", strip=True)
                    m = _COUNT_RE.search(text)
                    if not m:
                        continue
                    names = [n for n in (_label_name(t) for t in re.split(r"[\n\s,，、]+", text[m.end():])) if n]
                    for name in names[:int(m.group(1))]:  # 只取畫面上的人數，避免讀到後面訂單的專員
                        out.append({"date": day, "period": period, "group": group, "hours": hours,
                                    "name": name, "lemon": name.startswith("檸檬人")})
    return out


def summarize(entries: List[Dict]) -> Dict[tuple, Dict[str, int]]:
    """(date, group) → {專員: 時數}；不含檸檬人，同一人取最長時數。"""
    out: Dict[tuple, Dict[str, int]] = {}
    for e in entries:
        if e.get("lemon"):
            continue
        people = out.setdefault((e["date"], e["group"]), {})
        people[e["name"]] = max(people.get(e["name"], 0), int(e["hours"]))
    return out


def scan_range(get_html: Callable[[str], str], date_start: str, date_end: str) -> Dict[tuple, Dict[str, int]]:
    """逐週讀班表（後台一頁一週），回傳區間內的 summarize 結果。"""
    start, end = date.fromisoformat(date_start), date.fromisoformat(date_end)
    if end < start:
        start, end = end, start
    entries: List[Dict] = []
    week = start - timedelta(days=start.weekday())
    while week <= end:
        entries += parse_week_unassigned(get_html(week.isoformat()), week.isoformat())
        week += timedelta(days=7)
    s, e = start.isoformat(), end.isoformat()
    return {k: v for k, v in summarize(entries).items() if s <= k[0] <= e and v}


def period_for(group: str, hours: int) -> str:
    """組別＋時數 → 時段；沒有剛好的時數就取不超過的最長時段。"""
    options = GROUP_PERIODS[group]
    fit = [h for h in options if h <= hours] or [min(options)]
    return options[max(fit)]


def build_plan(summary: Dict[tuple, Dict[str, int]]) -> List[Dict]:
    """每個（日期, 時段組）一張保留單：人數＝人數、時數取最短。"""
    plan = []
    for (day, group), people in sorted(summary.items(), key=lambda kv: (kv[0][0], GROUPS.index(kv[0][1]))):
        hours = min(people.values())
        period = period_for(group, hours)
        plan.append({"service_date": day, "group": group, "period": period, "hours": PERIOD_INFO[period][1],
                     "person": len(people),
                     "staff": "、".join(f"{n}({h})" for n, h in sorted(people.items()))})
    return plan


def single_left(summary: Dict[tuple, Dict[str, int]]) -> List[Dict]:
    """只剩 1 位未配班專員的時段。"""
    rows = []
    for (day, group), people in sorted(summary.items(), key=lambda kv: (kv[0][0], GROUPS.index(kv[0][1]))):
        if len(people) == 1:
            name, hours = next(iter(people.items()))
            rows.append({"date": day, "group": group, "name": name, "hours": hours,
                         "text": f"{day.replace('-', '/')} {group}-1"})
    return rows


# ---------------------------------------------------------------------------
# 功能1：成立保留單
# ---------------------------------------------------------------------------
def _schedule_getter(lookup_result) -> Callable[[str], str]:
    from function.reserve_optimizer import fetch_schedule_html

    return lambda d: fetch_schedule_html(lookup_result, d)


def create_reserve_orders(*, env_name: str, lookup_result, region: str, address: str, plan: List[Dict],
                          payway: str = "儲值金", clean_type_id: str = "1", max_rounds: int = 10,
                          get_html: Optional[Callable[[str], str]] = None,
                          create_stored=None, create_single=None, finish=None, log_rows=None,
                          log: Callable[[str], None] = lambda _t: None) -> List[Dict]:
    """依計畫成立保留單；每輪先重讀班表，後台人力不足時人數減 1 再試。

    回傳每個日期時段的結果 [{service_date, group, period, person, success, order_no, message}]。
    """
    import quick_order as qo
    from function import reserve_optimizer as ro

    get_html = get_html or _schedule_getter(lookup_result)
    create_stored = create_stored or qo.quick_create_stored_value_orders
    create_single = create_single or qo.quick_create_order
    finish = finish or ro._finish_reserve_order
    log_rows = log_rows or ro._log_round_rows
    payway = qo.normalize_booking_payway(payway)
    base_url = lookup_result.get("base_url") or qo._configure_environment(env_name)
    batch_id = ro._build_batch_id()
    caps = {(p["service_date"], p["group"]): int(p["person"]) for p in plan}
    results: List[Dict] = []

    def done(key, **row):
        results.append({"service_date": key[0], "group": key[1], **row})
        caps.pop(key, None)

    for round_no in range(1, max_rounds + 1):
        if not caps:
            break
        dates = sorted({k[0] for k in caps})
        fresh = scan_range(get_html, dates[0], dates[-1])
        active = []
        for key in list(caps):
            people = fresh.get(key) or {}
            if not people:
                done(key, period="", person=0, success=False, order_no="", message="已無未配班專員")
                continue
            person = min(caps[key], len(people))
            period = period_for(key[1], min(people.values()))
            active.append({"key": key, "slot": f"{key[0]}_{period}", "period": period,
                           "hours": PERIOD_INFO[period][1], "person": person})
        log(f"第 {round_no} 輪：{len(active)} 個日期時段")

        def retry_or_stop(item, reason):
            key = item["key"]
            if item["person"] > 1:
                caps[key] = item["person"] - 1
                log(f"{key[0]} {key[1]} {item['person']} 人{reason}，改 {item['person'] - 1} 人再試")
            else:
                done(key, period=item["period"], person=0, success=False, order_no="", message=reason)

        if payway == "儲值金":
            groups: Dict[tuple, List[Dict]] = {}
            for item in active:
                groups.setdefault((item["hours"], item["person"]), []).append(item)
            for (hours, person), items in groups.items():
                by_slot = {i["slot"]: i for i in items}
                try:
                    outcome = create_stored(env_name, region, lookup_result, address, clean_type_id,
                                            list(by_slot), str(hours), person=str(person),
                                            extra_fields={"notice": ro.CUSTOMER_SERVICE_NOTE})
                except Exception as exc:
                    for item in items:
                        done(item["key"], period=item["period"], person=0, success=False, order_no="",
                             message=f"送出失敗：{exc}")
                    continue
                session = outcome.get("session") or lookup_result["session"]
                rows = []
                for order in outcome.get("orders") or []:
                    item = by_slot.get(order["slot"])
                    if not item:
                        continue
                    row = finish(session, base_url, order["order_no"], order["date"], order["period_s"],
                                 order.get("staff"), 0, batch_id)
                    rows.append(row)
                    done(item["key"], period=item["period"], person=person, success=True,
                         order_no=order["order_no"], staff=order.get("staff") or "",
                         message="" if row.get("customer_memo_ok") else f"備註未寫入：{row.get('customer_memo_message')}")
                log_rows(rows, batch_id)
                for slot in outcome.get("unavailable") or []:
                    if slot in by_slot:
                        retry_or_stop(by_slot[slot], "後台查不到可預約人力")
                for slot in outcome.get("not_created") or []:
                    if slot in by_slot:
                        reason = "儲值金餘額不足" if outcome.get("failed_count") else "送出後未找到新訂單，請至後台確認"
                        done(by_slot[slot]["key"], period=by_slot[slot]["period"], person=0, success=False,
                             order_no="", message=reason)
        else:
            for item in active:
                key = item["key"]
                try:
                    result = create_single(
                        env_name=env_name, payway=payway, region=region, lookup_result=lookup_result,
                        address=address, clean_type_id=clean_type_id, date_s=key[0], period_s=item["period"],
                        hour=str(item["hours"]), person=str(item["person"]), allow_auto_lemon_shift=False,
                        extra_fields={"notice": ro.CUSTOMER_SERVICE_NOTE},
                    )
                except Exception as exc:
                    if "無可預約" in str(exc) or "服務區域" in str(exc):
                        retry_or_stop(item, "後台查不到可預約人力")
                    else:
                        done(key, period=item["period"], person=0, success=False, order_no="", message=str(exc))
                    continue
                row = finish(result.get("session") or lookup_result["session"], base_url, result["order_no"],
                             key[0], item["period"], result.get("staff"), 0, batch_id)
                log_rows([row], batch_id)
                done(key, period=item["period"], person=item["person"], success=True,
                     order_no=result["order_no"], staff=result.get("staff") or "",
                     message="" if row.get("customer_memo_ok") else f"備註未寫入：{row.get('customer_memo_message')}")
    for key in list(caps):
        done(key, period="", person=0, success=False, order_no="", message=f"超過 {max_rounds} 輪仍未完成")
    results.sort(key=lambda r: (r["service_date"], GROUPS.index(r["group"])))
    return results


# ---------------------------------------------------------------------------
# 功能2：記錄未配班人員到獨立行事曆
# ---------------------------------------------------------------------------
def build_calendar_event(region: str, rows: List[Dict], date_start: str, date_end: str, now) -> dict:
    lines = [r["text"] for r in rows] or ["（沒有只剩 1 人的時段）"]
    lines += ["", f"範圍：{region} {date_start}～{date_end}（不含檸檬人、晚上時段）"]
    return dict(summary=f"{CALENDAR_PREFIX}{region} {len(rows)} 個時段（{now:%m/%d}）",
                description="\n".join(lines), start=now, reminder_minutes=[0],
                replace_prefix=f"{CALENDAR_PREFIX}{region}")
