# memo.py
# -*- coding: utf-8 -*-
import re
import time
from datetime import datetime
from typing import Optional, List, Dict, Callable

import streamlit as st  # 僅用於讀取 st.secrets，不做任何畫面輸出
import requests
from bs4 import BeautifulSoup
import gspread
from google.oauth2.service_account import Credentials


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
    log = make_logger(ui_logger)

    email = RUNTIME_EMAIL
    password = RUNTIME_PASSWORD

    if not email or not password:
        raise RuntimeError("缺少 Email / Password")

    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    })

    r = session_get(s, LOGIN_URL)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    token_el = soup.select_one("input[name=_token]")
    if not token_el:
        raise RuntimeError("登入頁找不到 _token")

    token = token_el.get("value", "")

    resp = session_post(
        s,
        LOGIN_URL,
        data={
            "_token": token,
            "email": email,
            "password": password,
        },
        allow_redirects=True,
    )
    resp.raise_for_status()

    check = session_get(s, PURCHASE_URL, allow_redirects=True)
    check.raise_for_status()

    if "/login" in check.url:
        raise RuntimeError("登入失敗，請確認帳密")

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

        edit_link = tr.select_one('a[href*="/purchase/edit/"]')
        edit_url = f"{BASE_URL}{edit_link['href']}" if edit_link and edit_link.get("href", "").startswith("/") else (edit_link["href"] if edit_link else "")
        row_data["edit_url"] = edit_url
        row_data["purchase_id"] = get_purchase_id_from_edit_url(edit_url)
        data.append(row_data)

    dedup = {}
    for item in data:
        dedup[item["order_no"]] = item
    return list(dedup.values())


def search_all_orders_by_phone(session, phone, log=None) -> List[Dict]:
    r = session_get(
        session,
        PURCHASE_URL,
        params={
            "keyword": "",
            "name": "",
            "phone": phone,
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
            "purchase_status": "",
            "progress_status": "",
            "invoiceStatus": "",
            "otherFee": "",
            "orderBy": "",
        },
    )
    r.raise_for_status()

    if log:
        debug_dump_list_rows(r.text, log, max_rows=20)

    return parse_purchase_list_page(r.text)


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


def search_by_conditions_once(session, date_mode: str, date_start: str, date_end: str, purchase_status_name: str) -> List[Dict]:
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
        "progress_status": "0",
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

    r = session_get(session, PURCHASE_URL, params=params)
    r.raise_for_status()

    items = parse_purchase_list_page(r.text)
    filtered = [
        x for x in items
        if x.get("status_code") == "0" and (not purchase_status or x.get("purchase_status") == purchase_status)
    ]
    return filtered


def search_by_conditions(session, date_mode: str, date_start: str, date_end: str, purchase_status_name: str) -> List[Dict]:
    if purchase_status_name == "全部":
        unpaid = search_by_conditions_once(session, date_mode, date_start, date_end, "未付款")
        paid = search_by_conditions_once(session, date_mode, date_start, date_end, "已付款")
        merged = {}
        for x in unpaid + paid:
            merged[x["order_no"]] = x
        items = list(merged.values())
        items.sort(key=lambda x: (display_service_date(x), x.get("order_no", "")))
        return items

    return search_by_conditions_once(session, date_mode, date_start, date_end, purchase_status_name)


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
    item["name"] = detail.get("customer_name", "") or item.get("name", "")
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
    item["_detail"] = detail
    return item


def enrich_items_from_detail(session, items: List[Dict], phone="", log=None, context_label="") -> List[Dict]:
    result = []
    total = len(items)

    if log and context_label:
        log(f"[明細補抓] {context_label}，共 {total} 筆")

    for idx, item in enumerate(items, start=1):
        try:
            result.append(enrich_item_from_detail(session, item, phone))
        except Exception as e:
            if log:
                log(f"[明細補抓失敗] {item.get('order_no', '')}：{e}")
            result.append(item)

        if log and total > 0 and (idx == total or idx == 1 or idx % 5 == 0):
            log(f"[明細補抓進度] {idx}/{total}")

    return result


def has_any_same_address_history(current_item: Dict, history_items: List[Dict]) -> bool:
    """
    判斷這個地址是不是完全沒有出現過任何歷史訂單（不論付款/處理狀態、不論備註是否為空）。
    用來分辨「真的是新成單」跟「有歷史單但條件不符合自動回填」這兩種情況。
    """
    current_order_no = current_item.get("order_no", "")
    current_addr = current_item.get("address", "")

    for x in history_items:
        if x.get("order_no") == current_order_no:
            continue
        if same_address(x.get("address", ""), current_addr):
            return True
    return False


def find_best_source_order(current_item: Dict, history_items: List[Dict]) -> Optional[Dict]:
    candidates = []

    current_order_no = current_item.get("order_no", "")
    current_phone = normalize_phone(current_item.get("phone", ""))
    current_addr = current_item.get("address", "")
    current_dt = item_service_date_obj(current_item)

    for x in history_items:
        if x.get("order_no") == current_order_no:
            continue

        if current_phone and x.get("phone") and normalize_phone(x.get("phone")) != current_phone:
            continue

        if not same_address(x.get("address", ""), current_addr):
            continue

        dt = item_service_date_obj(x)
        if not dt:
            continue
        if current_dt and dt >= current_dt:
            continue

        if x.get("purchase_status") != "1":
            continue

        if x.get("status_code") not in ("1", "2"):
            continue

        notice = str(x.get("notice", "")).strip()
        if not notice:
            continue

        candidates.append(x)

    if not candidates:
        return None

    candidates.sort(key=lambda k: item_service_date_obj(k), reverse=True)
    return candidates[0]


def build_preview_row(target: Dict, history_items: List[Dict]) -> Dict:
    source = find_best_source_order(target, history_items)

    if not source and not has_any_same_address_history(target, history_items):
        # 這個地址完全沒有歷史訂單 → 視為新成單，自動帶入固定提醒文字
        return {
            "order_id": target.get("order_no", ""),
            "customer_name": target.get("name", ""),
            "phone": target.get("phone", ""),
            "address": target.get("address", ""),
            "service_date": display_service_date(target),
            "purchase_status_name": target.get("purchase_status_name", ""),
            "status_name": target.get("status", ""),
            "source_order_id": "",
            "source_service_date": "",
            "source_purchase_status_name": "",
            "source_status_name": "",
            "source_notice_exists": True,
            "source_notice_preview": DEFAULT_NEW_ORDER_NOTICE,
            "can_autofill": True,
            "is_new_order": True,
        }

    return {
        "order_id": target.get("order_no", ""),
        "customer_name": target.get("name", ""),
        "phone": target.get("phone", ""),
        "address": target.get("address", ""),
        "service_date": display_service_date(target),
        "purchase_status_name": target.get("purchase_status_name", ""),
        "status_name": target.get("status", ""),
        "source_order_id": source.get("order_no", "") if source else "",
        "source_service_date": display_service_date(source) if source else "",
        "source_purchase_status_name": source.get("purchase_status_name", "") if source else "",
        "source_status_name": source.get("status", "") if source else "",
        "source_notice_exists": bool(str(source.get("notice", "")).strip()) if source else False,
        "source_notice_preview": str(source.get("notice", "")).strip()[:80] if source else "",
        "can_autofill": bool(source),
        "is_new_order": False,
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


def get_target_and_source_for_order(session, target: Dict, log) -> Dict:
    target_order_no = target.get("order_no", "")
    target_form = parse_edit_page(session, target["edit_url"], target.get("phone", ""))

    target_phone = normalize_phone(target_form.get("phone", "") or target.get("phone", ""))
    target_name = target_form.get("customer_name", "") or target.get("name", "")
    target_addr = target_form.get("address", "") or target.get("address", "")
    target_service_date = target_form.get("service_date", "") or display_service_date(target)

    if not target_phone or not target_addr:
        raise RuntimeError(f"❌ 處理失敗 {target_order_no}：目標單缺少電話或地址")

    log("[歷史查詢] 開始抓同電話全部歷史訂單")
    items = search_all_orders_by_phone(session, target_phone)
    log(f"[歷史查詢] 主列表共 {len(items)} 筆")

    items = enrich_items_from_detail(
        session,
        items,
        target_phone,
        log=log,
        context_label=f"同電話 {target_phone} 歷史訂單"
    )

    target_item = None
    for x in items:
        if x.get("order_no") == target_order_no:
            target_item = x
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

    source = find_best_source_order(target_item, items)

    if not source:
        if not has_any_same_address_history(target_item, items):
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
        raise RuntimeError(f"❌ 處理失敗 {target_order_no}：找不到同地址＋已付款＋已處理＋有備註的最近來源單")

    source_notice = str(source.get("notice", "")).strip()
    if not source_notice:
        raise RuntimeError(f"❌ 處理失敗 {target_order_no}：來源單沒有客服備註")

    return {
        "target_form": target_form,
        "target_phone": target_phone,
        "target_name": target_name,
        "target_addr": target_addr,
        "target_service_date": target_service_date,
        "source": source,
        "source_notice": source_notice,
    }


def execute_target_order(session, target: Dict, source_type: str, source_value: str, log, log_ws, override_notice: Optional[str] = None):
    CURRENT_ROW_LOGS.clear()

    target_order_no = target.get("order_no", "")
    meta = get_target_and_source_for_order(session, target, log)

    target_form = meta["target_form"]
    target_phone = meta["target_phone"]
    target_name = meta["target_name"]
    target_addr = meta["target_addr"]
    target_service_date = meta["target_service_date"]
    source = meta["source"]
    source_notice = meta["source_notice"]

    # 新成單（找不到歷史來源訂單）時，如果使用者有自己編輯過提醒文字，優先採用使用者輸入的內容，
    # 不強制使用寫死的 DEFAULT_NEW_ORDER_NOTICE。
    if source.get("order_no") == "（新成單）" and override_notice is not None and override_notice.strip():
        source_notice = override_notice.strip()

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

    items = enrich_items_from_detail(
        session,
        items,
        phone,
        log=log,
        context_label=f"電話 {phone} 查詢結果"
    )

    targets = [x for x in items if x.get("status_code") == "0"]

    preview = []
    total = len(targets)
    for idx, item in enumerate(targets, start=1):
        preview.append(build_preview_row(item, items))
        if idx == total or idx == 1 or idx % 5 == 0:
            log(f"[整理預覽進度] {idx}/{total}")

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

    if not items:
        return []

    phone_cache = {}
    preview = []

    for idx, item in enumerate(items, start=1):
        phone = normalize_phone(item.get("phone", ""))
        if not phone:
            preview.append(build_preview_row(item, [item]))
            continue

        if phone not in phone_cache:
            log(f"[歷史比對] 開始抓電話 {phone} 的全部歷史訂單")
            history = search_all_orders_by_phone(session, phone)
            log(f"[歷史比對] 電話 {phone} 主列表共 {len(history)} 筆")
            history = enrich_items_from_detail(
                session,
                history,
                phone,
                log=log,
                context_label=f"電話 {phone} 歷史訂單"
            )
            phone_cache[phone] = history

        preview.append(build_preview_row(item, phone_cache[phone]))

        if idx == len(items) or idx == 1 or idx % 5 == 0:
            log(f"[整理預覽進度] {idx}/{len(items)}")

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
    log_ws = get_log_ws()
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
