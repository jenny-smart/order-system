# -*- coding: utf-8 -*-
"""檸檬系統保留單安全取消。"""

from __future__ import annotations

import re
from typing import List, Optional

import orders
from function import cancel_order as co

SYSTEM_RESERVE_MEMO = "系統保留單"


def _assert_supported_env(env_name):
    if str(env_name or "").strip().lower() not in {"dev", "prod"}:
        raise RuntimeError("保留單功能只支援 prod 正式機或 dev 測試機。")


def _memo_matches_filter(memo, memo_filter):
    memo = str(memo or "").strip()
    if memo_filter == "僅系統保留單": return SYSTEM_RESERVE_MEMO in memo
    if memo_filter == "僅空白": return memo == ""
    if memo_filter == "系統保留單或空白": return memo == "" or SYSTEM_RESERVE_MEMO in memo
    if memo_filter == "全部（僅供查看）": return True
    raise ValueError(f"未知客人備註篩選：{memo_filter}")


def _fetch_phone_orders_fast(env_name, backend_email, backend_password, phone, clean_date_s, clean_date_e, max_pages=12):
    session, base_url = co._new_logged_in_session(env_name, backend_email, backend_password)
    found, seen = [], set()
    debug = {"pages_scanned": 0, "cards_scanned": 0, "orders_parsed": 0}
    for page in range(1, max_pages + 1):
        params = dict(co.PURCHASE_FILTER_PARAMS_TEMPLATE)
        params.update({"phone": phone, "page": str(page), "orderBy": "date_clean:desc"})
        resp = session.get(f"{base_url}/purchase", params=params, headers=orders.HEADERS, allow_redirects=True, timeout=12)
        debug["pages_scanned"] += 1
        if resp.status_code != 200:
            raise RuntimeError(f"保留單搜尋失敗：HTTP {resp.status_code}")
        blocks = orders.extract_order_cards_from_purchase_html(resp.text)
        debug["cards_scanned"] += len(blocks)
        if not blocks: break
        page_dates = []
        for block in blocks:
            item = co._order_from_block(block)
            if not item: continue
            pid = str(item.get("purchase_id") or "")
            if not pid or pid in seen: continue
            seen.add(pid)
            if item.get("service_date"): page_dates.append(str(item["service_date"]))
            found.append(item)
        if len(blocks) < 20: break
        if page_dates and max(page_dates) < clean_date_s: break
    debug["orders_parsed"] = len(found)
    return found, debug


def find_reserve_orders(env_name, backend_email, backend_password, phone, clean_date_s, clean_date_e, memo_filter="系統保留單或空白", periods: Optional[List[str]]=None, return_debug=False):
    _assert_supported_env(env_name)
    phone = re.sub(r"\D", "", str(phone or ""))
    if not re.fullmatch(r"09\d{8}", phone): raise ValueError("手機號碼需為 09 開頭共 10 碼")
    if not clean_date_s or not clean_date_e or clean_date_s > clean_date_e: raise ValueError("請輸入正確服務日期區間")
    periods_set = {re.sub(r"\s+", "", str(p)) for p in (periods or []) if str(p).strip()}
    all_rows, debug = _fetch_phone_orders_fast(env_name, backend_email, backend_password, phone, clean_date_s, clean_date_e)
    candidates = []
    for row in all_rows:
        service_date = str(row.get("service_date") or "")
        if not service_date or not clean_date_s <= service_date <= clean_date_e: continue
        if periods_set and re.sub(r"\s+", "", str(row.get("period") or "")) not in periods_set: continue
        candidates.append(row)
    session, base_url = co._new_logged_in_session(env_name, backend_email, backend_password)
    found, detail_errors = [], 0
    for row in candidates:
        try:
            detail = co.fetch_order_cancel_details(session, base_url, row["purchase_id"])
        except Exception:
            detail_errors += 1
            continue
        memo = str(detail.get("memo") or "").strip()
        if not _memo_matches_filter(memo, memo_filter): continue
        item = dict(row)
        item["customer_memo"] = memo
        item["cancel_eligible"] = (memo == "" or SYSTEM_RESERVE_MEMO in memo)
        found.append(item)
    found.sort(key=lambda x: (x.get("service_date", ""), x.get("period", ""), x.get("order_no", "")))
    debug.update({"date_period_candidates": len(candidates), "memo_matches": len(found), "detail_errors": detail_errors})
    return (found, debug) if return_debug else found


def cancel_selected_reserve_orders(env_name, backend_email, backend_password, reserve_orders):
    _assert_supported_env(env_name)
    selected = [dict(r) for r in reserve_orders or []]
    if not selected: raise ValueError("目前沒有選擇要取消的保留單")
    session, base_url = co._new_logged_in_session(env_name, backend_email, backend_password)
    safe_rows, skipped = [], []
    for row in selected:
        try:
            detail = co.fetch_order_cancel_details(session, base_url, row["purchase_id"])
            current_memo = str(detail.get("memo") or "").strip()
        except Exception as exc:
            skipped.append({**row, "ok": False, "message": f"取消前讀取客人備註失敗，已跳過：{exc}"}); continue
        if current_memo and SYSTEM_RESERVE_MEMO not in current_memo:
            skipped.append({**row, "ok": False, "customer_memo": current_memo, "message": "客人備註已有其他內容，已跳過不取消。"}); continue
        safe_rows.append(row)
    cancelled = []
    if safe_rows:
        cancelled = co.cancel_orders(env_name, backend_email, backend_password, safe_rows, cancel_status="不需退款", customer_memo="取消系統保留單", charge_note="", refund_note="")
    return cancelled + skipped
