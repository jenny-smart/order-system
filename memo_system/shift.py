# shift.py
# -*- coding: utf-8 -*-
"""
自動勾班模組

修正紀錄（2026-06）：
1. get_shift_page_state 改為同時回傳所有 hidden input 欄位（含 _method 等），
   讓 submit_shift_payload 能帶著這些欄位一起送出，符合 Laravel 的 method spoofing。
2. submit_shift_payload 加上 month 參數，POST URL 帶 ?month=YYYY-MM。
3. clear_person_shift_dates 確認當月有勾選才送出，無勾選直接略過。
"""
import re
from datetime import date, timedelta
from typing import Dict, List, Optional, Callable, Tuple

import requests
from bs4 import BeautifulSoup

from . import memo

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
    soup = BeautifulSoup(r.text, "html.parser")

    token_el = soup.select_one('input[name="_token"]')
    token = token_el.get("value", "") if token_el else ""

    # 抓所有 hidden input（排除 _token 本身，因為已單獨處理）
    hidden_fields: Dict[str, str] = {}
    for el in soup.select('input[type="hidden"]'):
        name = el.get("name", "")
        value = el.get("value", "")
        if name and name != "_token":
            hidden_fields[name] = value

    # 抓已勾選的 shift_ radio
    existing: Dict[str, str] = {}
    for el in soup.select('input[name^="shift_"][checked]'):
        name = el.get("name", "")
        value = el.get("value", "")
        key = name[len("shift_"):]
        if value:
            existing[key] = value

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

    payload = {f"shift_{k}": v for k, v in merged.items()}
    payload["_token"] = token

    # 帶入 _method=PUT 等 Laravel hidden 欄位
    if hidden_fields:
        payload.update(hidden_fields)

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


def check_merged_conflicts(merged: Dict[str, str]) -> List[str]:
    warnings = []
    by_date: Dict[str, Dict[str, str]] = {}
    for key, value in merged.items():
        date_val, slot = key.rsplit("_", 1)
        by_date.setdefault(date_val, {})[slot] = value
    for date_val, slots in by_date.items():
        for slot in slots:
            for conflicting_slot in CONFLICT_MAP.get(slot, set()):
                if conflicting_slot in slots:
                    pair = tuple(sorted([slot, conflicting_slot]))
                    msg = f"⚠️ {date_val} 同時勾選了 {pair[0]}={slots[pair[0]]} 跟 {pair[1]}={slots[pair[1]]}，請確認"
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
) -> Dict:
    """
    將指定人員在 date_start ~ date_end 期間勾選指定班別。
    指定日期範圍內會先清掉 all/1/2/3 舊勾選，再套用本次選擇的班別。
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
