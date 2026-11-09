# -*- coding: utf-8 -*-
"""排班／檸檬人勾班共用邏輯，供 orders.py／quick_order.py 共用。

3 組原本分歧的函式（_parse_cleaner_shift_page、_set_cleaner_shift_if_available，
以及 _parse_cleaner_shift_page 依賴的 _shift_value_to_code_by_name）採用
quick_order.py 版本：判斷班別代碼時會多考慮欄位所屬的群組（避免同一數值在不同
群組代表不同班別造成誤判），且寫入排班後會重新抓一次班表頁面確認真的存進去了，
比 orders.py 原本只看 HTTP 狀態碼更嚴謹。

核心限制（不可破壞）：只能使用後台系統當下回應的候補人力（檸檬人）；
補班時只排除與目標時段衝突或已勾同時段的檸檬人（不再因當天有任何班別就整天
排除），且保留其既有班別、只新增目標時段；絕不拆解、改動其他客人已經配好班的專員。

Change Log
v2026.11.09-1
- 修正：當天沒有任何檸檬人勾班，卻全部被判成「已勾班」。排班頁改用
  BeautifulSoup 只讀真正有 checked 屬性的 shift_ 欄位，日期由欄位名稱判斷；
  POST 也只帶回真正已勾的班，不會誤寫假欄位。
- 新增：開排班頁時核對專員名稱，ID 對不到該檸檬人就跳過，避免勾到別人。
- 新增 release_unused_lemon_shifts：本次補勾的檸檬人當次用完，成單後仍在
  班表「未配班」的（或訂單失敗時）立即取消勾班，不留到下次。
- 新增 count_section_available／lemon_shortfall：先用查詢班表（依客人地址）
  看該時段可派幾人，只補缺的人數；
  快速成單與批次（批次、批次優化、批次優化＋雲端成單）共用。
- 檸檬人已勾班／衝突時自動換下一位直到補滿；清單用完就擴大搜尋，
  失敗時只顯示統計，不再逐位列出。
"""

import re
from datetime import date

import orders
from shared.shift_page import parse_shift_page, build_shift_payload  # noqa: F401

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


_SHIFT_NAME_RE = re.compile(r"^shift_(\d{4}-\d{2}-\d{2})_(.+)$")


# =============================================================================
# 共用排班頁讀寫（v2026.11.09-1）
# 做法比照「排班管理 → 檸檬人批次勾班」（memo_system/shift.py）：
# BeautifulSoup 只讀真正有 checked 屬性的 shift_ 欄位、帶回所有 hidden 欄位
# （_method=PUT 等），POST 帶 Referer。memo_system 也改呼叫這裡，所有成單
# （快速成單、批次 Sheet、選列重試、颱風轉移）與排班管理共用同一套程式。
# =============================================================================
def shift_codes_on_date(existing, date_str):
    codes = set()
    prefix = f"{date_str}_"
    for key, value in (existing or {}).items():
        if key.startswith(prefix):
            codes.add(_shift_value_to_code_by_name(f"shift_{key}", value))
    return codes


def _parse_cleaner_shift_page(html_text, date_str=None):
    """相容舊呼叫：回傳 (csrf, checked_fields, checked_codes_on_date)。"""
    token, existing, hidden_fields = parse_shift_page(html_text)
    fields = list(hidden_fields.items()) + [(f"shift_{k}", v) for k, v in existing.items()]
    codes = shift_codes_on_date(existing, date_str) if date_str else set()
    return token, fields, codes


def _parse_cleaner_name_on_shift_page(html_text):
    """只認排班頁標題的「專員：檸檬人N」或 <label>檸檬人N</label>；找不到就不核對。"""
    txt = html_text or ""
    m = re.search(r"專員\s*[：:]\s*(?:<[^>]+>\s*)*(檸檬人\d+)", txt) or re.search(r"<label>\s*(檸檬人\d+)\s*</label>", txt)
    return m.group(1) if m else ""


def _shift_url(base_url, cleaner_id):
    return f"{str(base_url).rstrip('/')}/cleaner1/{cleaner_id}/shift"


def _read_shift_state(session, base_url, cleaner_id, month, expected_name=""):
    """回傳 (token, existing, hidden_fields, err)。"""
    resp = session.get(_shift_url(base_url, cleaner_id), params={"month": month}, headers=orders.HEADERS, allow_redirects=True)
    if resp.status_code != 200:
        return "", {}, {}, f"HTTP {resp.status_code}"
    token, existing, hidden_fields = parse_shift_page(resp.text)
    if expected_name:
        page_name = _parse_cleaner_name_on_shift_page(resp.text)
        if page_name and page_name != expected_name:
            return token, existing, hidden_fields, f"排班頁專員為 {page_name}，與 {expected_name} 不符"
    return token, existing, hidden_fields, ""


def _get_cleaner_shift_form_info(session, base_url, cleaner_id, date_str, expected_name=""):
    token, existing, hidden_fields, err = _read_shift_state(session, base_url, cleaner_id, str(date_str)[:7], expected_name)
    fields = list(hidden_fields.items()) + [(f"shift_{k}", v) for k, v in existing.items()]
    return token, fields, shift_codes_on_date(existing, date_str), err


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

    # 比照排班管理：先用 /schedule 的專員下拉選單（select#cleaner_id）找檸檬人帳號。
    try:
        from bs4 import BeautifulSoup
        r0 = session.get(f"{base_url}/schedule", headers=orders.HEADERS, allow_redirects=True)
        if r0.status_code == 200:
            sel = BeautifulSoup(r0.text or "", "html.parser").select_one("select#cleaner_id")
            for opt in (sel.select("option") if sel is not None else []):
                val = (opt.get("value") or "").strip()
                if val and val != "0" and re.fullmatch(r"檸檬人\d+", opt.get_text(strip=True)):
                    add_entry(val, opt.get_text(strip=True))
    except Exception:
        pass

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
    """檸檬人補班：只排除與目標時段衝突的既有班，不再因當天任何班別就整天排除。"""
    csrf, checked_fields, checked_codes, err = _get_cleaner_shift_form_info(
        session, base_url, cleaner_id, date_str,
        expected_name=cleaner_name if re.fullmatch(r"檸檬人\d+", str(cleaner_name or "")) else "",
    )
    if err:
        return {"success": False, "name": cleaner_name, "id": cleaner_id, "reason": err, "checked": sorted(checked_codes)}
    target_shift_code = _shift_value_to_code(target_shift_code)
    # 同一時段已經有班：不要重複勾，避免搶到既有訂單已使用的人力。
    if target_shift_code in checked_codes:
        return {
            "success": False, "name": cleaner_name, "id": cleaner_id,
            "reason": f"{date_str} {target_shift_code} 已勾班（可能已有其他訂單使用），換下一位",
            "checked": sorted(checked_codes), "already_checked": True,
        }
    # 只檢查真正衝突的班別。
    # 例如目標 14:00-17:00（下3），上午上2/上3/上4不衝突，可繼續補下午班。
    conflicts = sorted(c for c in checked_codes if _shift_codes_conflict(c, target_shift_code))
    if conflicts:
        return {
            "success": False, "name": cleaner_name, "id": cleaner_id,
            "reason": f"{date_str} 已勾 {'、'.join(conflicts)}，與 {target_shift_code} 衝突",
            "checked": sorted(checked_codes), "protected_existing_shift": True,
        }
    target_name = f"shift_{date_str}_{_shift_code_to_group(target_shift_code)}"
    target_value = _shift_code_to_value(target_shift_code)
    # 比照排班管理批次勾班：保留原本所有已勾班與 hidden 欄位，只新增這次目標時段。
    payload = {}
    for name, value in checked_fields:
        payload.setdefault(name, value)
    payload[target_name] = target_value
    payload["_token"] = csrf
    month = str(date_str)[:7]
    url = _shift_url(base_url, cleaner_id)
    headers = dict(orders.HEADERS)
    headers["Referer"] = f"{url}?month={month}"
    resp = session.post(url, params={"month": month}, data=payload, headers=headers, allow_redirects=True)
    ok = resp.status_code in (200, 302)
    # 寫入成功不代表後台真的存到；重讀一次確認目標班別存在。
    if ok:
        _csrf2, _fields2, checked_after, err2 = _get_cleaner_shift_form_info(session, base_url, cleaner_id, date_str)
        ok = not err2 and target_shift_code in checked_after
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

    v2026.11.09-1：檸檬人該時段已勾班或衝突時自動換下一位，直到補滿為止；
    目前清單用完仍不足就擴大搜尋更多檸檬人，不再一次只看前幾位就失敗。
    失敗訊息只列統計，不逐位列出。
    """
    target_shift_code = _period_to_shift_code(period_s)
    if not target_shift_code:
        return {"success": False, "message": f"無法判斷服務時段 {period_s} 對應班別", "assigned": [], "skipped": []}
    need = int(person_count)
    month = str(service_date)[:7]
    assigned = []
    assigned_ids = []
    skipped = []
    seen_candidate_names = set()
    seen_candidate_ids = set()
    min_needed = need
    found_any = False
    while len(assigned) < need:
        cleaners = _search_lemon_cleaners(session, base_url, target_month=month, min_needed=min_needed)
        fresh = [
            (cid, cname) for cid, cname in cleaners
            if str(cid) not in seen_candidate_ids and str(cname) not in seen_candidate_names
        ]
        if not fresh:
            break
        found_any = True
        for cleaner_id, cleaner_name in fresh:
            if len(assigned) >= need:
                break
            seen_candidate_ids.add(str(cleaner_id))
            seen_candidate_names.add(str(cleaner_name))
            result = _set_cleaner_shift_if_available(session, base_url, cleaner_id, cleaner_name, service_date, target_shift_code)
            if result.get("success"):
                assigned.append(cleaner_name)
                assigned_ids.append(str(cleaner_id))
            else:
                skipped.append(result)
        # 這批全部看完仍不足：要求清單至少多出缺額的人數，再找下一批。
        min_needed = len(seen_candidate_ids) + (need - len(assigned))
    if not found_any:
        return {"success": False, "message": "找不到檸檬人清單", "assigned": [], "skipped": []}
    ok = len(assigned) >= need
    if ok:
        message = f"已預先補勾檸檬人：{'、'.join(assigned)}"
    else:
        busy = sum(1 for x in skipped if x.get("already_checked"))
        conflict = sum(1 for x in skipped if x.get("protected_existing_shift"))
        other = len(skipped) - busy - conflict
        parts = [f"已檢查 {len(seen_candidate_ids)} 位檸檬人"]
        if busy:
            parts.append(f"{busy} 位該時段已有班")
        if conflict:
            parts.append(f"{conflict} 位時段衝突")
        if other:
            parts.append(f"{other} 位讀取／寫入失敗")
        message = f"可用檸檬人不足：需要 {need} 位，只補到 {len(assigned)} 位（{'，'.join(parts)}）"
    return {
        "success": ok,
        "message": message,
        "assigned": assigned, "assigned_ids": assigned_ids, "skipped": skipped, "target_shift_code": target_shift_code,
    }


def count_section_available(session, payload, token, slot):
    """用「查詢班表」（後台 get_section，依客人地址／區域）算該時段可派幾人。

    以 1 人查詢：時段有出現就數 cleaner 名單。回傳 0＝這個地址該時段沒人；
    None＝查不到人數（呼叫端改用原本人數）。
    """
    from shared.staff_section import extract_cleaners_from_section_response, slot_exists_in_section_response
    try:
        data = dict(payload or {})
        data["person"] = "1"
        raw = orders.get_all_sections_raw(session, data, token)
        if not slot_exists_in_section_response(raw, slot):
            return 0
        cleaners = extract_cleaners_from_section_response(raw, slot)
        return len(cleaners) if cleaners else None
    except Exception:
        return None


def lemon_shortfall(need, available=None, api_available=0):
    """v2026.11.09-2：依查詢班表（客人地址可派的人）算缺幾人，只補缺的檸檬人。

    回傳 (要補幾位, 說明)。查不到可派人數時沿用原本做法：需要 − 成單查詢已列出人數。
    """
    need = max(int(need or 0), 1)
    fallback = max(1, need - max(int(api_available or 0), 0))
    if available is None:
        return fallback, f"查詢班表讀不到可派人數，補 {fallback} 位"
    n = max(1, need - int(available))
    return n, f"查詢班表此地址可派 {available} 人，需要 {need} 人，補 {n} 位"


# =============================================================================
# v2026.11.09-3：本次勾的檸檬人當次用完——沒被訂單用到的立即取消勾班
# =============================================================================
def schedule_unassigned_lemons(session, base_url, service_date, period_s):
    """讀 /schedule 當日該時段灰底「未配班」名單中的檸檬人名稱。讀不到回傳 None。"""
    try:
        from bs4 import BeautifulSoup
        resp = session.get(f"{base_url}/schedule", params={"date": str(service_date), "staffId": ""},
                           headers=orders.HEADERS, allow_redirects=True)
        if getattr(resp, "status_code", None) != 200 or not isinstance(resp.text, str):
            return None
        target = str(period_s or "").replace(" ", "")
        mmdd = str(service_date)[5:]
        soup = BeautifulSoup(resp.text, "html.parser")
        for table in soup.find_all("table"):
            rows = table.find_all("tr")
            if not rows:
                continue
            heads = [re.sub(r"\s+", "", c.get_text(" ", strip=True)) for c in rows[0].find_all(["th", "td"], recursive=False)]
            cols = [i for i, h in enumerate(heads) if h == target] or [i for i, h in enumerate(heads) if target in h]
            if not cols:
                continue
            for row in rows[1:]:
                cells = row.find_all(["th", "td"], recursive=False)
                if not cells or mmdd not in cells[0].get_text(" ", strip=True):
                    continue
                if cols[0] >= len(cells):
                    return None
                text = cells[cols[0]].get_text(" ", strip=True)
                idx = text.find("未配班")
                if idx < 0:
                    return set()
                return set(re.findall(r"檸檬人\d+", text[idx:]))
        return None
    except Exception:
        return None


def _remove_cleaner_shift(session, base_url, cleaner_id, cleaner_name, date_str, target_shift_code):
    """取消本次替檸檬人新增的那一個時段（其他已勾班保留）。"""
    month = str(date_str)[:7]
    token, existing, hidden_fields, err = _read_shift_state(session, base_url, cleaner_id, month, expected_name=cleaner_name)
    if err:
        return False, err
    key = f"{date_str}_{_shift_code_to_group(target_shift_code)}"
    if key not in existing:
        return True, "已無此班"
    merged = {k: v for k, v in existing.items() if k != key}
    url = _shift_url(base_url, cleaner_id)
    headers = dict(orders.HEADERS)
    headers["Referer"] = f"{url}?month={month}"
    resp = session.post(url, params={"month": month}, data=build_shift_payload(token, merged, hidden_fields),
                        headers=headers, allow_redirects=True)
    if resp.status_code not in (200, 302):
        return False, f"HTTP {resp.status_code}"
    _, after, _, _ = _read_shift_state(session, base_url, cleaner_id, month)
    return (key not in after), ("" if key not in after else "取消後仍有勾班")


def release_unused_lemon_shifts(session, base_url, service_date, period_s, added, order_failed=False):
    """本次補勾、但沒有被訂單用到的檸檬人，取消勾班，不留到下次。

    added：[(cleaner_id, cleaner_name), ...]，只會處理本次新增的檸檬人。
    以班表該時段「未配班」名單判斷沒被用到；班表讀不到時，只有訂單失敗才全部取消。
    """
    added = [(str(i), str(n)) for i, n in (added or []) if i]
    if not added:
        return {"released": [], "failed": [], "message": ""}
    code = _period_to_shift_code(period_s)
    unused = schedule_unassigned_lemons(session, base_url, service_date, period_s)
    if unused is None:
        targets = added if order_failed else []
    else:
        targets = [(i, n) for i, n in added if n in unused]
    released, failed = [], []
    for cid, name in targets:
        try:
            ok, why = _remove_cleaner_shift(session, base_url, cid, name, service_date, code)
        except Exception as exc:
            ok, why = False, str(exc)
        (released if ok else failed).append(name if ok else f"{name}（{why}）")
    parts = []
    if released:
        parts.append(f"未用到的檸檬人已取消勾班：{'、'.join(released)}")
    if failed:
        parts.append(f"⚠️ 取消勾班失敗，請手動取消：{'、'.join(failed)}")
    if unused is None and not order_failed:
        parts.append("⚠️ 讀不到班表未配班名單，請確認本次補勾的檸檬人是否都有用到")
    return {"released": released, "failed": failed, "message": "；".join(parts)}


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
