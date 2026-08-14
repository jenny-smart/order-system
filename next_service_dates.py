# ============================================================
# 檔名：next_service_dates.py
# 版本：v1.1
# 模組：依電話+地址查後台最近3次服務日期，寫回 Google Sheet L-N 欄
# 最後更新：2026-07-09
#
# Change Log
# v1.1
# - 修正登入方式：跟 orders.py / quick_order.py 裡其餘所有函式一致，一律
#   使用 Step 1 畫面輸入的 backend_email / backend_password 登入，不再
#   從 accounts.py 讀取區域專屬帳密（accounts.py 在 orders.py 裡只用於
#   get_region_by_address 判斷地址所屬區域，從未被用來登入）。
#   login_region() 因此改名為 login_backend()，只吃 env_name +
#   backend_email + backend_password，跟其他 17 個功能的登入方式統一。
# v1.0
# - 新增功能：讀取「台北/台中-建議下次服務時間」等工作表的 B欄（地址）+
#   E欄（電話），逐列查後台該電話底下所有訂單，比對地址後取最近3次服務
#   日期，寫入 L/M/N 欄（L=最近一次，N=最遠一次，愈遠放愈後面）。
# - 直接沿用 orders.py 既有的登入/查詢/解析邏輯（login、extract_order_
#   cards_from_purchase_html、normalize_phone、PURCHASE_FILTER_PARAMS_
#   TEMPLATE），以及 quick_order.py 的地址/日期解析（_extract_address_
#   line、_parse_service_date_time_loose），不重新造輪子。
# - 排除純儲值金訂單（訂單卡片沒有地址那一行）跟已取消/已退款訂單
#   （卡片文字裡出現「取消時間」或「已退款」）。
# - 地址比對用「核心片段」比對（路/街/巷/弄/號之後的部分），可以正確
#   辨識「大安區台北市文山區福興路62號8樓之四」跟「台北市文山區福興路
#   62號8樓之四」是同一地址，不受行政區前綴順序或有無影響。
# ============================================================
# -*- coding: utf-8 -*-
import re
import time

import requests
import gspread

import orders
from orders import (
    login, HEADERS, PURCHASE_FILTER_PARAMS_TEMPLATE,
    extract_order_cards_from_purchase_html, normalize_phone,
    build_gsheet_client,
)
from quick_order import _extract_address_line, _parse_service_date_time_loose
from env import BASE_URL_DEV, BASE_URL_PROD


# =========================
# 環境設定（沿用 orders.py 既有做法：依 env_name 動態切換 dev/prod）
# =========================
def _configure_env_globals(env_name):
    base_url = BASE_URL_DEV if env_name == "dev" else BASE_URL_PROD
    orders.BASE_URL = base_url
    orders.LOGIN_URL = f"{base_url}/login"
    orders.PURCHASE_URL = f"{base_url}/purchase"
    return base_url


# =========================
# 地址比對：核心片段比對，容許行政區前綴順序不同/有無
# =========================
def _address_core(addr_norm):
    """
    取地址裡「路/街/大道」之後的部分（含門牌、樓層），用來比對同一地址
    即使行政區前綴順序不同或缺漏也能正確辨識。
    例：「大安區台北市文山區福興路62號8樓之四」
        vs「台北市文山區福興路62號8樓之四」
    -> 都能取出「福興路62號8樓之四」來比對。
    """
    m = re.search(r"(路|街|大道)[^路街大道]*?(\d+號.*)?$", addr_norm)
    return addr_norm[m.start():] if m else addr_norm


def _normalize_addr(addr):
    text = re.sub(r"\s+", "", str(addr or "").strip())
    return text.replace("台", "臺")


def _is_same_address(target_addr, candidate_addr):
    t = _normalize_addr(target_addr)
    c = _normalize_addr(candidate_addr)
    if not t or not c:
        return False
    if t == c:
        return True
    t_core = _address_core(t)
    c_core = _address_core(c)
    if not t_core or not c_core:
        return False
    return t_core in c or c_core in t


# =========================
# 查詢某電話底下所有訂單卡片（處理分頁）
# =========================
def _fetch_all_blocks_for_phone(session, phone_norm, max_pages=10):
    all_blocks = []
    for page in range(1, max_pages + 1):
        params = dict(PURCHASE_FILTER_PARAMS_TEMPLATE)
        params["phone"] = phone_norm
        params["page"] = str(page)
        resp = session.get(orders.PURCHASE_URL, params=params, headers=HEADERS, allow_redirects=True)
        if resp.status_code != 200:
            break
        blocks = extract_order_cards_from_purchase_html(resp.text)
        if not blocks:
            break
        all_blocks.extend(blocks)
        if len(blocks) < 20:
            break
    return all_blocks


# =========================
# 核心：查最近 N 次服務日期
# =========================
def get_recent_service_dates(session, phone, address, n=3):
    """
    回傳該電話+地址最近 n 次「實際服務日期」字串 list，由新到舊排序。
    排除：純儲值金訂單（卡片沒有地址那一行）、已取消訂單（卡片文字含
    「取消時間」）、已退款訂單（卡片文字含「已退款」）。
    """
    phone_norm = normalize_phone(phone)
    if not phone_norm:
        return []

    blocks = _fetch_all_blocks_for_phone(session, phone_norm)
    matched_dates = []

    for block in blocks:
        lines = block.get("lines", [])
        joined = "\n".join(lines)

        if "取消時間" in joined or "已退款" in joined:
            continue

        block_addr = _extract_address_line(lines)
        if not block_addr:
            continue  # 純儲值金訂單沒有服務地址，跳過

        if not _is_same_address(address, block_addr):
            continue

        service_date, _service_time = _parse_service_date_time_loose(joined)
        if service_date:
            matched_dates.append(service_date)

    unique_sorted = sorted(set(matched_dates), reverse=True)
    return unique_sorted[:n]


# =========================
# 登入：跟其他功能一致，用 Step 1 畫面輸入的帳密登入一次，回傳可重複
# 使用的 session（台北/台中訂單都在同一個後台網域下查得到，不需要
# 依區域切換帳密）
# =========================
def login_backend(env_name, backend_email, backend_password):
    _configure_env_globals(env_name)

    session = requests.Session()
    if not login(session, backend_email, backend_password):
        raise Exception("後台登入失敗，請確認帳號密碼")

    return session


# =========================
# 寫回 Google Sheet（沿用已登入的 session，不重新登入）
# =========================
def update_next_service_dates_sheet(
    session, spreadsheet_id, gid,
    phone_col="E", address_col="B", start_row=2, out_cols=("L", "M", "N"),
    logger=print,
):
    """
    讀取指定試算表（依 gid 指定分頁）B欄（地址）+ E欄（電話），
    查最近3次服務日期，寫入 L/M/N 欄（L=最近一次，N=最遠一次）。
    session 需先呼叫 login_backend() 取得（全部工作表共用同一個 session，
    不用每份工作表都重新登入一次）。
    """
    gc = build_gsheet_client()
    sh = gc.open_by_key(spreadsheet_id)
    ws = sh.get_worksheet_by_id(int(gid))

    all_values = ws.get_all_values()
    last_row = len(all_values)

    col_idx = {
        "address": gspread.utils.a1_to_rowcol(f"{address_col}1")[1] - 1,
        "phone": gspread.utils.a1_to_rowcol(f"{phone_col}1")[1] - 1,
    }

    updates = []
    for row_idx in range(start_row, last_row + 1):
        row_data = all_values[row_idx - 1]
        address = row_data[col_idx["address"]] if col_idx["address"] < len(row_data) else ""
        phone = row_data[col_idx["phone"]] if col_idx["phone"] < len(row_data) else ""

        if not address.strip() or not phone.strip():
            continue

        recent_dates = get_recent_service_dates(session, phone, address, n=3)
        logger(f"第{row_idx}列：{address}（{phone}）-> {recent_dates}")

        if not recent_dates:
            continue

        padded = recent_dates + [""] * (3 - len(recent_dates))
        updates.append((row_idx, padded))
        time.sleep(0.3)  # 禮貌性延遲，避免對後台造成負擔

    for row_idx, values in updates:
        cell_range = f"{out_cols[0]}{row_idx}:{out_cols[2]}{row_idx}"
        ws.update(cell_range, [values])
        time.sleep(0.2)

    logger(f"✅ {region} gid={gid} 完成，共更新 {len(updates)} 列。")
    return len(updates)


# =========================
# 主執行：處理 Jenny 提供的 4 份工作表
# =========================
SHEETS = [
    # (區域, spreadsheet_id, gid)
    ("台北", "1T01k68sV0NY6MPD2nw8Tg1ijC9dOXhhr26G5-Bc9bJM", "94436291"),
    ("台北", "1T01k68sV0NY6MPD2nw8Tg1ijC9dOXhhr26G5-Bc9bJM", "1675299427"),
    ("台中", "17t3JcUEF0tQwr4a3fvLXUceCXgQDsmihYz7tkRQOc6s", "1389645036"),
    ("台中", "17t3JcUEF0tQwr4a3fvLXUceCXgQDsmihYz7tkRQOc6s", "1534882634"),
]


def run_all(env_name, backend_email, backend_password, logger=print):
    """
    用 Step 1 輸入的帳密登入一次，依序處理全部 4 份工作表（共用同一個 session）。
    """
    logger("▶ 登入後台…")
    session = login_backend(env_name, backend_email, backend_password)

    total_updated = 0
    for _region, spreadsheet_id, gid in SHEETS:
        logger(f"▶ 開始處理：{_region}｜gid={gid}")
        try:
            total_updated += update_next_service_dates_sheet(
                session, spreadsheet_id, gid, logger=logger,
            )
        except Exception as e:
            logger(f"❌ {_region} gid={gid} 執行失敗：{e}")

    logger(f"✅ 全部完成，共更新 {total_updated} 列。")
    return total_updated


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 3:
        print("用法：python next_service_dates.py <後台帳號> <後台密碼>")
        sys.exit(1)
    run_all("prod", sys.argv[1], sys.argv[2])
