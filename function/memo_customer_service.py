# -*- coding: utf-8 -*-
"""客服作業（舊客回購備註回填／新成單提醒建立／客服備忘錄整理）。

原本 memo_system/memo.py 的業務邏輯（訂單搜尋/解析/比對/回填）併入這裡，
跟 UI 合成一個檔案；memo_system/memo.py 已刪除。
"""

import re
import time
from typing import Optional, List, Dict

import streamlit as st
from bs4 import BeautifulSoup

from shared import memo_backend
from shared.memo_backend import (
    set_runtime_credentials, secret_value, SLEEP_SECONDS, CURRENT_ROW_LOGS,
    make_logger, blank_result, with_retry, session_get, session_post,
    get_ws, get_log_ws, append_log_row, apply_sheet_presentation, login,
)
from shared.memo_text import (
    normalize_phone, parse_phone_list, normalize_text, same_address,
    safe_cell, parse_date, parse_row_spec, extract_name_from_text_block,
    extract_service_date_from_page_text, extract_address_from_text_block,
    get_purchase_id_from_edit_url, display_service_date, item_service_date_obj,
)
from function.ui_common import step
from function.memo_shared import get_session, DEFAULT_RESULT, normalize_result
from shared.execution_log_service import log_execution
import traceback as _memo_traceback


# 新成單（地址完全沒有歷史訂單）時，自動帶入的固定提醒文字
DEFAULT_NEW_ORDER_NOTICE = (
    "請現場跟客戶溝通清潔優先順序，並請回報以下內容\n"
    "＊工作項目＋時間分配\n"
    "＊特別注意事項\n"
    "＊服務小貼心"
)


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
        edit_url = f"{memo_backend.BASE_URL}{edit_link['href']}" if edit_link and edit_link.get("href", "").startswith("/") else (edit_link["href"] if edit_link else "")
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
        memo_backend.PURCHASE_URL,
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
        memo_backend.PURCHASE_URL,
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

    r = session_get(session, memo_backend.PURCHASE_URL, params=params)
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
        action = f"{memo_backend.BASE_URL}{action}"

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


def safe_get(row, *keys, default=""):
    for k in keys:
        if k in row and row.get(k) is not None:
            return row.get(k)
    return default


def clear_pick_states():
    for k in [k for k in st.session_state.keys() if k.startswith("pick_")]:
        del st.session_state[k]


def reset_mode_state_if_changed(current_mode):
    if st.session_state.last_mode != current_mode:
        st.session_state.preview_rows = []
        st.session_state.sheet_summary = None
        clear_pick_states()
        st.session_state.last_mode = current_mode


def render_preview_blocks(rows):
    step("4", "查詢結果預覽")
    if not rows:
        st.info("查無資料")
        return []

    can_rows = [r for r in rows if r.get("can_autofill")]
    no_rows  = [r for r in rows if not r.get("can_autofill")]

    m1, m2, m3 = st.columns(3)
    m1.metric("查詢總筆數", len(rows))
    m2.metric("可自動回填", len(can_rows))
    m3.metric("無可參照來源", len(no_rows))

    st.markdown(
        '<div class="info-strip">'
        '<b>預覽說明</b><ul>'
        '<li>目前訂單：要回填備註的目標訂單</li>'
        '<li>來源訂單：最近一筆可參照的歷史訂單</li>'
        '<li>新成單：沒有歷史來源時，會帶入預設提醒文字</li>'
        '</ul></div>',
        unsafe_allow_html=True
    )

    selected_ids = []

    def render_section(title, items, section_key, default_checked):
        st.markdown(f"### {title}")
        if not items:
            st.caption("沒有資料")
            return

        c1, c2, c3 = st.columns([1, 1, 4])
        with c1:
            if st.button("本區全選", key=f"sel_{section_key}", use_container_width=True):
                for row in items:
                    oid = str(row.get("order_id", "")).strip()
                    if oid:
                        st.session_state[f"pick_{oid}"] = True
        with c2:
            if st.button("本區全不選", key=f"unsel_{section_key}", use_container_width=True):
                for row in items:
                    oid = str(row.get("order_id", "")).strip()
                    if oid:
                        st.session_state[f"pick_{oid}"] = False
        with c3:
            st.caption(f"本區共 {len(items)} 筆")

        for row in items:
            order_id = str(row.get("order_id", "")).strip()
            checked = st.checkbox(
                f"選取 {order_id}",
                key=f"pick_{order_id}",
                value=st.session_state.get(f"pick_{order_id}", default_checked),
                label_visibility="collapsed"
            )

            card_cls = "preview-card preview-ok" if row.get("can_autofill") else "preview-card preview-ng"
            target_name          = row.get("customer_name", "")
            phone                = row.get("phone", "")
            address              = row.get("address", "")
            service_date         = row.get("service_date", "")
            purchase_status_name = row.get("purchase_status_name", "")
            source_order_id      = row.get("source_order_id", "")
            source_service_date  = row.get("source_service_date", "")
            source_purchase_status_name = row.get("source_purchase_status_name", "")
            source_status_name   = row.get("source_status_name", "")
            source_notice_preview = row.get("source_notice_preview", "")
            is_new_order         = row.get("is_new_order", False)
            can_autofill         = row.get("can_autofill", False)

            if is_new_order:
                source_notice_display_html = "（請於下方欄位編輯要寫入後台的提醒文字）"
                suggestion_text = "新成單，將帶入下方可編輯的提醒文字"
            elif can_autofill:
                source_notice_display_html = source_notice_preview.replace("\n", "<br>") if source_notice_preview else ""
                suggestion_text = "建議執行"
            else:
                source_notice_display_html = source_notice_preview.replace("\n", "<br>") if source_notice_preview else ""
                suggestion_text = "無可參照來源，請人工確認"

            st.markdown(f"""
            <div class="{card_cls}">
                <div class="preview-title">目前訂單：{order_id}</div>
                <div class="preview-sub">
                    <b>客戶 / 電話：</b>{target_name} / {phone}<br>
                    <b>地址：</b>{address}<br>
                    <b>目前服務日期：</b>{service_date}
                    <b>目前付款狀態：</b>{purchase_status_name or "-"}
                </div>
                <hr style="margin:10px 0;">
                <div class="preview-sub">
                    <b>來源訂單：</b>{source_order_id or "無"}<br>
                    <b>來源服務日期：</b>{source_service_date or "-"}
                    <b>來源付款狀態：</b>{source_purchase_status_name or "-"}
                    <b>來源服務狀態：</b>{source_status_name or "-"}<br>
                    <b>來源備註：</b>{source_notice_display_html or "無"}
                </div>
                <div class="preview-sub" style="margin-top:8px;">
                    <b>建議：</b>{suggestion_text}
                </div>
            </div>
            """, unsafe_allow_html=True)

            if is_new_order:
                st.text_area(
                    f"✏️ 新成單提醒文字（{order_id}，可自行編輯，將寫入後台備註）",
                    value=st.session_state.get(f"new_notice_{order_id}", DEFAULT_NEW_ORDER_NOTICE),
                    key=f"new_notice_{order_id}",
                    height=130,
                )

            if checked and order_id:
                selected_ids.append(order_id)

    render_section("可自動回填", can_rows, "can_autofill", True)
    render_section("無可參照來源", no_rows, "no_source", False)

    st.markdown("---")
    step("5", "執行確認")
    st.metric("目前勾選", len(selected_ids))
    st.caption("執行後會把來源客服備註（或新成單固定提醒文字）寫入目標訂單，並把目標訂單服務狀態改為已處理。")
    return selected_ids


def render(backend_email, backend_password, env):
    email, env_option = backend_email, env
    step("3", "設定查詢條件")

    mode = st.radio(
        "",
        ["By Google Sheet", "By 電話", "By 搜尋條件"],
        horizontal=True,
        label_visibility="collapsed",
        key="memo_mode",
    )
    reset_mode_state_if_changed(mode)

    row_spec = ""; force = False; sheet_run_mode = "指定列號"; sheet_limit = 5
    phone_text = ""; date_mode = "服務日期"; purchase_status_name = "全部"
    start_date = None; end_date = None
    sheet_summary_btn = False; search_btn = False; execute_btn = False

    if mode == "By Google Sheet":
        sheet_run_mode = st.radio("處理方式", ["指定列號", "依剩餘筆數處理"], horizontal=True)
        if sheet_run_mode == "指定列號":
            st.markdown('<div class="info-strip"><b>列號格式</b><ul><li>單列：<code>2</code></li><li>多列：<code>2,3,5</code></li><li>區間：<code>2,3,5-7</code></li></ul></div>', unsafe_allow_html=True)
            c1, c2 = st.columns([5, 1])
            with c1:
                row_spec = st.text_input("列號")
            with c2:
                st.markdown("<div style='height:26px'></div>", unsafe_allow_html=True)
                force = st.checkbox("強制重跑")
            execute_btn = st.button("🚀 執行", use_container_width=True, disabled=not st.session_state.credentials_ready)
        else:
            c1, c2 = st.columns(2)
            with c1:
                sheet_summary_btn = st.button("🔍 查詢目前筆數", use_container_width=True, disabled=not st.session_state.credentials_ready)
            with c2:
                sheet_limit = st.number_input("本次處理筆數", min_value=1, value=5)
            if st.session_state.sheet_summary:
                s = st.session_state.sheet_summary
                m1, m2, m3 = st.columns(3)
                m1.metric("總筆數", s.get("total_rows", 0))
                m2.metric("未處理筆數", s.get("pending_rows", 0))
                m3.metric("已處理筆數", s.get("done_rows", 0))
            execute_btn = st.button("🚀 執行前 N 筆未處理資料", use_container_width=True, disabled=not st.session_state.credentials_ready)

    elif mode == "By 電話":
        phone_text = st.text_area("電話號碼", placeholder="可輸入多支，以逗號或換行分隔，例：0912345678,0922345678")
        st.caption("會先找出「目標訂單」，再比對最近一筆可參照的來源訂單。")
        c1, c2 = st.columns(2)
        with c1:
            search_btn = st.button("🔍 查詢列表", use_container_width=True, disabled=not st.session_state.credentials_ready)
        with c2:
            execute_btn = st.button("🚀 執行勾選項目", use_container_width=True, disabled=not st.session_state.credentials_ready)

    else:
        c1, c2 = st.columns(2)
        with c1:
            date_mode = st.selectbox("日期條件", ["服務日期", "購買日期"])
        with c2:
            purchase_status_name = st.selectbox("付款狀態", ["全部", "已付款", "未付款"], index=0)
        c3, c4 = st.columns(2)
        with c3:
            start_date = st.date_input("開始日期", value=None)
        with c4:
            end_date = st.date_input("結束日期", value=None)
        st.caption("搜尋條件固定只撈服務狀態＝未處理的目標訂單，再比對最近的可參照來源。")
        c5, c6 = st.columns(2)
        with c5:
            search_btn = st.button("🔍 查詢列表", use_container_width=True, disabled=not st.session_state.credentials_ready)
        with c6:
            execute_btn = st.button("🚀 執行勾選項目", use_container_width=True, disabled=not st.session_state.credentials_ready)

    with st.expander("執行 LOG", expanded=True):
        log_box = st.empty()
        log_box.text("\n".join(st.session_state.logs[-3000:]) if st.session_state.logs else "尚未執行")

    result_container = st.container()

    def ui_log(msg):
        st.session_state.logs.append(str(msg))
        try:
            log_box.text("\n".join(st.session_state.logs[-3000:]))
        except Exception:
            pass

    def render_result(result):
        r = normalize_result(result)
        with result_container:
            st.markdown("---")
            step("6", "執行結果")
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("執行筆數", r["processed"])
            c2.metric("成功", r["success"])
            c3.metric("失敗", r["failed"])
            c4.metric("略過", r["skipped"])
            c5.metric("回寫筆數", r["updated_orders"])
            if r["errors"]:
                with st.expander(f"⚠️ 錯誤明細（{len(r['errors'])} 筆）", expanded=True):
                    for i, err in enumerate(r["errors"], 1):
                        st.markdown(f"**{i}.** {err}")
            elif r["processed"] > 0:
                st.success(f"✅ 全部完成，共處理 {r['processed']} 筆，成功 {r['success']} 筆。")
            else:
                st.info("執行完成，無資料被處理。")

    def reset_before_action(clear_preview=True, clear_selection=True):
        st.session_state.logs = []
        st.session_state.result = None
        if clear_preview:
            st.session_state.preview_rows = []
            st.session_state.sheet_summary = None
        if clear_selection:
            clear_pick_states()
        try:
            log_box.text("尚未執行")
        except Exception:
            pass

    def reset_before_execute_keep_preview():
        st.session_state.logs = []
        st.session_state.result = None
        try:
            log_box.text("尚未執行")
        except Exception:
            pass

    if st.session_state.result is not None:
        render_result(st.session_state.result)

    if sheet_summary_btn:
        try:
            st.session_state.is_running = True
            reset_before_action(clear_preview=True, clear_selection=True)
            ui_log("===== 查詢目前筆數 =====")
            with st.spinner("查詢中，請稍候…"):
                st.session_state.sheet_summary = get_sheet_summary(ui_logger=ui_log)
            ui_log("✅ 查詢完成")
        except Exception as e:
            ui_log(f"❌ 查詢失敗：{e}")
            st.error(str(e))
        finally:
            st.session_state.is_running = False

    if search_btn:
        try:
            st.session_state.is_running = True
            reset_before_action(clear_preview=True, clear_selection=True)
            ui_log("===== 開始查詢 =====")
            with st.spinner("查詢中，請稍候…"):
                session = get_session(email, env_option, ui_logger=ui_log)
                if mode == "By 電話":
                    if not phone_text.strip():
                        raise ValueError("請輸入至少一支電話")
                    preview_rows = preview_by_phone_multi(phone_text=phone_text.strip(), ui_logger=ui_log, session=session)
                else:
                    start_text = start_date.strftime("%Y/%m/%d") if start_date else ""
                    end_text   = end_date.strftime("%Y/%m/%d") if end_date else ""
                    preview_rows = preview_by_conditions(
                        date_mode=date_mode, date_start=start_text, date_end=end_text,
                        purchase_status_name=purchase_status_name, ui_logger=ui_log, session=session,
                    )
            st.session_state.preview_rows = preview_rows or []
            ui_log(f"✅ 查詢完成，共 {len(st.session_state.preview_rows)} 筆")
            st.rerun()
        except Exception as e:
            ui_log(f"❌ 查詢錯誤：{e}")
            st.error(str(e))
        finally:
            st.session_state.is_running = False

    if mode in ["By 電話", "By 搜尋條件"] and st.session_state.preview_rows:
        st.markdown("---")
        render_preview_blocks(st.session_state.preview_rows)

    if execute_btn:
        try:
            st.session_state.is_running = True
            reset_before_execute_keep_preview()

            if mode == "By Google Sheet":
                ui_log("===== 開始執行 =====")
                with st.spinner("執行中，請稍候…"):
                    session = get_session(email, env_option, ui_logger=ui_log)
                    if sheet_run_mode == "指定列號":
                        result = main(row_spec=row_spec, force=force, ui_logger=ui_log, session=session)
                    else:
                        result = main_first_n_pending(limit=int(sheet_limit), ui_logger=ui_log, session=session)
            else:
                if not st.session_state.preview_rows:
                    raise RuntimeError("請先查詢列表")
                current_selected_ids = []
                custom_notices = {}
                for row in st.session_state.preview_rows:
                    oid = str(safe_get(row, "order_id", default="")).strip()
                    if oid and st.session_state.get(f"pick_{oid}", False):
                        current_selected_ids.append(oid)
                        if row.get("is_new_order"):
                            custom_notices[oid] = st.session_state.get(f"new_notice_{oid}", DEFAULT_NEW_ORDER_NOTICE)
                if not current_selected_ids:
                    raise RuntimeError("請先勾選要執行的資料")
                ui_log("===== 開始執行勾選項目 =====")
                ui_log(f"勾選筆數：{len(current_selected_ids)}")
                with st.spinner("執行中，請稍候…"):
                    session = get_session(email, env_option, ui_logger=ui_log)
                    result = main_by_selected_order_ids(
                        order_ids=current_selected_ids, ui_logger=ui_log,
                        session=session, custom_notices=custom_notices,
                    )

            ui_log("===== 執行完成 =====")
            st.session_state.result = result
            render_result(result)
            _r = normalize_result(result)
            log_execution(
                function_name="客服備註自動回填", status="失敗" if _r["failed"] else "成功",
                run_type=mode, target=row_spec if mode == "By Google Sheet" else phone_text.strip(),
                message=f"處理{_r['processed']}筆，成功{_r['success']}筆，失敗{_r['failed']}筆，回寫{_r['updated_orders']}筆",
            )
        except Exception as e:
            ui_log(f"❌ 執行錯誤：{e}")
            st.session_state.result = {**DEFAULT_RESULT, "failed": 1, "errors": [str(e)]}
            render_result(st.session_state.result)
            log_execution(
                function_name="客服備註自動回填", status="失敗", run_type=mode,
                message=str(e), traceback_text=_memo_traceback.format_exc(),
            )
        finally:
            st.session_state.is_running = False
