# -*- coding: utf-8 -*-
"""評價預約成單：把內勤工作表單「評價預約」分頁的指定列約成訂單（雲端執行）。

更新記錄：
2026-11-12（新增）
- 讀「評價預約」F 欄（預約日期）＋G 欄（時間／人時）的手寫內容，拆成要約的日期：
  「、，和及＋」＝每個日期各約一單；「或」「.」「12/2-12/4」＝擇一（依序查班表，第一個有時段的成單）。
- 人數／時數、時段、購買項目、付款方式、發票：表上沒寫的沿用該客人同地址上一張已付款訂單。
  大掃除期間（服務金額設定 PART1／PART2）沿用的時數不足 3 小時改為 3 小時；表上明寫不足 3 小時的不成單。
- 成單走 quick_create_order（與舊客成單同一套核心，含大掃除計價）；預設不補勾檸檬人。
- 同一天同地址已有訂單就不重複成單。
- 寫回：A 欄訂單編號（多筆用 + 串接）、L 欄成單日期／時段或無法成單原因；F、G 欄原文不動。
- A 欄已有內容的列一律略過；G 欄註記「已約／詢問中／未回覆」的列不成單。
- F、G 欄還有判讀不了的文字（例：2女、各3人8）就不成單，原因寫在 L 欄，交給客服處理。

執行：python -m shared.rating_booking_order --region 台北 --rows 226-254 [--allow-auto-lemon] [--dry-run]
由 .github/workflows/rating-booking-order.yml 執行；Actions 紀錄只印列號與筆數，不印客戶姓名、電話。
"""
from __future__ import annotations

import argparse
import contextlib
import io
import re
import traceback
import unicodedata
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Taipei")
TOOL_NAME = "評價預約成單"
BOOKING_TAB = "評價預約"
WEEKDAY_ZH = "一二三四五六日"

# 分頁欄位（1 起算）。目前只有台北的版面（A 訂單編號、C 姓名、D 電話、E 地址、F 預約日期、G 時間、L 成單結果）。
LAYOUTS = {
    "台北": dict(order_col=1, name_col=3, phone_col=4, address_col=5, date_col=6, time_col=7, result_col=12),
}
REGIONS = tuple(LAYOUTS)

PERIOD_HOURS = {
    "08:30-12:30": 4, "09:00-11:00": 2, "09:00-12:00": 3,
    "14:00-16:00": 2, "14:00-17:00": 3, "14:00-18:00": 4,
    "09:00-16:00": 6, "09:00-18:00": 8,
}
HALF_PERIOD = {
    ("AM", 2): "09:00-11:00", ("AM", 3): "09:00-12:00", ("AM", 4): "08:30-12:30",
    ("PM", 2): "14:00-16:00", ("PM", 3): "14:00-17:00", ("PM", 4): "14:00-18:00",
    ("FULL", 6): "09:00-16:00", ("FULL", 8): "09:00-18:00",
}
HALF_LABEL = {"AM": "上午", "PM": "下午", "FULL": "全天"}
CLEAN_TYPE_ID = {"居家清潔": "1", "辦公室清潔": "2", "裝修細清": "3"}
PAYWAYS = ("信用卡", "ATM", "儲值金")
SKIP_WORDS = ("已約", "己約", "詢問中", "未回覆")
PEAK_MIN_HOURS = 3
STALE_DAYS = 60       # 沒寫年份的日期：已過 60 天內視為過期，更早的當成明年
MAX_RANGE_DAYS = 31


class PlanError(Exception):
    """這一列（或這個日期）無法成單的原因。"""


# ------------------------------------------------------------
# 文字解析（不連後台）
# ------------------------------------------------------------
def _clean(text) -> str:
    return unicodedata.normalize("NFKC", str(text or "")).strip()


def _infer_date(month: int, day: int, today: date, year: int | None = None) -> date | None:
    try:
        if year:
            return date(year, month, day)
        d = date(today.year, month, day)
    except ValueError:
        return None
    if d < today and (today - d).days > STALE_DAYS:
        try:
            d = date(today.year + 1, month, day)
        except ValueError:
            return None
    return d


_DATE_TOKEN = re.compile(
    r"(?P<iso>(?P<iy>\d{4})[-/](?P<im>\d{1,2})[-/](?P<id>\d{1,2}))"
    r"|(?P<range>(?P<rm>\d{1,2})/(?P<rd>\d{1,2})\s*[-~]\s*(?:(?P<rm2>\d{1,2})/)?(?P<rd2>\d{1,2})(?![\d:/]))"
    r"|(?P<md>(?P<m>\d{1,2})/(?P<d>\d{1,2}))"
    r"|(?P<cn>(?P<cm>\d{1,2})月\s*(?P<cd>\d{1,2})\s*[日號]?)"
    r"|(?P<compact>待約\s*(?P<pm>\d{1,2})(?P<pd>\d{2})(?!\d))"
    r"|(?P<vague>(?P<vm>\d{1,2})月(?:初|中|底|份)?)"
)
# 同月份接續的日：「1/23.24.30.31」「5/18、21、25、28」
_DAY_CONT = re.compile(r"\s*(?P<sep>[.、,和及或])\s*(?P<day>\d{1,2})(?![\d/月人小:hH\-~])")
_WEEKDAY_NOISE = re.compile(r"[(（]\s*[一二三四五六日]\s*[)）]|(?:星期|週|周)[一二三四五六日]")


_CONNECTORS = re.compile(r"[\s或和及改、,.+~\-]+")


def parse_dates(text, today: date) -> tuple[list[list[dict]], str, str]:
    """F 欄 → (groups, 日期前後的文字, 夾在日期中間判讀不了的文字)。
    groups 之間是「各約一單」，group 裡面是「擇一」。

    每個候選：{"date": date 或 None, "label": 顯示文字}；date 為 None 表示只寫月份、沒有確切日期。
    """
    text = _clean(text)
    if re.fullmatch(r"\d{3,4}", text):  # 整格只寫 1104／602
        text = "待約" + text
    tokens = []  # (start, end, [候選…])
    pos = 0
    while True:
        m = _DATE_TOKEN.search(text, pos)
        if not m:
            break
        alts = []
        end = m.end()
        if m.group("iso"):
            d = _infer_date(int(m.group("im")), int(m.group("id")), today, int(m.group("iy")))
            alts = [d]
        elif m.group("range"):
            start = _infer_date(int(m.group("rm")), int(m.group("rd")), today)
            stop = _infer_date(int(m.group("rm2") or m.group("rm")), int(m.group("rd2")), today)
            if start and stop and stop < start and not m.group("rm2"):
                stop = None
            if start and stop and start <= stop and (stop - start).days <= MAX_RANGE_DAYS:
                alts = [start + timedelta(days=i) for i in range((stop - start).days + 1)]
            else:
                alts = [None]
        elif m.group("md") or m.group("cn") or m.group("compact"):
            if m.group("md"):
                month, day = int(m.group("m")), int(m.group("d"))
            elif m.group("cn"):
                month, day = int(m.group("cm")), int(m.group("cd"))
            else:
                month, day = int(m.group("pm")), int(m.group("pd"))
            first = _infer_date(month, day, today)
            alts = [first]
            cont_sep = ""
            while first:
                c = _DAY_CONT.match(text, end)
                if not c:
                    break
                nxt = _infer_date(month, int(c.group("day")), today)
                if not nxt:
                    break
                cont_sep = cont_sep or c.group("sep")
                alts.append(nxt)
                end = c.end()
            if len(alts) > 1 and cont_sep not in (".", "或"):
                # 「5/18、21、25」＝各約一單：拆成各自的 token
                for i, d in enumerate(alts):
                    tokens.append((m.start() if i == 0 else end, end, [d], "AND" if i else ""))
                pos = end
                continue
        else:  # 只寫月份
            alts = [None]
            tokens.append((m.start(), end, [{"date": None, "label": m.group("vague")}], ""))
            pos = end
            continue
        tokens.append((m.start(), end, alts, ""))
        pos = end

    groups: list[list[dict]] = []
    rest_parts, middle_parts = [], []
    last_end = 0
    for index, (start, end, alts, forced) in enumerate(tokens):
        between = text[last_end:start]
        if index == 0:
            rest_parts.append(between)
        else:  # 夾在兩個日期中間的字：只能是連接詞，其他（例：6/2 下4 或 6/17 全天）無法判斷是指哪一天
            middle_parts.append(_CONNECTORS.sub(" ", _WEEKDAY_NOISE.sub(" ", between)).strip())
        candidates = []
        for a in alts:
            if isinstance(a, dict):
                candidates.append(a)
            elif a is None:
                candidates.append({"date": None, "label": text[start:end].strip()})
            else:
                candidates.append({"date": a, "label": f"{a.month}/{a.day}"})
        if "改" in between:
            groups = []  # 「11/28改12/5」：以後面的日期為準
        if groups and forced != "AND" and ("或" in between or between.strip() == "."):
            groups[-1].extend(candidates)
        else:
            groups.append(candidates)
        last_end = end
    rest_parts.append(text[last_end:])
    return groups, " ".join(p for p in rest_parts if p), " ".join(p for p in middle_parts if p)


_PERIOD = re.compile(r"(?<![\d/:])(\d{1,2}):?(\d{2})?\s*[-~]\s*(\d{1,2}):?(\d{2})?(?![\d/:])")
_PERSON_HOUR = re.compile(r"(\d)\s*人\s*(\d)\s*(?:小時|小|hr|h|H)?")
_HALF_HOUR = re.compile(r"(上午|早上|下午|上|下)\s*(\d)(?!\d)\s*(?:小時|小|hr|h|H)?")
_HALF = re.compile(r"上午|早上|下午|全天|整天")
_HOUR = re.compile(r"(\d)\s*(?:小時|小|hr|h|H)")
_PERSON = re.compile(r"(\d)\s*人")


def parse_hints(text) -> dict:
    """時段／人數／時數的提示。回傳 period（HH:MM-HH:MM）、half（AM／PM／FULL）、hour、person、rest（沒用到的文字）。"""
    text = _WEEKDAY_NOISE.sub(" ", _clean(text))
    hints = {"period": "", "half": "", "hour": 0, "person": 0}

    def take(pattern, handler):
        nonlocal text
        m = pattern.search(text)
        if m and handler(m) is not False:
            text = text[:m.start()] + " " + text[m.end():]

    def on_period(m):
        h1, m1, h2, m2 = int(m.group(1)), int(m.group(2) or 0), int(m.group(3)), int(m.group(4) or 0)
        if not (6 <= h1 < h2 <= 21 and m1 < 60 and m2 < 60):
            return False
        hints["period"] = f"{h1:02d}:{m1:02d}-{h2:02d}:{m2:02d}"

    def on_person_hour(m):
        hints["person"], hints["hour"] = int(m.group(1)), int(m.group(2))

    def on_half_hour(m):
        hints["half"] = "PM" if m.group(1) in ("下午", "下") else "AM"
        hints["hour"] = hints["hour"] or int(m.group(2))

    def on_half(m):
        word = m.group(0)
        hints["half"] = hints["half"] or ("PM" if word == "下午" else "FULL" if word in ("全天", "整天") else "AM")

    def on_hour(m):
        hints["hour"] = hints["hour"] or int(m.group(1))

    def on_person(m):
        hints["person"] = hints["person"] or int(m.group(1))

    take(_PERIOD, on_period)
    take(_PERSON_HOUR, on_person_hour)
    take(_HALF_HOUR, on_half_hour)
    take(_HALF, on_half)
    take(_HOUR, on_hour)
    take(_PERSON, on_person)
    hints["rest"] = re.sub(r"[\s,、，。.;；:+＋]+", " ", text.replace("待約", " ")).strip()
    return hints


def parse_row(date_text, time_text, today: date) -> dict:
    """一列的 F、G 欄 → {"skip": 原因, "groups": [...], "hints": {...}, "note": 沒解析到的文字}。"""
    f_text, g_text = _clean(date_text), _clean(time_text)
    for word in SKIP_WORDS:
        if word in f_text or word in g_text:
            return {"skip": f"表上註記「{word}」", "groups": [], "hints": {}, "note": ""}
    groups, rest, middle = parse_dates(f_text, today)
    f_hints, g_hints = parse_hints(rest), parse_hints(g_text)
    hints = {k: g_hints[k] or f_hints[k] for k in ("period", "half", "hour", "person")}
    note = " ".join(x for x in (middle, f_hints["rest"], g_hints["rest"]) if x)
    if not groups:
        return {"skip": "沒有寫預約日期" if not f_text else f"預約日期「{f_text}」沒有確切日期",
                "groups": [], "hints": hints, "note": note}
    return {"skip": "", "groups": groups, "hints": hints, "note": note}


def normalize_period(text) -> str:
    """「09:00 - 12:00」「9:00~12:00」→「09:00-12:00」；看不懂回傳空字串。"""
    m = re.search(r"(\d{1,2}):(\d{2})\s*[-~～]\s*(\d{1,2}):(\d{2})", _clean(text))
    if not m:
        return ""
    return f"{int(m.group(1)):02d}:{m.group(2)}-{int(m.group(3)):02d}:{m.group(4)}"


def _half_of(period: str) -> str:
    if PERIOD_HOURS.get(period, 0) >= 6:
        return "FULL"
    if not period:
        return ""
    return "AM" if int(period[:2]) < 12 else "PM"


def resolve_slot(hints: dict, last: dict, peak: bool) -> dict:
    """決定時段／人數／時數。表上有寫的用表上的，沒寫的沿用上一張訂單 last（time／person／hour）。

    peak＝服務日在大掃除期間：沿用的時數不足 3 小時改為 3 小時；表上明寫不足 3 小時則不成單。
    """
    person = int(hints.get("person") or 0) or int(float(last.get("person") or 0))
    if not person:
        raise PlanError("表上沒寫人數，上一張訂單也查不到人數")
    last_period = normalize_period(last.get("time"))
    last_hour = PERIOD_HOURS.get(last_period) or int(float(last.get("hour") or 0))
    adjusted = ""
    period = hints.get("period") or ""
    if period:
        if period not in PERIOD_HOURS:
            raise PlanError(f"表上的時段 {period} 不是後台的標準時段")
        hour = PERIOD_HOURS[period]
        if hints.get("hour") and int(hints["hour"]) != hour:
            raise PlanError(f"表上的時段 {period} 與 {hints['hour']} 小時對不起來")
        if peak and hour < PEAK_MIN_HOURS:
            raise PlanError(f"大掃除期間至少 {PEAK_MIN_HOURS} 小時，表上寫的是 {hour} 小時")
    else:
        hour = int(hints.get("hour") or 0)
        written = bool(hour)
        hour = hour or last_hour
        if not hour:
            raise PlanError("表上沒寫時段，上一張訂單也查不到時段")
        if peak and hour < PEAK_MIN_HOURS:
            if written:
                raise PlanError(f"大掃除期間至少 {PEAK_MIN_HOURS} 小時，表上寫的是 {hour} 小時")
            adjusted = f"大掃除期間，上一張 {hour} 小時改為 {PEAK_MIN_HOURS} 小時"
            hour = PEAK_MIN_HOURS
        half = hints.get("half") or ""
        if hour >= 6:
            if half in ("AM", "PM"):
                raise PlanError(f"{HALF_LABEL[half]}排不下 {hour} 小時")
            half = "FULL"
        elif half == "FULL":
            raise PlanError("表上寫全天，但沒寫 6 或 8 小時，上一張訂單也不是全天")
        elif not half:
            half = _half_of(last_period)
            if half in ("", "FULL"):
                raise PlanError(f"{hour} 小時要約上午或下午，表上沒寫，上一張訂單也看不出來")
        period = HALF_PERIOD.get((half, hour))
        if not period:
            raise PlanError(f"後台沒有{HALF_LABEL[half]} {hour} 小時的標準時段")
    return {"period": period, "person": person, "hour": hour, "adjusted": adjusted}


def loose_address(text) -> str:
    """比對地址用：去空白與郵遞區號、臺→台、F→樓、之／- 視為相同。"""
    s = re.sub(r"\s+", "", _clean(text))
    s = re.sub(r"^\d{3,6}", "", s).replace("臺", "台")
    s = re.sub(r"(\d)[Ff]", r"\1樓", s)
    return s.replace("-", "之").replace("本號", "")


def parse_rows(spec) -> list[int]:
    """執行列號（例：226-254 或 230,233,240-245）。"""
    rows = set()
    for part in _clean(spec).split(","):
        part = part.strip()
        if not part:
            continue
        m = re.fullmatch(r"(\d+)\s*-\s*(\d+)", part)
        if m and 0 < int(m.group(1)) <= int(m.group(2)):
            rows.update(range(int(m.group(1)), int(m.group(2)) + 1))
        elif part.isdigit() and int(part) > 0:
            rows.add(int(part))
        else:
            raise ValueError(f"列號格式錯誤：{part}")
    if not rows:
        raise ValueError("請輸入要執行的列號，例如 226-254")
    return sorted(rows)


def date_label(d: date) -> str:
    return f"{d:%Y-%m-%d}（{WEEKDAY_ZH[d.weekday()]}）"


# ------------------------------------------------------------
# 工作表
# ------------------------------------------------------------
def _col_letter(n: int) -> str:
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def read_rows(ws, layout: dict, rows: list[int]) -> list[dict]:
    from memo_system.memo import with_retry

    width = max(layout.values())
    values = with_retry(ws.get, f"A1:{_col_letter(width)}{max(rows)}")
    result = []
    for row_no in rows:
        row = values[row_no - 1] if row_no - 1 < len(values) else []
        cell = lambda col: str(row[col - 1]).strip() if col - 1 < len(row) else ""  # noqa: E731
        result.append({"row": row_no, "order": cell(layout["order_col"]), "name": cell(layout["name_col"]),
                       "phone": cell(layout["phone_col"]), "address": cell(layout["address_col"]),
                       "date_text": cell(layout["date_col"]), "time_text": cell(layout["time_col"])})
    return result


def write_result(ws, layout: dict, row_no: int, order_nos: list[str], result_text: str) -> None:
    from memo_system.memo import with_retry

    updates = [{"range": f"{_col_letter(layout['result_col'])}{row_no}", "values": [[result_text]]}]
    if order_nos:
        updates.append({"range": f"{_col_letter(layout['order_col'])}{row_no}", "values": [["+".join(order_nos)]]})
    with_retry(ws.batch_update, updates, value_input_option="RAW")


# ------------------------------------------------------------
# 後台：查客人、上一張訂單、成單
# ------------------------------------------------------------
def _is_peak(service_date: date, pricing: dict) -> bool:
    from service_pricing import period_for

    try:
        return period_for(service_date, pricing) != "normal"
    except Exception:
        return False


def load_customer(ctx: dict, phone: str, address: str) -> dict:
    """查會員、對出後台留存的同一個地址、找同地址上一張已付款訂單。"""
    import quick_order as qo

    session = ctx["session"]
    token = qo.get_csrf_token(session)
    member_payload = qo.get_member(session, phone, token, "1")
    if not member_payload:
        raise PlanError("這支電話在後台查無會員")
    member = member_payload.get("member", {}) or {}
    addresses = [str(a.get("address") or "").strip() for a in member.get("memberAddressList", []) or []]
    target = loose_address(address)
    matched = next((a for a in addresses if a and loose_address(a) == target), "")
    if not matched:
        raise PlanError("會員的留存地址裡沒有表上這個地址")
    paid = qo.get_customer_paid_orders(session, phone, [a for a in addresses if a], name=str(member.get("name") or ""))
    same = [o for o in paid if loose_address(o.get("address")) == target]
    today_s = ctx["today"].isoformat()
    last = next((o for o in same if str(o.get("date") or "") <= today_s), None) or (same[0] if same else None)
    if not last:
        raise PlanError("查無同地址的已付款訂單，沒有上一張可以沿用")
    payway = str(last.get("payway") or "")
    if payway not in PAYWAYS:
        raise PlanError(f"上一張訂單 {last.get('order_no')} 看不出付款方式")
    clean_type = str(last.get("clean_type") or "")
    if clean_type not in CLEAN_TYPE_ID:
        raise PlanError(f"上一張訂單 {last.get('order_no')} 的購買項目「{clean_type or '空白'}」無法用來成單")
    lookup = {"session": session, "token": token, "phone": phone, "member_payload": member_payload,
              "base_url": ctx["base_url"], "env_name": ctx["env"]}
    return {"lookup": lookup, "address": matched, "last": last, "payway": payway,
            "clean_type": clean_type, "clean_type_id": CLEAN_TYPE_ID[clean_type]}


def plan_row(ctx: dict, row: dict) -> dict:
    """一列的成單計畫。回傳 status（ready／skip／fail）、reason、groups（每個候選帶 slot 或 problem）。"""
    import quick_order as qo

    plan = {"row": row["row"], "name": row["name"], "date_text": row["date_text"], "time_text": row["time_text"],
            "status": "skip", "reason": "", "groups": [], "note": "", "customer": None}
    if row["order"]:
        plan["reason"] = f"A 欄已有「{row['order']}」"
        return plan
    if not row["name"] or not (row["phone"] or row["address"] or row["date_text"]):
        plan["reason"] = "空白列或區塊標題"
        return plan
    parsed = parse_row(row["date_text"], row["time_text"], ctx["today"])
    plan["note"] = parsed["note"]
    if parsed["skip"]:
        plan.update(status="fail" if "註記" not in parsed["skip"] else "skip", reason=parsed["skip"])
        return plan
    if parsed["note"]:
        plan.update(status="fail", reason=f"表上還有判讀不了的文字「{parsed['note']}」，請人工確認")
        return plan
    phone = qo.normalize_phone(row["phone"])
    if not phone:
        plan.update(status="fail", reason="沒有電話，查不到會員")
        return plan
    if not row["address"]:
        plan.update(status="fail", reason="沒有地址")
        return plan
    try:
        with contextlib.redirect_stdout(io.StringIO()):  # 後台查詢的除錯輸出含客戶資料，不進 Actions 紀錄
            customer = load_customer(ctx, phone, row["address"])
    except PlanError as exc:
        plan.update(status="fail", reason=str(exc))
        return plan
    plan["customer"] = customer
    bookable = 0
    for group in parsed["groups"]:
        out = []
        for cand in group:
            item = {"date": cand["date"], "label": cand["label"], "slot": None, "problem": ""}
            if not cand["date"]:
                item["problem"] = "沒有確切日期"
            elif cand["date"] <= ctx["today"]:
                item["problem"] = "日期已過"
            else:
                try:
                    item["slot"] = resolve_slot(parsed["hints"], customer["last"], _is_peak(cand["date"], ctx["pricing"]))
                    bookable += 1
                except PlanError as exc:
                    item["problem"] = str(exc)
            out.append(item)
        plan["groups"].append(out)
    if bookable:
        plan["status"] = "ready"
    else:
        problems = [f"{c['label']} {c['problem']}" for g in plan["groups"] for c in g]
        plan.update(status="fail", reason="；".join(dict.fromkeys(problems)))
    return plan


def _existing_orders(ctx: dict, customer: dict, dates: list[date]) -> dict:
    """同地址在這些日期已有（未取消）的訂單：{日期字串: 訂單編號}。"""
    import quick_order as qo

    target = loose_address(customer["address"])
    found = {}
    for block in qo._order_blocks_for_dates(ctx["session"], customer["lookup"]["phone"], [d.isoformat() for d in dates]):
        joined = "\n".join(block.get("lines", []))
        if "已取消" in joined or "已退款" in joined:
            continue
        service_date, _ = qo._parse_service_date_time_loose(joined)
        if service_date and target in loose_address(joined):
            found.setdefault(service_date, block.get("order_no"))
    return found


def _slot_text(cand: dict) -> str:
    slot = cand["slot"]
    return f"{date_label(cand['date'])} {slot['period']} {slot['person']}人{slot['hour']}小時"


def book_group(ctx: dict, customer: dict, group: list[dict], allow_auto_lemon: bool) -> dict:
    """一組候選日期擇一成單。回傳 {"order_no", "text"}；沒成單時 order_no 為空、text 是原因。"""
    import quick_order as qo

    ready = [c for c in group if c["slot"]]
    notes = [f"{c['label']} {c['problem']}" for c in group if not c["slot"]]
    if not ready:
        return {"order_no": "", "text": "無法成單：" + "；".join(notes)}
    existing = _existing_orders(ctx, customer, [c["date"] for c in ready])
    if existing:
        day, order_no = next(iter(existing.items()))
        return {"order_no": "", "text": f"未成單：{day} 同地址已有訂單 {order_no}，不重複約"}

    def create(cand, lemon):
        slot = cand["slot"]
        result = qo.quick_create_order(
            env_name=ctx["env"], payway=customer["payway"], region=ctx["region"], lookup_result=customer["lookup"],
            address=customer["address"], clean_type_id=customer["clean_type_id"], date_s=cand["date"].isoformat(),
            period_s=slot["period"], hour=str(slot["hour"]), person=str(slot["person"]),
            allow_auto_lemon_shift=lemon)
        order_no = str((result or {}).get("order_no") or "").strip()
        if not order_no:
            raise RuntimeError("後台沒有回傳訂單編號")
        text = f"成單 {_slot_text(cand)} {order_no}"
        if lemon:
            text += "（已開啟補勾檸檬人）"
        if slot["adjusted"]:
            text += f"（{slot['adjusted']}）"
        warn = str((result or {}).get("address_mismatch_warning") or "").strip()
        if warn:
            text += f" ⚠️{warn}"
        return {"order_no": order_no, "text": text}

    for cand in ready:
        slot = cand["slot"]
        try:
            rows = qo.quick_check_available_slots(
                env_name=ctx["env"], payway=customer["payway"], lookup_result=customer["lookup"],
                address=customer["address"], clean_type_id=customer["clean_type_id"],
                date_s=cand["date"].isoformat(), hour=slot["hour"], person=str(slot["person"]),
                periods=[slot["period"]], period_hours={slot["period"]: slot["hour"]})
        except Exception as exc:
            notes.append(f"{cand['label']} 查班表失敗（{exc}）")
            continue
        if not rows or not rows[0].get("available"):
            notes.append(f"{cand['label']} {slot['period']} 無時段" + (f"（{rows[0]['error']}）" if rows and rows[0].get("error") else ""))
            continue
        try:
            return create(cand, False)
        except Exception as exc:
            # 送單後才失敗：訂單可能已建立，不再試其他日期，交給客服確認
            return {"order_no": "", "text": f"成單失敗：{_slot_text(cand)}（{exc}），請到後台確認是否已建立；其他日期未嘗試"}
    if allow_auto_lemon:
        for cand in ready:
            try:
                return create(cand, True)
            except Exception as exc:
                notes.append(f"{cand['label']} 補勾檸檬人後仍失敗（{exc}）")
    return {"order_no": "", "text": "無法成單：" + "；".join(notes)}


def describe_plan(plan: dict) -> dict:
    """預覽用的一列。"""
    parts = []
    for group in plan["groups"]:
        items = [(_slot_text(c) if c["slot"] else f"{c['label']}（{c['problem']}）") for c in group]
        parts.append(("擇一：" if len(group) > 1 else "") + " ／ ".join(items))
    customer = plan.get("customer") or {}
    last = customer.get("last") or {}
    adjusted = next((c["slot"]["adjusted"] for g in plan["groups"] for c in g if c["slot"] and c["slot"]["adjusted"]), "")
    return {
        "列": plan["row"], "姓名": plan["name"], "預約日期（F）": plan["date_text"], "時間（G）": plan["time_text"],
        "結果": {"ready": "可成單", "fail": "無法成單", "skip": "略過"}[plan["status"]],
        "要約的日期／時段": "\n".join(f"{i}. {p}" for i, p in enumerate(parts, 1)) if len(parts) > 1 else "".join(parts),
        "原因／提醒": "；".join(x for x in (plan["reason"], adjusted) if x),
        "付款／項目": f"{customer.get('payway', '')} {customer.get('clean_type', '')}".strip(),
        "沿用訂單": str(last.get("order_no") or ""),
    }


# ------------------------------------------------------------
# 執行
# ------------------------------------------------------------
def build_context(region: str, env: str, email: str = "", password: str = "", today: date | None = None) -> dict:
    import orders  # noqa: F401  先載入 orders，再用 shared.gsheet
    import requests
    import quick_order as qo
    from accounts import ACCOUNTS
    from service_pricing import load_config

    if region not in LAYOUTS:
        raise ValueError(f"目前只支援：{'、'.join(LAYOUTS)}")
    if not email or not password:
        account = ACCOUNTS.get(region) or {}
        email, password = str(account.get("email") or ""), str(account.get("password") or "")
    if not email or not password:
        raise RuntimeError(f"{region}未設定後台帳密")
    base_url = qo._configure_environment(env)
    session = requests.Session()
    if not qo.login(session, email, password):
        raise RuntimeError("後台登入失敗，請確認帳號密碼")
    return {"region": region, "env": env, "session": session, "base_url": base_url,
            "today": today or datetime.now(TZ).date(), "pricing": load_config()}


def open_tab(region: str):
    from shared.rating_schedule import get_tab

    return get_tab(region, BOOKING_TAB)


def run(region: str, rows_spec, env: str = "prod", allow_auto_lemon: bool = False, dry_run: bool = False,
        email: str = "", password: str = "", ctx: dict | None = None, ws=None, logger=print) -> dict:
    """dry_run＝只預覽（不成單、不寫回）。env=dev 時在測試機成單，但不寫回正式工作表。"""
    rows = parse_rows(rows_spec)
    layout = LAYOUTS[region]
    ctx = ctx or build_context(region, env, email, password)
    if ws is None:
        spreadsheet, ws = open_tab(region)
        sheet_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet.id}/edit#gid={ws.id}"
    else:
        sheet_url = ""
    write_back = not dry_run and env != "dev"
    summary = {"region": region, "rows": len(rows), "orders": 0, "booked_rows": 0, "ready_rows": 0,
               "failed_rows": 0, "skipped_rows": 0,
               "preview": [], "results": [], "sheet_url": sheet_url, "dry_run": dry_run}
    stamp = f"[{ctx['today']:%m/%d}] "
    for row in read_rows(ws, layout, rows):
        try:
            plan = plan_row(ctx, row)
        except Exception as exc:
            plan = {"row": row["row"], "name": row["name"], "date_text": row["date_text"], "time_text": row["time_text"],
                    "status": "fail", "reason": f"查詢失敗（{exc}）", "groups": [], "note": "", "customer": None}
        summary["preview"].append(describe_plan(plan))
        if plan["status"] == "skip":
            summary["skipped_rows"] += 1
            logger(f"ROW {plan['row']} 略過", flush=True)
            continue
        if dry_run:
            summary["failed_rows" if plan["status"] == "fail" else "ready_rows"] += 1
            continue
        if plan["status"] == "fail":
            text, order_nos = "無法成單：" + plan["reason"], []
        else:
            outcomes = []
            for group in plan["groups"]:
                try:
                    with contextlib.redirect_stdout(io.StringIO()):
                        outcomes.append(book_group(ctx, plan["customer"], group, allow_auto_lemon))
                except Exception as exc:
                    outcomes.append({"order_no": "", "text": f"成單失敗（{exc}），請到後台確認"})
            order_nos = [o["order_no"] for o in outcomes if o["order_no"]]
            text = "\n".join(o["text"] for o in outcomes)
        summary["orders"] += len(order_nos)
        summary["booked_rows" if order_nos else "failed_rows"] += 1
        summary["results"].append({"列": plan["row"], "姓名": plan["name"], "訂單編號": "+".join(order_nos), "結果": text})
        logger(f"ROW {plan['row']} 成單 {len(order_nos)} 筆" if order_nos else f"ROW {plan['row']} 未成單", flush=True)
        if write_back:
            try:
                write_result(ws, layout, plan["row"], order_nos, stamp + text)
            except Exception as exc:
                summary["results"][-1]["結果"] += f"\n⚠️ 寫回工作表失敗（{exc}）"
                logger(f"ROW {plan['row']} 寫回工作表失敗：{type(exc).__name__}", flush=True)
    return summary


def _log(status: str, region: str, message: str, traceback_text: str = "") -> None:
    try:
        from shared.execution_log_service import log_execution

        log_execution(function_name=TOOL_NAME, status=status, run_type="雲端", area=region,
                      message=message, traceback_text=traceback_text)
    except Exception as exc:
        print(f"WARN 執行 Log 寫入失敗：{exc}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=TOOL_NAME)
    parser.add_argument("--region", default="台北")
    parser.add_argument("--rows", required=True)
    parser.add_argument("--env", default="prod")
    parser.add_argument("--allow-auto-lemon", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    env = "dev" if str(args.env).strip().lower() == "dev" else "prod"
    try:
        summary = run(args.region, args.rows, env=env, allow_auto_lemon=args.allow_auto_lemon, dry_run=args.dry_run)
    except Exception as exc:
        _log("失敗", args.region, f"{type(exc).__name__}: {exc}", traceback.format_exc())
        raise
    if args.dry_run:
        message = (f"{args.region} 列 {args.rows}：試跑，可成單 {summary['ready_rows']} 列，"
                   f"無法成單 {summary['failed_rows']} 列，略過 {summary['skipped_rows']} 列")
    else:
        message = (f"{args.region} 列 {args.rows}：成單 {summary['orders']} 筆（{summary['booked_rows']} 列），"
                   f"無法成單 {summary['failed_rows']} 列，略過 {summary['skipped_rows']} 列")
    print("FINISH " + message, flush=True)
    _log("成功", args.region, message)


if __name__ == "__main__":
    main()
