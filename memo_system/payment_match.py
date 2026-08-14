# -*- coding: utf-8 -*-
"""付款後 5 碼／星和診所對帳；刻意與 atm.py 完全分離。"""
import json
import os
import re
from datetime import datetime
from itertools import combinations
from typing import Callable, Dict, List, Optional

import gspread
from google.oauth2.service_account import Credentials

from . import memo


REGION_SECRET_PREFIX = {
    "台北": "TAIPEI",
    "台中": "TAICHUNG",
    "桃園": "TAOYUAN",
    "新竹": "HSINCHU",
    "高雄": "KAOHSIUNG",
}
WORKSHEET_TITLE = "ATM"
STAR_CLINIC = "星和診所"
REGIONAL_FILTER_EMAIL = "jenny.hc@lemonclean.com.tw"
SOUTH_ADDRESS_PREFIXES = ("高雄", "台南", "臺南")
HSINCHU_ADDRESS_PREFIXES = ("新竹",)
PURCHASE_FILTER_DEFAULTS = {
    "keyword": "", "name": "", "phone": "", "orderNo": "",
    "date_s": "", "date_e": "", "clean_date_s": "", "clean_date_e": "",
    "paid_at_s": "", "paid_at_e": "", "refundDateS": "", "refundDateE": "",
    "buy": "", "area_id": "", "isCharge": "", "isRefund": "",
    "payway": "", "purchase_status": "", "progress_status": "",
    "invoiceStatus": "", "otherFee": "", "orderBy": "",
}


def _logger(callback: Optional[Callable[[str], None]] = None):
    def log(message):
        message = str(message)
        print(message, flush=True)
        if callback:
            callback(message)
    return log


def _client():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    info = None
    try:
        import streamlit as st
        for key in ("gcp_service_account", "GOOGLE_SERVICE_ACCOUNT"):
            if key in st.secrets:
                info = dict(st.secrets[key])
                break
    except Exception:
        pass
    if info is None and os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip():
        info = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
    if info is not None:
        return gspread.authorize(Credentials.from_service_account_info(info, scopes=scopes))
    return gspread.authorize(Credentials.from_service_account_file(memo.GOOGLE_SERVICE_ACCOUNT_FILE, scopes=scopes))


def _secret_text(key: str) -> str:
    try:
        import streamlit as st
        value = st.secrets.get(key, "")
        if value is not None and str(value).strip():
            return str(value).strip()
        section = st.secrets.get("sheet_settings", {})
        value = section.get(key, "") if section else ""
        if value is not None and str(value).strip():
            return str(value).strip()
    except Exception:
        pass
    return str(os.getenv(key, "") or "").strip()


def _sheet_config(region: str) -> Dict:
    if region not in REGION_SECRET_PREFIX:
        raise ValueError(f"不支援的地區：{region}")
    prefix = REGION_SECRET_PREFIX[region]
    spreadsheet_id = _secret_text(f"ATM_{prefix}_SPREADSHEET_ID")
    gid_text = _secret_text(f"ATM_{prefix}_GID")
    worksheet_title = _secret_text(f"ATM_{prefix}_WORKSHEET_TITLE")
    if not spreadsheet_id:
        raise ValueError(f"Secrets 尚未設定「{region}」付款比對試算表 ID")
    try:
        gid = int(gid_text) if gid_text else None
    except ValueError as exc:
        raise ValueError(f"Secrets 的「{region}」GID 必須是整數") from exc
    if gid is None and not worksheet_title:
        if region in {"台北", "台中"}:
            worksheet_title = WORKSHEET_TITLE
        else:
            raise ValueError(f"Secrets 尚未設定「{region}」付款比對分頁 GID 或名稱")
    return {"spreadsheet_id": spreadsheet_id, "gid": gid, "worksheet_title": worksheet_title}


def get_worksheet(region: str):
    config = _sheet_config(region)
    spreadsheet = _client().open_by_key(config["spreadsheet_id"])
    if config["gid"] is not None:
        worksheet = spreadsheet.get_worksheet_by_id(int(config["gid"]))
        if worksheet is None:
            raise ValueError(f"找不到「{region}」指定分頁 gid={config['gid']}")
        return worksheet
    return spreadsheet.worksheet(config["worksheet_title"])


def extract_purchase_list(html: str) -> Optional[Dict]:
    marker = html.find("purchaseList:")
    start = html.find("{", marker) if marker >= 0 else -1
    if start < 0:
        return None
    depth = 0
    in_string = escaped = False
    for pos in range(start, len(html)):
        char = html[pos]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(html[start:pos + 1])
                except (TypeError, ValueError):
                    return None
    return None


def _service_category(item: Dict) -> str:
    clean_type = str(item.get("clean_type_id") or "")
    if clean_type in {"5", "6"}:
        return "家電清潔"
    if clean_type in {"7", "8"}:
        return "水洗清潔"
    return "居家清潔"


def _money(value) -> int:
    try:
        return int(round(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def _row(item: Dict) -> Dict:
    service_date = str(item.get("date_clean") or "")[:10]
    return {
        "service_month": service_date[:7].replace("-", "."),
        "order_no": str(item.get("order_no") or ""),
        "name": str(item.get("name") or ""),
        "service_date": service_date,
        "net_amount": _money(item.get("total")) - _money(item.get("fare")),
        "last5": str(item.get("account5") or "").strip(),
        "service_category": _service_category(item),
        "service_detail": "清潔服務",
        "paid_at": str(item.get("paid_at") or "")[:16],
    }


def _starts_with(address, prefixes) -> bool:
    text = re.sub(r"\s+", "", str(address or ""))
    return any(text.startswith(prefix) for prefix in prefixes)


def _stored_value_purchase_region(item: Dict) -> str:
    """辨識「儲值金-新竹(儲值金...)」這類儲值金購買訂單。"""
    text = json.dumps(item, ensure_ascii=False, default=str)
    match = re.search(r"儲值金[-－]?\s*(台北|台中|桃園|新竹|高雄|台南|臺南)\s*[（(]", text)
    if match:
        return "台南" if match.group(1) == "臺南" else match.group(1)
    if (str(item.get("clean_type_id")) == "0"
            and _money(item.get("stored_value")) > 0
            and not str(item.get("address") or "").strip()):
        return "儲值金"
    return ""


def _fetch_purchase_items(session, params: Dict, log=None, label="") -> List[Dict]:
    """讀取後台訂單搜尋的所有分頁；不與 atm.py 共用任何流程。"""
    query = dict(PURCHASE_FILTER_DEFAULTS)
    query.update(params)
    items = []
    page = 1
    while True:
        query["page"] = page
        response = memo.session_get(session, f"{memo.BASE_URL}/purchase", params=query)
        response.raise_for_status()
        payload = extract_purchase_list(response.text)
        if not payload:
            break
        items.extend(item for item in payload.get("data", []) if isinstance(item, dict))
        last_page = int(payload.get("last_page") or 1)
        if log and label:
            log(f"{label}：讀取第 {page}/{last_page} 頁")
        if page >= last_page:
            break
        page += 1
    return items


def _service_history_addresses(session, item: Dict, cache: Dict[str, List[str]]) -> List[str]:
    """依電話查既有服務訂單地址，供沒有地址的儲值金購買訂單判斷地區。"""
    phone = re.sub(r"\D+", "", str(item.get("phone") or ""))
    cache_key = phone or f"member:{item.get('member_id') or ''}"
    if cache_key in cache:
        return cache[cache_key]
    if not phone:
        cache[cache_key] = []
        return []
    history = _fetch_purchase_items(session, {
        "phone": phone,
        "p_board": "on",
    })
    addresses = []
    for old_item in history:
        address = str(old_item.get("address") or "").strip()
        if address and str(old_item.get("date_clean") or "").strip() and address not in addresses:
            addresses.append(address)
    cache[cache_key] = addresses
    return addresses


def _include_for_jenny_region(session, item: Dict, region: str,
                              history_cache: Dict[str, List[str]]) -> bool:
    """Jenny 專用分流：高雄含台南；新竹不得混入高雄／台南。"""
    if region not in {"高雄", "新竹"}:
        return True

    address = str(item.get("address") or "").strip()
    stored_region = _stored_value_purchase_region(item)
    if not stored_region:
        is_south = _starts_with(address, SOUTH_ADDRESS_PREFIXES)
        return is_south if region == "高雄" else not is_south

    addresses = _service_history_addresses(session, item, history_cache)
    has_south = any(_starts_with(value, SOUTH_ADDRESS_PREFIXES) for value in addresses)
    has_hsinchu = any(_starts_with(value, HSINCHU_ADDRESS_PREFIXES) for value in addresses)

    # 曾有高雄／台南服務地址即歸高雄；新竹只收沒有南部地址的純新竹會員。
    belongs_to_south = has_south
    belongs_to_hsinchu = has_hsinchu and not has_south
    return belongs_to_south if region == "高雄" else belongs_to_hsinchu


def search_orders(session, paid_start: str, paid_end: str, payment_status: str,
                  region: str = "", login_email: str = "", ui_logger=None) -> List[Dict]:
    """依付款日期、付款狀態與 ATM 搜尋所有分頁，星和診所亦全數保留。"""
    if payment_status not in {"0", "1"}:
        raise ValueError("付款狀態必須是待付款或已付款")
    log = _logger(ui_logger)
    params = {
        "paid_at_s": paid_start, "paid_at_e": paid_end,
        "payway": "2", "purchase_status": payment_status, "p_board": "on",
    }
    items = _fetch_purchase_items(session, params, log=log, label="付款訂單")
    if not items:
        log("查無訂單，或後台頁面格式已變更")

    output, seen, skipped_zero, skipped_region = [], set(), 0, 0
    history_cache: Dict[str, List[str]] = {}
    use_jenny_filter = str(login_email or "").strip().lower() == REGIONAL_FILTER_EMAIL
    for item in items:
        if use_jenny_filter and not _include_for_jenny_region(session, item, region, history_cache):
            skipped_region += 1
            continue
        row = _row(item)
        if row["net_amount"] == 0:
            skipped_zero += 1
            continue
        if row["order_no"] and row["order_no"] not in seen:
            seen.add(row["order_no"])
            output.append(row)
    output.sort(key=lambda row: (row["paid_at"], row["order_no"]))
    if skipped_zero:
        log(f"略過 {skipped_zero} 筆總金額扣車馬費為 0 的訂單")
    if use_jenny_filter and region in {"高雄", "新竹"}:
        log(f"{region}地區篩選完成，排除 {skipped_region} 筆其他地區訂單")
    log(f"共取得 {len(output)} 筆；其中星和診所 {sum(r['name'] == STAR_CLINIC for r in output)} 筆")
    return output


def _values(row: Dict) -> List:
    return [row[key] for key in (
        "service_month", "order_no", "name", "service_date", "net_amount",
        "last5", "service_category", "service_detail", "paid_at",
    )]


def paste_orders(region: str, rows: List[Dict], ui_logger=None) -> Dict:
    """從銀行 B 欄最後資料列下方 5 列開始，獨立貼至 K:S。"""
    log = _logger(ui_logger)
    rows = [row for row in rows if _money(row.get("net_amount")) != 0]
    if not rows:
        log("沒有非零淨額的資料可以貼入 K:S")
        return {"pasted": 0, "start_row": None}
    ws = get_worksheet(region)
    values = memo.with_retry(ws.get_all_values)
    last_bank_row = max((i for i, row in enumerate(values, 1)
                         if len(row) >= 2 and str(row[1]).strip()), default=1)
    start = last_bank_row + 5
    while start <= len(values) and any(str(v).strip() for v in values[start - 1][10:19]):
        start += 5
    payload = [_values(row) for row in rows]
    memo.with_retry(ws.update, f"K{start}:S{start + len(payload) - 1}", payload, value_input_option="RAW")
    log(f"已貼上 {len(payload)} 筆至 K{start}:S{start + len(payload) - 1}")
    return {"pasted": len(payload), "start_row": start}


def _amount(value) -> Optional[int]:
    text = re.sub(r"[^0-9.-]", "", str(value or ""))
    try:
        return int(round(float(text))) if text else None
    except ValueError:
        return None


def _date(value: str) -> Optional[datetime]:
    digits = re.sub(r"\D", "", str(value or ""))
    for size, fmt in ((14, "%Y%m%d%H%M%S"), (12, "%Y%m%d%H%M"), (8, "%Y%m%d")):
        if len(digits) >= size:
            try:
                return datetime.strptime(digits[:size], fmt)
            except ValueError:
                pass
    return None


def _identity_match(note: str, row: Dict) -> bool:
    compact = re.sub(r"\s", "", str(note or ""))
    code = re.sub(r"\D", "", row.get("last5", ""))
    return bool((code and re.sub(r"\D", "", compact).endswith(code))
                or (row["name"] and row["name"] in compact)
                or row["name"] == STAR_CLINIC and STAR_CLINIC in compact)


def _find_group(income: int, note: str, bank_time: str, candidates: List[Dict]) -> List[Dict]:
    bank_dt = _date(bank_time)
    eligible = []
    for row in candidates:
        if not _identity_match(note, row):
            continue
        paid_dt = _date(row["paid_at"])
        if bank_dt and paid_dt and paid_dt < bank_dt:
            continue
        eligible.append(row)
    eligible.sort(key=lambda row: (_date(row["paid_at"]) or datetime.max, row["order_no"]))
    for size in range(1, min(8, len(eligible)) + 1):
        groups = [group for group in combinations(eligible, size)
                  if sum(row["net_amount"] for row in group) == income]
        if len(groups) == 1:
            return list(groups[0])
        if len(groups) > 1:
            return []
    return []


def match_bank_rows(region: str, ui_logger=None) -> Dict:
    """以 F 欄收入、H 欄備註、B 欄日期，比對 K:S；支援多單金額加總。"""
    log = _logger(ui_logger)
    ws = get_worksheet(region)
    sheet = memo.with_retry(ws.get_all_values)
    last_bank_row = max((i for i, row in enumerate(sheet, 1)
                         if len(row) >= 2 and str(row[1]).strip()), default=1)
    candidates = []
    for i, raw in enumerate(sheet, 1):
        if i <= last_bank_row or len(raw) < 19 or not str(raw[11]).strip():
            continue
        candidates.append({
            "source_row": i, "service_month": raw[10], "order_no": raw[11],
            "name": raw[12], "service_date": raw[13], "net_amount": _amount(raw[14]) or 0,
            "last5": raw[15], "service_category": raw[16], "service_detail": raw[17],
            "paid_at": raw[18],
        })
    used, updates, matched, matched_banks, review = set(), [], 0, 0, 0
    for bank_row in range(2, last_bank_row + 1):
        raw = sheet[bank_row - 1]
        income = _amount(raw[5] if len(raw) > 5 else "")  # F
        note = raw[7] if len(raw) > 7 else ""              # H
        bank_time = raw[1] if len(raw) > 1 else ""         # B
        if not income or (len(raw) > 11 and str(raw[11]).strip()):
            continue
        group = _find_group(income, note, bank_time, [c for c in candidates if c["order_no"] not in used])
        if not group:
            review += 1
            continue
        target_rows = list(range(bank_row, bank_row + len(group)))
        if any(r <= len(sheet) and any(str(v).strip() for v in sheet[r - 1][10:19]) for r in target_rows):
            review += 1
            continue
        if any(r != bank_row and r <= last_bank_row and any(str(v).strip() for v in sheet[r - 1][1:8]) for r in target_rows):
            review += 1
            log(f"第 {bank_row} 列為多訂單，但下方銀行列非空，留待人工確認")
            continue
        for target, candidate in zip(target_rows, group):
            updates.append({"range": f"K{target}:S{target}", "values": [[*_values(candidate)]]})
            updates.append({"range": f"K{candidate['source_row']}:S{candidate['source_row']}", "values": [[""] * 9]})
            used.add(candidate["order_no"])
            matched += 1
        matched_banks += 1
        log(f"第 {bank_row} 列配對 {len(group)} 筆，合計 {income}")
    if updates:
        memo.with_retry(ws.batch_update, updates, value_input_option="RAW")
    return {"matched_orders": matched, "matched_bank_rows": matched_banks, "review": review}
