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

修正（2026-07-21）：
- 支援一筆銀行收入由 2～5 筆訂單加總組成。只有金額總和相等、每筆都有
  末碼或姓名證據、且符合的組合唯一時才自動配對；多組可能或續列不足時
  保留人工確認，避免只靠金額誤配。

修正（2026-11-09）：
- 清潔異動「待退款」且退款方式為 ATM 時，同待收款寫入待配對區，L 欄負數、
  N/O＝清潔／退款（下拉選單由 ensure_candidate_row_format 套用）。
- ② 配對：負數候選列不參與收入配對；支出配對到同訂單清潔異動退款時，
  移除該筆負數候選列，避免重複。排程取消訂單複查略過負數列。
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
REGION_SECRET_PREFIX = {
    "台北": "TAIPEI",
    "台中": "TAICHUNG",
    "桃園": "TAOYUAN",
    "新竹": "HSINCHU",
    "高雄": "KAOHSIUNG",
}

ATM_WORKSHEET_TITLE = "ATM"

COL_ORDER_NO = 10
COL_BANK_TIME = 2       # B
COL_BANK_INCOME = 5     # E
COL_BANK_NOTE = 6       # F
COL_CUSTOMER_NAME = 11  # K
COL_ORDER_AMOUNT = 12   # L
COL_STATUS_NOTE = 13    # M
COL_RECONCILED_AT = 16  # P
COL_PAID_AT = 17        # Q
COL_INVOICE_NO = 18     # R
COL_MAIL_STATUS = 19    # S
COL_RECON_STATUS = 20   # T
COL_MOVE_WITH_MATCH = 21  # U：配對時隨訂單資料一併上移


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


def default_date_until_tw(days_back: int = 0) -> str:
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

    if service_account_info is None:  # 部署端（例如 tool-system 排程）提供的服務帳號
        from . import host
        service_account_info = host.lookup_service_account()

    if service_account_info is not None:
        creds = Credentials.from_service_account_info(service_account_info, scopes=scopes)
        return gspread.authorize(creds)

    try:
        from accounts import GOOGLE_SERVICE_ACCOUNT_FILE as local_credentials_file
    except Exception:
        local_credentials_file = ""
    credentials_file = str(local_credentials_file or memo.GOOGLE_SERVICE_ACCOUNT_FILE).strip()
    from pathlib import Path
    credentials_path = Path(credentials_file).expanduser()
    if not credentials_path.is_absolute() and not credentials_path.is_file():
        from accounts import LOCAL_ACCOUNTS_FILE
        credentials_path = LOCAL_ACCOUNTS_FILE.parent / credentials_path
    creds = Credentials.from_service_account_file(
        str(credentials_path),
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


# 分頁依名稱找：「ATM」，沒有時用「富邦ATM」（桃園／新竹的支出明細檔）
ATM_TAB_TITLES = ("ATM", "富邦ATM")


def _atm_root_rule(region: str):
    """桃園／新竹的 ATM 在「名冊薪資」第 2 個檔（支出明細），其餘地區在「內勤工作表單」。"""
    return ("名冊薪資", 1) if region in ("桃園", "新竹") else ("內勤工作表單", 0)


def _atm_sheet_config(region: str) -> Dict:
    """ATM 一律依年度根目錄找當年度檔（不讀 secrets 的試算表 ID／GID）。"""
    if region not in REGION_SECRET_PREFIX:
        raise ValueError(f"未知地區「{region}」，目前支援：{list(REGION_SECRET_PREFIX.keys())}")
    from year_roots import root_file_id

    category, index = _atm_root_rule(region)
    spreadsheet_id = root_file_id(category, region, file_index=index)
    return {"spreadsheet_id": spreadsheet_id, "gid": None, "worksheet_title": ATM_WORKSHEET_TITLE}


def find_atm_tab(spreadsheet, region: str):
    """依名稱找 ATM 分頁；都找不到就報錯（不會改用第一個分頁）。"""
    by_title = {ws.title: ws for ws in spreadsheet.worksheets()}
    for title in ATM_TAB_TITLES:
        if title in by_title:
            return by_title[title]
    raise ValueError(
        f"「{region}」ATM 試算表「{spreadsheet.title}」找不到「{'」或「'.join(ATM_TAB_TITLES)}」分頁，請確認分頁名稱"
    )


def get_atm_worksheet(region: str):
    config = _atm_sheet_config(region)
    return find_atm_tab(get_atm_spreadsheet(config["spreadsheet_id"]), region)


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
    order_no = str(order_no or "").strip()
    if not order_no:
        return None
    url = f"{memo.BASE_URL}/purchase"
    r = memo.session_get(session, url, params={"orderNo": order_no})
    r.raise_for_status()

    data = extract_purchase_list_json(r.text)
    if not data:
        return None

    for item in data.get("data", []):
        if str(item.get("order_no", "")).strip() == order_no:
            return item

    # 絕不可在訂單編號沒有精確命中時拿搜尋結果第一筆代替，否則會更新錯單。
    return None


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
        # 逐筆結果（給排程寫行事曆）：completed＝完成對帳；no_invoice＝已付款但未開立發票
        "completed": [], "no_invoice": [],
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
            bank_values = [memo.safe_cell(row, col) for col in range(1, 7)]
            customer_name = memo.safe_cell(row, COL_CUSTOMER_NAME)
            sheet_order_amount = _to_int_amount(memo.safe_cell(row, COL_ORDER_AMOUNT))

            if not order_no:
                log(f"⏭ 第{r}列：J欄沒有訂單編號，可能是非訂單收入，略過系統更新")
                result["skipped"] += 1
                continue

            if not re.fullmatch(r"[A-Za-z]{2}\d{6,}", order_no):
                log(f"⏭ 第{r}列：J欄「{order_no}」不是有效訂單編號，略過系統更新")
                result["skipped"] += 1
                continue

            if not any(str(value).strip() for value in bank_values):
                log(f"⏭ 第{r}列：左側 A～F 沒有銀行明細，不執行付款、開票或寄信")
                result["skipped"] += 1
                continue

            if not customer_name or sheet_order_amount is None or sheet_order_amount <= 0:
                log(f"⏭ 第{r}列：J～L 訂單資料不完整，不執行付款、開票或寄信")
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
            if not purchase_id:
                raise ValueError(f"後台訂單 {order_no} 缺少 purchase_id，已停止")

            backend_order_no = str(purchase.get("order_no") or "").strip()
            if backend_order_no != order_no:
                raise ValueError(f"後台回傳訂單編號 {backend_order_no or '空白'}，與 J 欄 {order_no} 不一致")

            backend_total = _to_int_amount(purchase.get("total")) or 0
            backend_fare = _to_int_amount(purchase.get("fare")) or 0
            backend_net_amount = backend_total - backend_fare
            if backend_net_amount != sheet_order_amount:
                raise ValueError(
                    f"訂單 {order_no} 金額不一致：Sheet L欄={sheet_order_amount}，"
                    f"後台總金額扣車馬費={backend_net_amount}"
                )

            payway = str(purchase.get("payway") or "").strip()
            if payway != "2":
                raise ValueError(f"訂單 {order_no} 付款方式不是 ATM（後台 payway={payway or '空白'}）")
            raw_status = purchase.get("purchase_status")
            status_code = "" if raw_status is None else str(raw_status).strip()
            if status_code == "2":
                if memo.safe_cell(row, COL_STATUS_NOTE) != "取消訂單":
                    _clear_data_validation(ws, r, COL_STATUS_NOTE, COL_STATUS_NOTE)
                    memo.with_retry(ws.update_cell, r, COL_STATUS_NOTE, "取消訂單")
                log(f"⏭ 第{r}列（{order_no}）：後台狀態為「取消訂單」，不執行對帳動作，M欄已標註「取消訂單」")
                result["skipped"] += 1
                continue
            if status_code == "3":
                raise ValueError(f"訂單 {order_no} 後台狀態為「已退款」，禁止歸入對帳或重新標記已付款")
            if status_code not in {"0", "1"}:
                raise ValueError(f"訂單 {order_no} 後台付款狀態無法確認，已停止對帳")
            log(f"找到 purchase_id={purchase_id}")

            updates = []
            # 2026-11-06 Jenny：訂單本來就已付款時，千萬不要再發確認信
            pre_paid_at = str(purchase.get("paid_at") or "").strip()
            already_paid = status_code == "1" or bool(pre_paid_at and not pre_paid_at.startswith("0000"))
            send_mail = do_send_mail and not already_paid
            mail_note = ""  # 勾了發確認信卻沒發時寫進 S 欄的原因
            if do_send_mail and already_paid:
                mail_note = "原已付款，未發信"
                log("（訂單本來就已付款，不再發確認信）")
            invoice_missing_reason = ""

            if do_mark_paid:
                if str(purchase.get("purchase_status") or "") == "1":
                    log("（已經是已付款狀態，略過按已付款）")
                else:
                    mark_paid(session, purchase_id)
                    log("✅ 已按下「已付款」")

            # 所有後續動作都必須建立在「重新查詢同一訂單」後，後台確實回覆已付款
            # 且有付款時間；不可用本機時間或 Sheet 內容自行生成付款時間。
            if do_mark_paid:
                refreshed = find_purchase_by_order_no(session, order_no)
                if not refreshed:
                    raise ValueError(f"按已付款後無法重新查到同一訂單 {order_no}")
                purchase = refreshed

            paid_at = str(purchase.get("paid_at") or "").strip()
            is_paid = str(purchase.get("purchase_status") or "") == "1"
            if (do_mark_paid or do_issue_invoice or do_send_mail) and (not is_paid or not paid_at):
                raise ValueError(f"訂單 {order_no} 尚未由後台確認已付款及付款時間，禁止後續動作及 Sheet 回填")

            if do_issue_invoice:
                if purchase.get("invoice_no"):
                    log(f"（已有發票號碼 {purchase['invoice_no']}，略過開立發票）")
                else:
                    # 開立發票失敗不再整列中止：付款狀態照樣回寫，但不發確認信，並列入「未開立發票」
                    try:
                        issue_invoice(session, purchase_id)
                        log("✅ 已按下「開立發票」")
                    except Exception as exc:
                        invoice_missing_reason = f"開立發票失敗：{exc}"
                    refreshed = find_purchase_by_order_no(session, order_no)
                    if not refreshed:
                        raise ValueError(f"開立發票後無法重新查到同一訂單 {order_no}")
                    purchase = refreshed
                    if not str(purchase.get("invoice_no") or "").strip():
                        invoice_missing_reason = invoice_missing_reason or "後台尚未回覆發票號碼"
                        log(f"⚠️ 第{r}列（{order_no}）：未開立發票（{invoice_missing_reason}），不發確認信")
                        if send_mail:
                            mail_note = "未開發票，未發信"
                        send_mail = False

            # 2026-11-07 Jenny：只有「當日改成已付款」的訂單才發確認信
            if send_mail and _bank_date(paid_at) != today_tw():
                log(f"（付款時間 {paid_at} 不是今天，不發確認信）")
                mail_note = "非當日付款，未發信"
                send_mail = False

            if send_mail:
                mail_resp = send_confirmation_mail(session, order_no)
                log(f"✅ 已發確認信，回應：{mail_resp}")

            # 最後再精確查詢一次；Q/R 只能使用這筆系統訂單實際回傳的欄位。
            refreshed = find_purchase_by_order_no(session, order_no)
            if not refreshed:
                raise ValueError(f"完成動作後無法重新查到同一訂單 {order_no}")
            purchase = refreshed

            paid_at = str(purchase.get("paid_at") or "").strip()
            invoice_no = str(purchase.get("invoice_no") or "").strip()
            if str(purchase.get("purchase_status") or "").strip() != "1" or not paid_at:
                raise ValueError(f"訂單 {order_no} 最終狀態並非已付款，禁止寫回對帳完成")

            updates.append((COL_RECONCILED_AT, _now_text()))
            if paid_at:
                updates.append((COL_PAID_AT, paid_at))
            if invoice_no:
                updates.append((COL_INVOICE_NO, invoice_no))
            if send_mail:
                updates.append((COL_MAIL_STATUS, "已發送"))
            elif mail_note:
                updates.append((COL_MAIL_STATUS, mail_note))
            updates.append((COL_RECON_STATUS, "已更新系統（未開發票）" if invoice_missing_reason else "已更新系統"))

            _clear_data_validation(ws, r, COL_RECONCILED_AT, COL_RECON_STATUS)

            for col, value in updates:
                memo.with_retry(ws.update_cell, r, col, value)
                log(f"已寫回第{r}列 第{col}欄 = {value}")

            result["processed"] += 1
            result["success"] += 1
            detail = {
                "region": region, "row": r, "order_no": order_no, "name": customer_name,
                "amount": sheet_order_amount, "invoice_no": invoice_no,
                "already_paid": already_paid, "mail_sent": send_mail,
            }
            result["completed"].append(detail)
            if invoice_missing_reason:
                result["no_invoice"].append(dict(detail, reason=invoice_missing_reason))

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


def _candidate_has_bank_evidence(candidate: Dict, note: str) -> bool:
    """多訂單加總配對不可只靠金額；每筆至少要有末碼或姓名證據。"""
    return bool(
        (candidate.get("last_code") and _bank_note_has_code(note, candidate.get("last_code")))
        or _note_matches_name(note, candidate.get("name"))
        or _similar_text(note, candidate.get("name"))
    )


def _find_sum_combinations(
    income: int,
    candidates: List[Dict],
    note: str,
    max_orders: int = 5,
    max_results: int = 2,
) -> List[List[Dict]]:
    """找 2～max_orders 筆、加總等於收入的組合；找到兩組即可判定有歧義。"""
    eligible = [
        c for c in candidates
        if c.get("amount") is not None
        and 0 < int(c["amount"]) < int(income)
        and _candidate_has_bank_evidence(c, note)
    ]
    eligible.sort(key=lambda c: (int(c.get("amount") or 0), int(c.get("row") or 0)), reverse=True)
    results: List[List[Dict]] = []

    def search(start: int, chosen: List[Dict], total: int):
        if len(results) >= max_results:
            return
        if total == income:
            if len(chosen) >= 2:
                results.append(list(chosen))
            return
        if total > income or len(chosen) >= max_orders:
            return
        for pos in range(start, len(eligible)):
            amount = int(eligible[pos]["amount"])
            if total + amount > income:
                continue
            chosen.append(eligible[pos])
            search(pos + 1, chosen, total + amount)
            chosen.pop()
            if len(results) >= max_results:
                return

    search(0, [], 0)
    return results


def _format_match_text(year_month: str, service_type: str, fee_type: str, order_no: str, name: str) -> str:
    service_type = service_type or "清潔"
    fee_type = fee_type or "服務費用"
    return f"{year_month}-{service_type}-{fee_type},{order_no},{name}"


# -----------------------------------------------------------------------------
# 待配對列規則（2026-11-06 Jenny）
# 1. G 欄不得空白：G 是組合公式，沿用上方最近一列的公式。
# 3. N/O 在資料進 ATM 分頁時就填好（2026-11-07 Jenny）：
#    ① 待付款清單（後台訂單）→ 清潔／服務費用；
#    清潔異動填入 → 工具組 → 清潔／工具組，其他 → 清潔／異動費。
#    ② 配對直接沿用候選列的 N/O；舊資料 N/O 空白才補：有訂單 → 服務費用，無訂單 2000 → 新訓費。
# 4. I（以及 N、O）欄要和上方一樣是下拉選單：複製上方最近一列的資料驗證。
# -----------------------------------------------------------------------------
COL_G_SUMMARY = 7   # G
COL_I_MONTH = 9     # I
COL_N_SERVICE = 14  # N
COL_O_FEE = 15      # O
TRAINEE_FEE_AMOUNT = 2000
DROPDOWN_COLUMNS = [COL_I_MONTH, COL_N_SERVICE, COL_O_FEE]


UNPAID_SERVICE_FEE = ("清潔", "服務費用")


def change_order_service_fee(change_text: str = "") -> tuple:
    """清潔異動填入 ATM 的 N/O：工具組 → 清潔／工具組；其他 → 清潔／異動費。"""
    text = str(change_text or "")
    if "工具組" in text or "工具包" in text:
        return "清潔", "工具組"
    return "清潔", "異動費"


TRAINEE_SERVICE_FEE = ("清潔", "新訓費")


def default_service_fee(amount, order_no: str = "") -> tuple:
    """N/O 空白時的補值（2026-11-07 Jenny）：有訂單 → 清潔／服務費用；
    沒有訂單編號：2000 → 清潔／新訓費，其他金額 → 費用類別留空給人工確認。"""
    if str(order_no or "").strip():
        return UNPAID_SERVICE_FEE
    if _to_int_amount(amount) == TRAINEE_FEE_AMOUNT:
        return TRAINEE_SERVICE_FEE
    return "清潔", ""


def _fallback_g_formula(row: int) -> str:
    return f'=I{row}&"-"&N{row}&"-"&O{row}&","&J{row}&","&K{row}'


def _g_formulas(ws, upto_row: int) -> List[str]:
    """G1:G{upto_row} 的公式文字（不是計算結果）。"""
    try:
        values = memo.with_retry(ws.get, f"G1:G{upto_row}", value_render_option="FORMULA")
    except Exception:
        return []
    return [str(r[0]) if r else "" for r in (values or [])]


def _rows_with_validation(ws, columns: List[int], upto_row: int) -> Dict[int, set]:
    """每一欄有資料驗證（下拉選單）的列號集合。"""
    found: Dict[int, set] = {c: set() for c in columns}
    if upto_row <= 0:
        return found
    try:
        title = ws.title.replace("'", "''")
        lo, hi = min(columns), max(columns)
        a1 = f"'{title}'!{chr(64 + lo)}1:{chr(64 + hi)}{upto_row}"
        meta = ws.spreadsheet.fetch_sheet_metadata(params={
            "ranges": a1,
            "fields": "sheets(properties.sheetId,data(startRow,startColumn,rowData.values.dataValidation))",
        })
    except Exception:
        return found
    for sheet in meta.get("sheets", []):
        for block in sheet.get("data", []):
            start_row = int(block.get("startRow", 0))
            start_col = int(block.get("startColumn", 0))
            for r_off, row_data in enumerate(block.get("rowData", []) or []):
                for c_off, cell in enumerate(row_data.get("values", []) or []):
                    col = start_col + c_off + 1
                    if col in found and cell.get("dataValidation"):
                        found[col].add(start_row + r_off + 1)
    return found


def _nearest_above(rows: set, target: int) -> int:
    above = [r for r in rows if r < target]
    return max(above) if above else 0


def _nearest(rows: set, target: int, exclude: set = frozenset()) -> int:
    """上方最近一列；上方沒有就找下方最近一列。"""
    usable = {r for r in rows if r not in exclude and r != target}
    above = [r for r in usable if r < target]
    if above:
        return max(above)
    below = [r for r in usable if r > target]
    return min(below) if below else 0


def _copy_request(ws, source: int, target: int, col_start: int, col_end: int, paste_type: str) -> Dict:
    return {"copyPaste": {
        "source": {"sheetId": ws.id, "startRowIndex": source - 1, "endRowIndex": source,
                   "startColumnIndex": col_start - 1, "endColumnIndex": col_end},
        "destination": {"sheetId": ws.id, "startRowIndex": target - 1, "endRowIndex": target,
                        "startColumnIndex": col_start - 1, "endColumnIndex": col_end},
        "pasteType": paste_type, "pasteOrientation": "NORMAL",
    }}


def _month_text(value) -> str:
    """I 欄月份一律存成文字「YYYY.MM」。數字 2026.11／2026.1 → 2026.11／2026.10；日期序號 → 該日期年月。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return str(value or "").strip()
    if value > 20000:  # 日期序號（例 46327 = 2026-11-01）
        day = _date(1899, 12, 30) + timedelta(days=int(value))
        return f"{day:%Y.%m}"
    return f"{value:.2f}"


def _validation_rules(ws, columns: List[int], upto_row: int, log=None) -> Dict[int, Dict[int, Dict]]:
    """{欄: {列: 下拉選單規則}}。讀取失敗會寫進 LOG 並往上拋，不再默默當成「沒有下拉」。"""
    title = ws.title.replace("'", "''")
    lo, hi = min(columns), max(columns)
    a1 = f"'{title}'!{chr(64 + lo)}1:{chr(64 + hi)}{upto_row}"
    meta = memo.with_retry(ws.spreadsheet.fetch_sheet_metadata, params={
        "ranges": a1,
        "fields": "sheets(properties.sheetId,data(startRow,startColumn,rowData.values.dataValidation))",
    })
    found: Dict[int, Dict[int, Dict]] = {c: {} for c in columns}
    for sheet in meta.get("sheets", []):
        for block in sheet.get("data", []):
            start_row = int(block.get("startRow", 0))
            start_col = int(block.get("startColumn", 0))
            for r_off, row_data in enumerate(block.get("rowData", []) or []):
                for c_off, cell in enumerate(row_data.get("values", []) or []):
                    col = start_col + c_off + 1
                    if col in found and cell.get("dataValidation"):
                        found[col][start_row + r_off + 1] = cell["dataValidation"]
    return found


def _row_range(ws, row: int, col_start: int, col_end: int) -> Dict:
    return {"sheetId": ws.id, "startRowIndex": row - 1, "endRowIndex": row,
            "startColumnIndex": col_start - 1, "endColumnIndex": col_end}


def ensure_candidate_row_format(ws, target_rows: List[int], log=None) -> Dict:
    """每次寫入／移動 G:O 後呼叫（2026-11-07 Jenny：G 欄不得空白；I/N/O 固定下拉選單、格式一致）。

    1. 範本列＝最後一列 I、N、O 三欄都有下拉選單的列（沒有就用最後一列 I 有下拉的列）。
    2. 目標列：G:O 格式從範本列複製；I/N/O 下拉選單直接套用範本列的規則（不靠複製，確保一定有下拉）；
       I 欄數字格式固定文字，存成數字／日期的月份改寫成文字「YYYY.MM」。
    3. G 空白就複製範本列（或最近一列）的 G 公式。
    任何一步失敗都寫進 result["errors"]（畫面會顯示），並改用較保守的方式重試。
    """
    log = log or (lambda msg: None)
    result = {"g_filled": 0, "dropdown_copied": 0, "format_copied": 0, "month_fixed": 0,
              "template": 0, "errors": []}
    target_rows = sorted({int(r) for r in target_rows if r})
    if not target_rows:
        return result
    upto = max(max(target_rows), int(getattr(ws, "row_count", 0) or 0))

    try:
        rules = _validation_rules(ws, DROPDOWN_COLUMNS, upto, log)
    except Exception as exc:
        rules = {c: {} for c in DROPDOWN_COLUMNS}
        result["errors"].append(f"讀取 I/N/O 下拉選單失敗：{exc}")
        log(f"❌ 讀取 I/N/O 下拉選單失敗：{exc}")
    i_rows = set(rules[COL_I_MONTH])
    full_rows = i_rows & set(rules[COL_N_SERVICE]) & set(rules[COL_O_FEE])
    template = max(full_rows or i_rows or {0})
    result["template"] = template
    if not template:
        result["errors"].append("ATM 分頁找不到 I 欄有下拉選單的列可當範本")
        log("❌ ATM 分頁找不到 I 欄有下拉選單的列可當範本，請先手動設定一列（I、N、O 下拉選單）")
    else:
        log(f"G:O 範本列：第{template}列")

    fmt_requests, dv_requests, text_requests, g_requests = [], [], [], []
    for row in target_rows:
        if template and row != template:
            fmt_requests.append(_copy_request(ws, template, row, COL_G_SUMMARY, COL_O_FEE, "PASTE_FORMAT"))
            missing = False
            for col in DROPDOWN_COLUMNS:
                rule = rules[col].get(template)
                if rule and rules[col].get(row) != rule:
                    dv_requests.append({"setDataValidation": {"range": _row_range(ws, row, col, col), "rule": rule}})
                    missing = True
            if missing:
                result["dropdown_copied"] += 1
        text_requests.append({"repeatCell": {
            "range": _row_range(ws, row, COL_I_MONTH, COL_I_MONTH),
            "cell": {"userEnteredFormat": {"numberFormat": {"type": "TEXT"}}},
            "fields": "userEnteredFormat.numberFormat",
        }})

    formulas = _g_formulas(ws, upto)
    formula_rows = {i for i, f in enumerate(formulas, start=1) if f.startswith("=")}
    fallback_g = []
    for row in target_rows:
        current = formulas[row - 1] if row - 1 < len(formulas) else ""
        if str(current).strip():
            continue
        source = template if template in formula_rows else _nearest(formula_rows, row)
        if source:
            g_requests.append(_copy_request(ws, source, row, COL_G_SUMMARY, COL_G_SUMMARY, "PASTE_FORMULA"))
        else:
            fallback_g.append(row)
        result["g_filled"] += 1

    def send(requests, label) -> bool:
        if not requests:
            return True
        try:
            memo.with_retry(ws.spreadsheet.batch_update, {"requests": requests})
            return True
        except Exception as exc:
            result["errors"].append(f"{label}失敗：{exc}")
            log(f"❌ {label}失敗：{exc}")
            return False

    # 格式先套，再套下拉選單與文字格式（格式失敗不影響下拉選單）
    if send(fmt_requests, "G:O 格式套用"):
        result["format_copied"] = len(fmt_requests)
    if not send(dv_requests + text_requests, "I/N/O 下拉選單與 I 欄文字格式"):
        # 整批失敗時逐列重試，找出哪幾列不行
        ok = 0
        for row in target_rows:
            per_row = [r for r in dv_requests + text_requests
                       if (r.get("setDataValidation") or r.get("repeatCell"))["range"]["startRowIndex"] == row - 1]
            if send(per_row, f"第{row}列下拉選單"):
                ok += 1
        log(f"逐列重試下拉選單：成功 {ok}／{len(target_rows)} 列")
    send(g_requests, "G 欄公式")
    for row in fallback_g:
        memo.with_retry(ws.update, f"G{row}", [[_fallback_g_formula(row)]], value_input_option="USER_ENTERED")
        log(f"⚠️ 第{row}列：找不到 G 欄公式可參照，改用預設組合公式")

    # I 欄數字／日期 → 文字「YYYY.MM」
    try:
        raw = memo.with_retry(ws.get, f"I1:I{upto}", value_render_option="UNFORMATTED_VALUE") or []
    except Exception as exc:
        raw = []
        result["errors"].append(f"讀取 I 欄失敗：{exc}")
    month_updates = []
    for row in target_rows:
        value = raw[row - 1][0] if row - 1 < len(raw) and raw[row - 1] else ""
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            month_updates.append({"range": f"I{row}", "values": [[_month_text(value)]]})
    if month_updates:
        memo.with_retry(ws.batch_update, month_updates, value_input_option="RAW")
        result["month_fixed"] = len(month_updates)

    log(f"G:O 整理：範本第{template}列、格式套用 {result['format_copied']} 列、補下拉 {result['dropdown_copied']} 列、"
        f"G 補公式 {result['g_filled']} 格、I 欄改回文字月份 {result['month_fixed']} 格"
        + (f"；錯誤 {len(result['errors'])} 項" if result["errors"] else ""))
    return result


def normalize_atm_rows(region: str, ui_logger=None, ws=None) -> Dict:
    """整理現有 ATM 分頁：凡 I:L 有資料的列，G 補公式、G:O 格式統一（I 下拉選單），
    N/O 兩欄都空白時補值：有訂單 → 清潔異動有同訂單同金額的收款列就用 異動費／工具組，否則 服務費用；
    沒有訂單 → 2000 新訓費，其他只填「清潔」、費用留人工。"""
    log = make_logger(ui_logger)
    ws = ws or get_atm_worksheet(region)
    rows = memo.with_retry(ws.get_all_values)
    data_rows = [idx for idx, row in enumerate(rows, start=1)
                 if idx > 1 and any(memo.safe_cell(row, c) for c in range(COL_I_MONTH, COL_ORDER_AMOUNT + 1))]
    result = {"rows": len(data_rows), "no_filled": 0}
    if not data_rows:
        return result

    change_fee: Dict[tuple, tuple] = {}
    try:
        from . import change_order

        for crow in memo.with_retry(change_order.get_worksheet(region).get_all_values)[1:]:
            no, amount = memo.safe_cell(crow, 7), _to_int_amount(memo.safe_cell(crow, 14))
            if no and amount and memo.safe_cell(crow, 3) == change_order.TYPE_CHARGE:
                change_fee[(no, amount)] = change_order_service_fee(f"{memo.safe_cell(crow, 3)} {memo.safe_cell(crow, 10)}")
    except Exception as exc:
        log(f"⚠️ 讀取「{region}」清潔異動失敗，N/O 一律依訂單判斷：{exc}")

    updates = []
    for idx in data_rows:
        row = rows[idx - 1]
        if memo.safe_cell(row, COL_N_SERVICE) or memo.safe_cell(row, COL_O_FEE):
            continue
        order_no = memo.safe_cell(row, COL_ORDER_NO)
        amount = _to_int_amount(memo.safe_cell(row, COL_ORDER_AMOUNT))
        if not order_no and amount is None:
            continue
        values = change_fee.get((order_no, amount)) if order_no else None
        values = values or default_service_fee(amount, order_no)
        updates.append({"range": f"N{idx}:O{idx}", "values": [list(values)]})
    if updates:
        memo.with_retry(ws.batch_update, updates, value_input_option="RAW")
        result["no_filled"] = len(updates)
    fmt = ensure_candidate_row_format(ws, data_rows, log=log)
    result.update({k: v for k, v in fmt.items() if k != "errors"})
    result["errors"] = list(fmt.get("errors") or [])
    log(f"✅ 已整理 ATM 分頁 {len(data_rows)} 列：N/O 補值 {result['no_filled']} 列、G 補公式 {result.get('g_filled', 0)} 格、"
        f"下拉／格式套用 {result.get('format_copied', 0)} 列、I 欄改回文字月份 {result.get('month_fixed', 0)} 格")
    return result


RECENT_MATCH_WORKDAYS = 3


def recent_workdays_start(today: _date, workdays: int = RECENT_MATCH_WORKDAYS) -> _date:
    """近 N 個上班日（含今天，今天是上班日才算一天）的第一天；中間連假不計入。
    例：週一 → 上週四；週六 → 週三；春節連假後第一天 → 連假前 2 個上班日。"""
    try:
        from shared.weekend_reminder_schedule import is_off_day, load_work_calendar

        calendar = load_work_calendar()
    except Exception:
        calendar, is_off_day = {}, (lambda value, _cal: value.weekday() >= 5)
    day = today
    counted = 0 if is_off_day(today, calendar) else 1
    while counted < workdays:
        day = previous_workday(day)
        counted += 1
    return day


def recent_unmatched_bank_rows(rows: List[List[str]], today: Optional[_date] = None,
                               workdays: int = RECENT_MATCH_WORKDAYS) -> List[int]:
    """近 3 個上班日（含今天；中間休假日的入帳也一併納入）A:F 有銀行明細、H:O 全空白的列。
    日期看 A 欄，A 讀不到再看 B 欄。"""
    today = today or today_tw()
    since = recent_workdays_start(today, workdays)
    picked = []
    for idx, row in enumerate(rows, start=1):
        a_to_f = [memo.safe_cell(row, c) for c in range(1, 7)]
        if not any(a_to_f):
            continue
        if any(memo.safe_cell(row, c) for c in range(8, 16)):  # H:O
            continue
        day = _bank_date(a_to_f[0]) or _bank_date(a_to_f[1])
        if day is None or not (since <= day <= today):
            continue
        picked.append(idx)
    return picked


COL_BANK_EXPENSE = 4  # D：支出（退款、新訓費等轉出）
REFUND_SERVICE_FEE = ("清潔", "退款")


def load_change_order_refunds(region: str) -> List[Dict]:
    """清潔異動分頁裡的退款列：退款日期（AC）、訂單（G）、姓名（H）、金額（T 匯款金額，空白用 S 退款金額）。"""
    from . import change_order

    values = memo.with_retry(change_order.get_worksheet(region).get_all_values)
    col = lambda letter: sum((ord(ch) - 64) * 26 ** i for i, ch in enumerate(reversed(letter)))
    refunds = []
    for row in values[1:]:
        refund_day = _bank_date(memo.safe_cell(row, col("AC")))
        order_no = memo.safe_cell(row, col("G"))
        if not refund_day or not order_no:
            continue
        amounts = {a for a in (_to_int_amount(memo.safe_cell(row, col("T"))),
                               _to_int_amount(memo.safe_cell(row, col("S")))) if a}
        service_day = _bank_date(memo.safe_cell(row, col("I")))
        refunds.append({
            "date": refund_day, "order_no": order_no, "name": memo.safe_cell(row, col("H")),
            "amounts": amounts, "line_url": memo.safe_cell(row, col("D")),
            "year_month": f"{service_day:%Y.%m}" if service_day else f"{refund_day:%Y.%m}",
        })
    return refunds


def match_refund(refunds: List[Dict], bank_day: Optional[_date], amount: Optional[int],
                 used_order_nos: Optional[set] = None) -> tuple:
    """退款日期＝銀行日期、金額相同（T 匯款金額或 S 退款金額）且唯一才配對。
    回傳 (退款資料或 None, 狀態／原因)；已出現在 ATM J 欄的訂單不再使用。"""
    used = used_order_nos or set()
    same_day = [r for r in refunds if bank_day and r["date"] == bank_day and r["order_no"] not in used]
    exact = [r for r in same_day if amount in r["amounts"]]
    if len(exact) == 1:
        return exact[0], "退款"
    if len(exact) > 1:
        return None, f"同日同金額退款 {len(exact)} 筆，請人工確認"
    if same_day:
        return None, f"清潔異動同日退款 {len(same_day)} 筆但金額不符，請人工確認"
    return None, "清潔異動找不到同日退款"


# 公司匯款：F 欄像公司名稱時，比對同金額訂單的發票抬頭（2026-11-07 Jenny）
COMPANY_HINT = re.compile(
    r"公司|有限|股份|企業|集團|實業|科技|國際|工程|建設|診所|醫院|醫療|牙醫|藥局|工作室|事務所|"
    r"商行|商號|行號|協會|學會|基金會|管委會|管理委員會|學校|幼兒園|補習班|銀行|餐廳|飯店|旅館|民宿"
)
COMPANY_SUFFIX = re.compile(r"(股份)?有限公司|公司|企業社|商行|商號|行號")
INVOICE_TITLE_KEYS = ("company_title", "invoice_title", "companyTitle", "buyer_name", "title")


def looks_like_company(note: str) -> bool:
    return bool(COMPANY_HINT.search(str(note or "")))


def _company_core(text: str) -> str:
    return COMPANY_SUFFIX.sub("", _compact_text(text))


def company_name_matches(note: str, invoice_title: str) -> bool:
    """銀行備註常被截斷或省略「股份有限公司」：去掉公司字尾後互相包含（至少 2 字）或高度相似就算相符。"""
    a, b = _company_core(note), _company_core(invoice_title)
    if len(a) < 2 or len(b) < 2:
        return False
    return a in b or b in a or _similar_text(a, b, threshold=0.8)


def purchase_invoice_title(purchase: Optional[Dict]) -> str:
    for key in INVOICE_TITLE_KEYS:
        value = str((purchase or {}).get(key) or "").strip()
        if value:
            return value
    return ""


CHANGE_ORDER_FEE_TYPES = ("異動費", "工具組")


def mark_change_order_collected(region: str, order_no: str, amount: int, bank_time: str) -> str:
    """② 配對到清潔異動來的款項後，只回填清潔異動該筆的 M 欄收款時間（＝ATM B 欄入帳日期時間）。

    2026-11-07 Jenny：不得改動清潔異動其他欄位，尤其 B 欄狀態（B 欄不是用收款時間判斷是否已收款）。
    找列條件：C＝異動服務收款、G＝訂單、N＝金額、M 空白；同條件多列只填第一列並回報。回傳結果文字。
    """
    from . import change_order

    ws = change_order.get_worksheet(region)
    values = memo.with_retry(ws.get_all_values)
    same = [
        idx for idx, row in enumerate(values, start=1)
        if idx > 1
        and memo.safe_cell(row, 7) == order_no
        and memo.safe_cell(row, 3) == change_order.TYPE_CHARGE
        and _to_int_amount(memo.safe_cell(row, 14)) == amount
    ]
    if not same:
        return f"清潔異動找不到 {order_no} 異動服務收款 ${amount}"
    empty_m = [idx for idx in same if not memo.safe_cell(values[idx - 1], 13)]
    if not empty_m:
        return f"清潔異動第{same[0]}列已有收款時間，未改動"
    row_num = empty_m[0]
    memo.with_retry(ws.update, f"M{row_num}", [[str(bank_time or "").strip() or _now_text()]],
                    value_input_option="RAW")
    extra = f"（另有 {len(empty_m) - 1} 列同條件未填）" if len(empty_m) > 1 else ""
    return f"已回填清潔異動第{row_num}列收款時間{extra}"


def _trainee_name(note: str) -> str:
    return re.sub(r"(新訓|新訓費).*$", "", str(note or "")).strip()


def preview_recent_unmatched_bank_rows(region: str, today: Optional[_date] = None) -> List[Dict]:
    """盤點：列出 ② 留空列號時會處理的列，給介面先確認。"""
    rows = memo.with_retry(get_atm_worksheet(region).get_all_values)
    return [{
        "列號": idx,
        "日期": memo.safe_cell(rows[idx - 1], 1),
        "入帳時間": memo.safe_cell(rows[idx - 1], COL_BANK_TIME),
        "摘要": memo.safe_cell(rows[idx - 1], 3),
        "收入": memo.safe_cell(rows[idx - 1], COL_BANK_INCOME),
        "備註": memo.safe_cell(rows[idx - 1], COL_BANK_NOTE),
    } for idx in recent_unmatched_bank_rows(rows, today=today)]


def _write_trainee_fee(ws, idx: int, bank_day: Optional[_date], amount: int, note: str) -> None:
    """沒有訂單的 2000：I 入帳月份、K 備註裡的姓名、L 金額、N/O 清潔／新訓費；T 標「新訓費」（③ 不會處理）。"""
    memo.with_retry(ws.update, f"I{idx}:O{idx}", [[
        f"{bank_day:%Y.%m}" if bank_day else "", "", _trainee_name(note), amount, "", *TRAINEE_SERVICE_FEE,
    ]], value_input_option="RAW")
    _clear_data_validation(ws, idx, COL_RECON_STATUS, COL_RECON_STATUS)
    memo.with_retry(ws.update_cell, idx, COL_RECON_STATUS, "新訓費")


def auto_match_bank_rows(
    region: str,
    row_spec: str = "",
    overwrite_existing: bool = False,
    default_service_type: str = "",
    default_fee_type: str = "",
    allow_review_prefill: bool = True,
    ui_logger=None,
    today: Optional[_date] = None,
    session=None,
) -> Dict:
    """row_spec 留空：只處理近 3 個上班日 A:F 有資料但 H:O 空白的列（不再掃全部列）。
    有 session 時，F 欄像公司名稱會到後台查同金額訂單的發票抬頭比對。"""
    log = make_logger(ui_logger)
    result = {
        "processed": 0, "success": 0, "failed": 0, "skipped": 0,
        "updated_orders": 0, "ambiguous": 0, "unmatched": 0,
        "confirm_required": 0, "non_order": 0, "split_payment": 0,
        "errors": [], "matched_rows": [],
        # 需人工處理（畫面表格）：列號／類型／訂單／姓名／金額／說明
        "review": [],
    }

    def add_review(row_idx: int, kind: str, text: str, c: Optional[Dict] = None, amount=None) -> None:
        c = c or {}
        result["review"].append({
            "列號": row_idx, "類型": kind, "訂單": c.get("order_no") or "",
            "姓名": c.get("name") or "", "金額": amount if amount is not None else c.get("amount", ""),
            "說明": text,
        })

    ws = get_atm_worksheet(region)
    log(f"===== 開始自動配對 ATM 銀行明細（{region}）=====")
    # 先整理現有列：G 補公式、G:O 格式統一、N/O 空白補值（候選列 N/O 正確，配對時才會帶對）
    try:
        nr = normalize_atm_rows(region, ui_logger=ui_logger, ws=ws) or {}
        for err in nr.get("errors") or []:
            add_review("", "G:O 整理", err)
    except Exception as exc:
        log(f"⚠️ 整理 ATM 分頁 G:O 失敗：{exc}")
        add_review("", "G:O 整理", f"整理失敗：{exc}")
    rows = memo.with_retry(ws.get_all_values)
    if str(row_spec or "").strip():
        target_row_nums = memo.parse_row_spec(row_spec)
        log(f"指定銀行列號：{target_row_nums}")
    else:
        target_row_nums = recent_unmatched_bank_rows(rows, today=today)
        since = recent_workdays_start(today or today_tw())
        log(f"未指定列號：近 {RECENT_MATCH_WORKDAYS} 個上班日（{since:%m/%d} 起）A:F 有資料、H:O 空白的列 → {target_row_nums or '無'}")
        if not target_row_nums:
            log("===== 自動配對完成 =====")
            return result
    target_row_set = set(target_row_nums)

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
    refund_candidates: Dict[str, List[Dict]] = {}
    for idx, row in enumerate(rows, start=1):
        # 只從 B 欄最後一列下方找待配對清單，不回頭掃銀行明細區
        if idx <= last_b_row:
            continue
        order_no = memo.safe_cell(row, COL_MATCH_ORDER_NO)
        name = memo.safe_cell(row, COL_NAME)
        amount = _to_int_amount(memo.safe_cell(row, COL_AMOUNT))
        last_code = memo.safe_cell(row, COL_LAST_CODE)

        if amount is None:
            continue
        if amount < 0:
            # 清潔異動 ATM 待退款（負數）：不參與收入配對，支出配對到同訂單退款時再移除
            if order_no:
                refund_candidates.setdefault(order_no, []).append({"row": idx, "amount": amount})
            continue
        # N/O 沿用候選列（① 待付款／清潔異動進來時已填好）；舊資料空白才補
        rule_service, rule_fee = default_service_fee(amount, order_no)
        service_type = memo.safe_cell(row, COL_SERVICE_TYPE) or default_service_type or rule_service
        fee_type = memo.safe_cell(row, COL_FEE_TYPE) or default_fee_type or rule_fee
        if not order_no and not (name and (service_type or fee_type)):
            continue

        candidates.append({
            "row": idx,
            "extra": memo.safe_cell(row, COL_EXTRA),
            "u_value": memo.safe_cell(row, COL_MOVE_WITH_MATCH),
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
    touched_rows: List[int] = []
    cleared_rows: List[int] = []  # 候選資料移走後的原列：G 也不得空白、格式要一致
    refunds_cache: Optional[List[Dict]] = None
    invoice_titles: Dict[str, str] = {}

    def collect_change_order(row_idx: int, c: Dict, bank_time: str) -> None:
        """清潔異動來的異動費／工具組配對成功 → 只回填清潔異動 M 欄收款時間。"""
        if c.get("fee_type") not in CHANGE_ORDER_FEE_TYPES or not c.get("order_no"):
            return
        try:
            text = mark_change_order_collected(region, c["order_no"], c["amount"], bank_time)
        except Exception as exc:
            text = f"回填清潔異動失敗：{exc}"
        result.setdefault("change_order_collected", []).append(f"第{row_idx}列 {c['order_no']}：{text}")
        ok = text.startswith("已回填") and "另有" not in text
        if not ok:
            add_review(row_idx, "清潔異動未回填" if not text.startswith("已回填") else "清潔異動多列", text, c)
        log(f"{'✅' if ok else '⚠️'} 第{row_idx}列 {c['order_no']}：{text}")

    def invoice_title_of(order_no: str) -> str:
        if order_no not in invoice_titles:
            try:
                invoice_titles[order_no] = purchase_invoice_title(find_purchase_by_order_no(session, order_no))
            except Exception as exc:
                invoice_titles[order_no] = ""
                log(f"⚠️ 查訂單 {order_no} 發票抬頭失敗：{exc}")
        return invoice_titles[order_no]

    for idx, row in enumerate(rows, start=1):
        try:
            if target_row_set and idx not in target_row_set:
                continue

            income = _to_int_amount(memo.safe_cell(row, COL_INCOME))
            bank_time = memo.safe_cell(row, COL_BANK_TIME)
            note = memo.safe_cell(row, COL_NOTE)
            current_order_no = memo.safe_cell(row, COL_MATCH_ORDER_NO)
            bank_day = _bank_date(memo.safe_cell(row, 1)) or _bank_date(bank_time)

            if income is None:
                expense = _to_int_amount(memo.safe_cell(row, COL_BANK_EXPENSE))
                if expense is None or current_order_no or memo.safe_cell(row, COL_SERVICE_TYPE):
                    continue
                # 支出（D 欄）：先找清潔異動同日退款；找不到且 2000 → 新訓費；其他人工確認
                result["processed"] += 1
                if refunds_cache is None:
                    try:
                        refunds_cache = load_change_order_refunds(region)
                    except Exception as exc:
                        refunds_cache = []
                        log(f"⚠️ 讀取「{region}」清潔異動退款失敗：{exc}")
                refund, status_text = match_refund(refunds_cache, bank_day, expense, used_order_nos)
                if refund:
                    used_order_nos.add(refund["order_no"])
                    memo.with_retry(ws.update, f"H{idx}:O{idx}", [[
                        refund["line_url"], refund["year_month"], refund["order_no"], refund["name"],
                        expense, "", *REFUND_SERVICE_FEE,
                    ]], value_input_option="RAW")
                    _clear_data_validation(ws, idx, COL_RECON_STATUS, COL_RECON_STATUS)
                    memo.with_retry(ws.update_cell, idx, COL_RECON_STATUS, status_text)
                    touched_rows.append(idx)
                    result["success"] += 1
                    log(f"✅ 第{idx}列：支出 ${expense} → 清潔異動退款 {refund['order_no']} {refund['name']}")
                    pending = refund_candidates.get(refund["order_no"]) or []
                    if pending:
                        source_row = pending.pop(0)["row"]
                        memo.with_retry(ws.update, f"H{source_row}:O{source_row}", [[""] * 8], value_input_option="RAW")
                        cleared_rows.append(source_row)
                        log(f"↳ 已從下方待配對列表移除 ATM 待退款列第{source_row}列 H:O")
                elif expense == TRAINEE_FEE_AMOUNT:
                    _write_trainee_fee(ws, idx, bank_day, expense, note)
                    touched_rows.append(idx)
                    result["success"] += 1; result["non_order"] += 1
                    log(f"✅ 第{idx}列：支出 $2000、沒有訂單 → 清潔／新訓費")
                else:
                    result["unmatched"] += 1; result["failed"] += 1
                    result["errors"].append(f"第{idx}列：支出 ${expense}，{status_text}")
                    add_review(idx, "支出／退款待確認", f"{note}：{status_text}", amount=expense)
                    log(f"❌ 第{idx}列：支出 ${expense}，{status_text}")
                continue

            result["processed"] += 1

            if current_order_no and not overwrite_existing:
                result["skipped"] += 1
                log(f"⏭ 第{idx}列：已有訂單 {current_order_no}，略過")
                continue

            amount_candidates = [c for c in candidates if c["amount"] == income]
            if not overwrite_existing:
                amount_candidates = [c for c in amount_candidates if (not c["order_no"]) or c["order_no"] not in used_order_nos or c["order_no"] == current_order_no]

            available_candidates = candidates
            if not overwrite_existing:
                available_candidates = [
                    c for c in candidates
                    if (not c["order_no"]) or c["order_no"] not in used_order_nos or c["order_no"] == current_order_no
                ]

            # 單筆等額找不到時，再嘗試 2～5 筆訂單加總。每筆都必須有末碼或
            # 姓名證據，而且只能有唯一組合，否則一律交由人工確認。
            sum_combinations = [] if amount_candidates else _find_sum_combinations(
                income, available_candidates, note, max_orders=5, max_results=2
            )
            if len(sum_combinations) > 1:
                text = "多筆加總有多組可能，請人工確認"
                add_review(idx, "多筆候選", f"{note}：{text}", amount=income)
                result["ambiguous"] += 1
                result["failed"] += 1
                result["errors"].append(f"第{idx}列：{text}")
                log(f"⚠️ 第{idx}列：{text}")
                continue

            if len(sum_combinations) == 1:
                combo = sum_combinations[0]
                target_rows = [idx]
                # 第二筆起寫入緊接在下方、銀行時間與備註相同的空白續列。
                for next_idx in range(idx + 1, min(last_b_row, len(rows)) + 1):
                    next_row = rows[next_idx - 1]
                    if _to_int_amount(memo.safe_cell(next_row, COL_INCOME)) is not None:
                        break
                    if not _datetime_equals(memo.safe_cell(next_row, COL_BANK_TIME), bank_time):
                        break
                    if _compact_text(memo.safe_cell(next_row, COL_NOTE)) != _compact_text(note):
                        break
                    if memo.safe_cell(next_row, COL_MATCH_ORDER_NO) and not overwrite_existing:
                        break
                    target_rows.append(next_idx)
                    if len(target_rows) >= len(combo):
                        break

                if len(target_rows) < len(combo):
                    text = f"找到唯一的 {len(combo)} 筆加總組合，但相同時間/備註的空白續列不足"
                    add_review(idx, "需確認", "、".join(c["order_no"] for c in combo) + f"：{text}", amount=income)
                    result["confirm_required"] += 1
                    result["failed"] += 1
                    result["errors"].append(f"第{idx}列：{text}")
                    log(f"⚠️ 第{idx}列：{text}")
                    continue

                for target_row, c in zip(target_rows, combo):
                    values = [[
                        c.get("extra", ""), c["year_month"], c["order_no"], c["name"],
                        c["amount"], c["last_code"], c["service_type"], c["fee_type"],
                    ]]
                    source_row = int(c.get("row") or 0)
                    _copy_data_validation(ws, source_row, target_row, [COL_EXTRA, COL_MONTH, COL_SERVICE_TYPE, COL_FEE_TYPE])
                    memo.with_retry(ws.update, f"H{target_row}:O{target_row}", values, value_input_option="RAW")
                    if c.get("u_value"):
                        memo.with_retry(ws.update_cell, target_row, COL_MOVE_WITH_MATCH, c["u_value"])
                    _clear_data_validation(ws, target_row, COL_RECONCILED_AT, COL_RECONCILED_AT)
                    _clear_data_validation(ws, target_row, COL_RECON_STATUS, COL_RECON_STATUS)
                    memo.with_retry(ws.update_cell, target_row, COL_RECONCILED_AT, _now_text())
                    memo.with_retry(ws.update_cell, target_row, COL_RECON_STATUS, "已配對（多訂單加總）")

                    if source_row and source_row != target_row:
                        _copy_data_validation(ws, target_row, source_row, [COL_EXTRA, COL_MONTH, COL_SERVICE_TYPE, COL_FEE_TYPE])
                        memo.with_retry(ws.update, f"H{source_row}:O{source_row}", [["", "", "", "", "", "", "", ""]], value_input_option="RAW")
                        if c.get("u_value"):
                            memo.with_retry(ws.update_cell, source_row, COL_MOVE_WITH_MATCH, "")
                        _clear_data_validation(ws, source_row, COL_RECON_STATUS, COL_RECON_STATUS)
                        memo.with_retry(ws.update_cell, source_row, COL_RECON_STATUS, "")
                        cleared_rows.append(source_row)

                    touched_rows.append(target_row)
                    if c["order_no"]:
                        used_order_nos.add(c["order_no"])
                    log(f"✅ 第{target_row}列：多訂單加總 → {c['order_no']} {c['name']} ${c['amount']}")
                    collect_change_order(target_row, c, bank_time)

                result["success"] += len(combo)
                result["updated_orders"] += len(combo)
                continue

            split_candidates = [c for c in candidates if _is_split_payment_candidate(income, c, note)]
            code_matches = [c for c in amount_candidates if c["last_code"] and _bank_note_has_code(note, c["last_code"])]
            name_matches = [c for c in amount_candidates if _note_matches_name(note, c["name"])]
            company_matches = []
            if not code_matches and not name_matches and session is not None and looks_like_company(note):
                order_candidates = [c for c in amount_candidates if c.get("order_no")]
                company_matches = [c for c in order_candidates if company_name_matches(note, invoice_title_of(c["order_no"]))]
                if order_candidates and not company_matches:
                    titles = "、".join(f"{c['order_no']}「{invoice_title_of(c['order_no']) or '無抬頭'}」" for c in order_candidates[:5])
                    log(f"第{idx}列：F 欄「{note}」像公司名稱，同金額訂單發票抬頭不符：{titles}")

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
            elif len(company_matches) == 1:
                matches = company_matches; match_type = "公司抬頭+金額"
            elif len(company_matches) > 1:
                matches = company_matches; match_type = "公司抬頭+金額"
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
                    or str(match_type).startswith("公司抬頭+金額")
                    or "F欄與K欄姓名相近" in str(match_type)
                    or "M欄日期時間=B欄" in str(match_type)
                    or str(match_type).startswith("疑似拆單")
                )
                if not evidence_ok:
                    text = f"待人工確認：同金額候選 {c.get('order_no') or '-'} {c.get('name')}，但缺少末碼/姓名/時間依據"
                    add_review(idx, "未配對", f"{note}：{text}", amount=income)
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
                if c.get("u_value"):
                    memo.with_retry(ws.update_cell, idx, COL_MOVE_WITH_MATCH, c["u_value"])
                _clear_data_validation(ws, idx, COL_RECONCILED_AT, COL_RECONCILED_AT)
                _clear_data_validation(ws, idx, COL_RECON_STATUS, COL_RECON_STATUS)
                memo.with_retry(ws.update_cell, idx, COL_RECONCILED_AT, _now_text())
                memo.with_retry(ws.update_cell, idx, COL_RECON_STATUS, status_text)
                touched_rows.append(idx)

                if source_row and source_row != idx:
                    _copy_data_validation(ws, idx, source_row, [COL_EXTRA, COL_MONTH, COL_SERVICE_TYPE, COL_FEE_TYPE])
                    memo.with_retry(ws.update, f"H{source_row}:O{source_row}", [["", "", "", "", "", "", "", ""]], value_input_option="RAW")
                    if c.get("u_value"):
                        memo.with_retry(ws.update_cell, source_row, COL_MOVE_WITH_MATCH, "")
                    _copy_data_validation(ws, idx, source_row, [COL_EXTRA, COL_MONTH, COL_SERVICE_TYPE, COL_FEE_TYPE])
                    _clear_data_validation(ws, source_row, COL_RECON_STATUS, COL_RECON_STATUS)
                    memo.with_retry(ws.update_cell, source_row, COL_RECON_STATUS, "")
                    cleared_rows.append(source_row)
                    log(f"↳ 已從下方待配對列表移除原候選列第{source_row}列 H:O 與 T")

                if needs_confirm:
                    result["confirm_required"] += 1
                    if is_non_order:
                        result["non_order"] += 1
                    if is_split:
                        result["split_payment"] += 1
                    result["errors"].append(f"第{idx}列：已預填需確認 {status_text} {c['order_no'] or '-'} {c['name']}（{match_type}）")
                    add_review(idx, status_text, f"已預填，請確認（{match_type}；F 欄：{note}）", c)
                    log(f"⚠️ 第{idx}列：已預填需使用者確認 → {c['order_no'] or '-'} {c['name']} ${c['amount']}（{status_text}／{match_type}）")
                else:
                    log(f"✅ 第{idx}列：{match_type} → {c['order_no']} {c['name']} ${c['amount']}")
                    collect_change_order(idx, c, bank_time)

                if c["order_no"]:
                    used_order_nos.add(c["order_no"])
                result["success"] += 1
                result["updated_orders"] += 1

            elif len(matches) > 1:
                text = "多筆候選：" + "、".join(f"{c.get('order_no') or '-'} {c.get('name')}" for c in matches[:5])
                add_review(idx, "多筆候選", f"{note}：{text}", amount=income)
                result["ambiguous"] += 1
                result["failed"] += 1
                result["errors"].append(f"第{idx}列：{text}")
                log(f"⚠️ 第{idx}列：{text}")

            elif income == TRAINEE_FEE_AMOUNT and (
                "新訓" in note or not any(c.get("order_no") for c in amount_candidates)
            ):
                # 沒有訂單可對、金額 2000 → 清潔／新訓費（其他金額一律人工確認）
                _write_trainee_fee(ws, idx, bank_day, income, note)
                touched_rows.append(idx)
                result["success"] += 1; result["non_order"] += 1
                log(f"✅ 第{idx}列：收入 $2000、沒有訂單 → 清潔／新訓費")

            else:
                if len(amount_candidates) > 1:
                    text = f"待人工確認：同金額候選 {len(amount_candidates)} 筆，但缺少末碼/姓名/時間依據"
                elif len(amount_candidates) == 1:
                    c = amount_candidates[0]
                    text = f"待人工確認：同金額候選 {c.get('order_no') or '-'} {c['name']}，但缺少末碼/姓名/時間依據"
                else:
                    text = "待人工確認"
                add_review(idx, "未配對", f"{note}：{text}", amount=income)
                result["unmatched"] += 1
                result["failed"] += 1
                result["errors"].append(f"第{idx}列：{text}")
                log(f"❌ 第{idx}列：{text}")

        except Exception as e:
            msg = f"❌ 第{idx}列配對失敗：{e}"
            log(msg)
            add_review(idx, "執行錯誤", str(e))
            result["failed"] += 1
            result["errors"].append(msg)

    if touched_rows or cleared_rows:
        try:
            ensure_candidate_row_format(ws, touched_rows + cleared_rows, log=log)
        except Exception as exc:
            log(f"⚠️ 補 G 欄公式／下拉選單失敗：{exc}")
            result["errors"].append(f"補 G 欄公式／下拉選單失敗：{exc}")

    result["matched_rows"] = sorted(set(touched_rows))
    log("===== 自動配對完成 =====")
    return result


# -----------------------------------------------------------------------------
# 待付款清單查詢
# -----------------------------------------------------------------------------
def unpaid_block_reason(purchase: Optional[Dict]) -> str:
    """不是待付款的原因；空字串＝仍待付款。

    除了 purchase_status 必須是 0，有付款日期（paid_at）也視為已付款：2026-11-05 黃妙禎 08:38 已執行已付款，
    15:00 仍被當待付款貼上（ATM 對帳判斷已付款時也同時看 paid_at）。
    """
    if not purchase:
        return "查無訂單"
    raw_status = purchase.get("purchase_status")
    status_code = "" if raw_status is None else str(raw_status).strip()
    if status_code != "0":
        return {"1": "已付款", "2": "取消訂單", "3": "已退款"}.get(status_code, f"未知狀態 {status_code or '空白'}")
    paid_at = str(purchase.get("paid_at") or "").strip()
    if paid_at and not paid_at.startswith("0000"):
        return f"已付款（付款日期 {paid_at}）"
    return ""


def search_atm_unpaid_orders(session, date_until: Optional[str] = None, ui_logger=None,
                             date_since: Optional[str] = None) -> List[Dict]:
    """
    date_since：訂購日期起（排程同步用；手動查詢不帶＝不限起日）。

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
        "date_s": date_since or "", "date_e": date_until,
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

    log(f"===== 查詢 ATM 待付款名單（訂購日期：{date_since or '不限'}～{date_until}）=====")
    r = memo.session_get(session, url, params=params)
    r.raise_for_status()

    data = extract_purchase_list_json(r.text)
    if not data:
        log("⚠️ 找不到訂單統計表的內嵌資料（頁面結構可能改變，或查無資料）")
        return []

    items = data.get("data", [])
    log(f"後台回傳 {len(items)} 筆 ATM 訂單，開始核對付款狀態")

    rows = []
    for item in items:
        status_name = unpaid_block_reason(item)
        if status_name:
            order_no = str(item.get("order_no") or "").strip() or "無訂單編號"
            log(f"⚠️ 略過 {order_no}：實際狀態為「{status_name}」")
            continue
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
            # 客戶匯款帳號後 5 碼（有填才有）→ M 欄，② 用來比對 F 欄
            "last_code": str(item.get("account5") or "").strip(),
        })
        log(f"  - {year_month}　{order_no}　{name}　總金額{total} - 車馬費{fare} = {net_amount}")

    log(f"狀態核對完成：{len(rows)} 筆待付款 ATM 訂單可進入對帳區")
    return rows


def _auto_normalize(region: str, ws, log, result: Dict) -> None:
    """按執行時自動整理 ATM 分頁 G:O，不用另外按整理。失敗只記錯誤，不影響貼上結果。"""
    try:
        result["normalized"] = normalize_atm_rows(region, ui_logger=log, ws=ws)
        result["errors"].extend(f"整理 G:O：{e}" for e in result["normalized"].get("errors") or [])
    except Exception as exc:
        log(f"⚠️ 整理 ATM 分頁 G:O 失敗：{exc}")
        result["errors"].append(f"整理 ATM 分頁 G:O 失敗：{exc}")


def paste_atm_unpaid_list(region: str, rows: List[Dict], ui_logger=None) -> Dict:
    """新增未出現的待付款訂單並回填 P/T。

    去重檢查整個 ATM 分頁的 J 欄：同一張訂單只要已列過（不論在銀行明細區上方或下方）就不再新增。
    （2026-11：原本只檢查 A 欄最後一筆以下，A 欄往下補資料後，11/02 已列過的待付款訂單又被重列。）
    """
    log = make_logger(ui_logger)
    result = {"pasted": 0, "skipped_duplicates": 0, "start_row": None, "errors": []}

    if not rows:
        log("沒有資料可以貼")
        return result

    ws = get_atm_worksheet(region)
    all_values = memo.with_retry(ws.get_all_values)

    # 新增位置以 A 欄最後一筆＋5 列定位；去重檢查整欄 J。
    last_a_row = max(
        (idx for idx, row in enumerate(all_values, start=1)
         if row and str(row[0]).strip()),
        default=0,
    )

    existing_order_nos = set()
    last_unpaid_row = 0
    for idx, row in enumerate(all_values, start=1):
        order_no = row[9] if len(row) > 9 else ""
        if str(order_no).strip():
            existing_order_nos.add(str(order_no).strip())
        if idx <= last_a_row:
            continue
        i_to_l = row[8:12] if len(row) > 8 else []
        if any(str(value).strip() for value in i_to_l):
            last_unpaid_row = idx

    pending_rows = []
    seen_order_nos = set(existing_order_nos)
    for row in rows:
        order_no = str(row.get("order_no") or "").strip()
        if not order_no:
            log("⚠️ 略過一筆沒有訂單編號的資料")
            continue
        if order_no in seen_order_nos:
            result["skipped_duplicates"] += 1
            continue
        seen_order_nos.add(order_no)
        pending_rows.append(row)

    if not pending_rows:
        log(f"沒有新訂單可新增；已略過 {result['skipped_duplicates']} 筆重複訂單")
        _auto_normalize(region, ws, log, result)
        return result

    # 維持原規則：A 欄最後一筆下方空 4 列；既有 I:L 絕不覆蓋。
    start_row = max(last_a_row + 5, last_unpaid_row + 1)
    end_row = start_row + len(pending_rows) - 1

    current_row_count = int(getattr(ws, "row_count", 0) or len(all_values))
    if end_row > current_row_count:
        memo.with_retry(ws.add_rows, end_row - current_row_count)

    updates = []
    pasted_at = _now_text()
    for offset, row in enumerate(pending_rows):
        row_num = start_row + offset
        # 2026-11-07 Jenny：ATM 待對帳時就把 H:O 填完整（H 見下方、I:L 訂單、M 後 5 碼、N/O 清潔／服務費用）
        updates.append({
            "range": f"I{row_num}:O{row_num}",
            "values": [[
                row["year_month"],
                row["order_no"],
                row["name"],
                row["net_amount"],
                row.get("last_code", ""),
                *UNPAID_SERVICE_FEE,
            ]],
        })
        updates.append({"range": f"P{row_num}", "values": [[pasted_at]]})
        updates.append({"range": f"T{row_num}", "values": [["待對帳"]]})

        # H 欄 LINE 連結只在原儲存格為空時寫入，避免覆蓋人工資料。
        existing_h = ""
        if row_num <= len(all_values) and len(all_values[row_num - 1]) >= 8:
            existing_h = str(all_values[row_num - 1][7]).strip()
        if row.get("line_url") and not existing_h:
            updates.append({
                "range": f"H{row_num}",
                "values": [[row["line_url"]]],
            })

    memo.with_retry(ws.batch_update, updates, value_input_option="RAW")
    # 貼上後順便整理整張 ATM 分頁（含剛貼的列）：G 公式、G:O 格式／下拉、I 文字月份、N/O 空白補值
    _auto_normalize(region, ws, log, result)

    result["pasted"] = len(pending_rows)
    result["start_row"] = start_row
    log(
        f"✅ 已新增 {len(pending_rows)} 筆至 H{start_row}:O{end_row}；"
        f"略過 {result['skipped_duplicates']} 筆重複訂單"
    )
    return result


def append_change_order_charges(region: str, rows: List[Dict], ui_logger=None) -> Dict:
    """把清潔異動的待收款／ATM 待退款追加到同地區 ATM 工作表（I:L 資料、N/O 類別、G 公式與下拉選單）。

    rows 每筆：year_month, order_no, name, amount（待退款為負數）, change_text, kind（"charge"／"refund"）
    2026-11-09 Jenny：ATM 待退款同樣寫入，金額負數，N/O＝清潔／退款（與支出配對一致）。
    """
    log = make_logger(ui_logger)
    result = {"pasted": 0, "start_row": None}
    if not rows:
        return result

    ws = get_atm_worksheet(region)
    all_values = memo.with_retry(ws.get_all_values)

    last_a_row = max(
        (idx for idx, row in enumerate(all_values, start=1)
         if row and str(row[0]).strip()),
        default=0,
    )
    last_unpaid_row = max(
        (idx for idx, row in enumerate(all_values, start=1)
         if any(str(value).strip() for value in row[8:12])),
        default=0,
    )
    start_row = max(last_a_row + 5, last_unpaid_row + 1)
    end_row = start_row + len(rows) - 1

    current_row_count = int(getattr(ws, "row_count", 0) or len(all_values))
    if end_row > current_row_count:
        memo.with_retry(ws.add_rows, end_row - current_row_count)

    values = [[
        row.get("year_month", ""),
        row.get("order_no", ""),
        row.get("name", ""),
        row.get("amount", 0),
    ] for row in rows]
    memo.with_retry(
        ws.update,
        values=values,
        range_name=f"I{start_row}:L{end_row}",
        value_input_option="RAW",
    )
    # N/O 依異動內容：工具組 → 清潔／工具組；其他 → 清潔／異動費；ATM 待退款 → 清潔／退款
    service_fee = [
        list(REFUND_SERVICE_FEE if row.get("kind") == "refund" else change_order_service_fee(row.get("change_text", "")))
        for row in rows
    ]
    memo.with_retry(
        ws.update,
        values=service_fee,
        range_name=f"N{start_row}:O{end_row}",
        value_input_option="RAW",
    )
    try:
        ensure_candidate_row_format(ws, list(range(start_row, end_row + 1)), log=log)
    except Exception as exc:
        log(f"⚠️ 補 G 欄公式／下拉選單失敗：{exc}")

    result.update({"pasted": len(rows), "start_row": start_row})
    refund_count = sum(1 for row in rows if row.get("kind") == "refund")
    log(f"✅ 已同步 {len(rows) - refund_count} 筆待收款、{refund_count} 筆 ATM 待退款至 ATM 工作表 G{start_row}:O{end_row}")
    return result


def flag_cancelled_pending_orders(region: str, session, ui_logger=None) -> Dict:
    """排程複查待對帳區；取消訂單在同列 M 欄標記。"""
    log = make_logger(ui_logger)
    log(f"===== 開始複查「{region}」待對帳列是否已取消 =====")
    ws = get_atm_worksheet(region)
    all_values = memo.with_retry(ws.get_all_values)
    last_a_row = max(
        (idx for idx, row in enumerate(all_values, start=1)
         if row and str(row[0]).strip()),
        default=0,
    )
    updates = []
    checked = 0
    for row_num, row in enumerate(all_values, start=1):
        if row_num <= last_a_row:
            continue
        order_no = memo.safe_cell(row, COL_ORDER_NO)
        if not order_no or memo.safe_cell(row, COL_RECON_STATUS) == "已更新系統":
            continue
        amount = _to_int_amount(memo.safe_cell(row, COL_ORDER_AMOUNT))
        if amount is not None and amount < 0:
            continue  # 清潔異動 ATM 待退款列，訂單取消是正常情況，不標記
        checked += 1
        purchase = find_purchase_by_order_no(session, order_no)
        raw_status = purchase.get("purchase_status") if purchase else None
        status_code = "" if raw_status is None else str(raw_status).strip()
        if status_code == "2" and memo.safe_cell(row, COL_STATUS_NOTE) != "取消訂單":
            updates.append({"range": f"M{row_num}", "values": [["取消訂單"]]})
            log(f"⚠️ {region} 第{row_num}列 {order_no} 已取消，M欄已標註「取消訂單」")

    if updates:
        memo.with_retry(ws.batch_update, updates, value_input_option="RAW")
    log(f"===== 「{region}」複查完成：檢查 {checked} 筆，{len(updates)} 筆取消訂單已標註 =====")
    return {"checked": checked, "flagged": len(updates)}


def confirm_unpaid_rows(session, rows: List[Dict], ui_logger=None) -> List[Dict]:
    """貼上前逐張用訂單編號再查一次，只保留仍是待付款（purchase_status 0）的訂單。

    2026-11-05：已付款（08:38 已執行已付款）的訂單 15:00 仍出現在待付款清單結果裡被貼上；
    單張查詢與「取消訂單複查」用同一個 find_purchase_by_order_no。查詢失敗的訂單這次不貼，下次再試。
    """
    log = make_logger(ui_logger)
    confirmed = []
    for row in rows:
        order_no = str(row.get("order_no") or "").strip()
        try:
            purchase = find_purchase_by_order_no(session, order_no) if order_no else None
        except Exception as exc:
            log(f"⚠️ {order_no} 單張複查失敗，這次不貼：{exc}")
            continue
        reason = unpaid_block_reason(purchase)
        if not reason:
            confirmed.append(row)
            continue
        log(f"⚠️ 略過 {order_no} {row.get('name', '')}：單張複查狀態為「{reason}」")
    log(f"單張複查完成：{len(confirmed)}／{len(rows)} 筆確認仍待付款")
    return confirmed


def previous_workday(day) -> "date":
    """day 前一個上班日（依辦公日曆；週六日、國定假日往前推，補班日算上班）。"""
    from datetime import date as _date, timedelta as _td

    if isinstance(day, str):
        day = _date.fromisoformat(day)
    try:
        from shared.weekend_reminder_schedule import is_off_day, load_work_calendar

        calendar = load_work_calendar()
    except Exception:
        calendar, is_off_day = {}, (lambda value, _cal: value.weekday() >= 5)
    previous = day - _td(days=1)
    while is_off_day(previous, calendar):
        previous -= _td(days=1)
    return previous


def run_scheduled_unpaid_sync(ui_logger=None, date_until: Optional[str] = None) -> Dict:
    """沿用 ATM 對帳查詢／貼上功能，排程同步台北與台中待付款清單。

    只查訂購日期「前一個上班日～今天」的待付款：涵蓋前一天最後一次同步後、週末／國定假日的新訂單，
    不再每次撈全部歷史待付款（舊單只靠去重擋，A 欄位置變動時曾被重列）。重疊部分由整欄 J 去重略過。
    """
    log = make_logger(ui_logger)
    date_until = date_until or today_tw().isoformat()
    date_since = previous_workday(date_until).isoformat()
    results = {}
    errors = []

    try:
        from accounts import ACCOUNTS
    except Exception:
        ACCOUNTS = {}

    for region in ("台北", "台中"):
        prefix = REGION_SECRET_PREFIX[region]
        try:
            account = ACCOUNTS.get(region, {}) if isinstance(ACCOUNTS, dict) else {}
            email = str(account.get("email") or _secret_text(f"{prefix}_EMAIL")).strip()
            password = str(account.get("password") or _secret_text(f"{prefix}_PASSWORD")).strip()
            if not email or not password:
                raise RuntimeError(
                    f"本機 ~/lemon/accounts.py 缺少「{region}」email/password"
                )

            memo.set_runtime_credentials(email, password)
            session = memo.login(ui_logger=ui_logger)
            try:
                status_check = flag_cancelled_pending_orders(
                    region=region, session=session, ui_logger=ui_logger,
                )
                rows = search_atm_unpaid_orders(
                    session=session, date_until=date_until, date_since=date_since,
                    ui_logger=ui_logger,
                )
                rows = confirm_unpaid_rows(session, rows, ui_logger=ui_logger)
                results[region] = paste_atm_unpaid_list(
                    region=region, rows=rows, ui_logger=ui_logger,
                )
                results[region]["status_check"] = status_check
            finally:
                session.close()
        except Exception as exc:
            errors.append(f"{region}：{exc}")
            log(f"❌ {region}：{exc}")

    if errors:
        raise RuntimeError("；".join(errors))
    return results


AUTO_RECONCILE_STATUSES = ("已配對", "已配對（多訂單加總）")
# 2026-11-06 Jenny：排程 ③ 不處理 11/6 之前（B 欄銀行入帳日）的資料
AUTO_RECONCILE_FROM = _date(2026, 11, 6)


def _bank_date(value) -> Optional[_date]:
    m = re.search(r"(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})", str(value or ""))
    if not m:
        return None
    try:
        return _date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def rows_ready_for_reconcile(rows: List[List[str]], from_date: Optional[_date] = AUTO_RECONCILE_FROM) -> List[int]:
    """③ 排程只處理 ② 確定配對（T＝已配對）、左側有銀行明細、J 有訂單編號、M 不是取消訂單的列，
    而且 B 欄入帳日不早於 from_date（讀不到日期也不處理）。
    需確認／疑似拆單／非訂單收入一律留給人工。"""
    ready = []
    for idx, row in enumerate(rows, start=1):
        if memo.safe_cell(row, COL_RECON_STATUS) not in AUTO_RECONCILE_STATUSES:
            continue
        if from_date:
            bank_day = _bank_date(memo.safe_cell(row, COL_BANK_TIME))
            if bank_day is None or bank_day < from_date:
                continue
        if _to_int_amount(memo.safe_cell(row, COL_BANK_INCOME)) is None:
            continue
        if not re.fullmatch(r"[A-Za-z]{2}\d{6,}", memo.safe_cell(row, COL_ORDER_NO)):
            continue
        if memo.safe_cell(row, COL_STATUS_NOTE) == "取消訂單":
            continue
        # 異動費／工具組／退款／新訓費不是原訂單付款，不能按已付款（異動費已在 ② 回填清潔異動）
        if memo.safe_cell(row, 15) not in ("", "服務費用"):
            continue
        ready.append(idx)
    return ready


def match_and_reconcile(region: str, session, row_spec: str = "", ui_logger=None,
                        allow_review_prefill: bool = True, overwrite_existing: bool = False,
                        do_mark_paid: bool = True, do_issue_invoice: bool = True, do_send_mail: bool = True,
                        only_matched_rows: bool = True, today: Optional[_date] = None) -> Dict:
    """② 配對銀行明細後接著 ③ 更新系統對帳。

    ③ 只處理 T 欄「已配對」的列（見 rows_ready_for_reconcile）；only_matched_rows=True（手動勾選 ②＋③）
    時再限縮為這次 ② 剛配對的列。確認信只發給這次才改成已付款、付款日是今天的訂單。
    """
    log = make_logger(ui_logger)
    item = {"match": {}, "reconcile": {}, "reconcile_rows": []}
    log(f"===== ② 配對銀行明細（{region}）=====")
    item["match"] = auto_match_bank_rows(
        region=region, row_spec=row_spec, overwrite_existing=overwrite_existing,
        allow_review_prefill=allow_review_prefill, ui_logger=ui_logger, today=today, session=session,
    )
    ws = get_atm_worksheet(region)
    ready = rows_ready_for_reconcile(memo.with_retry(ws.get_all_values))
    if only_matched_rows:
        matched = set(item["match"].get("matched_rows") or [])
        ready = [r for r in ready if r in matched]
    item["reconcile_rows"] = ready
    if not ready:
        log(f"{region}：沒有已配對、待更新系統的列")
        return item
    log(f"===== ③ 更新系統對帳（{region}）：第 {ready} 列 =====")
    item["reconcile"] = process_atm_rows(
        region=region, row_spec=",".join(str(r) for r in ready),
        do_mark_paid=do_mark_paid, do_issue_invoice=do_issue_invoice, do_send_mail=do_send_mail,
        ui_logger=ui_logger, session=session,
    )
    return item


def run_scheduled_match_and_reconcile(ui_logger=None) -> Dict:
    """每日排程：台北／台中各跑 ② 配對銀行明細，再對確定配對的列跑 ③ 更新系統對帳
    （按已付款＋開立發票＋發確認信，與手動預設相同）。"""
    log = make_logger(ui_logger)
    results = {}
    errors = []

    try:
        from accounts import ACCOUNTS
    except Exception:
        ACCOUNTS = {}

    for region in ("台北", "台中"):
        prefix = REGION_SECRET_PREFIX[region]
        item = {"match": {}, "reconcile": {}, "reconcile_rows": []}
        results[region] = item
        try:
            account = ACCOUNTS.get(region, {}) if isinstance(ACCOUNTS, dict) else {}
            email = str(account.get("email") or _secret_text(f"{prefix}_EMAIL")).strip()
            password = str(account.get("password") or _secret_text(f"{prefix}_PASSWORD")).strip()
            if not email or not password:
                raise RuntimeError(f"缺少「{region}」後台 email/password")

            memo.set_runtime_credentials(email, password)
            session = memo.login(ui_logger=ui_logger)
            try:
                item.update(match_and_reconcile(region, session=session, ui_logger=ui_logger,
                                                only_matched_rows=False))
            finally:
                session.close()
        except Exception as exc:
            errors.append(f"{region}：{exc}")
            item["error"] = str(exc)
            log(f"❌ {region}：{exc}")

    if errors:
        exc = RuntimeError("；".join(errors))
        exc.results = results  # 讓呼叫端仍能印出另一區的結果
        raise exc
    return results


if __name__ == "__main__":
    import sys

    if "--scheduled-unpaid" not in sys.argv:
        raise SystemExit("請指定 --scheduled-unpaid")
    from .atm_schedule import main
    main()
