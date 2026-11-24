# -*- coding: utf-8 -*-
"""付款後 5 碼／星和診所對帳；刻意與 atm.py 完全分離。"""
import json
import os
import re
import unicodedata
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
    """與 ATM 同一個分頁：依年度根目錄找檔（不讀 secrets 的試算表 ID／GID）。"""
    from .atm import _atm_sheet_config

    return _atm_sheet_config(region)


def get_worksheet(region: str):
    from .atm import find_atm_tab

    config = _sheet_config(region)
    return find_atm_tab(_client().open_by_key(config["spreadsheet_id"]), region)


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


# -----------------------------------------------------------------------------
# 工作表欄位（2026-11-15 Jenny：照「富邦ATM」／高雄「ATM」分頁實際欄位）
#   E＝存入金額；桃園／新竹 B＝交易時間、F＝附註；高雄 A＝交易時間、G＝帳號／備註
#   I＝服務年月 J＝訂單編號 K＝姓名 L＝金額 M＝後5碼 N＝服務類別 O＝服務細項／費用
#   查詢結果維持貼在銀行明細下方 K:S（K 年月 L 訂單編號 M 姓名 N 服務日期 O 金額
#   P 後5碼 Q 類別 R 細項 S 付款時間）；銀行列依 J 欄訂單編號對應 K:S 的 L 欄
#   P＝銀行列配不到時寫「待確認：原因」
# -----------------------------------------------------------------------------
COL_INCOME = 5   # E
COL_I = 9        # I
COL_J = 10       # J
COL_REVIEW = 16  # P
REVIEW_PREFIX = "待確認："


def _bank_columns(region: str) -> Dict[str, int]:
    if region == "高雄":
        return {"time": 1, "note": 7}
    return {"time": 2, "note": 6}


def _cell(row: List, col: int) -> str:
    return str(row[col - 1]).strip() if len(row) >= col else ""


def _last_bank_row(sheet: List[List]) -> int:
    """銀行明細最後一列：A 或 B 欄有資料（下方 G/I 欄可能有空公式，不算）。"""
    return max((i for i, row in enumerate(sheet, 1) if _cell(row, 1) or _cell(row, 2)), default=1)


def _values(row: Dict) -> List:
    """貼到待比對區 K:S 的值。"""
    return [row[key] for key in (
        "service_month", "order_no", "name", "service_date", "net_amount",
        "last5", "service_category", "service_detail", "paid_at",
    )]


# N/O 依 ATM 工作表下拉選單的寫法：N＝清潔、O＝服務費用（家電／水洗訂單 N 為「家電」／「水洗」）
# 2026-11-15 Jenny：高雄先改；2026-11-25 Jenny：ATM 待付款填入 ATM 工作表時，所有地區一律 N 清潔、O 服務費用
SHEET_CATEGORY = {"居家清潔": "清潔", "家電清潔": "家電", "水洗清潔": "水洗"}
SHEET_FEE = "服務費用"
KAOHSIUNG_CATEGORY, KAOHSIUNG_FEE = SHEET_CATEGORY, SHEET_FEE  # 舊名相容


def _sheet_values(row: Dict, region: str = "") -> Dict[str, List]:
    """依訂單編號覆蓋銀行列：I 與 K:O（N/O 一律用下拉選單的值，不分地區）。"""
    category, detail = SHEET_CATEGORY.get(row["service_category"], "清潔"), SHEET_FEE
    return {
        "I": [row["service_month"]],
        "K:O": [row["name"], row["net_amount"], row["last5"], category, detail],
    }


def paste_orders(region: str, rows: List[Dict], ui_logger=None) -> Dict:
    """從銀行明細最後一列下方 5 列開始，貼到 K:S 待比對區。"""
    log = _logger(ui_logger)
    rows = [row for row in rows if _money(row.get("net_amount")) != 0]
    if not rows:
        log("沒有非零淨額的資料可以貼入 K:S")
        return {"pasted": 0, "start_row": None}
    ws = get_worksheet(region)
    values = memo.with_retry(ws.get_all_values)
    start = _last_bank_row(values) + 5
    while start <= len(values) and any(str(v).strip() for v in values[start - 1][10:19]):
        start += 1
    payload = [_values(row) for row in rows]
    end = start + len(payload) - 1
    if end > int(getattr(ws, "row_count", 0) or len(values)):
        memo.with_retry(ws.add_rows, end - int(getattr(ws, "row_count", 0) or len(values)))
    memo.with_retry(ws.update, f"K{start}:S{end}", payload, value_input_option="RAW")
    log(f"已貼上 {len(payload)} 筆至 K{start}:S{end}")
    return {"pasted": len(payload), "start_row": start}


def _amount(value) -> Optional[int]:
    text = re.sub(r"[^0-9.-]", "", str(value or ""))
    try:
        return int(round(float(text))) if text else None
    except ValueError:
        return None


def _date(value: str) -> Optional[datetime]:
    """支援「2026/11/9 23:02:12」「2026-11-05 15:05」等不補零格式。"""
    m = re.search(r"(\d{4})\D(\d{1,2})\D(\d{1,2})(?:\D+(\d{1,2}):(\d{2})(?::(\d{2}))?)?", str(value or ""))
    if not m:
        return None
    try:
        return datetime(*(int(g) for g in m.groups(default="0")))
    except ValueError:
        return None


def _norm_note(note: str) -> str:
    return re.sub(r"\s", "", unicodedata.normalize("NFKC", str(note or "")))


def _identity_match(note: str, row: Dict) -> bool:
    compact = _norm_note(note)
    code = re.sub(r"\D", "", row.get("last5", ""))
    return bool((code and re.sub(r"\D", "", compact).endswith(code))
                or (row["name"] and row["name"] in compact)
                or row["name"] == STAR_CLINIC and STAR_CLINIC in compact)


def _find_group(income: int, note: str, bank_time: str, candidates: List[Dict]):
    """回傳 (符合的訂單, 配不到的原因)。"""
    bank_dt = _date(bank_time)
    eligible = []
    for row in candidates:
        if not _identity_match(note, row):
            continue
        paid_dt = _date(row["paid_at"])
        if bank_dt and paid_dt and paid_dt < bank_dt.replace(second=0):
            continue
        eligible.append(row)
    if not eligible:
        return [], "備註沒有姓名或後5碼"
    eligible.sort(key=lambda row: (_date(row["paid_at"]) or datetime.max, row["order_no"]))
    for size in range(1, min(8, len(eligible)) + 1):
        groups = [group for group in combinations(eligible, size)
                  if sum(row["net_amount"] for row in group) == income]
        if len(groups) == 1:
            return list(groups[0]), ""
        if len(groups) > 1:
            return [], "多組金額相同"
    names = "、".join(sorted({row["name"] for row in eligible}))
    return [], f"姓名／後5碼相符（{names}），但金額加總不符"


def match_bank_rows(region: str, ui_logger=None, rows: Optional[List[Dict]] = None) -> Dict:
    """① J 欄已有訂單編號的列：依 J 對應下方 K:S（L 欄訂單編號），一律覆蓋 I、K:O。
    ② J 欄空白、E 欄有收入的列：以收入金額＋備註（姓名／後5碼）＋時間比對，支援多單加總。
    配不到的列在執行紀錄逐列寫原因，並在 P 欄標「待確認：原因」。"""
    log = _logger(ui_logger)
    cols = _bank_columns(region)
    ws = get_worksheet(region)
    sheet = memo.with_retry(ws.get_all_values)
    last_bank_row = _last_bank_row(sheet)
    candidates = {}
    for i, raw in enumerate(sheet, 1):
        order_no = _cell(raw, 12)  # K:S 的 L 欄
        if i <= last_bank_row or not order_no or order_no in candidates:
            continue
        candidates[order_no] = {
            "source_row": i, "service_month": _cell(raw, 11), "order_no": order_no,
            "name": _cell(raw, 13), "service_date": _cell(raw, 14),
            "net_amount": _amount(_cell(raw, 15)) or 0, "last5": _cell(raw, 16),
            "service_category": _cell(raw, 17), "service_detail": _cell(raw, 18), "paid_at": _cell(raw, 19),
        }
    # 畫面上剛查到的訂單也直接當候選（不必先貼到 K:S）；同一訂單以 K:S 已貼的為準
    from_search = 0
    for row in rows or []:
        order_no = str(row.get("order_no") or "").strip()
        if not order_no or order_no in candidates or _money(row.get("net_amount")) == 0:
            continue
        candidates[order_no] = {
            "source_row": None, "service_month": row.get("service_month", ""), "order_no": order_no,
            "name": row.get("name", ""), "service_date": row.get("service_date", ""),
            "net_amount": _money(row.get("net_amount")), "last5": str(row.get("last5") or ""),
            "service_category": row.get("service_category", ""), "service_detail": row.get("service_detail", ""),
            "paid_at": row.get("paid_at", ""),
        }
        from_search += 1
    log(f"銀行明細到第 {last_bank_row} 列；待比對訂單 {len(candidates)} 筆"
        f"（K:S {len(candidates) - from_search} 筆、畫面查詢結果 {from_search} 筆）")
    if not candidates:
        log("⚠️ 沒有待比對訂單：請先搜尋付款訂單（或貼到 K:S）再比對")

    used, updates = set(), []
    result = {"updated_by_order": 0, "matched_orders": 0, "matched_bank_rows": 0, "review": 0, "review_rows": []}

    def write_order(target: int, candidate: Dict):
        vals = _sheet_values(candidate, region)
        updates.append({"range": f"I{target}", "values": [vals["I"]]})
        updates.append({"range": f"J{target}", "values": [[candidate["order_no"]]]})
        updates.append({"range": f"K{target}:O{target}", "values": [vals["K:O"]]})
        if _cell(sheet[target - 1], COL_REVIEW).startswith(REVIEW_PREFIX):
            updates.append({"range": f"P{target}", "values": [[""]]})
        used.add(candidate["order_no"])

    # ① 依 J 欄訂單編號覆蓋
    for bank_row in range(2, last_bank_row + 1):
        order_no = _cell(sheet[bank_row - 1], COL_J)
        if not order_no:
            continue
        candidate = candidates.get(order_no)
        if not candidate:
            continue
        write_order(bank_row, candidate)
        result["updated_by_order"] += 1
    if result["updated_by_order"]:
        log(f"依 J 欄訂單編號覆蓋 I、K:O：{result['updated_by_order']} 列")

    # ② J 欄空白的收入列
    for bank_row in range(2, last_bank_row + 1):
        raw = sheet[bank_row - 1]
        income = _amount(_cell(raw, COL_INCOME))
        if not income or income <= 0 or _cell(raw, COL_J):
            continue
        note = _cell(raw, cols["note"])
        bank_time = _cell(raw, cols["time"])
        group, reason = _find_group(income, note, bank_time,
                                    [c for c in candidates.values() if c["order_no"] not in used])
        if group:
            target_rows = list(range(bank_row, bank_row + len(group)))
            for r in target_rows[1:]:
                below = sheet[r - 1] if r <= len(sheet) else []
                if (r > last_bank_row or _cell(below, COL_J) or _cell(below, COL_INCOME)
                        or _cell(below, cols["time"]) != bank_time):
                    reason = f"{len(group)} 筆訂單加總，但下方列非空（需 {len(group) - 1} 列同時間、無收入的續列）"
                    group = []
                    break
        if not group:
            text = f"{REVIEW_PREFIX}{reason}"
            log(f"第 {bank_row} 列｜{income:,}｜{note.replace(chr(10), ' ')}｜{reason}")
            updates.append({"range": f"P{bank_row}", "values": [[text]]})
            result["review"] += 1
            result["review_rows"].append({"row": bank_row, "amount": income, "note": note, "reason": reason})
            continue
        for target, candidate in zip(target_rows, group):
            write_order(target, candidate)
            result["matched_orders"] += 1
        result["matched_bank_rows"] += 1
        log(f"第 {bank_row} 列配對 {len(group)} 筆，合計 {income:,}")

    # 已寫到銀行列的訂單，從下方待比對區移除
    for candidate in candidates.values():
        if candidate["order_no"] in used and candidate["source_row"]:
            updates.append({"range": f"K{candidate['source_row']}:S{candidate['source_row']}", "values": [[""] * 9]})
    if updates:
        memo.with_retry(ws.batch_update, updates, value_input_option="RAW")
    return result
