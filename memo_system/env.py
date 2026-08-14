# atm.py
# -*- coding: utf-8 -*-
"""
ATM 對帳自動化模組

流程：
1. 從台北/台中 ATM Google Sheet（分頁名稱固定為「ATM」）讀取要處理的列號，取得 J 欄（訂單編號）
2. 用訂單編號去 https://backend.lemonclean.com.tw/purchase 搜尋，
   從頁面內嵌的 Vue purchaseList JSON 拿到該筆訂單的 purchase_id / 付款狀態等資訊
3. 依序執行：
   - 按「已付款」：GET /purchase/set_success/{purchase_id}
   - 按「開立發票」：GET /purchase/make_invoice/{purchase_id}
   - 按「發確認信」：GET /purchase/mail_success/{order_no}
4. 動作後重新查詢一次該筆訂單，把 P=對帳完成時間、Q=付款時間、R=發票號碼、S=發確認信、T=已更新系統 寫回 ATM Sheet

修正（2026-06）：
- _get_gspread_client() 把憑證初始化與 open_by_key 分開；
  原本的 try/except 會把 open_by_key 的權限錯誤也吞掉，
  導致 fallback 到本機 JSON 檔案，產生誤導性的 FileNotFoundError。
  現在只有「取得憑證」這步會 fallback，open_by_key 的錯誤會直接拋出。

修正（2026-07-07）：
- 新增 today_tw() / default_date_until_tw()：Streamlit Cloud 伺服器用 UTC
  時間，呼叫端（UI）原本如果是用 date.today() - timedelta(days=1) 算「查詢
  待付款清單，訂購日期迄＝前一天」，會拿到 UTC 的日期而不是台灣的日期。
  當台灣已經過了午夜、進入新的一天，但 UTC 還停在前一天時，這樣算出來的
  「前一天」就會多錯一天（例如台灣 7/7，卻算成 7/5，而不是預期的 7/6）。
  atm.py 本身不決定「查詢到前一天」這個預設值（是呼叫
  search_atm_unpaid_orders 的 UI 端決定的），所以請把 UI 端算 date_until
  預設值的地方，從 date.today() - timedelta(days=1) 改成
  atm.default_date_until_tw()。

修正（2026-07-07 之二）：
- search_atm_unpaid_orders 回傳的每筆資料新增 "line_url"（從 purchaseList
  內嵌 JSON 的 member.line 直接取得，不用另外爬頁面）。paste_atm_unpaid_list
  現在會把這個網址額外寫進 H 欄（跟 I~L 同一列），Google Sheets 會自動把
  純網址變成可點擊連結；姓名（K欄）本身維持純文字不變。

修正（2026-07-08）：
- ATM 對帳②「配對銀行明細」配合 H 欄 LINE 連結：候選資料移動與清空範圍
  從 I:O 改為 H:O，避免配對上移時漏搬或殘留 H 欄。

修正（2026-07-09）：
- ATM 對帳③「更新系統對帳」新增免開發票條件：J 欄訂單編號空白、
  訂單已有發票號碼、付款方式為儲值金、總金額扣除車馬費為 0。
- R 欄發票號碼只在本次真的執行「開立發票」且重新查到發票號碼時才回填，
  避免既有發票或免開發票訂單被誤寫回 ATM Sheet。
"""
import json
import os
import re
from datetime import datetime, timedelta, date as _date
from zoneinfo import ZoneInfo
from typing import Dict, List, Optional, Callable
from difflib import SequenceMatcher

import gspread
from google.oauth2.service_account import Credentials

from . import memo


# -----------------------------------------------------------------------------
# Config
# -----------------------------------------------------------------------------
ATM_SHEET_IDS = {
    "台北": "1bNcJuFuP--jdpNo2zJKOpvuq-5rSHW3LgGE8HEepf44",
    "台中": "1AlsgBL7uAooiU8hb0v-02J2MdBgDVJtGHgvD3U84hCM",
}

ATM_WORKSHEET_TITLE = "ATM"

COL_ORDER_NO = 10
COL_RECONCILED_AT = 16  # P
COL_PAID_AT = 17        # Q
COL_INVOICE_NO = 18     # R
COL_MAIL_STATUS = 19    # S
COL_RECON_STATUS = 20   # T


def make_logger(ui_logger: Optional[Callable[[str], None]] = None):
    def _log(msg: str):
        msg = str(msg)
        print(msg, flush=True)
        if ui_logger:
            ui_logger(msg)
    return _log


def _now_text() -> str:
    return datetime.now(ZoneInfo("Asia/Taipei")).strftime("%Y/%m/%d %H:%M:%S")


def today_tw() -> _date:
    """
    v2026-07-07 新增：用台灣時區算「今天」，取代 date.today()
    （date.today() 在 Streamlit Cloud 上是 UTC 時間，比台灣慢 8 小時，
    午夜到早上 8 點之間會誤判成前一天）。
    """
    return datetime.now(ZoneInfo("Asia/Taipei")).date()


def default_date_until_tw(days_back: int = 1) -> str:
    """
    v2026-07-07 新增：查詢 ATM 待付款清單時，UI 預設帶入的「訂購日期迄」
    （通常是「前一天」）要用這個函式算，不要用 date.today() - timedelta(...)。
    回傳格式為 YYYY-MM-DD 字串，直接餵給 search_atm_unpaid_orders 的
    date_until 參數。
    """
    return (today_tw() - timedelta(days=days_back)).strftime("%Y-%m-%d")


def _clear_data_validation(ws, row: int, col_start: int, col_end: int):
    try:
        sheet_id = ws.id
        body = {
            "requests": [{
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": row - 1,
                        "endRowIndex": row,
                        "startColumnIndex": col_start - 1,
                        "endColumnIndex": col_end,
                    },
                    "cell": {"dataValidation": None},
                    "fields": "dataValidation",
                }
            }]
        }
        memo.with_retry(ws.spreadsheet.batch_update, body)
    except Exception:
        pass


def _copy_data_validation(ws, source_row: int, target_row: int, columns: List[int]):
    if not source_row or not target_row or source_row == target_row:
        return
    try:
        sheet_id = ws.id
        requests = []
        for col in columns:
            requests.append({
                "copyPaste": {
                    "source": {
                        "sheetId": sheet_id,
                        "startRowIndex": source_row - 1,
                        "endRowIndex": source_row,
                        "startColumnIndex": col - 1,
                        "endColumnIndex": col,
                    },
                    "destination": {
                        "sheetId": sheet_id,
                        "startRowIndex": target_row - 1,
                        "endRowIndex": target_row,
                        "startColumnIndex": col - 1,
                        "endColumnIndex": col,
                    },
                    "pasteType": "PASTE_DATA_VALIDATION",
                    "pasteOrientation": "NORMAL",
                }
            })
        if requests:
            memo.with_retry(ws.spreadsheet.batch_update, {"requests": requests})
    except Exception:
        pass


# -----------------------------------------------------------------------------
# Google Sheet
#
# 修正：把「取得憑證」和「開啟工作表」分開。
# 原本 get_atm_spreadsheet 把兩步都放在同一個 try/except 裡，
# 導致 gc.open_by_key() 的權限錯誤（例如服務帳號沒被加進台中 Sheet）
# 也被吞掉，fallback 去找本機 JSON 檔案，產生誤導性的 FileNotFoundError。
# 現在只有「取得憑證」這步會 fallback；open_by_key 的錯誤會直接拋出，
# 錯誤訊息會清楚說明是「403 Permission denied」。
# -----------------------------------------------------------------------------
def _get_gspread_client():
    """
    取得授權過的 gspread client。

    v2026.07.11：修正憑證讀取邏輯——原本只檢查 st.secrets["GOOGLE_SERVICE_
    ACCOUNT"]（大寫），但實際部署的 Streamlit secrets 是用小寫的
    "gcp_service_account" 這個 key，導致這裡一直取不到、默默失敗
    （except Exception: pass），接著 fallback 到根本不存在的本機檔案
    google_service_account.json，最後報出「[Errno 2] No such file or
    directory」這種看起來像是缺檔案、實際上是憑證 key 名稱查錯的誤導性
    錯誤訊息。
    改成跟 orders.py 的 get_service_account_info() 一致：依序檢查
    gcp_service_account（小寫）→ GOOGLE_SERVICE_ACCOUNT（大寫）→
    GOOGLE_SERVICE_ACCOUNT_JSON 環境變數 → 本機檔案，任何一種有設定
    都能正確讀到。
    """
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    service_account_info = None
    try:
        import streamlit as _st
        if "gcp_service_account" in _st.secrets:
            service_account_info = dict(_st.secrets["gcp_service_account"])
        elif "GOOGLE_SERVICE_ACCOUNT" in _st.secrets:
            service_account_info = dict(_st.secrets["GOOGLE_SERVICE_ACCOUNT"])
    except Exception:
        pass

    if service_account_info is None:
        raw_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
        if raw_json:
            service_account_info = json.loads(raw_json)

    if service_account_info is not None:
        creds = Credentials.from_service_account_info(service_account_info, scopes=scopes)
        return gspread.authorize(creds)

    creds = Credentials.from_service_account_file(
        memo.GOOGLE_SERVICE_ACCOUNT_FILE,
        scopes=scopes,
    )
    return gspread.authorize(creds)


def get_atm_spreadsheet(sheet_id: str):
    """
    開啟指定 Sheet ID 的 Google Spreadsheet。

    若服務帳號沒有該 Sheet 的存取權限，會拋出清楚的 APIError [403]，
    而不是誤觸 fallback 導致找不到本機 JSON 檔案的混淆錯誤。

    ⚠️ 台中工作表需要手動把服務帳號 email 加入共用者（編輯者權限）：
       服務帳號 email 可以在台北工作表的共用清單裡找到。
    """
    gc = _get_gspread_client()
    return gc.open_by_key(sheet_id)


def get_atm_worksheet(region: str):
    if region not in ATM_SHEET_IDS:
        raise ValueError(f"未知地區「{region}」，目前支援：{list(ATM_SHEET_IDS.keys())}")
    sh = get_atm_spreadsheet(ATM_SHEET_IDS[region])
    return sh.worksheet(ATM_WORKSHEET_TITLE)


# -----------------------------------------------------------------------------
# 解析 /purchase 頁面內嵌的 Vue purchaseList JSON
# -----------------------------------------------------------------------------
def extract_purchase_list_json(html: str) -> Optional[Dict]:
    idx = html.find("purchaseList:")
    if idx == -1:
        return None
    start = html.find("{", idx)
    if start == -1:
        return None

    depth = 0
    in_str = False
    esc = False
    i = start

    while i < len(html):
        c = html[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    raw = html[start:i + 1]
                    try:
                        return json.loads(raw)
                    except Exception:
                        return None
        i += 1

    return None


def find_purchase_by_order_no(session, order_no: str) -> Optional[Dict]:
    url = f"{memo.BASE_URL}/purchase"
    r = memo.session_get(session, url, params={"orderNo": order_no})
    r.raise_for_status()

    data = extract_purchase_list_json(r.text)
    if not data:
        return None

    for item in data.get("data", []):
        if str(item.get("order_no", "")).strip() == str(order_no).strip():
            return item

    items = data.get("data", [])
    return items[0] if items else None


# -----------------------------------------------------------------------------
# 三個後台動作
# -----------------------------------------------------------------------------
def mark_paid(session, purchase_id) -> bool:
    url = f"{memo.BASE_URL}/purchase/set_success/{purchase_id}"
    r = memo.session_get(session, url)
    r.raise_for_status()
    return True


def issue_invoice(session, purchase_id) -> bool:
    url = f"{memo.BASE_URL}/purchase/make_invoice/{purchase_id}"
    r = memo.session_get(session, url)
    r.raise_for_status()
    return True


def send_confirmation_mail(session, order_no: str) -> Dict:
    url = f"{memo.BASE_URL}/purchase/mail_success/{order_no}"
    r = memo.session_get(session, url)
    r.raise_for_status()
    try:
        return r.json()
    except Exception:
        return {}


# -----------------------------------------------------------------------------
# 主流程：更新系統對帳
# -----------------------------------------------------------------------------
def process_atm_rows(
    region: str,
    row_spec: str,
    do_mark_paid: bool = True,
    do_issue_invoice: bool = True,
    do_send_mail: bool = True,
    ui_logger=None,
    session=None,
) -> Dict:
    log = make_logger(ui_logger)
    result = {
        "processed": 0, "success": 0, "failed": 0,
        "skipped": 0, "errors": [],
    }

    row_nums = memo.parse_row_spec(row_spec)
    log(f"===== 開始處理 ATM 對帳（{region}）=====")
    log(f"列號：{row_nums}")

    ws = get_atm_worksheet(region)
    rows = memo.with_retry(ws.get_all_values)
    session = session or memo.login(ui_logger=ui_logger)

    for r in row_nums:
        try:
            if r - 1 >= len(rows):
                log(f"❌ 第{r}列：超出資料範圍")
                result["failed"] += 1
                result["errors"].append(f"第{r}列：超出資料範圍")
                continue

            row = rows[r - 1]
            order_no = memo.safe_cell(row, COL_ORDER_NO)
            recon_status = memo.safe_cell(row, COL_RECON_STATUS)

            if not order_no:
                log(f"⏭ 第{r}列：J欄沒有訂單編號，可能是非訂單收入，略過系統更新")
                result["skipped"] += 1
                continue

            if str(recon_status).strip() in ["需確認", "非訂單", "非訂單收入", "疑似拆單"]:
                log(f"⏭ 第{r}列：T欄狀態為「{recon_status}」，不執行系統更新")
                result["skipped"] += 1
                continue

            log(f"\n----- 第{r}列：訂單 {order_no} -----")

            purchase = find_purchase_by_order_no(session, order_no)
            if not purchase:
                msg = f"❌ 第{r}列（{order_no}）：在後台找不到這筆訂單"
                log(msg)
                result["failed"] += 1
                result["errors"].append(msg)
                continue

            purchase_id = purchase.get("purchase_id")
            log(f"找到 purchase_id={purchase_id}")

            updates = []
            invoice_issued_now = False

            if do_mark_paid:
                if purchase.get("purchase_status") == 1:
                    log("（已經是已付款狀態，略過按已付款）")
                else:
                    mark_paid(session, purchase_id)
                    log("✅ 已按下「已付款」")

            total = _to_int_amount(purchase.get("total")) or 0
            fare = _to_int_amount(purchase.get("fare")) or 0
            net_amount = total - fare
            payway = str(purchase.get("payway") or "").strip()
            invoice_no_before = str(purchase.get("invoice_no") or "").strip()

            skip_invoice_reason = ""
            if not order_no:
                skip_invoice_reason = "J欄訂單編號為空白"
            elif invoice_no_before:
                skip_invoice_reason = f"訂單已有發票號碼 {invoice_no_before}"
            elif payway == "4" or payway == "儲值金":
                skip_invoice_reason = "付款方式為儲值金"
            elif net_amount == 0:
                skip_invoice_reason = f"總金額{total} - 車馬費{fare} = 0"

            if do_issue_invoice:
                if skip_invoice_reason:
                    log(f"⏭ 略過開立發票：{skip_invoice_reason}")
                else:
                    issue_invoice(session, purchase_id)
                    invoice_issued_now = True
                    log("✅ 已按下「開立發票」")

            if do_send_mail:
                mail_resp = send_confirmation_mail(session, order_no)
                log(f"✅ 已發確認信，回應：{mail_resp}")

            if do_mark_paid or invoice_issued_now:
                purchase = find_purchase_by_order_no(session, order_no) or purchase

            paid_at = purchase.get("paid_at") or ""
            invoice_no = purchase.get("invoice_no") or ""

            updates.append((COL_RECONCILED_AT, _now_text()))
            if do_mark_paid and paid_at:
                updates.append((COL_PAID_AT, paid_at))
            # R 欄發票號碼只在「本次真的有執行開立發票」後才回填。
            # 已有發票、儲值金、總金額扣車馬費為 0 等略過開票情境，不寫 R 欄。
            if invoice_issued_now and invoice_no:
                updates.append((COL_INVOICE_NO, invoice_no))
            if do_send_mail:
                updates.append((COL_MAIL_STATUS, "已發送"))
            updates.append((COL_RECON_STATUS, "已更新系統"))

            _clear_data_validation(ws, r, COL_RECONCILED_AT, COL_RECON_STATUS)

            for col, value in updates:
                memo.with_retry(ws.update_cell, r, col, value)
                log(f"已寫回第{r}列 第{col}欄 = {value}")

            result["processed"] += 1
            result["success"] += 1

        except Exception as e:
            msg = f"❌ 第{r}列 失敗：{e}"
            log(msg)
            result["processed"] += 1
            result["failed"] += 1
            result["errors"].append(msg)

    log("\n===== ATM 對帳處理完成 =====")
    return result


# -----------------------------------------------------------------------------
# ATM Sheet 自動配對
# -----------------------------------------------------------------------------
def _to_int_amount(value) -> Optional[int]:
    s = str(value or "").strip()
    if not s:
        return None
    s = re.sub(r"[^0-9\-]", "", s)
    if not s or s == "-":
        return None
    try:
        return int(s)
    except Exception:
        return None


def _digits(value: str) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _norm_code(value: str) -> str:
    d = _digits(value)
    return d.lstrip("0") or ("0" if d else "")


def _bank_note_has_code(bank_note: str, customer_code: str) -> bool:
    note_digits = _digits(bank_note)
    code_digits = _digits(customer_code)
    if not note_digits or not code_digits:
        return False
    note_norm = _norm_code(note_digits)
    code_norm = _norm_code(code_digits)
    last5_norm = _norm_code(note_digits[-5:])
    last4_norm = _norm_code(note_digits[-4:])
    return (
        note_digits.endswith(code_digits)
        or note_norm.endswith(code_norm)
        or last5_norm == code_norm
        or last4_norm == code_norm
    )


def _note_matches_name(bank_note: str, customer_name: str) -> bool:
    note = str(bank_note or "").strip()
    name = str(customer_name or "").strip()
    if not note or not name:
        return False
    note_compact = re.sub(r"\s+", "", note)
    name_compact = re.sub(r"\s+", "", name)
    if not note_compact or not name_compact:
        return False
    return note_compact in name_compact or name_compact in note_compact


def _compact_text(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]", "", str(value or "")).lower()


def _similar_text(a: str, b: str, threshold: float = 0.72) -> bool:
    aa = _compact_text(a)
    bb = _compact_text(b)
    if not aa or not bb:
        return False
    if aa in bb or bb in aa:
        return True
    return SequenceMatcher(None, aa, bb).ratio() >= threshold


def _normalize_datetime_text(value: str) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _datetime_equals(a: str, b: str) -> bool:
    aa = _normalize_datetime_text(a)
    bb = _normalize_datetime_text(b)
    if not aa or not bb:
        return False
    n = min(len(aa), len(bb))
    if n < 12:
        return False
    return aa[:n] == bb[:n]


def _build_confirm_code(candidate: Dict) -> str:
    raw = str(candidate.get("last_code") or "").strip()
    return raw if raw else "需確認"


def _is_non_order_candidate(candidate: Dict) -> bool:
    order_no = str(candidate.get("order_no") or "").strip()
    name = str(candidate.get("name") or "").strip()
    amount = candidate.get("amount")
    service_type = str(candidate.get("service_type") or "").strip()
    fee_type = str(candidate.get("fee_type") or "").strip()
    return (not order_no) and bool(name) and amount is not None and bool(service_type or fee_type)


def _is_split_payment_candidate(income: int, candidate: Dict, note: str) -> bool:
    amount = candidate.get("amount")
    if amount is None or income is None:
        return False
    try:
        if int(income) >= int(amount):
            return False
    except Exception:
        return False
    if candidate.get("last_code") and _bank_note_has_code(note, candidate.get("last_code")):
        return True
    if _note_matches_name(note, candidate.get("name")) or _similar_text(note, candidate.get("name")):
        return True
    return False


def _format_match_text(year_month: str, service_type: str, fee_type: str, order_no: str, name: str) -> str:
    service_type = service_type or "清潔"
    fee_type = fee_type or "服務費用"
    return f"{year_month}-{service_type}-{fee_type},{order_no},{name}"


def auto_match_bank_rows(
    region: str,
    row_spec: str = "",
    overwrite_existing: bool = False,
    default_service_type: str = "清潔",
    default_fee_type: str = "服務費用",
    allow_review_prefill: bool = True,
    ui_logger=None,
) -> Dict:
    log = make_logger(ui_logger)
    result = {
        "processed": 0, "success": 0, "failed": 0, "skipped": 0,
        "updated_orders": 0, "ambiguous": 0, "unmatched": 0,
        "confirm_required": 0, "non_order": 0, "split_payment": 0,
        "errors": [],
    }

    ws = get_atm_worksheet(region)
    rows = memo.with_retry(ws.get_all_values)
    target_row_nums = memo.parse_row_spec(row_spec) if str(row_spec or "").strip() else []
    target_row_set = set(target_row_nums)
    log(f"===== 開始自動配對 ATM 銀行明細（{region}）=====")
    if target_row_nums:
        log(f"指定銀行列號：{target_row_nums}")
    else:
        log("未指定銀行列號，將掃描全部列")

    COL_BANK_TIME = 2
    COL_INCOME = 5
    COL_NOTE = 6
    COL_SUMMARY = 7
    COL_EXTRA = 8
    COL_MONTH = 9
    COL_MATCH_ORDER_NO = 10
    COL_NAME = 11
    COL_AMOUNT = 12
    COL_LAST_CODE = 13
    COL_SERVICE_TYPE = 14
    COL_FEE_TYPE = 15

    # 找 B 欄最後一列有資料的列號，待配對清單只從此列下方建立
    last_b_row = 0
    for idx, row in enumerate(rows, start=1):
        b_val = row[1] if len(row) > 1 else ""
        if str(b_val).strip():
            last_b_row = idx
    log(f"B 欄最後一列（銀行明細區）：第 {last_b_row} 列，待配對清單從第 {last_b_row + 1} 列起")

    candidates = []
    for idx, row in enumerate(rows, start=1):
        # 只從 B 欄最後一列下方找待配對清單，不回頭掃銀行明細區
        if idx <= last_b_row:
            continue
        order_no = memo.safe_cell(row, COL_MATCH_ORDER_NO)
        name = memo.safe_cell(row, COL_NAME)
        amount = _to_int_amount(memo.safe_cell(row, COL_AMOUNT))
        last_code = memo.safe_cell(row, COL_LAST_CODE)
        service_type = memo.safe_cell(row, COL_SERVICE_TYPE) or default_service_type
        fee_type = memo.safe_cell(row, COL_FEE_TYPE) or default_fee_type

        if amount is None:
            continue
        if not order_no and not (name and (service_type or fee_type)):
            continue

        candidates.append({
            "row": idx,
            "extra": memo.safe_cell(row, COL_EXTRA),
            "year_month": memo.safe_cell(row, COL_MONTH),
            "order_no": order_no,
            "name": name,
            "amount": amount,
            "last_code": last_code,
            "service_type": service_type,
            "fee_type": fee_type,
        })

    used_order_nos = set()
    matched_names = set()
    for row in rows:
        income = _to_int_amount(memo.safe_cell(row, COL_INCOME))
        order_no = memo.safe_cell(row, COL_MATCH_ORDER_NO)
        name_val = memo.safe_cell(row, COL_NAME)
        if income is not None and order_no:
            used_order_nos.add(order_no)
            if name_val:
                matched_names.add(_compact_text(name_val))

    log(f"可配對候選訂單：{len(candidates)} 筆")

    for idx, row in enumerate(rows, start=1):
        try:
            if target_row_set and idx not in target_row_set:
                continue

            income = _to_int_amount(memo.safe_cell(row, COL_INCOME))
            bank_time = memo.safe_cell(row, COL_BANK_TIME)
            note = memo.safe_cell(row, COL_NOTE)
            current_order_no = memo.safe_cell(row, COL_MATCH_ORDER_NO)

            if income is None:
                continue

            result["processed"] += 1

            if current_order_no and not overwrite_existing:
                result["skipped"] += 1
                log(f"⏭ 第{idx}列：已有訂單 {current_order_no}，略過")
                continue

            amount_candidates = [c for c in candidates if c["amount"] == income]
            if not overwrite_existing:
                amount_candidates = [c for c in amount_candidates if (not c["order_no"]) or c["order_no"] not in used_order_nos or c["order_no"] == current_order_no]

            split_candidates = [c for c in candidates if _is_split_payment_candidate(income, c, note)]
            code_matches = [c for c in amount_candidates if c["last_code"] and _bank_note_has_code(note, c["last_code"])]
            name_matches = [c for c in amount_candidates if _note_matches_name(note, c["name"])]

            match_type = ""
            matches = []
            needs_confirm = False

            if len(code_matches) == 1:
                matches = code_matches; match_type = "末碼+金額"
            elif len(code_matches) > 1:
                matches = code_matches; match_type = "末碼+金額"
            elif len(name_matches) == 1:
                matches = name_matches; match_type = "備註姓名+金額"
            elif len(name_matches) > 1:
                matches = name_matches; match_type = "備註姓名+金額"
            elif len(split_candidates) == 1:
                matches = [dict(split_candidates[0], split_reason="疑似拆單")]
                match_type = "疑似拆單"; needs_confirm = True
            elif len(split_candidates) > 1:
                matches = [dict(c, split_reason="疑似拆單") for c in split_candidates]
                match_type = "疑似拆單"; needs_confirm = True
            else:
                matches = []

            if not matches and allow_review_prefill:
                review_matches = []
                for c in amount_candidates:
                    reasons = []
                    if _datetime_equals(c.get("last_code", ""), bank_time):
                        reasons.append("M欄日期時間=B欄")
                    if _similar_text(note, c.get("name", "")):
                        reasons.append("F欄與K欄姓名相近")
                    if reasons:
                        cc = dict(c)
                        cc["review_reasons"] = reasons
                        review_matches.append(cc)

                if len(review_matches) == 1:
                    matches = review_matches
                    match_type = "需確認候選：" + "、".join(review_matches[0].get("review_reasons", []))
                    needs_confirm = True
                elif len(review_matches) > 1:
                    matches = review_matches
                    match_type = "需確認候選"

            if len(matches) == 1:
                c = matches[0]
                evidence_ok = (
                    str(match_type).startswith("末碼+金額")
                    or str(match_type).startswith("備註姓名+金額")
                    or "F欄與K欄姓名相近" in str(match_type)
                    or "M欄日期時間=B欄" in str(match_type)
                    or str(match_type).startswith("疑似拆單")
                )
                if not evidence_ok:
                    text = f"待人工確認：同金額候選 {c.get('order_no') or '-'} {c.get('name')}，但缺少末碼/姓名/時間依據"
                    result["unmatched"] += 1
                    result["failed"] += 1
                    result["errors"].append(f"第{idx}列：{text}")
                    log(f"❌ 第{idx}列：{text}")
                    continue

                summary = _format_match_text(c["year_month"], c["service_type"], c["fee_type"], c["order_no"], c["name"])
                is_non_order = _is_non_order_candidate(c)
                is_split = str(match_type).startswith("疑似拆單") or bool(c.get("split_reason"))

                if is_non_order:
                    needs_confirm = True; status_text = "非訂單收入"
                    display_last_code = _build_confirm_code(c)
                elif is_split:
                    needs_confirm = True; status_text = "疑似拆單"
                    display_last_code = _build_confirm_code(c)
                elif needs_confirm:
                    status_text = "需確認"
                    display_last_code = _build_confirm_code(c)
                else:
                    status_text = "已配對"
                    display_last_code = c["last_code"]

                values = [[c.get("extra", ""), c["year_month"], c["order_no"], c["name"], c["amount"], display_last_code, c["service_type"], c["fee_type"]]]
                source_row = int(c.get("row") or 0)

                _copy_data_validation(ws, source_row, idx, [COL_EXTRA, COL_MONTH, COL_SERVICE_TYPE, COL_FEE_TYPE])
                memo.with_retry(ws.update, f"H{idx}:O{idx}", values, value_input_option="RAW")
                _clear_data_validation(ws, idx, COL_RECONCILED_AT, COL_RECONCILED_AT)
                _clear_data_validation(ws, idx, COL_RECON_STATUS, COL_RECON_STATUS)
                memo.with_retry(ws.update_cell, idx, COL_RECONCILED_AT, _now_text())
                memo.with_retry(ws.update_cell, idx, COL_RECON_STATUS, status_text)

                if source_row and source_row != idx:
                    _copy_data_validation(ws, idx, source_row, [COL_EXTRA, COL_MONTH, COL_SERVICE_TYPE, COL_FEE_TYPE])
                    memo.with_retry(ws.update, f"H{source_row}:O{source_row}", [["", "", "", "", "", "", "", ""]], value_input_option="RAW")
                    _copy_data_validation(ws, idx, source_row, [COL_EXTRA, COL_MONTH, COL_SERVICE_TYPE, COL_FEE_TYPE])
                    _clear_data_validation(ws, source_row, COL_RECON_STATUS, COL_RECON_STATUS)
                    memo.with_retry(ws.update_cell, source_row, COL_RECON_STATUS, "")
                    log(f"↳ 已從下方待配對列表移除原候選列第{source_row}列 H:O 與 T")

                if needs_confirm:
                    result["confirm_required"] += 1
                    if is_non_order:
                        result["non_order"] += 1
                    if is_split:
                        result["split_payment"] += 1
                    result["errors"].append(f"第{idx}列：已預填需確認 {status_text} {c['order_no'] or '-'} {c['name']}（{match_type}）")
                    log(f"⚠️ 第{idx}列：已預填需使用者確認 → {c['order_no'] or '-'} {c['name']} ${c['amount']}（{status_text}／{match_type}）")
                else:
                    log(f"✅ 第{idx}列：{match_type} → {c['order_no']} {c['name']} ${c['amount']}")

                if c["order_no"]:
                    used_order_nos.add(c["order_no"])
                result["success"] += 1
                result["updated_orders"] += 1

            elif len(matches) > 1:
                text = "多筆候選：" + "、".join(f"{c.get('order_no') or '-'} {c.get('name')}" for c in matches[:5])
                result["ambiguous"] += 1
                result["failed"] += 1
                result["errors"].append(f"第{idx}列：{text}")
                log(f"⚠️ 第{idx}列：{text}")

            else:
                if len(amount_candidates) > 1:
                    text = f"待人工確認：同金額候選 {len(amount_candidates)} 筆，但缺少末碼/姓名/時間依據"
                elif len(amount_candidates) == 1:
                    c = amount_candidates[0]
                    text = f"待人工確認：同金額候選 {c.get('order_no') or '-'} {c['name']}，但缺少末碼/姓名/時間依據"
                else:
                    text = "待人工確認"
                result["unmatched"] += 1
                result["failed"] += 1
                result["errors"].append(f"第{idx}列：{text}")
                log(f"❌ 第{idx}列：{text}")

        except Exception as e:
            msg = f"❌ 第{idx}列配對失敗：{e}"
            log(msg)
            result["failed"] += 1
            result["errors"].append(msg)

    log("===== 自動配對完成 =====")
    return result


# -----------------------------------------------------------------------------
# 待付款清單查詢
# -----------------------------------------------------------------------------
def search_atm_unpaid_orders(session, date_until: Optional[str] = None, ui_logger=None) -> List[Dict]:
    """
    v2026-07-07 修正：date_until 改成可選參數，沒有傳入時自動用
    default_date_until_tw()（台灣時區的前一天）當預設值，不再依賴呼叫端
    自己算「前一天」——避免呼叫端用 date.today() - timedelta(1)（在
    Streamlit Cloud 上是 UTC 時間）算出差一天的錯誤日期。
    """
    if not date_until:
        date_until = default_date_until_tw()
    log = make_logger(ui_logger)
    url = f"{memo.BASE_URL}/purchase"
    params = {
        "keyword": "", "name": "", "phone": "", "orderNo": "",
        "date_s": "", "date_e": date_until,
        "clean_date_s": "", "clean_date_e": "",
        "paid_at_s": "", "paid_at_e": "",
        "refundDateS": "", "refundDateE": "",
        "buy": "", "buy_item": "", "area_id": "",
        "isCharge": "", "isRefund": "",
        "payway": "2",          # ATM
        "purchase_status": "0", # 待付款
        "progress_status": "", "invoiceStatus": "", "otherFee": "",
        "orderBy": "",
        "p_board": "on",        # 訂單統計表
    }

    log(f"===== 查詢 ATM 待付款名單（訂購日期迄：{date_until}）=====")
    r = memo.session_get(session, url, params=params)
    r.raise_for_status()

    data = extract_purchase_list_json(r.text)
    if not data:
        log("⚠️ 找不到訂單統計表的內嵌資料（頁面結構可能改變，或查無資料）")
        return []

    items = data.get("data", [])
    log(f"查到 {len(items)} 筆待付款 ATM 訂單")

    rows = []
    for item in items:
        date_clean = str(item.get("date_clean") or "")
        year_month = date_clean[:7].replace("-", ".") if len(date_clean) >= 7 else ""
        order_no = item.get("order_no", "")
        name = item.get("name", "")
        total = item.get("total") or 0
        fare = item.get("fare") or 0
        net_amount = total - fare
        # v2026-07-07 新增：purchaseList 內嵌 JSON 裡的 member 物件本來就有
        # "line" 這個欄位（會員的 LINE 聊天連結網址），不用另外爬頁面，
        # 直接從這裡取出來給 UI 端用（例如把姓名做成可點擊的 LINE 連結）。
        line_url = str((item.get("member") or {}).get("line") or "")

        rows.append({
            "year_month": year_month,
            "order_no": order_no,
            "name": name,
            "total": total,
            "fare": fare,
            "net_amount": net_amount,
            "line_url": line_url,
        })
        log(f"  - {year_month}　{order_no}　{name}　總金額{total} - 車馬費{fare} = {net_amount}")

    return rows


def paste_atm_unpaid_list(region: str, rows: List[Dict], ui_logger=None) -> Dict:
    log = make_logger(ui_logger)
    result = {"pasted": 0, "start_row": None, "errors": []}

    if not rows:
        log("沒有資料可以貼")
        return result

    ws = get_atm_worksheet(region)
    all_values = memo.with_retry(ws.get_all_values)

    last_b_row = 0
    for idx, row in enumerate(all_values, start=1):
        b_val = row[1] if len(row) > 1 else ""
        if str(b_val).strip():
            last_b_row = idx

    start_row = last_b_row + 5

    def block_has_data(row_num: int) -> bool:
        if row_num - 1 >= len(all_values):
            return False
        row = all_values[row_num - 1]
        for col_idx in range(8, 13):  # I~M：0-based index 8~12
            if len(row) > col_idx and str(row[col_idx]).strip():
                return True
        return False

    while block_has_data(start_row):
        log(f"第 {start_row} 列的 I~L 欄已經有資料，往下移 5 列")
        start_row += 5

    updates = []
    for i, r in enumerate(rows):
        row_num = start_row + i
        updates.append({
            "range": f"I{row_num}:L{row_num}",
            "values": [[r["year_month"], r["order_no"], r["name"], r["net_amount"]]],
        })
        # v2026-07-07：LINE 聊天連結網址另外寫進 H 欄（純網址，Google Sheets
        # 貼上/寫入後會自動變成可點擊連結；不能跟姓名塞在同一格）。
        if r.get("line_url"):
            updates.append({
                "range": f"H{row_num}",
                "values": [[r["line_url"]]],
            })

    memo.with_retry(ws.batch_update, updates, value_input_option="RAW")

    result["pasted"] = len(rows)
    result["start_row"] = start_row
    log(f"✅ 已從第 {start_row} 列開始，貼上 {len(rows)} 筆資料到 I~L 欄")

    return result
