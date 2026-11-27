# -*- coding: utf-8 -*-
"""未配班檢查：讀 /schedule 灰底「未配班」名單，成立檸檬保留單／記錄只剩 1 人的時段。

更新記錄：
2026-11-27
- 檸檬人保留單（Jenny）：在成立保留單的日期區間內，客服備註沒有「檸檬人勿動」時
  - 專員只有檸檬人 → 取消訂單；
  - 檸檬人＋非檸檬人 → 先取消訂單，再就非檸檬人建立保留單（取消後非檸檬人回到灰底未配班，
    接著依未配班成立，同時段的未配班照樣合成一張）。
  客服備註有「檸檬人勿動」的保留單一律不動。
2026-11-22
- 合併單人保留單（Jenny）：同一天同一時段（上午／下午／全天）有 2 張以上「1 人」的系統保留單，
  先全部取消（客人備註改「取消系統保留單」），再依未配班重新成立一張 N 人保留單（時數取最短）。
  排程與頁面「確定成立」都會做：合併 → 成立 → 再檢查一次合併 → 有取消就再成立。
- 專員全是檸檬人的系統保留單一律取消（不算進上面的 1 人單）。
2026-11-22
- 只寫排程行事曆 SCHEDULE_NOTICE_CALENDAR_ID，拿掉 tpe@／jenny@ 預設；沒設定時報錯、不寫任何行事曆。
2026-11-21
- 新增（Jenny）。
  功能1 成立保留單：日期區間內只要有未配班專員（不管是不是新增），同一天同一時段
  （上午／下午／全天）的人合成一張保留單，人數＝人數、時數取最短（1人2小時＋1人3小時
  → 2人2小時；只有 1 人就成立 1人單）。後台查不到這麼多人（例如有人不服務保留地址）時，
  人數減 1 再試，直到 1 人。
  功能2 記錄未配班人員：未來 2 週某天某時段未配班只剩 1 位專員，記「YYYY/MM/DD 下午-1」，
  只寫排程行事曆（SCHEDULE_NOTICE_CALENDAR_ID），不寫 tpe@／jenny@。

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
# 排程行事曆（共用，見 shared/notice_calendar.py）
from shared.notice_calendar import NOTICE_CALENDAR_ENV, notice_calendar_ids, require_notice_calendar_ids  # noqa: E402,F401
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
# 合併單人保留單：同時段 2 張以上 1 人保留單 → 取消後重新成立 N 人單
# ---------------------------------------------------------------------------
def _staff_names(value) -> List[str]:
    return [n.strip() for n in re.split(r"\s*[Xx×]\s*|[,，、/]+", str(value or "")) if n.strip()]


def _is_lemon(name: str) -> bool:
    return str(name).startswith("檸檬人")


def _fetch_reserve_rows(env_name, backend_email, backend_password, date_start, date_end, finder=None) -> List[Dict]:
    """區間內可取消、已付款的系統保留單（沿用「檸檬保留單取消」的查詢）。"""
    from function.reserve_cancel import find_reserve_orders
    from function.reserve_optimizer import RESERVE_PHONE_DEFAULT

    finder = finder or find_reserve_orders
    rows = finder(env_name, backend_email, backend_password, RESERVE_PHONE_DEFAULT, date_start, date_end,
                  memo_filter="僅系統保留單")
    return [r for r in rows or [] if r.get("cancel_eligible")]


LEMON_KEEP_NOTE = "檸檬人勿動"


def _lemon_keep(row: Dict) -> bool:
    """客服備註（或訂單任一文字欄位）有「檸檬人勿動」。"""
    return any(LEMON_KEEP_NOTE in str(v) for v in row.values() if isinstance(v, str))


def lemon_only_reserves(rows: List[Dict]) -> List[Dict]:
    """專員只有檸檬人、且沒有「檸檬人勿動」的保留單 → 取消。"""
    out = []
    for row in rows:
        names = _staff_names(row.get("staff"))
        if names and all(_is_lemon(n) for n in names) and not _lemon_keep(row):
            out.append(row)
    return out


def mixed_lemon_reserves(rows: List[Dict]) -> List[Dict]:
    """檸檬人＋非檸檬人、且沒有「檸檬人勿動」的保留單 → 取消後就非檸檬人重建。"""
    out = []
    for row in rows:
        names = _staff_names(row.get("staff"))
        if (any(_is_lemon(n) for n in names) and any(not _is_lemon(n) for n in names)
                and not _lemon_keep(row)):
            out.append({**row, "rebuild_staff": "、".join(n for n in names if not _is_lemon(n))})
    return out


def single_reserve_groups(rows: List[Dict]) -> Dict[tuple, List[Dict]]:
    """(日期, 時段組) → 2 張以上的 1 人保留單（檸檬人單不算）。"""
    groups: Dict[tuple, List[Dict]] = {}
    for row in rows:
        period = re.sub(r"\s+", "", str(row.get("period") or ""))
        info = PERIOD_INFO.get(period)
        names = _staff_names(row.get("staff"))
        if not info or len(names) != 1 or _is_lemon(names[0]):
            continue
        groups.setdefault((str(row.get("service_date") or ""), info[0]), []).append(row)
    return {k: v for k, v in sorted(groups.items()) if len(v) >= 2}


def find_single_reserve_groups(env_name: str, backend_email: str, backend_password: str,
                               date_start: str, date_end: str, finder=None) -> Dict[tuple, List[Dict]]:
    return single_reserve_groups(_fetch_reserve_rows(env_name, backend_email, backend_password,
                                                     date_start, date_end, finder))


def cancel_single_reserve_groups(env_name: str, backend_email: str, backend_password: str,
                                 groups: Dict[tuple, List[Dict]], canceller=None,
                                 log: Callable[[str], None] = lambda _t: None) -> List[Dict]:
    """取消各組的 1 人保留單；回傳取消結果（含 ok／message）。"""
    from function.reserve_cancel import cancel_reserve_orders

    canceller = canceller or cancel_reserve_orders
    out: List[Dict] = []
    for (day, group), rows in groups.items():
        names = "、".join(f"{r.get('order_no')}({r.get('staff')})" for r in rows)
        log(f"{day} {group} 有 {len(rows)} 張 1 人保留單，取消後合併：{names}")
        try:
            results = canceller(env_name, backend_email, backend_password, rows, len(rows))
        except Exception as exc:
            results = [{**r, "ok": False, "message": f"取消失敗：{exc}"} for r in rows]
        for r in results:
            out.append({**r, "merge_group": group})
    return out


def _cancel_rows(env_name, backend_email, backend_password, rows, canceller=None) -> List[Dict]:
    from function.reserve_cancel import cancel_reserve_orders

    canceller = canceller or cancel_reserve_orders
    try:
        return canceller(env_name, backend_email, backend_password, rows, len(rows))
    except Exception as exc:
        return [{**r, "ok": False, "message": f"取消失敗：{exc}"} for r in rows]


def merge_and_create(*, env_name: str, backend_email: str, backend_password: str, lookup_result, region: str,
                     address: str, date_start: str, date_end: str, payway: str = "儲值金",
                     get_html: Optional[Callable[[str], str]] = None, finder=None, canceller=None, creator=None,
                     log: Callable[[str], None] = lambda _t: None) -> Dict[str, List[Dict]]:
    """取消檸檬人保留單（只有檸檬人／檸檬人＋專員，有「檸檬人勿動」的不動）、合併單人保留單
    → 依未配班成立保留單（被取消的專員回到未配班，一併重建）→ 再檢查一次，有取消就再成立。"""
    get_html = get_html or _schedule_getter(lookup_result)
    creator = creator or create_reserve_orders
    cancelled: List[Dict] = []
    created: List[Dict] = []
    for step in range(2):
        rows = _fetch_reserve_rows(env_name, backend_email, backend_password, date_start, date_end, finder)
        lemons = lemon_only_reserves(rows)
        if lemons:
            log(f"{len(lemons)} 張保留單專員只有檸檬人（沒有「檸檬人勿動」），取消：" + "、".join(
                f"{r.get('service_date')} {r.get('order_no')}({r.get('staff')})" for r in lemons))
            cancelled += [{**r, "merge_group": "檸檬人"} for r in
                          _cancel_rows(env_name, backend_email, backend_password, lemons, canceller)]
        mixed = mixed_lemon_reserves(rows)
        if mixed:
            log(f"{len(mixed)} 張保留單有檸檬人也有專員（沒有「檸檬人勿動」），先取消再就專員重建：" + "、".join(
                f"{r.get('service_date')} {r.get('order_no')}({r.get('staff')})" for r in mixed))
            cancelled += [{**r, "merge_group": "檸檬人＋專員"} for r in
                          _cancel_rows(env_name, backend_email, backend_password, mixed, canceller)]
        groups = single_reserve_groups(rows)
        if groups:
            cancelled += cancel_single_reserve_groups(env_name, backend_email, backend_password, groups, canceller, log)
        if step == 1 and not (groups or lemons or mixed):
            break
        plan = build_plan(scan_range(get_html, date_start, date_end))
        if step == 0 and not groups and not lemons and not mixed and not plan:
            break
        if plan:
            log(f"{len(plan)} 個日期時段有未配班，成立保留單")
            created += creator(env_name=env_name, lookup_result=lookup_result, region=region, address=address,
                               plan=plan, payway=payway, get_html=get_html, log=log)
    return {"cancelled": cancelled, "created": created}


# ---------------------------------------------------------------------------
# 功能2：記錄未配班人員到獨立行事曆
# ---------------------------------------------------------------------------
def build_calendar_event(region: str, rows: List[Dict], date_start: str, date_end: str, now) -> dict:
    lines = [r["text"] for r in rows] or ["（沒有只剩 1 人的時段）"]
    lines += ["", f"範圍：{region} {date_start}～{date_end}（不含檸檬人、晚上時段）"]
    return dict(summary=f"{CALENDAR_PREFIX}{region} {len(rows)} 個時段（{now:%m/%d}）",
                description="\n".join(lines), start=now, reminder_minutes=[0],
                replace_prefix=f"{CALENDAR_PREFIX}{region}")
