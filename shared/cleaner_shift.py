# -*- coding: utf-8 -*-
"""排班／檸檬人勾班共用邏輯，供 orders.py／quick_order.py 共用。

3 組原本分歧的函式（_parse_cleaner_shift_page、_set_cleaner_shift_if_available，
以及 _parse_cleaner_shift_page 依賴的 _shift_value_to_code_by_name）採用
quick_order.py 版本：判斷班別代碼時會多考慮欄位所屬的群組（避免同一數值在不同
群組代表不同班別造成誤判），且寫入排班後會重新抓一次班表頁面確認真的存進去了，
比 orders.py 原本只看 HTTP 狀態碼更嚴謹。

核心限制（不可破壞）：只能使用後台系統當下回應的、當天完全沒有排班的候補人力
（檸檬人）；絕不拆解、改動其他客人已經配好班的專員。
"""

import re
from datetime import date

import orders

VALUE_TO_SHIFT_CODE = {
    "6": "全6", "8": "全8",
    "0830-1230": "上4", "0900-1200": "上3", "0900-1100": "上2",
    "1400-1600": "下2", "1400-1700": "下3", "1400-1800": "下4",
    "1900-2100": "晚2",
}
SHIFT_CONFLICT_TABLE = {
    "全6": {"上3", "上4", "上2", "全6", "全8"},
    "全8": {"上3", "上4", "上2", "下2", "下3", "下4", "全6", "全8"},
    "上3": {"上3", "上4", "上2", "全6", "全8"},
    "上4": {"上3", "上4", "上2", "全6", "全8"},
    "上2": {"上3", "上4", "上2", "全6", "全8"},
    "下3": {"下2", "下3", "下4", "全6", "全8"},
    "下4": {"下2", "下3", "下4", "全6", "全8"},
    "下2": {"下2", "下3", "下4", "全6", "全8"},
}
PERIOD_TO_SHIFT_CODE = {
    "09:00-12:00": "上3", "08:30-12:30": "上4", "09:00-11:00": "上2",
    "14:00-16:00": "下2", "14:00-17:00": "下3", "14:00-18:00": "下4",
    "09:00-16:00": "全6", "09:00-18:00": "全8",
}


def _period_to_shift_code(period_s):
    compact = str(period_s or "").replace(" ", "")
    return PERIOD_TO_SHIFT_CODE.get(compact, "")


def _shift_value_to_code(value):
    value = str(value or "").strip()
    return VALUE_TO_SHIFT_CODE.get(value, value)


def _shift_value_to_code_by_name(name, value):
    name = str(name or "")
    value = str(value or "").strip()
    group = name.rsplit("_", 1)[-1] if "_" in name else ""
    if group == "1" and value in {"2", "3", "4"}:
        return {"2": "上2", "3": "上3", "4": "上4"}[value]
    if group == "2" and value in {"2", "3", "4"}:
        return {"2": "下2", "3": "下3", "4": "下4"}[value]
    if group == "3" and value == "2":
        return "晚2"
    return _shift_value_to_code(value)


def _shift_code_to_value(code):
    code = str(code or "").strip()
    for value, mapped in VALUE_TO_SHIFT_CODE.items():
        if mapped == code:
            return value
    return code


def _shift_code_to_group(code):
    code = str(code or "").strip()
    if code in {"全6", "全8"}:
        return "all"
    if code in {"上2", "上3", "上4"}:
        return "1"
    if code in {"下2", "下3", "下4"}:
        return "2"
    if code in {"晚2"}:
        return "3"
    return "1"


def _shift_codes_conflict(existing_code, target_code):
    existing_code = _shift_value_to_code(existing_code)
    target_code = _shift_value_to_code(target_code)
    if not existing_code or not target_code:
        return False
    if existing_code == target_code:
        return False
    if existing_code in {"全6", "全8"} or target_code in {"全6", "全8"}:
        return True
    return target_code in SHIFT_CONFLICT_TABLE.get(existing_code, set())


def _parse_cleaner_shift_page(html_text, date_str=None):
    token_m = re.search(r'name=["\']_token["\'][^>]*value=["\']([^"\']+)["\']', html_text or "")
    csrf = token_m.group(1) if token_m else ""
    if not csrf:
        meta_m = re.search(r'<meta name="csrf-token" content="([^"]+)"', html_text or "")
        csrf = meta_m.group(1) if meta_m else ""
    checked_fields = []
    checked_codes_on_date = set()
    for m in re.finditer(r'<input\b[^>]*\btype=["\']hidden["\'][^>]*>', html_text or "", re.I):
        tag = m.group(0)
        name_m = re.search(r'\bname=["\']([^"\']+)["\']', tag, re.I)
        value_m = re.search(r'\bvalue=["\']([^"\']*)["\']', tag, re.I)
        if name_m:
            checked_fields.append((name_m.group(1), value_m.group(1) if value_m else ""))
    for m in re.finditer(r'<input\b[^>]*\bchecked\b[^>]*>', html_text or "", re.I):
        tag = m.group(0)
        name_m = re.search(r'\bname=["\']([^"\']+)["\']', tag, re.I)
        value_m = re.search(r'\bvalue=["\']?([^"\'\s>]+)', tag, re.I)
        date_m = re.search(r'\bdate=["\']([^"\']+)["\']', tag, re.I)
        if not name_m or not value_m:
            continue
        name = name_m.group(1)
        value = value_m.group(1)
        checked_fields.append((name, value))
        d = date_m.group(1) if date_m else ""
        if date_str and d == date_str:
            checked_codes_on_date.add(_shift_value_to_code_by_name(name, value))
    return csrf, checked_fields, checked_codes_on_date


def _get_cleaner_shift_form_info(session, base_url, cleaner_id, date_str):
    ym = str(date_str)[:7]
    resp = session.get(f"{base_url}/cleaner1/{cleaner_id}/shift", params={"month": ym}, headers=orders.HEADERS, allow_redirects=True)
    if resp.status_code != 200:
        return "", [], set(), f"HTTP {resp.status_code}"
    csrf, checked_fields, checked_codes = _parse_cleaner_shift_page(resp.text, date_str)
    return csrf, checked_fields, checked_codes, ""


def _get_cleaner_shifts_on_date(session, base_url, cleaner_id, date_str):
    _csrf, _fields, checked_codes, _msg = _get_cleaner_shift_form_info(session, base_url, cleaner_id, date_str)
    return checked_codes


def _search_lemon_cleaners(session, base_url, target_month=None, min_needed=0):
    entries = []
    seen_ids = set()
    seen_names = set()
    target_month = str(target_month or date.today().strftime("%Y-%m"))[:7]
    min_needed = int(min_needed or 0)

    def lemon_sort_key(item):
        m = re.search(r"檸檬人\s*(\d+)", item[1])
        return int(m.group(1)) if m else 9999

    def add_entry(cid, name):
        cid = str(cid or "").strip()
        name = re.sub(r"\s+", "", str(name or "").strip())
        m = re.search(r"檸檬人\d+", name)
        if m:
            name = m.group(0)
        if not cid or cid in seen_ids or "檸檬人" not in name:
            return
        if name in seen_names:
            return
        seen_ids.add(cid)
        seen_names.add(name)
        entries.append((cid, name))

    candidate_ids = []

    def add_candidate(cid):
        cid = str(cid or "").strip()
        if cid.isdigit() and cid not in candidate_ids:
            candidate_ids.append(cid)

    try:
        resp = session.get(f"{base_url}/cleaner1", params={"area_id": "", "keyword": "檸檬"}, headers=orders.HEADERS, allow_redirects=True)
    except Exception:
        resp = None

    if resp is not None and resp.status_code == 200:
        html = resp.text or ""
        row_blocks = re.split(r"<tr\b", html, flags=re.I)
        for row in row_blocks:
            if "檸檬人" not in row:
                continue
            name_m = re.search(r"檸檬人\d+", row)
            ids = re.findall(r"/cleaner1/(\d+)(?=[/'\"?#])", row, re.I)
            ids += re.findall(r"cleaner[_-]?id[=:'\" ]+(\d+)", row, re.I)
            for cid in ids:
                add_candidate(cid)
                if name_m:
                    add_entry(cid, name_m.group(0))
        for m in re.finditer(r"/cleaner1/(\d+)(?=[/'\"?#])", html, re.I):
            cid = m.group(1)
            ctx = html[max(0, m.start() - 1000): m.end() + 1000]
            name_m = re.search(r"檸檬人\d+", ctx)
            add_candidate(cid)
            if name_m:
                add_entry(cid, name_m.group(0))

    entries.sort(key=lemon_sort_key)
    if min_needed and len(entries) >= min_needed:
        return entries

    for cid in list(range(1, 501)):
        add_candidate(cid)

    for cid in candidate_ids:
        if str(cid) in seen_ids:
            continue
        try:
            r = session.get(f"{base_url}/cleaner1/{cid}/shift", params={"month": target_month}, headers=orders.HEADERS, allow_redirects=True)
        except Exception:
            continue
        if r.status_code != 200:
            continue
        txt = r.text or ""
        name_m = re.search(r"專員\s*[：:]\s*(?:<[^>]+>\s*)*(檸檬人\d+)", txt)
        if not name_m:
            name_m = re.search(r"<label>\s*(檸檬人\d+)\s*</label>", txt)
        if name_m:
            add_entry(cid, name_m.group(1))
            entries.sort(key=lemon_sort_key)
            if min_needed and len(entries) >= min_needed:
                break

    entries.sort(key=lemon_sort_key)
    return entries


def _set_cleaner_shift_if_available(session, base_url, cleaner_id, cleaner_name, date_str, target_shift_code):
    csrf, checked_fields, checked_codes, err = _get_cleaner_shift_form_info(session, base_url, cleaner_id, date_str)
    if err:
        return {"success": False, "name": cleaner_name, "id": cleaner_id, "reason": err, "checked": sorted(checked_codes)}
    target_shift_code = _shift_value_to_code(target_shift_code)
    if checked_codes:
        return {
            "success": False, "name": cleaner_name, "id": cleaner_id,
            "reason": f"{date_str} 已有班別 {'、'.join(sorted(checked_codes))}，為保護已配班人員不寫入新班別",
            "checked": sorted(checked_codes), "protected_existing_shift": True,
        }
    conflicts = sorted(c for c in checked_codes if _shift_codes_conflict(c, target_shift_code))
    if conflicts:
        return {"success": False, "name": cleaner_name, "id": cleaner_id, "reason": f"{date_str} 已勾 {'、'.join(conflicts)}，與 {target_shift_code} 衝突", "checked": sorted(checked_codes)}
    if target_shift_code in checked_codes:
        # 該時段已勾班，可能已被其他訂單佔用，跳過換下一位檸檬人
        return {"success": False, "name": cleaner_name, "id": cleaner_id, "reason": f"{date_str} {target_shift_code} 已勾班（可能已有其他訂單使用），換下一位", "checked": sorted(checked_codes), "already_checked": True}
    target_name = f"shift_{date_str}_{_shift_code_to_group(target_shift_code)}"
    target_value = _shift_code_to_value(target_shift_code)
    fields = []
    if csrf:
        fields.append(("_token", csrf))
    seen = set()
    for name, value in checked_fields:
        key = (name, value)
        if key in seen:
            continue
        seen.add(key)
        fields.append((name, value))
    if (target_name, target_value) not in seen:
        fields.append((target_name, target_value))
    resp = session.post(f"{base_url}/cleaner1/{cleaner_id}/shift", params={"month": str(date_str)[:7]}, data=fields, headers=orders.HEADERS, allow_redirects=True)
    ok = resp.status_code in (200, 302)
    if ok:
        _csrf2, _fields2, checked_after, _err2 = _get_cleaner_shift_form_info(session, base_url, cleaner_id, date_str)
        ok = target_shift_code in checked_after
    return {
        "success": ok, "name": cleaner_name, "id": cleaner_id,
        "message": f"{cleaner_name} 已補勾 {date_str} {target_shift_code}" if ok else f"POST 後未確認到班別 {date_str} {target_shift_code}（HTTP {resp.status_code}）",
        "checked": sorted(checked_codes), "target": target_shift_code,
    }


def ensure_lemon_cleaner_shifts(session, base_url, service_date, period_s, person_count):
    """
    v2026-07：查無班表時補勾檸檬人排班。與 quick_order.py 的同名函式邏輯一致，
    供批次（Google Sheet）流程共用，確保各成單功能行為一致。
    呼叫端必須自行決定是否要在「查無班表」時呼叫本函式（由
    allow_auto_lemon_shift 參數控制），本函式本身不做開關判斷。
    """
    target_shift_code = _period_to_shift_code(period_s)
    if not target_shift_code:
        return {"success": False, "message": f"無法判斷服務時段 {period_s} 對應班別", "assigned": [], "skipped": []}
    cleaners = _search_lemon_cleaners(session, base_url, target_month=str(service_date)[:7], min_needed=int(person_count))
    if not cleaners:
        return {"success": False, "message": "找不到檸檬人清單", "assigned": [], "skipped": []}
    need = int(person_count)
    assigned = []
    assigned_ids = []
    skipped = []
    seen_candidate_names = set()
    seen_candidate_ids = set()
    for cleaner_id, cleaner_name in cleaners:
        if str(cleaner_id) in seen_candidate_ids or str(cleaner_name) in seen_candidate_names:
            continue
        seen_candidate_ids.add(str(cleaner_id))
        seen_candidate_names.add(str(cleaner_name))
        if len(assigned) >= need:
            break
        result = _set_cleaner_shift_if_available(session, base_url, cleaner_id, cleaner_name, service_date, target_shift_code)
        if result.get("success"):
            assigned.append(cleaner_name)
            assigned_ids.append(str(cleaner_id))
        else:
            skipped.append(result)
    ok = len(assigned) >= need
    return {
        "success": ok,
        "message": f"已預先補勾檸檬人：{'、'.join(assigned)}" if ok else f"可用檸檬人不足：需要 {need} 位，找到 {len(assigned)} 位",
        "assigned": assigned, "assigned_ids": assigned_ids, "skipped": skipped, "target_shift_code": target_shift_code,
    }


def _get_schedule_edit_info(session, base_url, date_str, purchase_id):
    resp = session.get(f"{base_url}/schedule/edit", params={"date": date_str, "purchase_id": purchase_id}, headers=orders.HEADERS, allow_redirects=True)
    if resp.status_code != 200:
        return None, [], []
    token_m = re.search(r'<meta name="csrf-token" content="([^"]+)"', resp.text)
    csrf = token_m.group(1) if token_m else ""
    origin_ids = re.findall(r'name=["\']originShiftId\[\]["\'][^>]*value=["\']?(\d+)["\']?', resp.text)
    if not origin_ids:
        origin_ids = re.findall(r'value=["\']?(\d+)["\'][^>]*name=["\']originShiftId\[\]', resp.text)
    slots = []
    slot_blocks = re.split(r'name=["\']originShiftId\[\]', resp.text)[1:]
    for block in slot_blocks:
        slot_map = {}
        for m in re.finditer(r'<label[^>]+for=["\']shift_\d+_(\d+)["\'][^>]*>([^<]+)</label>', block):
            shift_id = m.group(1)
            name = m.group(2).strip()
            slot_map[name] = shift_id
        slots.append(slot_map)
    return csrf, origin_ids, slots
