# shift.py
# -*- coding: utf-8 -*-
"""
自動勾班模組

修正紀錄（2026-06）：
1. get_shift_page_state 改為同時回傳所有 hidden input 欄位（含 _method 等），
   讓 submit_shift_payload 能帶著這些欄位一起送出，符合 Laravel 的 method spoofing。
2. submit_shift_payload 加上 month 參數，POST URL 帶 ?month=YYYY-MM。
3. clear_person_shift_dates 確認當月有勾選才送出，無勾選直接略過。

v2026.11.20-1：新增 count_order_lemons_range／format_lemon_progress：
掃描 /schedule，統計每日上午／下午／全天「非檸檬保留單」訂單裡的檸檬人
（灰底未配班名單不算；同一位客人當天多張單且客服備註有「檸檬人勿動」的合併訂單也不算），
產生「檸檬人待換專員進度」文字。

v2026.11.09-1：排班頁解析與送出欄位改用 shared/shift_page.py，
與所有成單自動補檸檬人共用同一套程式（行為不變）。
"""
import re
from datetime import date, timedelta
from typing import Dict, List, Optional, Callable, Tuple

import requests
from bs4 import BeautifulSoup

from . import memo
from shared.shift_page import parse_shift_page, build_shift_payload

# -----------------------------------------------------------------------------
# 類型對照表
# -----------------------------------------------------------------------------
TYPE_MAP = {
    "全6": ("all", "6"),
    "全8": ("all", "8"),
    "上2": ("1", "0900-1100"),
    "上3": ("1", "0900-1200"),
    "上4": ("1", "0830-1230"),
    "下2": ("2", "1400-1600"),
    "下3": ("2", "1400-1700"),
    "下4": ("2", "1400-1800"),
    "晚2": ("3", "1900-2100"),
}

TYPE_DIGIT_MAP = {
    "上4": "4", "上3": "3", "上2": "2",
    "全6": "6", "全8": "8",
    "下2": "2", "下3": "3", "下4": "4",
    "晚2": "2",
}

CLEAR_TYPE = "清"
ALL_SLOTS = ["all", "1", "2", "3"]

CONFLICT_MAP = {
    "all": {"1", "2"},
    "1":   {"all"},
    "2":   {"all"},
    "3":   set(),
}


def get_conflicting_slot_keys(existing: Dict[str, str], date_val: str, slot: str) -> Dict[str, str]:
    conflicts = {}
    for conflicting_slot in CONFLICT_MAP.get(slot, set()):
        key = f"{date_val}_{conflicting_slot}"
        if key in existing:
            conflicts[key] = existing[key]
    return conflicts


def make_logger(ui_logger: Optional[Callable[[str], None]] = None):
    def _log(msg: str):
        msg = str(msg)
        print(msg, flush=True)
        if ui_logger:
            ui_logger(msg)
    return _log


# -----------------------------------------------------------------------------
# 匯入檔解析
# -----------------------------------------------------------------------------
def parse_import_file(file_obj, filename: str) -> List[Dict]:
    import pandas as pd
    if filename.lower().endswith(".csv"):
        df = pd.read_csv(file_obj, dtype=str)
    else:
        df = pd.read_excel(file_obj, dtype=str)

    df = df.rename(columns={"地區": "area", "日期": "date", "類型": "type", "時段": "period", "名稱": "name"})
    required = {"date", "type", "name"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"匯入檔缺少欄位：{missing}")

    rows = []
    for _, r in df.iterrows():
        date_val = str(r.get("date", "")).strip()
        type_val = str(r.get("type", "")).strip()
        name_val = str(r.get("name", "")).strip()
        if not date_val or not type_val or not name_val:
            continue
        date_val = re.sub(r"[./]", "-", date_val)[:10]
        rows.append({"area": str(r.get("area", "")).strip(), "date": date_val, "type": type_val, "name": name_val})
    return rows


def group_rows_by_name_and_month(rows: List[Dict]) -> Dict[str, Dict[str, List[Dict]]]:
    grouped: Dict[str, Dict[str, List[Dict]]] = {}
    for row in rows:
        grouped.setdefault(row["name"], {}).setdefault(row["date"][:7], []).append(row)
    return grouped


# -----------------------------------------------------------------------------
# 依姓名搜尋專員 ID
# -----------------------------------------------------------------------------
_CLEANER_NAME_TO_ID_CACHE: Dict[str, str] = {}


def build_cleaner_directory(session: requests.Session, force_refresh: bool = False) -> Dict[str, str]:
    global _CLEANER_NAME_TO_ID_CACHE
    if _CLEANER_NAME_TO_ID_CACHE and not force_refresh:
        return _CLEANER_NAME_TO_ID_CACHE
    r = memo.session_get(session, f"{memo.BASE_URL}/schedule")
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    select_el = soup.select_one("select#cleaner_id")
    directory = {}
    if select_el:
        for opt in select_el.select("option"):
            value = (opt.get("value") or "").strip()
            name = opt.get_text(strip=True)
            if value and value != "0" and name:
                directory[name] = value
    _CLEANER_NAME_TO_ID_CACHE = directory
    return directory


def search_cleaner1_by_keyword(session: requests.Session, keyword: str) -> Dict[str, str]:
    r = memo.session_get(session, f"{memo.BASE_URL}/cleaner1", params={"keyword": keyword})
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    results = {}
    for tr in soup.select("table tbody tr"):
        tds = tr.find_all("td", recursive=False)
        if len(tds) < 2:
            continue
        lines = tds[1].get_text(separator="\n", strip=True).split("\n")
        name = lines[0].strip() if lines else ""
        shift_link = tr.select_one('a[href*="/shift"]')
        if not name or not shift_link:
            continue
        m = re.search(r"/cleaner1/(\d+)/shift", shift_link.get("href", ""))
        if m:
            results[name] = m.group(1)
    return results


def find_cleaner_id_by_name(session: requests.Session, name: str) -> Optional[str]:
    global _CLEANER_NAME_TO_ID_CACHE
    directory = build_cleaner_directory(session)
    if name in directory:
        return directory[name]
    try:
        found = search_cleaner1_by_keyword(session, name)
    except Exception:
        found = {}
    if found:
        _CLEANER_NAME_TO_ID_CACHE.update(found)
    return _CLEANER_NAME_TO_ID_CACHE.get(name)


# -----------------------------------------------------------------------------
# 取得班表狀態（含所有 hidden 欄位）
#
# 修正：除了 _token 和已勾選的 shift_ 欄位之外，
# 也一併抓取表單裡所有其他 hidden input（例如 _method=PUT），
# 讓 submit 時能完整重現瀏覽器手動送出的 payload，
# 避免 Laravel method spoofing 不符導致後台沒有真正儲存。
# -----------------------------------------------------------------------------
def get_shift_page_state(
    session: requests.Session,
    cleaner_id: str,
    month: str,
) -> Tuple[str, Dict[str, str], Dict[str, str]]:
    """
    回傳 (token, existing_shift_dict, hidden_fields)

    existing_shift_dict：{"2026-07-01_all": "8", ...}
    hidden_fields：表單裡除了 _token 以外的所有 hidden input，
                   例如 {"_method": "PUT"}
    """
    url = f"{memo.BASE_URL}/cleaner1/{cleaner_id}/shift"
    r = memo.session_get(session, url, params={"month": month})
    r.raise_for_status()
    # v2026.11.09-1：與成單補檸檬人共用 shared/shift_page.py 解析。
    token, existing, hidden_fields = parse_shift_page(r.text)
    return token, existing, hidden_fields


# -----------------------------------------------------------------------------
# 匯入資料轉 payload key
# -----------------------------------------------------------------------------
def build_new_shift_entries(rows: List[Dict], log=None):
    entries: Dict[str, str] = {}
    clear_dates = set()
    for row in rows:
        type_val = row["type"]
        date_val = row["date"]
        if type_val == CLEAR_TYPE:
            clear_dates.add(date_val)
            continue
        if type_val not in TYPE_MAP:
            if log:
                log(f"⚠️ 未知類型「{type_val}」（{row.get('name', '')} {date_val}），略過")
            continue
        slot, value = TYPE_MAP[type_val]
        entries[f"{date_val}_{slot}"] = value
    return entries, clear_dates


def merge_shift_entries(
    existing: Dict[str, str],
    new_entries: Dict[str, str],
    clear_dates=None,
) -> Dict[str, str]:
    merged = dict(existing)
    for date_val in (clear_dates or []):
        for slot in ALL_SLOTS:
            merged.pop(f"{date_val}_{slot}", None)
    merged.update(new_entries)
    return merged


# -----------------------------------------------------------------------------
# 送出整月班表
#
# 修正：
# 1. 加上 month 參數，POST URL 帶 ?month=YYYY-MM
# 2. 加上 hidden_fields 參數，把 _method 等 Laravel 必要欄位一起帶進去
# -----------------------------------------------------------------------------
def submit_shift_payload(
    session: requests.Session,
    cleaner_id: str,
    token: str,
    merged: Dict[str, str],
    month: Optional[str] = None,
    hidden_fields: Optional[Dict[str, str]] = None,
):
    url = f"{memo.BASE_URL}/cleaner1/{cleaner_id}/shift"
    params = {"month": month} if month else {}
    referer = f"{url}?month={month}" if month else url

    # 帶入 _method=PUT 等 Laravel hidden 欄位（共用 shared/shift_page.py）
    payload = build_shift_payload(token, merged, hidden_fields)

    resp = memo.session_post(
        session,
        url,
        params=params,
        data=payload,
        headers={"Referer": referer, "User-Agent": "Mozilla/5.0"},
    )

    try:
        resp.raise_for_status()
    except requests.HTTPError as e:
        snippet = (resp.text or "")[:500].replace("\n", " ")
        has_cookie = any(
            "token" in c.name.lower() or "session" in c.name.lower()
            for c in session.cookies
        )
        raise requests.HTTPError(
            f"{e}\n"
            f"[診斷] _token 開頭：{token[:10]}…（長度 {len(token)}）"
            f"｜有 session cookie：{has_cookie}"
            f"｜回應前 500 字：{snippet}"
        ) from e

    return resp


# -----------------------------------------------------------------------------
# 找「檸檬人」空檔
# -----------------------------------------------------------------------------
LEMON_REN_PREFIX = "檸檬人"
LEMON_REN_DEFAULT_COUNT = 10
LEMON_REN_CHAR_SUFFIXES = "甲乙丙丁戊己"


def parse_lemon_label(text: str) -> Optional[Dict[str, str]]:
    m = re.match(r"^(?P<code>\d*)檸檬人(?P<rest>.+)$", text.strip())
    if not m:
        return None
    rest = m.group("rest")
    if not rest:
        return None
    rating = rest[-1]
    if not rating.isdigit():
        return None
    number_part = rest[:-1]
    if not number_part:
        return None
    if number_part.isdigit() or number_part in LEMON_REN_CHAR_SUFFIXES:
        return {"code": m.group("code"), "name": f"檸檬人{number_part}", "rating": rating}
    return None


def find_available_lemon_ren(
    session: requests.Session,
    date_val: str,
    type_val: str,
    max_count: int = LEMON_REN_DEFAULT_COUNT,
    log=None,
):
    if type_val == CLEAR_TYPE:
        raise ValueError("「清」不適用於找空檔勾選")
    if type_val not in TYPE_MAP:
        raise ValueError(f"未知類型「{type_val}」")

    slot, value = TYPE_MAP[type_val]
    month = date_val[:7]
    slot_key = f"{date_val}_{slot}"
    checked_candidates = []

    for i in range(1, max_count + 1):
        lemon_name = f"{LEMON_REN_PREFIX}{i}"
        cleaner_id = find_cleaner_id_by_name(session, lemon_name)
        if not cleaner_id:
            if log:
                log(f"⚠️ 找不到「{lemon_name}」的後台帳號，略過")
            continue

        token, existing, hidden_fields = get_shift_page_state(session, cleaner_id, month)
        occupied_reason = None

        if slot_key in existing:
            occupied_reason = f"{date_val} 的「{type_val}」時段已被勾選（{existing[slot_key]}）"
        else:
            conflicts = get_conflicting_slot_keys(existing, date_val, slot)
            if conflicts:
                conflict_desc = "、".join(f"{k}={v}" for k, v in conflicts.items())
                occupied_reason = f"{date_val} 已有互斥勾選（{conflict_desc}）"

        if occupied_reason:
            if log:
                log(f"⏭ {lemon_name}（id={cleaner_id}）{occupied_reason}，往下一位找")
            checked_candidates.append({
                "name": lemon_name,
                "cleaner_id": cleaner_id,
                "occupied_value": existing.get(slot_key, occupied_reason),
            })
            continue

        if log:
            log(f"✅ 找到空檔：{lemon_name}（id={cleaner_id}），{date_val} 的「{type_val}」目前是空的")

        return {
            "found": True,
            "name": lemon_name,
            "cleaner_id": cleaner_id,
            "month": month,
            "slot_key": slot_key,
            "value": value,
            "token": token,
            "existing": existing,
            "hidden_fields": hidden_fields,
            "checked_candidates": checked_candidates,
        }

    if log:
        log(f"❌ 檸檬人1~{max_count} 在 {date_val}「{type_val}」全部被佔用或找不到帳號")

    return {
        "found": False, "name": None, "cleaner_id": None,
        "month": month, "slot_key": slot_key, "value": value,
        "token": None, "existing": {}, "hidden_fields": {},
        "checked_candidates": checked_candidates,
    }


def confirm_lemon_ren_assignment(session: requests.Session, candidate: Dict, log=None):
    if not candidate.get("found"):
        raise RuntimeError("沒有找到可用的檸檬人，無法勾選")

    cleaner_id = candidate["cleaner_id"]
    month = candidate["month"]
    slot_key = candidate["slot_key"]
    value = candidate["value"]

    token, existing, hidden_fields = get_shift_page_state(session, cleaner_id, month)

    if slot_key in existing:
        raise RuntimeError(
            f"「{candidate['name']}」的 {slot_key} 在送出前已被勾選為 {existing[slot_key]}，"
            f"可能被別人搶先，請重新查詢"
        )

    merged = dict(existing)
    merged[slot_key] = value
    submit_shift_payload(session, cleaner_id, token, merged, month=month, hidden_fields=hidden_fields)

    if log:
        log(f"✅ 已將「{candidate['name']}」於 {slot_key} 勾選為 {value} 並儲存")

    return merged


FULL_DAY_HOURS = {"6": ("0900", "1600"), "8": ("0900", "1800")}


def _extends_full_day(full_value: str, slot: str, half_value: str) -> Optional[bool]:
    """全日班＋半天班是否為延長上班時間（全8＋上4 提早到 08:30、全6＋下3 延到 17:00）。

    無法判斷時回傳 None。
    """
    full = FULL_DAY_HOURS.get(str(full_value))
    match = re.fullmatch(r"(\d{4})-(\d{4})", str(half_value or ""))
    if not full or not match:
        return None
    start, end = match.groups()
    if slot == "1":
        return start < full[0]
    if slot == "2":
        return end > full[1]
    return None


def check_merged_conflicts(merged: Dict[str, str]) -> List[str]:
    """勾班後的提醒。全日班＋半天班若是延長上班時間（例：全8＋上4、全6＋下3）屬正常排法，
    不提醒；半天班完全落在全日班時間內（沒有延長）才提醒確認。"""
    warnings = []
    by_date: Dict[str, Dict[str, str]] = {}
    for key, value in merged.items():
        date_val, slot = key.rsplit("_", 1)
        by_date.setdefault(date_val, {})[slot] = value
    for date_val, slots in by_date.items():
        if "all" not in slots:
            continue
        for slot in ("1", "2"):
            if slot not in slots:
                continue
            if _extends_full_day(slots["all"], slot, slots[slot]):
                continue
            msg = (
                f"⚠️ {date_val} 同時勾選了 all={slots['all']} 跟 {slot}={slots[slot]}，"
                "半天班沒有延長全日班的上班時間，請確認"
            )
            if msg not in warnings:
                warnings.append(msg)
    return warnings


# -----------------------------------------------------------------------------
# 主流程：處理整份匯入檔
# -----------------------------------------------------------------------------
LEMON_REN_NAME_PATTERN = re.compile(r"^檸檬人")


def process_import_file(rows: List[Dict], dry_run: bool = True, ui_logger=None, session=None) -> Dict:
    log = make_logger(ui_logger)
    result = {
        "processed_people": 0, "processed_months": 0, "saved": 0,
        "skipped": [], "errors": [], "dry_run_payloads": [],
    }

    # 2026-07-08：排班匯入不再排除「檸檬人」。
    # 匯入檔若寫 檸檬人1、檸檬人2...，會和一般專員一樣依姓名找後台帳號並勾班。
    grouped = group_rows_by_name_and_month(rows)
    session = session or memo.login(ui_logger=ui_logger)
    build_cleaner_directory(session, force_refresh=True)

    for name, months in grouped.items():
        log(f"\n===== 處理專員：{name} =====")
        cleaner_id = find_cleaner_id_by_name(session, name)
        if not cleaner_id:
            msg = f"❌ 找不到專員「{name}」的後台 ID，略過"
            log(msg)
            result["skipped"].append(name)
            result["errors"].append(msg)
            continue

        result["processed_people"] += 1

        for month, month_rows in months.items():
            log(f"[{name}] 月份 {month}，共 {len(month_rows)} 筆匯入資料")
            try:
                token, existing, hidden_fields = get_shift_page_state(session, cleaner_id, month)
                new_entries, clear_dates = build_new_shift_entries(month_rows, log=log)
                mentioned_dates = clear_dates | {k.rsplit("_", 1)[0] for k in new_entries}
                merged = merge_shift_entries(existing, new_entries, mentioned_dates)
                result["processed_months"] += 1

                if clear_dates:
                    log(f"[{name} {month}] 將清空日期：{sorted(clear_dates)}")

                if dry_run:
                    log(f"[{name} {month}] DRY RUN，合併後共 {len(merged)} 筆，不會送出")
                    result["dry_run_payloads"].append((name, month, merged))
                else:
                    submit_shift_payload(session, cleaner_id, token, merged, month=month, hidden_fields=hidden_fields)
                    log(f"✅ [{name} {month}] 已儲存，共 {len(merged)} 筆")
                    result["saved"] += 1

            except Exception as e:
                msg = f"❌ [{name} {month}] 失敗：{e}"
                log(msg)
                result["errors"].append(msg)

    return result


# =============================================================================
# 清空排班
# =============================================================================
def date_range(date_start: str, date_end: str) -> List[str]:
    d1 = date.fromisoformat(date_start)
    d2 = date.fromisoformat(date_end)
    if d2 < d1:
        d1, d2 = d2, d1
    days = []
    cur = d1
    while cur <= d2:
        days.append(cur.isoformat())
        cur += timedelta(days=1)
    return days


def clear_person_shift_dates(
    session: requests.Session,
    name: str,
    dates_to_clear: List[str],
    ui_logger=None,
) -> Dict:
    """
    清空指定人員在 dates_to_clear 這些日期的整天排班並儲存。

    修正：
    - 確認當月有勾選才送出（無勾選直接略過）
    - submit 帶入 month 和 hidden_fields（含 _method=PUT）
    """
    log = make_logger(ui_logger)
    result = {
        "name": name, "cleaner_id": None,
        "cleared_dates": [], "cleared_slot_count": 0,
        "untouched_dates": [], "errors": [],
    }

    cleaner_id = find_cleaner_id_by_name(session, name)
    if not cleaner_id:
        msg = f"❌ 找不到「{name}」的後台帳號"
        log(msg)
        result["errors"].append(msg)
        return result

    result["cleaner_id"] = cleaner_id

    by_month: Dict[str, List[str]] = {}
    for d in dates_to_clear:
        by_month.setdefault(d[:7], []).append(d)

    for month, dates in by_month.items():
        try:
            token, existing, hidden_fields = get_shift_page_state(session, cleaner_id, month)

            # 先計算這個月起迄範圍內有哪些日期真的有勾選
            removed_keys = []
            month_cleared_dates = []
            for d in dates:
                day_had_entry = False
                for slot in ALL_SLOTS:
                    key = f"{d}_{slot}"
                    if key in existing:
                        removed_keys.append(key)
                        day_had_entry = True
                if day_had_entry:
                    result["cleared_dates"].append(d)
                    month_cleared_dates.append(d)
                else:
                    result["untouched_dates"].append(d)

            # 確認有勾選才送出，無勾選直接略過
            if not month_cleared_dates:
                log(f"ℹ️ [{name} {month}] 查詢範圍內這個月沒有任何已勾選的排班，略過")
                continue

            merged = merge_shift_entries(existing, {}, clear_dates=dates)
            submit_shift_payload(
                session, cleaner_id, token, merged,
                month=month,
                hidden_fields=hidden_fields,
            )

            result["cleared_slot_count"] += len(removed_keys)
            log(
                f"✅ [{name} {month}] 已清空 {sorted(month_cleared_dates)}，"
                f"移除 {len(removed_keys)} 筆既有勾選：{removed_keys}"
            )

        except Exception as e:
            msg = f"❌ [{name} {month}] 清空失敗：{e}"
            log(msg)
            result["errors"].append(msg)

    return result


def clear_person_shift_range(
    session: requests.Session,
    name: str,
    date_start: str,
    date_end: str,
    ui_logger=None,
) -> Dict:
    dates = date_range(date_start, date_end)
    return clear_person_shift_dates(session, name, dates, ui_logger=ui_logger)


# =============================================================================
# 檸檬人批次勾班
# =============================================================================
def assign_person_shift_range(
    session: requests.Session,
    names: List[str],
    date_start: str,
    date_end: str,
    type_values: List[str],
    ui_logger=None,
    weekends_only: bool = False,
    only_dates: Optional[List[str]] = None,
) -> Dict:
    """
    將指定人員在 date_start ~ date_end 期間勾選指定班別。
    指定日期範圍內會先清掉 all/1/2/3 舊勾選，再套用本次選擇的班別。
    weekends_only=True 時只處理週六、週日，平日的既有勾選完全不動。
    only_dates 有給時只處理清單內的日期（例如颱風假移轉的候選日期），其餘日期完全不動。
    """
    log = make_logger(ui_logger)
    clean_names = [str(n).strip() for n in names if str(n).strip()]
    clean_types = [str(t).strip() for t in type_values if str(t).strip()]

    result = {
        "processed_people": 0,
        "processed_months": 0,
        "saved": 0,
        "skipped": [],
        "errors": [],
        "warnings": [],
        "details": [],
    }

    if not clean_names:
        raise ValueError("請輸入至少一位人員")
    if not clean_types:
        raise ValueError("請選擇至少一個班別")

    invalid_types = [t for t in clean_types if t not in TYPE_MAP or t == CLEAR_TYPE]
    if invalid_types:
        raise ValueError(f"未知或不可用班別：{invalid_types}")

    dates = date_range(date_start, date_end)
    if weekends_only:
        dates = [d for d in dates if date.fromisoformat(d).weekday() >= 5]
        if not dates:
            raise ValueError("日期區間內沒有週六、週日")
    if only_dates is not None:
        wanted = {str(d).strip() for d in only_dates}
        dates = [d for d in dates if d in wanted]
        if not dates:
            raise ValueError("日期區間內沒有要勾班的日期")
    by_month: Dict[str, List[str]] = {}
    for d in dates:
        by_month.setdefault(d[:7], []).append(d)

    build_cleaner_directory(session, force_refresh=True)

    for name in clean_names:
        log(f"\n----- 勾班「{name}」-----")
        cleaner_id = find_cleaner_id_by_name(session, name)
        if not cleaner_id:
            msg = f"❌ 找不到「{name}」的後台帳號，略過"
            log(msg)
            result["skipped"].append(name)
            result["errors"].append(msg)
            continue

        result["processed_people"] += 1

        for month, month_dates in by_month.items():
            try:
                token, existing, hidden_fields = get_shift_page_state(session, cleaner_id, month)
                new_entries: Dict[str, str] = {}
                for d in month_dates:
                    for type_val in clean_types:
                        slot, value = TYPE_MAP[type_val]
                        new_entries[f"{d}_{slot}"] = value

                merged = merge_shift_entries(existing, new_entries, clear_dates=month_dates)
                warnings = check_merged_conflicts(merged)
                for w in warnings:
                    log(w)
                    result["warnings"].append(f"{name} {month}：{w}")

                submit_shift_payload(
                    session, cleaner_id, token, merged,
                    month=month,
                    hidden_fields=hidden_fields,
                )

                result["processed_months"] += 1
                result["saved"] += 1
                result["details"].append({
                    "name": name,
                    "month": month,
                    "dates": sorted(month_dates),
                    "types": list(clean_types),
                    "entry_count": len(new_entries),
                    "merged_count": len(merged),
                    "warnings": warnings,
                })
                log(
                    f"✅ [{name} {month}] 已儲存："
                    f"{len(month_dates)} 天 × {len(clean_types)} 班別，共 {len(new_entries)} 筆指定勾選"
                )
            except Exception as e:
                msg = f"❌ [{name} {month}] 勾班失敗：{e}"
                log(msg)
                result["errors"].append(msg)

    return result


def find_unassigned_lemon_bookings_range(
    session: requests.Session,
    date_start: str,
    date_end: str,
    ui_logger=None,
) -> List[Dict]:
    """
    掃描 date_start ~ date_end 的清潔班表，找出未配班清單中的檸檬人。
    後台 /schedule 一次顯示一週，因此以每週週一掃描一次，再過濾回指定區間。
    """
    log = make_logger(ui_logger)
    start = date.fromisoformat(date_start)
    end = date.fromisoformat(date_end)
    if end < start:
        start, end = end, start

    query_dates = []
    seen_weeks = set()
    cur = start
    while cur <= end:
        week_start = cur - timedelta(days=cur.weekday())
        if week_start not in seen_weeks:
            seen_weeks.add(week_start)
            query_dates.append(week_start)
        cur += timedelta(days=1)

    results = []
    seen = set()
    for q in query_dates:
        q_text = q.isoformat()
        log(f"===== 掃描週次：{q_text} =====")
        entries = find_unassigned_lemon_bookings(
            session=session,
            query_date=q_text,
            ui_logger=ui_logger,
        )
        for e in entries:
            e_date = str(e.get("date", ""))
            if date_start <= e_date <= date_end:
                key = (e_date, e.get("name"), e.get("raw"))
                if key not in seen:
                    seen.add(key)
                    results.append(e)

    results.sort(key=lambda x: (x.get("date", ""), x.get("name", ""), x.get("raw", "")))
    log(f"日期區間 {date_start} ~ {date_end} 共找到 {len(results)} 筆未配班清單中的檸檬人佔用紀錄")
    return results


# =============================================================================
# 從未配班清單清除檸檬人
# =============================================================================
def _parse_schedule_query_date(html: str, fallback: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    el = soup.select_one("input#date")
    if el and el.get("value"):
        return el.get("value").strip()
    return fallback


def _row_label_to_date(label: str, query_date: str) -> Optional[str]:
    m = re.match(r"(\d{2})-(\d{2})", label.strip())
    if not m:
        return None
    month, day = m.group(1), m.group(2)
    q = date.fromisoformat(query_date)
    year = q.year
    if q.month == 12 and int(month) == 1:
        year += 1
    elif q.month == 1 and int(month) == 12:
        year -= 1
    return f"{year}-{month}-{day}"


def parse_unassigned_lemon_entries(html: str, query_date: str) -> List[Dict]:
    soup = BeautifulSoup(html, "html.parser")
    seen = set()
    results = []
    for tr in soup.select("table tr"):
        tds = tr.find_all("td", recursive=False)
        if not tds:
            continue
        date_val = _row_label_to_date(tds[0].get_text(strip=True), query_date)
        if not date_val:
            continue
        for p in tr.select('p[style*="616161"]'):
            for span in p.find_all("span", recursive=True):
                if span.find_parent("a"):
                    continue
                text = span.get_text(strip=True)
                parsed = parse_lemon_label(text)
                if not parsed:
                    continue
                lemon_name = parsed["name"]
                dedup_key = (date_val, lemon_name)
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)
                results.append({"date": date_val, "name": lemon_name, "raw": text})
    return results


def find_unassigned_lemon_bookings(
    session: requests.Session,
    query_date: str,
    ui_logger=None,
) -> List[Dict]:
    log = make_logger(ui_logger)
    url = f"{memo.BASE_URL}/schedule"
    r = memo.session_get(session, url, params={"date": query_date})
    r.raise_for_status()
    actual_query_date = _parse_schedule_query_date(r.text, query_date)
    entries = parse_unassigned_lemon_entries(r.text, actual_query_date)
    log(f"在 {query_date} 所在那週的清潔班表裡，找到 {len(entries)} 筆未配班清單中的檸檬人佔用紀錄")
    for e in entries:
        log(f"  - {e['date']}　{e['name']}（原始文字：{e['raw']}）")
    return entries


def clear_unassigned_lemon_bookings(
    session: requests.Session,
    entries: List[Dict],
    ui_logger=None,
) -> List[Dict]:
    log = make_logger(ui_logger)
    by_name: Dict[str, List[str]] = {}
    for e in entries:
        by_name.setdefault(e["name"], []).append(e["date"])

    results = []
    for name, dates in by_name.items():
        log(f"\n===== 清空檸檬人：{name}（{sorted(set(dates))}）=====")
        res = clear_person_shift_dates(session, name, sorted(set(dates)), ui_logger=ui_logger)
        results.append(res)
    return results


# =============================================================================
# 檸檬人佔位統計（2026-11-20）：每日上午／下午／全天，非保留單訂單裡的檸檬人
# =============================================================================
LEMON_COUNT_GROUPS = ("上午", "下午", "全天", "晚上")
RESERVE_CUSTOMER_KEYWORD = "檸檬保留"
_PERIOD_RE = re.compile(r"(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})")
_ORDER_DATE_RE = re.compile(r"^\d{2}-\d{2}(\s+\d{2}-\d{2})*$")  # 訂購日期（可能接著紅字修改日期）
_UNASSIGNED_RE = re.compile(r"^未配班\s*(\d+)\s*人$")
_MARKERS = {"V", "X", "D", "v", "x", "d"}


def period_group(period: str) -> str:
    """時段 → 上午／下午／全天／晚上；看不懂回傳空字串。

    上午＝12:30 前結束；下午＝12:00 後開始；晚上＝19:00 後開始；其餘跨中午＝全天。
    """
    m = _PERIOD_RE.search(str(period or ""))
    if not m:
        return ""
    start = int(m.group(1)) * 60 + int(m.group(2))
    end = int(m.group(3)) * 60 + int(m.group(4))
    if start >= 19 * 60:
        return "晚上"
    if start >= 12 * 60:
        return "下午"
    if end <= 12 * 60 + 30:
        return "上午"
    return "全天"


def _clean_line(line: str) -> str:
    """去掉性別圖示與 V／X／D 標記，只留姓名或專員代號。"""
    tokens = [t for t in re.split(r"\s+", line.strip()) if t and t not in _MARKERS]
    text = " ".join(tokens)
    return re.sub(r"^[♂♀⚥\s]+", "", text).strip()


def _parse_cell_orders(cell) -> List[Dict]:
    """班表一格（某日某時段）→ 訂單清單 [{customer, staff:[...]}]；灰底未配班名單不算訂單。"""
    for p in cell.select('p[style*="616161"]'):
        p.decompose()
    lines = [x.strip() for x in cell.get_text("\n").split("\n") if x.strip()]
    orders: List[Dict] = []
    current: Optional[Dict] = None
    skip = 0
    expect_customer = False
    for line in lines:
        if skip:
            skip -= 1
            continue
        m = _UNASSIGNED_RE.match(re.sub(r"\s+", " ", line))
        if m:
            skip = int(m.group(1))
            current = None
            expect_customer = False
            continue
        if _ORDER_DATE_RE.match(line):
            current = {"customer": "", "staff": []}
            orders.append(current)
            expect_customer = True
            continue
        text = _clean_line(line)
        if not text:
            continue
        first = text.split(" ")[0]
        # 訂購日期下一行＝客人；之後行尾是星等數字的都是這張單的專員（前面不一定有區域編號，
        # 例如「陳靜怡3」）。客人姓名不會以數字結尾，沒有訂購日期行時才用它開新訂單。
        if not expect_customer and current is not None and first[-1:].isdigit():
            current["staff"].append(first)
            continue
        if current is None or not expect_customer:
            current = {"customer": "", "staff": []}
            orders.append(current)
        current["customer"] = text
        expect_customer = False
    return orders


def parse_order_lemon_entries(html: str, query_date: str) -> List[Dict]:
    """解析 /schedule 一週班表：非「檸檬保留」訂單裡的檸檬人。

    回傳 [{date, period, group, name, raw, customer}]；未配班名單、檸檬保留單都不算。
    """
    soup = BeautifulSoup(html or "", "html.parser")
    results: List[Dict] = []
    day_orders: Dict[tuple, int] = {}
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
            date_val = _row_label_to_date(cells[0].get_text(" ", strip=True), query_date)
            if not date_val:
                continue
            for idx, cell in enumerate(cells[1:], start=1):
                period = periods[idx] if idx < len(periods) else ""
                group = period_group(period)
                if not group:
                    continue
                for order in _parse_cell_orders(cell):
                    key = (date_val, _norm_name(order["customer"]))
                    day_orders[key] = day_orders.get(key, 0) + 1
                    if RESERVE_CUSTOMER_KEYWORD in order["customer"]:
                        continue
                    for raw in order["staff"]:
                        parsed = parse_lemon_label(raw)
                        if parsed:
                            results.append({
                                "date": date_val, "period": period, "group": group,
                                "name": parsed["name"], "raw": raw, "customer": order["customer"],
                            })
    for e in results:  # 同一位客人當天在班表上共有幾張單（合併訂單判斷用）
        e["same_day_orders"] = day_orders.get((e["date"], _norm_name(e["customer"])), 1)
    return results


def _norm_name(name: str) -> str:
    return re.sub(r"[\s♂♀⚥]+", "", str(name or ""))


LEMON_KEEP_NOTE = "檸檬人勿動"


def parse_purchase_notices(html: str) -> List[Dict]:
    """訂單管理列表（/purchase）每張單的客人姓名與客服備註。

    客服備註內容在 <label alt="...">客服備註</label> 的 alt／title 屬性；沒有這個標籤＝空白。
    """
    soup = BeautifulSoup(html or "", "html.parser")
    rows = soup.select("table tbody tr") or soup.select("tr")
    out = []
    for tr in rows:
        if not re.search(r"(LC|TT|KK)\d+", tr.get_text(" ", strip=True)):
            continue
        name_tag = tr.select_one('a[href*="/member?keyword"]')
        name = name_tag.get_text(strip=True) if name_tag else ""
        notice = ""
        for label in tr.find_all("label"):
            if label.get_text(strip=True) == "客服備註":
                notice = str(label.get("alt") or label.get("title") or "")
                break
        if name:
            out.append({"name": name, "notice": notice})
    return out


def _json_strings(value) -> List[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [x for v in value.values() for x in _json_strings(v)]
    if isinstance(value, list):
        return [x for v in value for x in _json_strings(v)]
    return []


def parse_purchase_json_notices(html: str) -> Optional[List[Dict]]:
    """訂單管理頁內嵌的 Vue purchaseList JSON → [{order_no, names, notice}]；沒有 JSON 回傳 None。

    客服備註欄位名稱不固定，只要訂單資料（不含會員資料）任一文字欄位含「檸檬人勿動」就記在 notice。
    """
    from .atm import extract_purchase_list_json

    data = extract_purchase_list_json(html or "")
    if not data:
        return None
    out = []
    for item in data.get("data") or []:
        member = item.get("member") or {}
        names = {str(item.get(k) or "") for k in ("name", "contact_name", "receiver_name")}
        if isinstance(member, dict):
            names.add(str(member.get("name") or ""))
        own = {k: v for k, v in item.items() if k != "member"}
        notice = "\n".join(x for x in _json_strings(own) if LEMON_KEEP_NOTE in x)
        out.append({"order_no": str(item.get("order_no") or ""), "names": {n for n in names if n},
                    "notice": notice})
    return out


def _lemon_keep_customers(session: requests.Session, date_val: str) -> set:
    """該服務日期，客服備註含「檸檬人勿動」的客人姓名（正規化後）。"""
    params = memo.blank_list_params()
    params["clean_date_s"] = params["clean_date_e"] = date_val
    keep = set()
    seen_orders = set()
    seen_pages = set()
    for page in range(1, 31):
        params["page"] = str(page)
        r = memo.session_get(session, f"{memo.BASE_URL}/purchase", params=params)
        r.raise_for_status()
        rows = parse_purchase_json_notices(r.text)
        if rows is None:  # 沒有內嵌 JSON：退回讀表格
            rows = [{"order_no": "", "names": {x["name"]}, "notice": x["notice"]}
                    for x in parse_purchase_notices(r.text)]
        sig = tuple(sorted((x["order_no"], tuple(sorted(x["names"]))) for x in rows))
        if not rows or sig in seen_pages:
            break
        seen_pages.add(sig)
        new_rows = [x for x in rows if not x["order_no"] or x["order_no"] not in seen_orders]
        if not new_rows:
            break
        for x in new_rows:
            if x["order_no"]:
                seen_orders.add(x["order_no"])
            if LEMON_KEEP_NOTE in x["notice"]:
                keep |= {_norm_name(n) for n in x["names"]}
        if len(rows) < 20:
            break
    return keep


def count_order_lemons_range(
    session: requests.Session,
    date_start: str,
    date_end: str,
    ui_logger=None,
) -> Dict:
    """掃描 date_start～date_end 的 /schedule，統計每日上午／下午／全天非保留單的檸檬人數。

    回傳 {"days": [{date, 上午, 下午, 全天, 晚上, 合計, 明細}], "entries": [...]}；
    同一天同一類別同一位檸檬人只算一次。
    """
    log = make_logger(ui_logger)
    start = date.fromisoformat(date_start)
    end = date.fromisoformat(date_end)
    if end < start:
        start, end = end, start
    today = memo.today_tw().date()
    if start < today:  # 日期不小於今天（今天以前已服務的單不算待換）
        start = today
    if end < start:
        log(f"{date_start} ~ {date_end} 都在今天以前，不統計")
        return {"days": [], "entries": [], "excluded": [], "merged_kept": []}
    s_text, e_text = start.isoformat(), end.isoformat()

    entries: List[Dict] = []
    seen = set()
    week = start - timedelta(days=start.weekday())
    while week <= end:
        r = memo.session_get(session, f"{memo.BASE_URL}/schedule", params={"date": week.isoformat()})
        r.raise_for_status()
        actual = _parse_schedule_query_date(r.text, week.isoformat())
        week_entries = parse_order_lemon_entries(r.text, actual)
        log(f"{week.isoformat()} 那週：訂單裡（不含檸檬保留）找到 {len(week_entries)} 筆檸檬人")
        for e in week_entries:
            key = (e["date"], e["period"], e["name"], e["customer"])
            if s_text <= e["date"] <= e_text and key not in seen:
                seen.add(key)
                entries.append(e)
        week += timedelta(days=7)

    # 合併訂單：同一位客人當天多張單、且客服備註有「檸檬人勿動」→ 不在待換名單
    merged_dates = sorted({e["date"] for e in entries if e.get("same_day_orders", 1) >= 2})
    excluded: List[Dict] = []
    for d in merged_dates:
        keep = _lemon_keep_customers(session, d)
        if not keep:
            continue
        for e in [x for x in entries if x["date"] == d and x.get("same_day_orders", 1) >= 2
                  and _norm_name(x["customer"]) in keep]:
            entries.remove(e)
            excluded.append(e)
    merged_left = sorted({(e["date"], e["customer"]) for e in entries if e.get("same_day_orders", 1) >= 2})
    if merged_left:
        log("同一客人當天多張單、但客服備註沒查到「檸檬人勿動」（照算）：" + "、".join(
            f"{d[5:]} {c}" for d, c in merged_left))
    if excluded:
        log(f"排除合併訂單（客服備註有「{LEMON_KEEP_NOTE}」）{len(excluded)} 筆：" + "、".join(
            f"{e['date'][5:]} {e['customer']} {e['name']}" for e in excluded))

    days: List[Dict] = []
    cur = start
    weekday = "一二三四五六日"
    while cur <= end:
        d = cur.isoformat()
        row: Dict = {"日期": d, "星期": weekday[cur.weekday()]}
        details = []
        total = 0
        for g in LEMON_COUNT_GROUPS:
            names = sorted({e["name"] for e in entries if e["date"] == d and e["group"] == g},
                           key=lambda n: (len(n), n))
            row[g] = len(names)
            total += len(names)
            for e in sorted((x for x in entries if x["date"] == d and x["group"] == g),
                            key=lambda x: (x["period"], x["customer"])):
                details.append(f"{g} {e['period']} {e['customer']}：{e['name']}")
        row["合計"] = total
        row["明細"] = "；".join(details)
        days.append(row)
        cur += timedelta(days=1)
    log(f"{s_text} ~ {e_text} 共 {len(entries)} 筆非保留單訂單的檸檬人")
    return {"days": days, "entries": entries, "excluded": excluded,
            "merged_kept": [{"date": d, "customer": c} for d, c in merged_left]}


def format_lemon_progress(days: List[Dict], title: str = "檸檬人待換專員進度：") -> str:
    """統計結果 → 可直接貼 LINE 的進度文字，只列有檸檬人的日期、0 的時段不寫。

    例：02/17-上午-1，下午-1
    """
    lines = [title]
    for row in days:
        parts = [f"{g}-{row.get(g, 0)}" for g in LEMON_COUNT_GROUPS if row.get(g, 0)]
        if parts:
            mmdd = str(row["日期"])[5:].replace("-", "/")
            lines.append(f"{mmdd}-" + "，".join(parts))
    return "\n".join(lines)
