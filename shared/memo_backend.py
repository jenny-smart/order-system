# -*- coding: utf-8 -*-
"""memo_system（客服備註搬移／ATM對帳／清潔異動／付款比對）共用的後台/Sheet 存取
基礎設施：secrets 讀取、env 切換、重試包裝、Google Sheet 讀寫、後台登入。

atm.py／shift.py／change_order.py／payment_match.py／function/memo_customer_service.py
都透過這裡取得 session/worksheet，取代原本各自 `from . import memo` 再借用
memo.py 身上這些函式的寫法。
"""

import time
from datetime import datetime
from typing import Optional, List, Callable

import streamlit as st  # 僅用於讀取 st.secrets，不做任何畫面輸出
import requests
from bs4 import BeautifulSoup
import gspread
from google.oauth2.service_account import Credentials

from shared.memo_text import (
    clip_text, safe_cell, parse_row_spec, normalize_phone, parse_phone_list,
    normalize_text, normalize_address, same_address, parse_date,
    extract_name_from_text_block, extract_service_date_from_page_text,
    extract_address_from_text_block, get_purchase_id_from_edit_url,
    display_service_date, item_service_date_obj,
)


def secret_value(key: str, default=""):
    try:
        return st.secrets.get(key, default)
    except Exception:
        return default


ENV_NAME = str(secret_value("ENV", "prod")).lower()
BASE_URL_DEV = str(secret_value("BASE_URL_DEV", "https://backend-dev.lemonclean.com.tw"))
BASE_URL_PROD = str(secret_value("BASE_URL_PROD", "https://backend.lemonclean.com.tw"))
SHEET_ID = str(secret_value("SHEET_ID", ""))

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


WORKSHEET_NAME = str(secret_value("WORKSHEET_NAME", "memo"))
LOG_SHEET_NAME = str(secret_value("LOG_SHEET_NAME", "memo_log"))
SLEEP_SECONDS = float(secret_value("SLEEP_SECONDS", 0.5))

REQUEST_TIMEOUT = 30
MAX_RETRIES = 3
RETRY_BACKOFF = 1.2

CURRENT_ROW_LOGS: List[str] = []


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
    from shared.gsheet import get_service_account_info

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    service_account_info = get_service_account_info()
    creds = Credentials.from_service_account_info(service_account_info, scopes=scopes)
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
