# memo.py
# -*- coding: utf-8 -*-
# ============================================================
# 更新記錄：
# 2026-11-12
# - 修正訂購人姓名抓錯（例：LC00220267／LC00220310／LC00220316 抓成「清掃坪數」「居家清潔」）：
#   原本取整列文字第一個 2～4 字中文行，姓名不是 2～4 字中文就會抓到服務項目。
#   改為讀「訂購資訊」欄的會員姓名連結（/member?keyword=），讀明細時不再蓋掉。
# - 列表另外讀客戶 LINE 聊天連結（chat.line.biz）存 line_url。
# 2026-11-11
# - preview row 新增 created_at（訂購時間）；新增 preview_section_label／preview_status_text／
#   preview_change_kinds，給 10:30 排程把①②③寫進「客服備註」分頁用（與畫面相同文字）。
# - 加速：讀訂單明細改為同時 5 筆並行（DETAIL_WORKERS），順序與結果不變。
# - 加速：歷史比對只讀「同電話＋同地址、服務日期早於該訂單的最近 3 筆」明細
#   （recent_same_address_history），不再把同電話全部歷史訂單逐筆開頁
#   （例：0966403195 有 81 筆）。服務日期先從列表「服務日期」欄讀。
#   已處理訂單先用列表服務日期篩掉已過期的，再讀明細。
# 2026-11-10
# - 查詢（By 電話／By 搜尋條件）除了未處理訂單，另外檢查同條件內「已處理」且客服備註
#   本來就有內容的訂單（服務日期 ≥ 今天）：標示 **VIP** 但付款方式不是儲值金、或 **N-**
#   已非首次服務 → 列為 section="processed"（畫面③），可勾選執行（保留原備註＋註記）。
#   本來就有客服備註但同地址無歷史的訂單，執行時也保留原備註（不再套固定新成單提醒）。
# - find_latest_same_order 只取服務日期早於目前訂單、非取消／退款的訂單當「前次」。
# - 寫入客服備註成功後，同步檢查會員管理該地址的[備註]（sync_address_memo）：
#   會員管理頁內嵌 memberAddressList 找出同地址的地址 ID → 讀地址備註頁內嵌的
#   list；最上方那則（以上方為主）空白才填入本次寫入的客服備註（去掉【服務異動】
#   行），已有內容不動，其他備註原樣保留一起送出。失敗只記 LOG，不影響訂單結果。
# - 同電話＋同地址，與前次的服務項目或服務時間（時數）不同時，在備註最前面註記：
#   【服務異動】
#   服務項目：前次 居家清潔（清掃坪數21~40、房間2…）
#   　　　　　本次 居家清潔（清掃坪數21~40、窗戶清潔2…）
#   服務時間：前次 14:00-18:00（4小時）／本次 09:00-11:00（2小時）
#   服務項目＝列表「訂購資訊」欄的服務類型＋細項清單；服務時間＝「服務日期」欄
#   的時段（7 小時以上扣 1 小時休息）。compose_copied_notice 預覽與寫入共用，
#   重複複製時舊的異動段落會先移除。前次客服備註空白的訂單，也用最近一筆同電話
#   ＋同地址訂單比對，把異動段落預填到備註欄。
# - 【服務異動】另外註記：
#   付款方式：前次為 VIP（前次客服備註有 **VIP** 或前次用儲值金付款），本次付款
#   方式不是儲值金（信用卡／ATM…）→「付款方式：前次 VIP（儲值金）／本次 信用卡」
#   目前訂單本來就有客服備註：保留原備註不覆蓋，一樣檢查——標示 **VIP** 但本次付款
#   不是儲值金、或有 **N-XXX** 但已不是首次服務（同電話＋同地址有歷史訂單）→ 註記，
#   **N-** 改 **O-**，【服務異動】加在原備註最上方（compose_notice_for）。
#   新客標記：**N-XXX** 代表新客，第二次起不是新客 → 複製的備註裡 **N-B** 改成
#   **O-B**，並註記「新客標記：前次 **N-B**／本次改為 **O-B**」。地址備註補填時
#   也是寫入改好的 **O-** 版本。
# - 修正勾選執行／單筆執行出現 APIError「Page Not Found」：order-system 的
#   env.py 沒有 SHEET_ID、Streamlit secrets 也沒設，memo_log 用空白 ID 開
#   Google Sheet 失敗，整個執行中斷。memo_log 改為輔助紀錄：開不了或寫入
#   失敗只在畫面 LOG 提示，不再擋住後台回寫（get_log_ws_safe）。
# 2026-11-09
# - 查訂單備註改成兩部份：
#   1. 同電話＋同地址之前有訂單 → 自動複製「離現在最近一次已服務日期」
#      的客服備註（服務日期 ≤ 今天且早於目標單，排除取消訂單／已退款，
#      取最近一筆有客服備註的訂單；不再要求來源單已付款＋已處理）。
#   2. 同電話＋同地址之前無訂單 → 只列出訂單號碼／姓名／電話／地址／付款狀態。
#   preview row 新增 has_history 欄位，來源備註預覽改為完整內容。
# - 勾選執行／單筆執行可帶入畫面上編輯過的客服備註（override_notice），
#   有相同訂單但無可複製備註、或無相同訂單的訂單，填入備註後也可執行。
# - preview row 新增 latest_same_order_id／latest_same_order_date（最近一筆
#   同電話＋同地址訂單，供人工參考）。
# - 列表查詢改為自動翻頁（fetch_purchase_list_all_pages），避免同電話
#   超過 20 筆時漏抓最近一次訂單。
# - parse_edit_page 新增 customer_memo（從頁面 Vue purchase JSON 讀取），
#   供獨立功能 function/customer_memo_query.py 使用。
# ============================================================
import re
import json
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional, List, Dict, Callable

import streamlit as st  # 僅用於讀取 st.secrets，不做任何畫面輸出
import requests
from bs4 import BeautifulSoup
import gspread
from google.oauth2.service_account import Credentials

try:
    from shared.text_parsing import _extract_clean_type_line, _extract_person_hour_line
except Exception:  # memo_system 單獨使用時的備援
    _CLEAN_TYPE_LABELS = ["居家清潔", "辦公室清潔", "裝修細清", "大掃除"]

    def _extract_clean_type_line(text):
        return next((label for label in _CLEAN_TYPE_LABELS if label in str(text or "")), "")

    def _extract_person_hour_line(text):
        m = re.search(r"(\d+)\s*人\s*(\d+(?:\.\d+)?)\s*(?:小時|時)", str(text or ""))
        return (m.group(1), m.group(2)) if m else ("", "")


# -----------------------------------------------------------------------------
# Config
# -----------------------------------------------------------------------------
try:
    from . import env  # type: ignore
except Exception:
    class env:  # type: ignore
        ENV = "prod"
        BASE_URL_DEV = "https://backend-dev.lemonclean.com.tw"
        BASE_URL_PROD = "https://backend.lemonclean.com.tw"
        WORKSHEET_NAME = "memo"
        LOG_SHEET_NAME = "memo_log"
        GOOGLE_SERVICE_ACCOUNT_FILE = ""
        SLEEP_SECONDS = 0.5
        SHEET_ID = ""


def secret_value(key: str, default=""):
    try:
        return st.secrets.get(key, default)
    except Exception:
        return default


ENV_NAME = str(secret_value("ENV", getattr(env, "ENV", "prod"))).lower()
BASE_URL_DEV = str(secret_value("BASE_URL_DEV", getattr(env, "BASE_URL_DEV", "https://backend-dev.lemonclean.com.tw")))
BASE_URL_PROD = str(secret_value("BASE_URL_PROD", getattr(env, "BASE_URL_PROD", "https://backend.lemonclean.com.tw")))
SHEET_ID = str(secret_value("SHEET_ID", getattr(env, "SHEET_ID", "")))

BASE_URL = ""
LOGIN_URL = ""
PURCHASE_URL = ""


def set_env(env_name: str):
    global ENV_NAME, BASE_URL, LOGIN_URL, PURCHASE_URL
    ENV_NAME = (env_name or "prod").lower()
    BASE_URL = BASE_URL_DEV if ENV_NAME == "dev" else BASE_URL_PROD
    BASE_URL = BASE_URL.rstrip("/")
    LOGIN_URL = f"{BASE_URL}/login"
    PURCHASE_URL = f"{BASE_URL}/purchase"


set_env(ENV_NAME)

RUNTIME_EMAIL = ""
RUNTIME_PASSWORD = ""


def set_runtime_credentials(email: str, password: str):
    global RUNTIME_EMAIL, RUNTIME_PASSWORD
    RUNTIME_EMAIL = (email or "").strip()
    RUNTIME_PASSWORD = (password or "").strip()


WORKSHEET_NAME = str(secret_value("WORKSHEET_NAME", getattr(env, "WORKSHEET_NAME", "memo")))
LOG_SHEET_NAME = str(secret_value("LOG_SHEET_NAME", getattr(env, "LOG_SHEET_NAME", "memo_log")))
GOOGLE_SERVICE_ACCOUNT_FILE = str(secret_value("GOOGLE_SERVICE_ACCOUNT_FILE", getattr(env, "GOOGLE_SERVICE_ACCOUNT_FILE", "")))
SLEEP_SECONDS = float(secret_value("SLEEP_SECONDS", getattr(env, "SLEEP_SECONDS", 0.5)))

REQUEST_TIMEOUT = 30
MAX_RETRIES = 3
RETRY_BACKOFF = 1.2

CURRENT_ROW_LOGS: List[str] = []

# 新成單（地址完全沒有歷史訂單）時，自動帶入的固定提醒文字
DEFAULT_NEW_ORDER_NOTICE = (
    "請現場跟客戶溝通清潔優先順序，並請回報以下內容\n"
    "＊工作項目＋時間分配\n"
    "＊特別注意事項\n"
    "＊服務小貼心"
)


def make_logger(ui_logger: Optional[Callable[[str], None]] = None):
    def _log(msg: str):
        msg = str(msg)
        print(msg, flush=True)
        CURRENT_ROW_LOGS.append(msg)
        if ui_logger:
            ui_logger(msg)
    return _log


def blank_result():
    return {
        "processed": 0,
        "success": 0,
        "failed": 0,
        "skipped": 0,
        "updated_orders": 0,
        "errors": [],
    }


def with_retry(fn, *args, **kwargs):
    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            last_err = e
            if attempt >= MAX_RETRIES:
                break
            time.sleep(RETRY_BACKOFF * attempt)
    raise last_err


def session_get(session: requests.Session, url: str, **kwargs):
    return with_retry(session.get, url, timeout=REQUEST_TIMEOUT, **kwargs)


def session_post(session: requests.Session, url: str, **kwargs):
    return with_retry(session.post, url, timeout=REQUEST_TIMEOUT, **kwargs)


def normalize_phone(p: str) -> str:
    return re.sub(r"\D+", "", str(p or ""))


def parse_phone_list(text: str) -> List[str]:
    raw = re.split(r"[,\n;、，]+", str(text or ""))
    phones = []
    for x in raw:
        p = normalize_phone(x)
        if p:
            phones.append(p)
    return list(dict.fromkeys(phones))


def normalize_text(t: str) -> str:
    return re.sub(r"\s+", "", str(t or ""))


def normalize_address(addr: str) -> str:
    s = str(addr or "").strip()
    s = normalize_text(s)
    s = s.replace("臺", "台")
    s = s.replace("，", ",")
    s = s.replace("（", "(").replace("）", ")")
    s = s.replace("－", "-").replace("–", "-").replace("—", "-")
    s = s.replace("之", "-")
    s = s.replace("號-", "號")
    s = s.replace("樓-", "樓")
    s = s.replace(",", "")
    s = s.replace("　", "")
    return s


def same_address(a: str, b: str) -> bool:
    na = normalize_address(a)
    nb = normalize_address(b)
    return bool(na and nb and na == nb)


def clip_text(text: str, limit: int = 50000) -> str:
    return str(text or "")[:limit]


def safe_cell(row: List[str], idx_1_based: int) -> str:
    i = idx_1_based - 1
    return str(row[i]).strip() if i < len(row) else ""


def parse_date(t: str):
    if not t:
        return None
    s = str(t).strip()
    for fmt in [
        "%Y/%m/%d",
        "%Y-%m-%d",
        "%Y/%m/%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
        "%Y-%m-%d %H:%M",
    ]:
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            pass
    m = re.search(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", s)
    if m:
        y, mo, d = map(int, m.groups())
        return datetime(y, mo, d)
    return None


def parse_row_spec(spec: str) -> List[int]:
    rows = set()
    for p in str(spec).split(","):
        p = p.strip()
        if not p:
            continue
        if "-" in p:
            a, b = map(int, p.split("-", 1))
            if a > b:
                a, b = b, a
            rows.update(range(a, b + 1))
        else:
            rows.add(int(p))
    return sorted(x for x in rows if x >= 2)


def extract_name_from_text_block(text: str) -> str:
    lines = [x.strip() for x in str(text or "").splitlines() if x.strip()]
    for line in lines:
        if re.search(r"^[\u4e00-\u9fff]{2,4}$", line):
            return line
    return ""


def extract_service_date_from_page_text(page_text: str) -> str:
    text = str(page_text or "")
    m = re.search(r"(\d{4}[/-]\d{2}[/-]\d{2})\s*\([一二三四五六日]\)", text)
    if m:
        return m.group(1).replace("-", "/")
    m = re.search(r"(\d{4}[/-]\d{2}[/-]\d{2})", text)
    if m:
        return m.group(1).replace("-", "/")
    return ""


def extract_address_from_text_block(text: str) -> str:
    text = str(text or "")
    city_pattern = (
        r"(?:台北市|臺北市|新北市|桃園市|新竹市|新竹縣|台中市|臺中市|"
        r"彰化縣|南投縣|雲林縣|嘉義市|嘉義縣|台南市|臺南市|高雄市|"
        r"屏東縣|宜蘭縣|花蓮縣|台東縣|臺東縣|基隆市)"
    )
    patterns = [
        rf"({city_pattern}[^\n]*?號(?:之\d+)?(?:\d+樓)?(?:之\d+)?(?:\d+室)?)",
        rf"({city_pattern}[^\n]*?樓之\d+)",
        rf"({city_pattern}[^\n]*?\d+樓)",
        rf"({city_pattern}[^\n]*?號)",
    ]
    for p in patterns:
        m = re.search(p, text)
        if m:
            return m.group(1).strip()
    return ""


def get_purchase_id_from_edit_url(edit_url: str) -> str:
    m = re.search(r"/purchase/edit/(\d+)", edit_url or "")
    return m.group(1) if m else ""


def display_service_date(item: Dict) -> str:
    return item.get("service_date") or item.get("raw_date_str") or ""


def item_service_date_obj(item: Dict):
    return item.get("service_date_obj") or item.get("raw_date_obj")


def today_tw() -> datetime:
    """台灣時區今天 00:00（naive datetime，方便跟 parse_date 結果比較）。"""
    now = datetime.now(ZoneInfo("Asia/Taipei"))
    return datetime(now.year, now.month, now.day)


def get_spreadsheet():
    """
    v2026.07.11：修正憑證讀取邏輯——原本只檢查 st.secrets["GOOGLE_SERVICE_
    ACCOUNT"]（大寫），但實際部署的 Streamlit secrets 是用小寫的
    "gcp_service_account" 這個 key，導致這裡一直取不到、默默失敗
    （except Exception: pass），接著 fallback 到根本不存在的本機檔案，
    報出誤導性的 FileNotFoundError。且原本的 try/except 範圍太大，連
    open_by_key 的權限錯誤也會被吞掉一起 fallback。
    改成：依序檢查 gcp_service_account（小寫）→ GOOGLE_SERVICE_ACCOUNT
    （大寫）→ 本機檔案，只有「取得憑證」這步會 fallback，open_by_key
    的錯誤會直接拋出。
    """
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    service_account_info = None
    if st is not None:
        try:
            if "gcp_service_account" in st.secrets:
                service_account_info = dict(st.secrets["gcp_service_account"])
            elif "GOOGLE_SERVICE_ACCOUNT" in st.secrets:
                service_account_info = dict(st.secrets["GOOGLE_SERVICE_ACCOUNT"])
        except Exception:
            pass

    if service_account_info is not None:
        creds = Credentials.from_service_account_info(service_account_info, scopes=scopes)
    else:
        creds = Credentials.from_service_account_file(
            GOOGLE_SERVICE_ACCOUNT_FILE,
            scopes=scopes,
        )
    gc = gspread.authorize(creds)
    return gc.open_by_key(SHEET_ID)


def get_ws():
    return get_spreadsheet().worksheet(WORKSHEET_NAME)


def get_log_ws():
    sh = get_spreadsheet()
    try:
        return sh.worksheet(LOG_SHEET_NAME)
    except Exception:
        ws = sh.add_worksheet(title=LOG_SHEET_NAME, rows=1000, cols=20)
        ws.append_row([
            "執行時間",
            "來源",
            "查詢值",
            "電話",
            "客戶姓名",
            "地址",
            "目前訂單",
            "目前服務日期",
            "前次訂單",
            "前次服務日期",
            "前次客服備註",
            "回寫筆數",
            "狀態",
            "錯誤訊息",
            "完整LOG",
        ])
        return ws


def get_log_ws_safe(log=None):
    """
    memo_log 只是輔助紀錄：SHEET_ID 未設定或試算表開不了時回傳 None，
    不中斷後台回寫（執行 Log 另由 memo_router 記錄）。
    """
    if not SHEET_ID:
        if log:
            log("⚠️ 未設定 SHEET_ID，本次不寫入 memo_log 工作表（後台回寫照常執行）")
        return None
    try:
        return get_log_ws()
    except Exception as e:
        if log:
            log(f"⚠️ memo_log 工作表無法開啟，本次不寫入（後台回寫照常執行）：{type(e).__name__}")
        return None


def append_log_row(
    log_ws,
    source_type: str,
    source_value: str,
    phone: str,
    name: str,
    address: str,
    current_order: str,
    current_service_date: str,
    prev_order: str,
    prev_service_date: str,
    prev_notice: str,
    updated_orders: int,
    status: str,
    error_msg: str,
    full_log: str,
):
    if log_ws is None:
        return
    try:
        _append_log_row_raw(log_ws, source_type, source_value, phone, name, address,
                            current_order, current_service_date, prev_order,
                            prev_service_date, prev_notice, updated_orders,
                            status, error_msg, full_log)
    except Exception:
        pass  # memo_log 寫入失敗不影響後台回寫結果


def _append_log_row_raw(log_ws, source_type, source_value, phone, name, address,
                        current_order, current_service_date, prev_order,
                        prev_service_date, prev_notice, updated_orders,
                        status, error_msg, full_log):
    with_retry(
        log_ws.append_row,
        [
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            source_type,
            source_value,
            phone,
            name,
            address,
            current_order,
            current_service_date,
            prev_order,
            prev_service_date,
            clip_text(prev_notice, 2000),
            updated_orders,
            status,
            error_msg,
            clip_text(full_log, 20000),
        ],
    )


def apply_sheet_presentation(ws, updated_rows: List[int]):
    if not updated_rows:
        return

    sheet_id = ws._properties["sheetId"]
    requests_body = []

    for row_num in updated_rows:
        requests_body.append({
            "updateDimensionProperties": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "ROWS",
                    "startIndex": row_num - 1,
                    "endIndex": row_num,
                },
                "properties": {"pixelSize": 21},
                "fields": "pixelSize"
            }
        })

    requests_body.append({
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 1,
                "startColumnIndex": 22,
                "endColumnIndex": 24,
            },
            "cell": {
                "userEnteredFormat": {
                    "wrapStrategy": "CLIP",
                    "verticalAlignment": "MIDDLE"
                }
            },
            "fields": "userEnteredFormat.wrapStrategy,userEnteredFormat.verticalAlignment"
        }
    })

    with_retry(ws.spreadsheet.batch_update, {"requests": requests_body})


def login(ui_logger=None):
    """登入檸檬後台（共用 shared.lemon_backend_login；程式結束時自動登出）。"""
    from shared.lemon_backend_login import login as backend_login

    log = make_logger(ui_logger)
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    })
    try:
        backend_login(s, RUNTIME_EMAIL, RUNTIME_PASSWORD, login_url=LOGIN_URL, check_url=PURCHASE_URL)
    except RuntimeError as exc:
        raise RuntimeError(f"登入失敗，請確認帳密：{exc}") from exc
    log("[登入] 已登入")
    return s


def parse_purchase_row_text(txt: str) -> Dict:
    txt = str(txt or "")

    order_no = ""
    order_m = re.search(r"(LC\d+)", txt)
    if order_m:
        order_no = order_m.group(1)

    dates = re.findall(r"\d{4}-\d{2}-\d{2}", txt)
    raw_date_str = dates[0].replace("-", "/") if dates else ""
    raw_date_obj = parse_date(dates[0]) if dates else None

    status = ""
    status_code = ""
    if "未處理" in txt:
        status = "未處理"
        status_code = "0"
    elif "已處理" in txt:
        status = "已處理"
        status_code = "1"
    elif "已完成" in txt:
        status = "已完成"
        status_code = "2"

    purchase_status_name = ""
    purchase_status = ""
    if "待付款" in txt or "未付款" in txt:
        purchase_status_name = "未付款"
        purchase_status = "0"
    elif "已付款" in txt:
        purchase_status_name = "已付款"
        purchase_status = "1"
    elif "取消訂單" in txt:
        purchase_status_name = "取消訂單"
        purchase_status = "2"
    elif "已退款" in txt:
        purchase_status_name = "已退款"
        purchase_status = "3"

    address = extract_address_from_text_block(txt)
    name = extract_name_from_text_block(txt)

    phone = ""
    m_phone = re.search(r"(09\d{8})", txt)
    if m_phone:
        phone = m_phone.group(1)

    return {
        "order_no": order_no,
        "raw_date_str": raw_date_str,
        "raw_date_obj": raw_date_obj,
        "status": status,
        "status_code": status_code,
        "address": address,
        "phone": phone,
        "name": name,
        "purchase_status_name": purchase_status_name,
        "purchase_status": purchase_status,
        "service_date": "",
        "service_date_obj": None,
        "notice": "",
        "clean_type": _extract_clean_type_line(txt),
        "period": extract_period(txt),
        "payway": extract_payway(txt),
        "hour": period_hours(extract_period(txt)) or normalize_hour(_extract_person_hour_line(txt)[1]),
        "service_items": [],
        "row_text": txt,
        "_detail": {},
    }


def parse_purchase_list_page(html: str) -> List[Dict]:
    soup = BeautifulSoup(html, "html.parser")
    data = []

    rows = soup.select("table tbody tr")
    if not rows:
        rows = soup.select("tr")

    for tr in rows:
        txt = tr.get_text("\n", strip=True)
        row_data = parse_purchase_row_text(txt)
        if not row_data["order_no"]:
            continue

        tds = tr.find_all("td", recursive=False)
        info_td = tds[1] if len(tds) > 1 else tr
        name_tag = info_td.select_one('a[href*="/member?keyword"]') or tr.select_one('a[href*="/member?keyword"]')
        if name_tag and name_tag.get_text(strip=True):
            row_data["name"] = name_tag.get_text(strip=True)
        line_tag = tr.select_one('a[href*="chat.line.biz"]')
        row_data["line_url"] = line_tag.get("href", "").strip() if line_tag else ""
        row_data["service_items"] = [li.get_text(" ", strip=True) for li in info_td.find_all("li")]
        if len(tds) > 2:
            m_sd = re.search(r"\d{4}-\d{2}-\d{2}", tds[2].get_text(" ", strip=True))
            if m_sd:
                row_data["service_date_obj"] = parse_date(m_sd.group(0))
                row_data["service_date"] = m_sd.group(0).replace("-", "/")

        edit_link = tr.select_one('a[href*="/purchase/edit/"]')
        edit_url = f"{BASE_URL}{edit_link['href']}" if edit_link and edit_link.get("href", "").startswith("/") else (edit_link["href"] if edit_link else "")
        row_data["edit_url"] = edit_url
        row_data["purchase_id"] = get_purchase_id_from_edit_url(edit_url)
        data.append(row_data)

    dedup = {}
    for item in data:
        dedup[item["order_no"]] = item
    return list(dedup.values())


LIST_MAX_PAGES = 100
PHONE_HISTORY_MAX_PAGES = 15


def fetch_purchase_list_all_pages(session, params: Dict, max_pages: int = LIST_MAX_PAGES, log=None, debug_first_page: bool = False) -> List[Dict]:
    """
    依同一組條件自動翻頁抓列表（後台每頁 20 筆）。
    沒有資料或整頁都是已抓過的訂單時停止，避免後台忽略 page 參數造成無窮迴圈。
    """
    merged: Dict[str, Dict] = {}
    for page in range(1, max_pages + 1):
        page_params = dict(params)
        page_params["page"] = str(page)
        r = session_get(session, PURCHASE_URL, params=page_params)
        r.raise_for_status()

        if log and debug_first_page and page == 1:
            debug_dump_list_rows(r.text, log, max_rows=20)

        items = parse_purchase_list_page(r.text)
        new_items = [x for x in items if x.get("order_no") and x["order_no"] not in merged]
        if not new_items:
            break
        for x in new_items:
            merged[x["order_no"]] = x
        if log and page > 1:
            log(f"[翻頁] 第 {page} 頁，累計 {len(merged)} 筆")
    else:
        if log:
            log(f"⚠️ 已達翻頁上限 {max_pages} 頁，結果可能不完整")
    return list(merged.values())


def blank_list_params() -> Dict:
    return {
        "keyword": "", "name": "", "phone": "", "orderNo": "",
        "date_s": "", "date_e": "", "clean_date_s": "", "clean_date_e": "",
        "paid_at_s": "", "paid_at_e": "", "refundDateS": "", "refundDateE": "",
        "buy": "", "area_id": "", "isCharge": "", "isRefund": "", "payway": "",
        "purchase_status": "", "progress_status": "", "invoiceStatus": "",
        "otherFee": "", "orderBy": "",
    }


def search_all_orders_by_phone(session, phone, log=None) -> List[Dict]:
    params = blank_list_params()
    params["phone"] = phone
    return fetch_purchase_list_all_pages(
        session, params, max_pages=PHONE_HISTORY_MAX_PAGES, log=log, debug_first_page=bool(log)
    )


def debug_dump_list_rows(html: str, log, max_rows: int = 20):
    """
    暫時除錯用：把列表頁每一列的原始文字印到 log 裡，
    用來確認「未處理／已處理／已完成」這幾個字到底有沒有真的出現在頁面文字裡，
    以及解析出來的 status / status_code 是否正確。
    確認完問題後可以把呼叫這個函式的地方移除。
    """
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.select("table tbody tr")
    if not rows:
        rows = soup.select("tr")

    log(f"[DEBUG] 列表頁原始 <tr> 數量：{len(rows)}")

    shown = 0
    for tr in rows:
        txt = tr.get_text(" | ", strip=True)
        if not txt:
            continue
        if shown >= max_rows:
            log(f"[DEBUG] 已超過 {max_rows} 列，後面省略")
            break

        parsed = parse_purchase_row_text(tr.get_text("\n", strip=True))
        log(f"[DEBUG] ----- 第 {shown + 1} 列 -----")
        log(f"[DEBUG] 原始文字：{txt[:300]}")
        log(f"[DEBUG] 解析結果：order_no={parsed['order_no']}，status={parsed['status']}，status_code={parsed['status_code']}，purchase_status_name={parsed['purchase_status_name']}")
        shown += 1


def search_orders_by_order_no(session, order_no: str) -> List[Dict]:
    r = session_get(
        session,
        PURCHASE_URL,
        params={
            "keyword": "",
            "name": "",
            "phone": "",
            "orderNo": order_no,
            "date_s": "",
            "date_e": "",
            "clean_date_s": "",
            "clean_date_e": "",
            "paid_at_s": "",
            "paid_at_e": "",
            "refundDateS": "",
            "refundDateE": "",
            "buy": "",
            "area_id": "",
            "isCharge": "",
            "isRefund": "",
            "payway": "",
            "purchase_status": "",
            "progress_status": "",
            "invoiceStatus": "",
            "otherFee": "",
            "orderBy": "",
        },
    )
    r.raise_for_status()
    return parse_purchase_list_page(r.text)


def search_by_conditions_once(session, date_mode: str, date_start: str, date_end: str, purchase_status_name: str,
                              progress: str = "0") -> List[Dict]:
    purchase_status_map = {
        "未付款": "0",
        "已付款": "1",
    }
    purchase_status = purchase_status_map.get(purchase_status_name, "")

    params = {
        "keyword": "",
        "name": "",
        "phone": "",
        "orderNo": "",
        "date_s": "",
        "date_e": "",
        "clean_date_s": "",
        "clean_date_e": "",
        "paid_at_s": "",
        "paid_at_e": "",
        "refundDateS": "",
        "refundDateE": "",
        "buy": "",
        "area_id": "",
        "isCharge": "",
        "isRefund": "",
        "payway": "",
        "purchase_status": purchase_status,
        "progress_status": progress,
        "invoiceStatus": "",
        "otherFee": "",
        "orderBy": "",
    }

    if date_mode == "服務日期":
        params["clean_date_s"] = (date_start or "").replace("/", "-")
        params["clean_date_e"] = (date_end or "").replace("/", "-")
    else:
        params["date_s"] = (date_start or "").replace("/", "-")
        params["date_e"] = (date_end or "").replace("/", "-")

    items = fetch_purchase_list_all_pages(session, params)
    filtered = [
        x for x in items
        if x.get("status_code") == progress and (not purchase_status or x.get("purchase_status") == purchase_status)
    ]
    return filtered


def search_by_conditions(session, date_mode: str, date_start: str, date_end: str, purchase_status_name: str,
                         progress: str = "0") -> List[Dict]:
    if purchase_status_name == "全部":
        unpaid = search_by_conditions_once(session, date_mode, date_start, date_end, "未付款", progress)
        paid = search_by_conditions_once(session, date_mode, date_start, date_end, "已付款", progress)
        merged = {}
        for x in unpaid + paid:
            merged[x["order_no"]] = x
        items = list(merged.values())
        items.sort(key=lambda x: (display_service_date(x), x.get("order_no", "")))
        return items

    return search_by_conditions_once(session, date_mode, date_start, date_end, purchase_status_name, progress)


NOTICE_FLAG_KEYS = ("付款方式：", "新客標記：")


def is_notice_flag_row(row: Dict) -> bool:
    """客服備註需註記：標示 VIP 但非儲值金付款、或 **N- 已非首次服務。"""
    change = str(row.get("service_change", "") or "")
    return any(k in change for k in NOTICE_FLAG_KEYS)


def might_need_notice_flag(item: Dict) -> bool:
    own = strip_change_block(item.get("notice", ""))
    return bool(own) and (VIP_TAG in own or bool(N_TAG_RE.search(own)))


def upcoming(item: Dict) -> bool:
    dt = item_service_date_obj(item)
    return bool(dt) and dt >= today_tw()


HISTORY_LIMIT = 3


def recent_same_address_history(session, target: Dict, phone_list_cache: Dict, log=None,
                                limit: int = HISTORY_LIMIT) -> List[Dict]:
    """
    同電話＋同地址、服務日期早於目標訂單的最近 limit 筆（排除取消／退款）；只讀這幾筆的明細。
    回傳 [target] + 這幾筆，給 build_preview_row 用。
    phone_list_cache：{電話: 列表（未讀明細，讀過明細的會就地更新）}
    """
    phone = normalize_phone(target.get("phone", ""))
    if not phone:
        return [target]
    if phone not in phone_list_cache:
        phone_list_cache[phone] = search_all_orders_by_phone(session, phone)
        if log:
            log(f"[歷史比對] 電話 {phone} 共 {len(phone_list_cache[phone])} 筆（只讀同地址最近 {limit} 筆明細）")
    target_dt = item_service_date_obj(target)
    same = [
        x for x in phone_list_cache[phone]
        if x.get("order_no") != target.get("order_no")
        and x.get("purchase_status") not in ("2", "3")
        and same_address(x.get("address", ""), target.get("address", ""))
        and item_service_date_obj(x)
        and (not target_dt or item_service_date_obj(x) < target_dt)
    ]
    same.sort(key=lambda k: item_service_date_obj(k), reverse=True)
    picked = same[:limit]
    todo = [x for x in picked if not x.get("_detail")]
    if todo:
        enrich_items_from_detail(session, todo, phone, log=None)
    return [target] + picked


def processed_flag_rows(items: List[Dict], history_for, log=None) -> List[Dict]:
    """
    已處理、服務日期 ≥ 今天、客服備註本來就有內容的訂單中，需註記的列（section="processed"）。
    history_for(item) 回傳同電話歷史訂單（判斷 **N- 是否已非首次服務）。
    """
    rows = []
    for item in items:
        if item.get("status_code") != "1" or not upcoming(item) or not might_need_notice_flag(item):
            continue
        row = build_preview_row(item, history_for(item))
        if not is_notice_flag_row(row):
            continue
        row["section"] = "processed"
        row["can_autofill"] = True
        rows.append(row)
    if log:
        log(f"[已處理客服備註檢查] 需註記 {len(rows)} 筆")
    return rows


def parse_select_value(select_el):
    """
    解析 <select> 目前選中的值。
    注意：原本的 fallback（用整個 select 的文字內容比對「已完成/已處理/未處理」）
    是不準確的，因為一個 <select> 通常會把所有選項文字都印在 DOM 裡，
    並非只有「目前選中」的那一個，這樣比對永遠會先命中「已完成」。
    這裡保留 option[selected] 的判斷（如果後台確實有輸出 selected 屬性），
    其餘狀況一律回傳空字串，交由呼叫端（列表頁解析結果）決定真正的狀態，
    不要再用這個 fallback 文字比對法。
    """
    selected = select_el.select_one("option[selected]")
    if selected is not None:
        return selected.get("value", "")

    # 找不到 selected 屬性時，不要用全文字比對猜測（不可靠），直接回傳空字串。
    return ""


CHANGE_PREFIXES = ("【服務異動】", "【時數異動】")


def normalize_hour(value) -> str:
    """時數統一成字串：3.0 → "3"、2.5 → "2.5"；空值或 0 回傳空字串。"""
    text = str(value if value is not None else "").strip()
    if not text:
        return ""
    try:
        num = float(text)
    except ValueError:
        return text
    if num <= 0:
        return ""
    return str(int(num)) if num.is_integer() else str(num)


VIP_TAG = "**VIP**"
STORED_VALUE_PAYWAY = "儲值金"
N_TAG_RE = re.compile(r"\*\*N-[^*\s]+\*\*")


def extract_payway(text: str) -> str:
    """列表卡片付款資訊的「付款方式：信用卡」。"""
    m = re.search(r"付款方式\s*[：:]\s*([^\s\n]+)", str(text or ""))
    return m.group(1).strip() if m else ""


def extract_period(text: str) -> str:
    """列表卡片的服務時段，例：09:00 - 11:00 → 09:00-11:00。"""
    m = re.search(r"(\d{1,2}:\d{2})\s*[-~～]\s*(\d{1,2}:\d{2})", str(text or ""))
    return f"{m.group(1).zfill(5)}-{m.group(2).zfill(5)}" if m else ""


def period_hours(period: str) -> str:
    """時段換算服務時數；7 小時以上扣 1 小時休息（09:00-18:00 → 8）。"""
    m = re.match(r"(\d{2}):(\d{2})-(\d{2}):(\d{2})$", str(period or ""))
    if not m:
        return ""
    h1, m1, h2, m2 = (int(x) for x in m.groups())
    hours = ((h2 * 60 + m2) - (h1 * 60 + m1)) / 60
    if hours <= 0:
        return ""
    if hours >= 7:
        hours -= 1
    return normalize_hour(hours)


def service_items_text(item: Dict) -> str:
    """服務項目：服務類型＋細項，例：居家清潔（清掃坪數21~40、房間2）。"""
    clean_type = str(item.get("clean_type", "") or "").strip()
    items = [str(x).strip() for x in (item.get("service_items") or []) if str(x).strip()]
    if items:
        return f"{clean_type}（{'、'.join(items)}）" if clean_type else "、".join(items)
    return clean_type


def service_time_text(item: Dict) -> str:
    period = str(item.get("period", "") or "")
    hour = normalize_hour(item.get("hour"))
    if period and hour:
        return f"{period}（{hour}小時）"
    return period or (f"{hour}小時" if hour else "")


def service_change_text(prev: Dict, cur: Dict, has_history: bool = True) -> str:
    """
    要註記的異動；沒有異動回傳空字串。
    - 服務項目／服務時間：和前次（prev）比，兩邊都有值且不同才列出
    - 付款方式：前次是 VIP（前次備註有 **VIP** 或前次用儲值金），或本次訂單原備註標示 **VIP**，
      但本次付款方式不是儲值金
    - 新客標記：前次備註或本次原備註有 **N-XXX**，且已不是首次服務（has_history）
    """
    prev = prev or {}
    cur = cur or {}
    lines = []
    if prev and cur:
        prev_items = (str(prev.get("clean_type", "")).strip(), sorted(str(x).strip() for x in (prev.get("service_items") or [])))
        cur_items = (str(cur.get("clean_type", "")).strip(), sorted(str(x).strip() for x in (cur.get("service_items") or [])))
        if (prev_items[0] or prev_items[1]) and (cur_items[0] or cur_items[1]) and prev_items != cur_items:
            lines.append(f"服務項目：前次 {service_items_text(prev)}")
            lines.append(f"　　　　　本次 {service_items_text(cur)}")
        ph, ch = normalize_hour(prev.get("hour")), normalize_hour(cur.get("hour"))
        if ph and ch and ph != ch:
            lines.append(f"服務時間：前次 {service_time_text(prev)}／本次 {service_time_text(cur)}")

    prev_notice = strip_change_block(prev.get("notice", ""))  # 只看備註本文，不看舊的異動段落
    own_notice = strip_change_block(cur.get("notice", ""))
    cur_payway = str(cur.get("payway", "") or "").strip()
    prev_is_vip = bool(prev) and (VIP_TAG in prev_notice or str(prev.get("payway", "")).strip() == STORED_VALUE_PAYWAY)
    if cur_payway and cur_payway != STORED_VALUE_PAYWAY:
        if prev_is_vip:
            lines.append(f"付款方式：前次 VIP（{STORED_VALUE_PAYWAY}）／本次 {cur_payway}")
        elif VIP_TAG in own_notice:
            lines.append(f"付款方式：備註標示 VIP／本次 {cur_payway}（非{STORED_VALUE_PAYWAY}）")

    if has_history:
        n_tags = []
        for tag in N_TAG_RE.findall(prev_notice) + N_TAG_RE.findall(own_notice):
            if tag not in n_tags:
                n_tags.append(tag)
        if n_tags:
            lines.append(f"新客標記：{'、'.join(n_tags)} 已非首次服務／本次改為 {'、'.join(to_returning_tag(t) for t in n_tags)}")
    return "\n".join(lines)


def to_returning_tag(tag: str) -> str:
    """新客標記改舊客：**N-B** → **O-B**。"""
    return re.sub(r"^\*\*N-", "**O-", tag)


def convert_new_customer_tags(notice: str) -> str:
    """備註裡所有 **N-XXX** 改成 **O-XXX**（第二次起不是新客）。"""
    return N_TAG_RE.sub(lambda m: to_returning_tag(m.group(0)), str(notice or ""))


def strip_change_block(notice: str) -> str:
    """移除舊的【服務異動】段落（標題行＋緊接的服務項目／服務時間行）。"""
    out, skipping = [], False
    for ln in str(notice or "").strip().splitlines():
        t = ln.strip()
        if t.startswith(CHANGE_PREFIXES):
            skipping = True
            continue
        if skipping and (t.startswith(("服務項目：", "服務時間：", "時數：", "付款方式：", "前次標記：", "新客標記：")) or ln.startswith("　　　　　")):
            continue
        skipping = False
        out.append(ln)
    return "\n".join(out).strip()


def compose_notice_for(target: Dict, prev: Optional[Dict], source: Optional[Dict], has_history: bool) -> str:
    """
    要寫入目前訂單的客服備註：
    - 目前訂單本來就有客服備註 → 保留原備註（不覆蓋）
    - 沒有 → 複製來源單（最近一次已服務）的客服備註
    已非首次服務時 **N-** 改 **O-**；有異動時在最上方加【服務異動】段落。
    """
    own = strip_change_block((target or {}).get("notice", ""))
    base = own or (strip_change_block(source.get("notice", "")) if source else "")
    body = convert_new_customer_tags(base) if has_history else base
    change = service_change_text(prev or {}, target or {}, has_history)
    if change:
        block = f"{CHANGE_PREFIXES[0]}\n{change}"
        return f"{block}\n\n{body}" if body else block
    return body


def compose_copied_notice(source_notice: str, prev: Optional[Dict], cur: Optional[Dict]) -> str:
    """
    複製前次客服備註；服務項目或服務時數與前次不同時，在最前面加【服務異動】段落。
    來源備註裡舊的異動段落先移除，避免一直累加。
    """
    change = service_change_text(prev or {}, cur or {})
    body = convert_new_customer_tags(strip_change_block(source_notice))
    if change:
        block = f"{CHANGE_PREFIXES[0]}\n{change}"
        return f"{block}\n\n{body}" if body else block
    return body


def parse_purchase_json(page_html: str) -> Dict:
    """讀取訂單修改頁內嵌的 Vue purchase 物件（同 cancel_order._parse_purchase_json）。"""
    m = re.search(r"purchase:\s*(\{.*?\})\s*\n?\s*\}\s*\n?\s*\}", page_html or "", re.S)
    if not m:
        return {}
    try:
        return json.loads(m.group(1))
    except Exception:
        return {}


def parse_edit_page(session, edit_url, phone=""):
    params = {}
    if phone:
        params["phone"] = phone

    r = session_get(session, edit_url, params=params)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    form = soup.select_one("form")
    if not form:
        raise RuntimeError(f"找不到表單: {edit_url}")

    action = form.get("action") or edit_url
    if action.startswith("/"):
        action = f"{BASE_URL}{action}"

    current_query_params = {}
    if "?" in r.url:
        query = r.url.split("?", 1)[1]
        for pair in query.split("&"):
            if "=" in pair:
                k, v = pair.split("=", 1)
                current_query_params[k] = v

    fields = {}
    for el in form.select("input, textarea, select"):
        name = el.get("name")
        if not name:
            continue

        tag = el.name.lower()
        if tag == "textarea":
            fields[name] = el.text or ""
        elif tag == "select":
            fields[name] = parse_select_value(el)
        else:
            input_type = (el.get("type") or "text").lower()
            if input_type in ("checkbox", "radio"):
                if el.has_attr("checked"):
                    fields[name] = el.get("value", "on")
            else:
                fields[name] = el.get("value", "")

    if "_token" not in fields:
        token_el = soup.select_one("input[name=_token]")
        if token_el:
            fields["_token"] = token_el.get("value", "")

    page_text = soup.get_text("\n", strip=True)

    notice_el = soup.select_one('textarea[name="notice"]')
    notice = notice_el.text.strip() if notice_el else str(fields.get("notice", "")).strip()

    # 客人備註是 Vue 渲染欄位，真正的值在頁面內嵌的 purchase JSON
    purchase_json = parse_purchase_json(r.text)
    customer_memo = str(purchase_json.get("memo") or fields.get("memo", "") or "").strip()

    order_no = ""
    m = re.search(r"(LC\d+)", page_text)
    if m:
        order_no = m.group(1)

    service_date = extract_service_date_from_page_text(page_text)

    customer_name = str(fields.get("name", "") or fields.get("customer_name", "") or "").strip()
    phone_value = str(fields.get("phone", "")).strip()
    address_value = str(fields.get("address", "")).strip()
    progress = str(fields.get("progress", "") or fields.get("progress_status", "")).strip()
    purchase_status = str(fields.get("purchase_status", "")).strip()
    hour_value = normalize_hour(purchase_json.get("hour") if purchase_json.get("hour") not in (None, "") else fields.get("hour", ""))
    person_value = str(purchase_json.get("person") if purchase_json.get("person") not in (None, "") else fields.get("person", "") or "").strip()

    purchase_id = get_purchase_id_from_edit_url(edit_url)

    purchase_status_name = ""
    if purchase_status == "0":
        purchase_status_name = "未付款"
    elif purchase_status == "1":
        purchase_status_name = "已付款"
    elif purchase_status == "2":
        purchase_status_name = "取消訂單"
    elif purchase_status == "3":
        purchase_status_name = "已退款"

    status_name = ""
    if progress == "0":
        status_name = "未處理"
    elif progress == "1":
        status_name = "已處理"
    elif progress == "2":
        status_name = "已完成"

    return {
        "action": action,
        "fields": fields,
        "notice": notice,
        "customer_memo": customer_memo,
        "hour": hour_value,
        "person": person_value,
        "progress": progress,
        "status_name": status_name,
        "purchase_status": purchase_status,
        "purchase_status_name": purchase_status_name,
        "order_no": order_no,
        "purchase_id": purchase_id,
        "edit_url": r.url,
        "query_params": current_query_params,
        "customer_name": customer_name,
        "phone": phone_value,
        "address": address_value,
        "page_text": page_text,
        "service_date": service_date,
        "service_date_obj": parse_date(service_date),
    }


def enrich_item_from_detail(session, item: Dict, phone="") -> Dict:
    if not item.get("edit_url"):
        return item

    detail = parse_edit_page(session, item["edit_url"], phone)
    item["service_date"] = detail.get("service_date", "") or item.get("service_date", "")
    item["service_date_obj"] = detail.get("service_date_obj") or item.get("service_date_obj")
    item["phone"] = detail.get("phone", "") or item.get("phone", "")
    item["name"] = item.get("name", "") or detail.get("customer_name", "")  # 列表姓名連結較準
    item["address"] = detail.get("address", "") or item.get("address", "")
    item["purchase_status_name"] = detail.get("purchase_status_name", "") or item.get("purchase_status_name", "")
    item["purchase_status"] = detail.get("purchase_status", "") or item.get("purchase_status", "")

    # progress / status_code / status：以列表頁解析結果為準。
    # 列表頁文字判斷（parse_purchase_row_text）是可靠的，因為列表頁每一列只會印出
    # 「目前」這一個狀態文字；明細頁的 <select> 解析（parse_select_value）目前不可靠，
    # 找不到 selected 屬性時只能回傳空字串，所以這裡只在列表頁原本沒有值時才採用明細頁的值，
    # 絕不能讓明細頁覆蓋掉列表頁已經判斷正確的狀態。
    if not item.get("progress"):
        item["progress"] = detail.get("progress", "")
    if not item.get("status_code"):
        item["status_code"] = detail.get("progress", "")
    if not item.get("status"):
        item["status"] = detail.get("status_name", "")

    item["notice"] = detail.get("notice", "") or item.get("notice", "")
    item["hour"] = item.get("hour", "") or detail.get("hour", "")
    item["person"] = detail.get("person", "") or item.get("person", "")
    item["customer_memo"] = detail.get("customer_memo", "") or item.get("customer_memo", "")
    item["_detail"] = detail
    return item


DETAIL_WORKERS = 5


def enrich_items_from_detail(session, items: List[Dict], phone="", log=None, context_label="") -> List[Dict]:
    """逐筆讀訂單修改頁補明細；同時 DETAIL_WORKERS 筆並行，回傳順序與輸入相同。"""
    from concurrent.futures import ThreadPoolExecutor

    total = len(items)
    if log and context_label:
        log(f"[明細補抓] {context_label}，共 {total} 筆")
    if not items:
        return []

    def _one(item):
        try:
            return enrich_item_from_detail(session, item, phone), None
        except Exception as e:
            return item, e

    result = []
    with ThreadPoolExecutor(max_workers=min(DETAIL_WORKERS, total)) as pool:
        for idx, (item, err) in enumerate(pool.map(_one, items), start=1):
            if err and log:
                log(f"[明細補抓失敗] {item.get('order_no', '')}：{err}")
            result.append(item)
            if log and (idx == total or idx == 1 or idx % 10 == 0):
                log(f"[明細補抓進度] {idx}/{total}")
    return result


def same_phone(a: str, b: str) -> bool:
    pa, pb = normalize_phone(a), normalize_phone(b)
    return not pa or not pb or pa == pb


def has_any_same_address_history(current_item: Dict, history_items: List[Dict]) -> bool:
    """
    判斷「同電話＋同地址」之前有沒有任何其他訂單（不論付款／處理狀態、不論備註是否為空）。
    有 → 第一部份（複製客服備註）；沒有 → 第二部份（只列出基本資料）。
    """
    current_order_no = current_item.get("order_no", "")
    current_phone = current_item.get("phone", "")
    current_addr = current_item.get("address", "")

    for x in history_items:
        if x.get("order_no") == current_order_no:
            continue
        if not same_phone(x.get("phone", ""), current_phone):
            continue
        if same_address(x.get("address", ""), current_addr):
            return True
    return False


def find_best_source_order(current_item: Dict, history_items: List[Dict]) -> Optional[Dict]:
    """
    找「同電話＋同地址」離現在最近一次已服務的訂單（有客服備註）。
    已服務：服務日期 ≤ 今天（台灣時區），且早於目標單服務日期；排除取消訂單／已退款。
    """
    candidates = []

    current_order_no = current_item.get("order_no", "")
    current_phone = current_item.get("phone", "")
    current_addr = current_item.get("address", "")
    current_dt = item_service_date_obj(current_item)
    today = today_tw()

    for x in history_items:
        if x.get("order_no") == current_order_no:
            continue
        if not same_phone(x.get("phone", ""), current_phone):
            continue
        if not same_address(x.get("address", ""), current_addr):
            continue

        dt = item_service_date_obj(x)
        if not dt:
            continue
        if dt > today:
            continue
        if current_dt and dt >= current_dt:
            continue

        if x.get("purchase_status") in ("2", "3"):
            continue

        notice = str(x.get("notice", "")).strip()
        if not notice:
            continue

        candidates.append(x)

    if not candidates:
        return None

    candidates.sort(key=lambda k: item_service_date_obj(k), reverse=True)
    return candidates[0]


def find_latest_same_order(current_item: Dict, history_items: List[Dict]) -> Optional[Dict]:
    """最近一筆同電話＋同地址的其他訂單（不限狀態、不限備註），供人工參考。"""
    same = [
        x for x in history_items
        if x.get("order_no") != current_item.get("order_no")
        and same_phone(x.get("phone", ""), current_item.get("phone", ""))
        and same_address(x.get("address", ""), current_item.get("address", ""))
        and item_service_date_obj(x)
        and x.get("purchase_status") not in ("2", "3")
    ]
    # 「前次」只算服務日期早於目前訂單的（不把之後的訂單當成前次）
    current_dt = item_service_date_obj(current_item)
    if current_dt:
        same = [x for x in same if item_service_date_obj(x) < current_dt]
    if not same:
        return None
    same.sort(key=lambda k: item_service_date_obj(k), reverse=True)
    return same[0]


def order_created_at_text(item: Dict) -> str:
    """列表卡片「訂購資訊」的訂購時間（第一個 YYYY-MM-DD HH:MM[:SS]），沒有回傳空字串。"""
    m = re.search(r"(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2}(?::\d{2})?)", str(item.get("row_text", "") or ""))
    return f"{m.group(1)} {m.group(2)}" if m else ""


def preview_section_label(row: Dict) -> str:
    if row.get("section") == "processed":
        return "③ 已處理需註記"
    if row.get("has_history", not row.get("is_new_order")):
        return "① 有相同訂單"
    return "② 無相同訂單"


def preview_status_text(row: Dict) -> str:
    if row.get("own_notice"):
        return "保留原備註＋註記" if row.get("service_change") else "保留原備註"
    if row.get("can_autofill"):
        return "複製最近已服務備註"
    if row.get("has_history", not row.get("is_new_order")):
        return "前次備註空白，請填寫"
    return "新客，請填寫"


def preview_change_kinds(row: Dict) -> str:
    change = str(row.get("service_change", "") or "")
    kinds = [label for key, label in (("服務項目：", "項目"), ("服務時間：", "時間"), ("付款方式：", "付款"), ("新客標記：", "N→O"))
             if key in change]
    return ("⚠️ " + "／".join(kinds)) if kinds else ""


def build_preview_row(target: Dict, history_items: List[Dict]) -> Dict:
    has_history = has_any_same_address_history(target, history_items)
    source = find_best_source_order(target, history_items) if has_history else None
    latest = find_latest_same_order(target, history_items) if has_history and not source else None
    own_notice = strip_change_block(target.get("notice", ""))

    return {
        "created_at": order_created_at_text(target),
        "order_id": target.get("order_no", ""),
        "customer_name": target.get("name", ""),
        "line_url": target.get("line_url", ""),
        "phone": target.get("phone", ""),
        "address": target.get("address", ""),
        "service_date": display_service_date(target),
        "purchase_status_name": target.get("purchase_status_name", ""),
        "status_name": target.get("status", ""),
        "source_order_id": source.get("order_no", "") if source else "",
        "source_service_date": display_service_date(source) if source else "",
        "source_purchase_status_name": source.get("purchase_status_name", "") if source else "",
        "source_status_name": source.get("status", "") if source else "",
        "source_notice_exists": bool(source),
        # 原本有客服備註：保留＋註記；沒有：複製來源備註＋異動段落；都沒有：只預填異動段落
        "source_notice_preview": compose_notice_for(target, source or latest, source, has_history),
        "own_notice": own_notice,
        "hour": normalize_hour(target.get("hour")),
        "source_hour": normalize_hour((source or latest or {}).get("hour")),
        "service_items_text": service_items_text(target),
        "source_service_items_text": service_items_text(source or latest) if (source or latest) else "",
        "service_time_text": service_time_text(target),
        "source_service_time_text": service_time_text(source or latest) if (source or latest) else "",
        "service_change": service_change_text(source or latest or {}, target, has_history),
        "latest_same_order_id": latest.get("order_no", "") if latest else "",
        "latest_same_order_date": display_service_date(latest) if latest else "",
        "has_history": has_history,
        "can_autofill": bool(source) or (bool(own_notice) and has_history),
        "is_new_order": not has_history,
    }


def submit_update(session, form_info, phone, new_notice):
    action = form_info["action"]
    fields = dict(form_info["fields"])
    query_params = dict(form_info.get("query_params", {}))

    if "notice" in fields:
        fields["notice"] = new_notice
    elif "purchase[notice]" in fields:
        fields["purchase[notice]"] = new_notice
    else:
        fields["notice"] = new_notice

    updated_progress = False
    for key in ["progress", "progress_status", "purchase[progress]", "purchase[progress_status]"]:
        if key in fields:
            fields[key] = "1"
            updated_progress = True
    if not updated_progress:
        fields["progress"] = "1"

    if form_info.get("purchase_id") and "id" not in query_params:
        query_params["id"] = form_info["purchase_id"]

    if phone and "phone" not in query_params:
        query_params["phone"] = phone

    resp = session_post(
        session,
        action,
        params=query_params,
        data=fields,
        headers={
            "Referer": form_info["edit_url"],
            "User-Agent": "Mozilla/5.0",
        },
        allow_redirects=True,
    )
    resp.raise_for_status()
    return resp


def verify_update(session, edit_url, phone, expected_notice, order_no=None):
    form = parse_edit_page(session, edit_url, phone)

    actual_notice = str(form.get("notice", "")).strip()

    norm_expected = normalize_text(expected_notice)
    norm_actual = normalize_text(actual_notice)

    notice_ok = norm_actual == norm_expected or (norm_expected[:20] and norm_expected[:20] in norm_actual)

    if order_no:
        # 處理狀態（progress）改用「重新查詢列表頁」來判斷，因為明細頁的 <select> 解析
        # 目前不可靠（找不到 selected 屬性時無法判斷目前選中哪個選項）；
        # 列表頁文字判斷是可靠的（每一列只會印出「目前」這一個狀態文字）。
        rows = search_orders_by_order_no(session, order_no)
        row = next((x for x in rows if x.get("order_no") == order_no), None)
        progress_ok = bool(row) and row.get("status_code") == "1"
    else:
        actual_progress = str(form.get("progress", "")).strip()
        progress_ok = actual_progress == "1"

    return notice_ok and progress_ok, form


def get_target_and_source_for_order(session, target: Dict, log, override_notice: Optional[str] = None) -> Dict:
    target_order_no = target.get("order_no", "")
    target_form = parse_edit_page(session, target["edit_url"], target.get("phone", ""))

    target_phone = normalize_phone(target_form.get("phone", "") or target.get("phone", ""))
    target_name = target_form.get("customer_name", "") or target.get("name", "")
    target_addr = target_form.get("address", "") or target.get("address", "")
    target_service_date = target_form.get("service_date", "") or display_service_date(target)

    if not target_phone or not target_addr:
        raise RuntimeError(f"❌ 處理失敗 {target_order_no}：目標單缺少電話或地址")

    log("[歷史查詢] 開始抓同電話歷史訂單列表")
    phone_list = search_all_orders_by_phone(session, target_phone)
    log(f"[歷史查詢] 列表共 {len(phone_list)} 筆，只讀同地址最近 {HISTORY_LIMIT} 筆明細")

    target_item = None
    for x in phone_list:
        if x.get("order_no") == target_order_no:
            target_item = enrich_item_from_detail(session, x, target_phone)
            break

    if not target_item:
        target_item = {
            "order_no": target_order_no,
            "phone": target_phone,
            "name": target_name,
            "address": target_addr,
            "service_date": target_service_date,
            "service_date_obj": target_form.get("service_date_obj"),
            "purchase_status_name": target.get("purchase_status_name", ""),
            "purchase_status": target.get("purchase_status", ""),
            "status": "未處理",
            "status_code": "0",
            "edit_url": target.get("edit_url", ""),
        }

    items = recent_same_address_history(session, target_item, {normalize_phone(target_phone): phone_list})
    source = find_best_source_order(target_item, items)
    manual_notice = str(override_notice or "").strip()

    if manual_notice:
        # 畫面上有填／改過客服備註 → 以畫面內容為準（有來源單時仍保留來源單資訊供 log）
        log(f"[人工備註] {target_order_no}：使用畫面填入的客服備註")
        return {
            "target_form": target_form,
            "target_phone": target_phone,
            "target_name": target_name,
            "target_addr": target_addr,
            "target_service_date": target_service_date,
            "source": source or {
                "order_no": "（人工填寫）",
                "purchase_status_name": "",
                "status": "",
                "service_date": "",
            },
            "source_notice": manual_notice,
        }

    has_history = has_any_same_address_history(target_item, items)
    current = dict(target_item)
    if not current.get("hour"):
        current["hour"] = target_form.get("hour", "")
    if not str(current.get("notice", "") or "").strip():
        current["notice"] = str(target_form.get("notice", "") or "")
    own_notice = strip_change_block(current.get("notice", ""))

    if own_notice:
        # 目前訂單本來就有客服備註：保留原備註，只加註記（已非首次服務才 N- 改 O-）
        prev = source or find_latest_same_order(target_item, items)
        new_notice = compose_notice_for(current, prev, source, has_history)
        change = service_change_text(prev or {}, current, has_history)
        log(f"[保留原備註] {target_order_no}" + (f"：{change.replace(chr(10), '；')}" if change else "：無異動"))
        return {
            "target_form": target_form,
            "target_phone": target_phone,
            "target_name": target_name,
            "target_addr": target_addr,
            "target_service_date": target_service_date,
            "source": source or {"order_no": "（保留原備註）", "purchase_status_name": "", "status": "", "service_date": ""},
            "source_notice": new_notice,
        }

    if not source:
        if not has_history:
            log(f"[新成單] {target_order_no}：此地址無歷史訂單，使用固定提醒文字")
            return {
                "target_form": target_form,
                "target_phone": target_phone,
                "target_name": target_name,
                "target_addr": target_addr,
                "target_service_date": target_service_date,
                "source": {
                    "order_no": "（新成單）",
                    "purchase_status_name": "",
                    "status": "",
                    "service_date": "",
                },
                "source_notice": DEFAULT_NEW_ORDER_NOTICE,
            }
        raise RuntimeError(f"❌ 處理失敗 {target_order_no}：同電話＋同地址有歷史訂單，但找不到已服務且有客服備註的來源單")

    if not str(source.get("notice", "")).strip():
        raise RuntimeError(f"❌ 處理失敗 {target_order_no}：來源單沒有客服備註")
    source_notice = compose_notice_for(current, source, source, has_history)
    change = service_change_text(source, current, has_history)
    if change:
        log(f"[服務異動] {change.replace(chr(10), '；')}，已註記於備註")

    return {
        "target_form": target_form,
        "target_phone": target_phone,
        "target_name": target_name,
        "target_addr": target_addr,
        "target_service_date": target_service_date,
        "source": source,
        "source_notice": source_notice,
    }


# ============================================================
# 會員管理：地址[備註]
# ============================================================
def _extract_json_after(text: str, key: str):
    """在頁面原始碼找 key 後面的 JSON 陣列／物件（例："memberAddressList": 或 list:）。"""
    results = []
    decoder = json.JSONDecoder()
    for m in re.finditer(re.escape(key), text or ""):
        start = m.end()
        while start < len(text) and text[start] in " \t\r\n":
            start += 1
        try:
            value, _ = decoder.raw_decode(text, start)
            results.append(value)
        except ValueError:
            continue
    return results


def find_member_address(session, phone: str, address: str) -> Optional[Dict]:
    """會員管理頁（/member?keyword=電話）內嵌 memberAddressList，找出同地址的那筆。"""
    r = session_get(session, f"{BASE_URL}/member", params={"keyword": phone})
    r.raise_for_status()
    for address_list in _extract_json_after(r.text, '"memberAddressList":'):
        if not isinstance(address_list, list):
            continue
        for item in address_list:
            if isinstance(item, dict) and same_address(str(item.get("address", "")), address):
                return item
    return None


def read_address_memos(session, address_id, phone: str):
    """讀地址備註頁：回傳 (memos list[{id, memo}], token)。"""
    url = f"{BASE_URL}/member/{address_id}/address_memo/edit"
    r = session_get(session, url, params={"keyword": phone})
    r.raise_for_status()
    lists = _extract_json_after(r.text, "list:")
    memos = lists[0] if lists and isinstance(lists[0], list) else None
    if memos is None:
        raise RuntimeError("讀不到地址備註清單")
    soup = BeautifulSoup(r.text, "html.parser")
    token_el = soup.select_one('input[name="_token"]') or soup.select_one('meta[name="csrf-token"]')
    token = (token_el.get("value") or token_el.get("content") or "") if token_el else ""
    if not token:
        raise RuntimeError("讀不到地址備註頁 _token")
    return memos, token


def address_memo_text(notice: str) -> str:
    """寫入地址備註用：去掉只屬於單次訂單的【服務異動】行。"""
    return strip_change_block(notice)


def sync_address_memo(session, phone: str, address: str, notice: str, log) -> str:
    """
    該客人該地址的[備註]最上方那則空白 → 填入 notice；已有內容不動。
    其他備註原樣保留（同一頁 PUT 會整批覆蓋，所以全部一起送）。
    回傳結果文字給 LOG；任何錯誤只回報，不拋出。
    """
    memo_text = address_memo_text(notice)
    if not memo_text:
        return "略過（沒有可填入的備註）"
    try:
        item = find_member_address(session, phone, address)
        if not item or not item.get("id"):
            return "略過（會員管理找不到這個地址）"
        address_id = item["id"]
        memos, token = read_address_memos(session, address_id, phone)

        top = memos[0] if memos else None
        if top and str(top.get("memo") or "").strip():
            return "已有內容，未變更"

        rows = [{"id": str(m.get("id") or ""), "memo": str(m.get("memo") or "")} for m in memos]
        if rows:
            rows[0]["memo"] = memo_text
        else:
            rows = [{"id": "", "memo": memo_text}]

        data = [("_token", token), ("_method", "PUT")]
        for row in rows:
            data.append(("id[]", row["id"]))
            data.append(("memo[]", row["memo"]))
        resp = session_post(
            session,
            f"{BASE_URL}/member/{address_id}/address_memo",
            params={"keyword": phone},
            data=data,
            allow_redirects=True,
        )
        resp.raise_for_status()

        after, _ = read_address_memos(session, address_id, phone)
        if after and str(after[0].get("memo") or "").strip():
            return "已補填上回備註"
        return "送出後驗證未看到備註，請人工確認"
    except Exception as e:
        return f"失敗（{type(e).__name__}: {str(e)[:80]}），請人工確認"


def execute_target_order(session, target: Dict, source_type: str, source_value: str, log, log_ws, override_notice: Optional[str] = None):
    CURRENT_ROW_LOGS.clear()

    target_order_no = target.get("order_no", "")
    meta = get_target_and_source_for_order(session, target, log, override_notice=override_notice)

    target_form = meta["target_form"]
    target_phone = meta["target_phone"]
    target_name = meta["target_name"]
    target_addr = meta["target_addr"]
    target_service_date = meta["target_service_date"]
    source = meta["source"]
    source_notice = meta["source_notice"]

    log(f"\n===== 處理訂單 {target_order_no} =====")
    log(f"目前訂單: {target_order_no}")
    log(f"客戶: {target_name}")
    log(f"電話: {target_phone}")
    log(f"地址: {target_addr}")
    log(f"日期: {target_service_date}")
    log(f"[來源訂單] {source.get('order_no', '')} / {display_service_date(source)} / {source.get('purchase_status_name', '')} / {source.get('status', '')}")

    submit_update(session, target_form, target_phone, source_notice)
    time.sleep(SLEEP_SECONDS)

    ok, verified_form = verify_update(session, target["edit_url"], target_phone, source_notice, order_no=target_order_no)
    if not ok:
        reason_text = f"❌ 處理失敗 {target_order_no}：更新後驗證失敗"
        log(reason_text)
        append_log_row(
            log_ws=log_ws,
            source_type=source_type,
            source_value=source_value,
            phone=target_phone,
            name=target_name,
            address=target_addr,
            current_order=target_order_no,
            current_service_date=target_service_date,
            prev_order=source["order_no"],
            prev_service_date=display_service_date(source),
            prev_notice=source_notice,
            updated_orders=0,
            status="失敗",
            error_msg=reason_text,
            full_log="\n".join(CURRENT_ROW_LOGS),
        )
        return {"ok": False, "error": reason_text, "updated_orders": 0}

    log(f"✅ 驗證成功 {target_order_no}")
    address_memo_result = sync_address_memo(session, target_phone, target_addr, source_notice, log)
    log(f"[地址備註] {target_order_no}：{address_memo_result}")
    append_log_row(
        log_ws=log_ws,
        source_type=source_type,
        source_value=source_value,
        phone=target_phone,
        name=target_name,
        address=target_addr,
        current_order=target_order_no,
        current_service_date=target_service_date,
        prev_order=source["order_no"],
        prev_service_date=display_service_date(source),
        prev_notice=source_notice,
        updated_orders=1,
        status="成功",
        error_msg="",
        full_log="\n".join(CURRENT_ROW_LOGS),
    )
    return {"ok": True, "error": "", "updated_orders": 1}


def process_single_case(session, order, name, phone, addr, date, log):
    target_items = search_orders_by_order_no(session, order)
    target_items = enrich_items_from_detail(session, target_items, phone, log=log, context_label=f"目標訂單 {order}")
    target = next((x for x in target_items if x.get("order_no") == order), None)

    if not target:
        raise RuntimeError(f"❌ 處理失敗 {order}：找不到目標訂單")

    meta = get_target_and_source_for_order(session, target, log)
    target_form = meta["target_form"]
    target_phone = meta["target_phone"]
    source = meta["source"]
    source_notice = meta["source_notice"]

    submit_update(session, target_form, target_phone, source_notice)
    time.sleep(SLEEP_SECONDS)

    ok, _ = verify_update(session, target["edit_url"], target_phone, source_notice, order_no=order)
    if ok:
        log(f"✅ 成功：已回填 {order}")
        return {
            "ok": True,
            "prev_date": display_service_date(source),
            "prev_order": source["order_no"],
            "prev_notice": source_notice,
            "updated_orders": 1,
            "error": "",
        }

    reason_text = f"❌ 處理失敗 {order}：更新後驗證失敗"
    log(reason_text)
    return {
        "ok": False,
        "prev_date": display_service_date(source),
        "prev_order": source["order_no"],
        "prev_notice": source_notice,
        "updated_orders": 0,
        "error": reason_text,
    }


def preview_by_phone(phone, ui_logger=None, session=None):
    CURRENT_ROW_LOGS.clear()
    log = make_logger(ui_logger)

    phone = normalize_phone(phone)
    if not phone:
        raise RuntimeError("電話不可為空")

    log("\n===== 預覽 BY電話 =====")
    log(f"輸入電話: {phone}")

    session = session or login(ui_logger=ui_logger)

    log("[查詢列表] 開始抓電話主列表")
    items = search_all_orders_by_phone(session, phone, log=log)
    log(f"[查詢列表] 主列表共 {len(items)} 筆")

    phone_list_cache = {phone: items}
    targets = [x for x in items if x.get("status_code") == "0"]
    processed = [x for x in items if x.get("status_code") == "1" and upcoming(x)]
    to_read = [x for x in targets + processed if not x.get("_detail")]
    enrich_items_from_detail(session, to_read, phone, log=log, context_label=f"電話 {phone} 未處理／即將服務")

    preview = []
    total = len(targets)
    for idx, item in enumerate(targets, start=1):
        preview.append(build_preview_row(item, recent_same_address_history(session, item, phone_list_cache)))
        if idx == total or idx == 1 or idx % 5 == 0:
            log(f"[整理預覽進度] {idx}/{total}")

    candidates = [x for x in processed if might_need_notice_flag(x)]
    preview.extend(processed_flag_rows(
        candidates, lambda it: recent_same_address_history(session, it, phone_list_cache), log=log))

    preview.sort(
        key=lambda x: (
            0 if x.get("can_autofill") else 1,
            str(x.get("service_date", "")),
            str(x.get("order_id", "")),
        )
    )
    return preview


def preview_by_phone_multi(phone_text, ui_logger=None, session=None):
    phones = parse_phone_list(phone_text)
    if not phones:
        raise RuntimeError("請輸入至少一支有效電話")

    session = session or login(ui_logger=ui_logger)

    all_rows = []
    seen = set()
    for idx, phone in enumerate(phones, start=1):
        if ui_logger:
            ui_logger(f"[多電話查詢] {idx}/{len(phones)}：{phone}")
        rows = preview_by_phone(phone, ui_logger=ui_logger, session=session)
        for row in rows:
            oid = row.get("order_id", "")
            if oid and oid not in seen:
                seen.add(oid)
                all_rows.append(row)

    all_rows.sort(
        key=lambda x: (
            0 if x.get("can_autofill") else 1,
            str(x.get("service_date", "")),
            str(x.get("order_id", "")),
        )
    )
    return all_rows


def preview_by_conditions(date_mode, date_start, date_end, purchase_status_name, limit=None, ui_logger=None, session=None):
    CURRENT_ROW_LOGS.clear()
    log = make_logger(ui_logger)

    if not date_start and not date_end:
        raise RuntimeError("請至少選擇開始日期或結束日期")

    log("\n===== 預覽 BY搜尋條件 =====")
    log(f"日期條件: {date_mode}")
    log(f"日期區間: {date_start or '(空)'} ~ {date_end or '(空)'}")
    log(f"付款狀態: {purchase_status_name}")
    log("處理狀態: 未處理")
    log("查詢列表: 不先限制處理筆數")

    session = session or login(ui_logger=ui_logger)

    log("[查詢列表] 開始抓符合條件的主列表")
    items = search_by_conditions(session, date_mode, date_start, date_end, purchase_status_name)
    log(f"[查詢列表] 主列表共 {len(items)} 筆")

    items = enrich_items_from_detail(
        session,
        items,
        log=log,
        context_label="搜尋條件主列表"
    )


    phone_list_cache = {}
    preview = []

    for idx, item in enumerate(items, start=1):
        preview.append(build_preview_row(item, recent_same_address_history(session, item, phone_list_cache, log=log)))
        if idx == len(items) or idx == 1 or idx % 5 == 0:
            log(f"[整理預覽進度] {idx}/{len(items)}")

    # 已處理且客服備註本來就有內容的訂單：檢查 VIP 非儲值金／**N- 已非首次服務
    log("[已處理客服備註檢查] 開始抓同條件已處理訂單")
    processed = search_by_conditions(session, date_mode, date_start, date_end, purchase_status_name, progress="1")
    seen = {r["order_id"] for r in preview}
    processed = [x for x in processed if x.get("order_no") not in seen and upcoming(x)]
    log(f"[已處理客服備註檢查] 已處理且服務日期 ≥ 今天 {len(processed)} 筆，讀取明細")
    processed = enrich_items_from_detail(session, processed, log=log, context_label="已處理訂單")
    candidates = [x for x in processed if x.get("status_code") == "1" and upcoming(x) and might_need_notice_flag(x)]
    log(f"[已處理客服備註檢查] 客服備註有 VIP／**N- 標記 {len(candidates)} 筆，比對同地址最近 {HISTORY_LIMIT} 筆")
    preview.extend(processed_flag_rows(
        candidates, lambda it: recent_same_address_history(session, it, phone_list_cache, log=log), log=log))

    dedup = {}
    for row in preview:
        dedup[row["order_id"]] = row

    result = list(dedup.values())
    result.sort(
        key=lambda x: (
            0 if x.get("can_autofill") else 1,
            str(x.get("service_date", "")),
            str(x.get("order_id", "")),
        )
    )
    return result


def get_sheet_summary(ui_logger=None):
    log = make_logger(ui_logger)
    ws = get_ws()
    rows = with_retry(ws.get_all_values)

    total_rows = max(0, len(rows) - 1)
    pending_rows = 0
    done_rows = 0

    for row in rows[1:]:
        v_status = safe_cell(row, 22)
        if v_status:
            done_rows += 1
        else:
            order = safe_cell(row, 2)
            addr = safe_cell(row, 14)
            phone = safe_cell(row, 15)
            if order and addr and phone:
                pending_rows += 1

    log(f"總筆數={total_rows}, 未處理={pending_rows}, 已處理={done_rows}")
    return {
        "total_rows": total_rows,
        "pending_rows": pending_rows,
        "done_rows": done_rows,
    }


def get_first_n_pending_rows(limit: int) -> List[int]:
    ws = get_ws()
    rows = with_retry(ws.get_all_values)

    row_nums = []
    for idx, row in enumerate(rows[1:], start=2):
        v_status = safe_cell(row, 22)
        order = safe_cell(row, 2)
        addr = safe_cell(row, 14)
        phone = safe_cell(row, 15)

        if not v_status and order and addr and phone:
            row_nums.append(idx)

        if len(row_nums) >= limit:
            break

    return row_nums


def main_first_n_pending(limit: int, ui_logger=None, session=None):
    row_nums = get_first_n_pending_rows(limit)
    if not row_nums:
        return {
            "processed": 0,
            "success": 0,
            "failed": 0,
            "skipped": 0,
            "updated_orders": 0,
            "errors": ["沒有可處理的未處理列"],
        }
    row_spec = ",".join(str(x) for x in row_nums)
    return main(row_spec=row_spec, force=False, ui_logger=ui_logger, session=session)


def main(row_spec="2", force=False, ui_logger=None, session=None):
    ws = get_ws()
    log_ws = get_log_ws()
    rows = with_retry(ws.get_all_values)

    row_nums = parse_row_spec(row_spec)
    log = make_logger(ui_logger)

    result = blank_result()
    updates = []
    updated_row_numbers = []

    session = session or login(ui_logger=ui_logger)

    for r in row_nums:
        CURRENT_ROW_LOGS.clear()

        try:
            if r - 1 >= len(rows):
                log(f"\n===== 第{r}列 =====")
                log("❌ 超出資料範圍")
                result["failed"] += 1
                result["errors"].append(f"第{r}列：超出資料範圍")
                continue

            row = rows[r - 1]

            order = safe_cell(row, 2)
            date = safe_cell(row, 8)
            name = safe_cell(row, 13)
            addr = safe_cell(row, 14)
            phone = safe_cell(row, 15)
            v_status = safe_cell(row, 22)

            log(f"\n===== 第{r}列 =====")

            if v_status and not force:
                log(f"訂單: {order}")
                log("⏭ 已有狀態，略過")
                result["skipped"] += 1
                continue

            if not order or not addr or not phone:
                reason_text = f"❌ 處理失敗 第{r}列：缺少訂單 / 地址 / 電話"
                log(reason_text)
                result["failed"] += 1
                result["errors"].append(reason_text)
                continue

            single_result = process_single_case(
                session=session,
                order=order,
                name=name,
                phone=phone,
                addr=addr,
                date=date,
                log=log,
            )

            updates.append({
                "range": f"S{r}:X{r}",
                "values": [[
                    single_result["prev_date"],
                    single_result["prev_order"],
                    single_result["prev_notice"],
                    "成功" if single_result["ok"] else "失敗",
                    "\n".join(CURRENT_ROW_LOGS),
                    single_result["prev_notice"],
                ]],
            })
            updated_row_numbers.append(r)

            append_log_row(
                log_ws=log_ws,
                source_type="BY列號",
                source_value=str(r),
                phone=phone,
                name=name,
                address=addr,
                current_order=order,
                current_service_date=date,
                prev_order=single_result["prev_order"],
                prev_service_date=single_result["prev_date"],
                prev_notice=single_result["prev_notice"],
                updated_orders=single_result["updated_orders"],
                status="成功" if single_result["ok"] else "失敗",
                error_msg=single_result["error"],
                full_log="\n".join(CURRENT_ROW_LOGS),
            )

            result["processed"] += 1
            result["updated_orders"] += single_result["updated_orders"]

            if single_result["ok"]:
                result["success"] += 1
            else:
                result["failed"] += 1
                result["errors"].append(single_result["error"])

        except Exception as e:
            reason_text = f"❌ 處理失敗 第{r}列：{e}"
            log(reason_text)
            append_log_row(
                log_ws=log_ws,
                source_type="BY列號",
                source_value=str(r),
                phone="",
                name="",
                address="",
                current_order="",
                current_service_date="",
                prev_order="",
                prev_service_date="",
                prev_notice="",
                updated_orders=0,
                status="失敗",
                error_msg=reason_text,
                full_log="\n".join(CURRENT_ROW_LOGS),
            )
            result["failed"] += 1
            result["errors"].append(reason_text)

    if updates:
        with_retry(ws.batch_update, updates, value_input_option="RAW")
        apply_sheet_presentation(ws, updated_row_numbers)

    return result


def main_by_selected_order_ids(order_ids, ui_logger=None, session=None, custom_notices: Optional[Dict[str, str]] = None):
    CURRENT_ROW_LOGS.clear()
    log = make_logger(ui_logger)
    log_ws = get_log_ws_safe(log)
    result = blank_result()
    custom_notices = custom_notices or {}

    if not order_ids:
        msg = "❌ 處理失敗：未提供任何訂單"
        log(msg)
        result["failed"] = 1
        result["errors"].append(msg)
        return result

    session = session or login(ui_logger=ui_logger)
    source_type = "BY勾選執行"
    source_value = ",".join(order_ids[:50])

    for order_id in order_ids:
        try:
            items = search_orders_by_order_no(session, order_id)
            items = enrich_items_from_detail(
                session,
                items,
                log=log,
                context_label=f"目標訂單 {order_id}"
            )

            target = next((x for x in items if x.get("order_no") == order_id), None)
            if not target:
                raise RuntimeError(f"❌ 處理失敗 {order_id}：找不到訂單")

            single_result = execute_target_order(
                session=session,
                target=target,
                source_type=source_type,
                source_value=source_value,
                log=log,
                log_ws=log_ws,
                override_notice=custom_notices.get(order_id),
            )

            result["processed"] += 1
            result["updated_orders"] += single_result["updated_orders"]

            if single_result["ok"]:
                result["success"] += 1
            else:
                result["failed"] += 1
                result["errors"].append(single_result["error"])

        except Exception as e:
            reason_text = str(e)
            log(reason_text)
            result["processed"] += 1
            result["failed"] += 1
            result["errors"].append(reason_text)

            append_log_row(
                log_ws=log_ws,
                source_type=source_type,
                source_value=source_value,
                phone="",
                name="",
                address="",
                current_order=order_id,
                current_service_date="",
                prev_order="",
                prev_service_date="",
                prev_notice="",
                updated_orders=0,
                status="失敗",
                error_msg=reason_text,
                full_log="\n".join(CURRENT_ROW_LOGS),
            )

    return result


# -----------------------------------------------------------------------------
# CLI 入口
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    row_spec_arg = sys.argv[1] if len(sys.argv) > 1 else "2"

    cli_email = str(secret_value("LEMON_EMAIL", ""))
    cli_password = str(secret_value("LEMON_PASSWORD", ""))
    set_runtime_credentials(cli_email, cli_password)

    result = main(row_spec=row_spec_arg, force=False)
    print(result)
