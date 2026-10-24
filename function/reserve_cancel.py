# -*- coding: utf-8 -*-
"""Helpers for system reserve-order tagging and safe cancellation."""

from __future__ import annotations

import re
from typing import List, Optional

from function import cancel_order as co
import orders
from shared.reserve_sheet_log import append_log_rows

SYSTEM_RESERVE_MEMO = "系統保留單"
CANCELLED_RESERVE_MEMO = "取消系統保留單"
# 代客保留：用檸檬保留帳號替客人先 booking，客人備註寫「代客保留：客人姓名」。
PROXY_RESERVE_MEMO = "代客保留"
PROXY_FILTER = "代客保留（客人備註含關鍵字）"
CANCELLED_PREFIX = "取消"


def _is_active_proxy_memo(memo: str, keyword: str) -> bool:
    """客人備註含關鍵字（例如 代客保留：王小明），且還沒被取消（取消後備註前面加「取消」）。"""
    memo = str(memo or "").strip()
    return bool(keyword) and keyword in memo and not memo.startswith(CANCELLED_PREFIX)


def proxy_keyword(value: str) -> str:
    """關鍵字必須含「代客保留」，避免誤取消其他訂單。"""
    keyword = re.sub(r"\s+", "", str(value or "")).replace(":", "：")
    if PROXY_RESERVE_MEMO not in keyword:
        raise ValueError(f"客人備註關鍵字必須包含「{PROXY_RESERVE_MEMO}」，例如：代客保留：王小明")
    return keyword


def _is_active_reserve_memo(memo: str) -> bool:
    """客人備註是「系統保留單」且還沒被取消（取消後會改成「取消系統保留單」）。"""
    memo = str(memo or "").strip()
    return SYSTEM_RESERVE_MEMO in memo and CANCELLED_RESERVE_MEMO not in memo


def _assert_supported_env(env_name: str) -> None:
    env = str(env_name or "").strip().lower()
    if env not in {"dev", "prod"}:
        raise RuntimeError("保留單功能只支援 prod 正式機或 dev 測試機。")


def _purchase_id_from_order_no(order_no: str) -> str:
    digits = re.sub(r"\D", "", str(order_no or ""))
    return str(int(digits)) if digits else ""


def mark_system_reserve_order(env_name: str, backend_email: str, backend_password: str, order_no: str) -> dict:
    _assert_supported_env(env_name)
    purchase_id = _purchase_id_from_order_no(order_no)
    if not purchase_id:
        return {"ok": False, "order_no": order_no, "message": "無法取得 purchase_id"}
    session, base_url = co._new_logged_in_session(env_name, backend_email, backend_password)
    ok, msg = co._update_cancel_notes(
        session, base_url, purchase_id,
        customer_memo=SYSTEM_RESERVE_MEMO, charge_note="", refund_note="",
    )
    return {"ok": bool(ok), "order_no": order_no, "message": msg or ("客人備註已註記系統保留單" if ok else "客人備註註記失敗")}


def _memo_matches_filter(memo: str, memo_filter: str, keyword: str = "") -> bool:
    memo = str(memo or "").strip()
    if memo_filter == PROXY_FILTER:
        return _is_active_proxy_memo(memo, keyword)
    if memo_filter == "僅系統保留單":
        return _is_active_reserve_memo(memo)
    if memo_filter == "僅空白":
        return memo == ""
    if memo_filter == "系統保留單或空白":
        return memo == "" or _is_active_reserve_memo(memo)
    if memo_filter == "全部（僅供查看）":
        return True
    raise ValueError(f"未知客人備註篩選：{memo_filter}")


def _fetch_phone_orders_fast(
    env_name: str,
    backend_email: str,
    backend_password: str,
    phone: str,
    clean_date_s: str,
    clean_date_e: str,
    max_pages: int = 12,
) -> tuple[List[dict], dict]:
    """Fetch recent phone orders newest-first and stop after passing requested range.

    Reserve orders can be zero-dollar/processed, so payment status cannot be used.
    The previous implementation scanned up to 50 pages oldest-first, which could look
    like a frozen button. This version requests newest-first and normally needs only
    the first few pages for a recent service-date window.
    """
    session, base_url = co._new_logged_in_session(env_name, backend_email, backend_password)
    purchase_url = f"{base_url}/purchase"
    found: List[dict] = []
    seen = set()
    pages_scanned = 0
    cards_scanned = 0

    for page in range(1, max_pages + 1):
        params = dict(co.PURCHASE_FILTER_PARAMS_TEMPLATE)
        params.update({
            "phone": phone,
            "page": str(page),
            "orderBy": "date_clean:desc",
        })
        resp = session.get(
            purchase_url,
            params=params,
            headers=orders.HEADERS,
            allow_redirects=True,
            timeout=12,
        )
        pages_scanned += 1
        if resp.status_code != 200:
            raise RuntimeError(f"保留單搜尋失敗：HTTP {resp.status_code}")

        blocks = orders.extract_order_cards_from_purchase_html(resp.text)
        cards_scanned += len(blocks)
        if not blocks:
            break

        page_dates = []
        for block in blocks:
            item = co._order_from_block(block)
            if not item:
                continue
            pid = str(item.get("purchase_id") or "")
            if not pid or pid in seen:
                continue
            seen.add(pid)
            service_date = str(item.get("service_date") or "")
            if service_date:
                page_dates.append(service_date)
            found.append(item)

        if len(blocks) < 20:
            break

        # Newest-first: once a full page is entirely older than requested start,
        # later pages cannot contain matches.
        dated = [d for d in page_dates if d]
        if dated and max(dated) < clean_date_s:
            break

    return found, {
        "pages_scanned": pages_scanned,
        "cards_scanned": cards_scanned,
        "orders_parsed": len(found),
    }


def find_reserve_orders(
    env_name: str, backend_email: str, backend_password: str, phone: str,
    clean_date_s: str, clean_date_e: str,
    memo_filter: str = "系統保留單或空白", periods: Optional[List[str]] = None,
    return_debug: bool = False, memo_keyword: str = "",
):
    _assert_supported_env(env_name)
    keyword = proxy_keyword(memo_keyword) if memo_filter == PROXY_FILTER else ""
    phone = re.sub(r"\D", "", str(phone or ""))
    if not re.fullmatch(r"09\d{8}", phone):
        raise ValueError("手機號碼需為 09 開頭共 10 碼")
    if not clean_date_s or not clean_date_e or clean_date_s > clean_date_e:
        raise ValueError("請輸入正確服務日期區間")

    periods_set = {re.sub(r"\s+", "", str(p)) for p in (periods or []) if str(p).strip()}
    all_rows, debug = _fetch_phone_orders_fast(
        env_name, backend_email, backend_password, phone, clean_date_s, clean_date_e
    )

    candidates = []
    for row in all_rows:
        row_phone = re.sub(r"\D", "", str(row.get("phone") or ""))
        if row_phone and row_phone != phone:
            continue
        service_date = str(row.get("service_date") or "")
        if not service_date or not (clean_date_s <= service_date <= clean_date_e):
            continue
        if periods_set:
            period = re.sub(r"\s+", "", str(row.get("period") or ""))
            if period not in periods_set:
                continue
        candidates.append(row)

    session, base_url = co._new_logged_in_session(env_name, backend_email, backend_password)
    found = []
    detail_errors = 0
    for row in candidates:
        try:
            detail = co.fetch_order_cancel_details(session, base_url, row["purchase_id"])
        except Exception as exc:
            detail_errors += 1
            if memo_filter == "全部（僅供查看）":
                item = dict(row)
                item["customer_memo"] = ""
                item["memo_read_error"] = str(exc)
                item["cancel_eligible"] = False
                found.append(item)
            continue

        memo = str(detail.get("memo") or "").strip()
        if not _memo_matches_filter(memo, memo_filter, keyword):
            continue
        item = dict(row)
        item["customer_memo"] = memo
        if keyword:
            item["memo_keyword"] = keyword
            item["cancel_eligible"] = True
        else:
            item["cancel_eligible"] = (memo == "" or _is_active_reserve_memo(memo))
        for key in (
            "amount", "total_amount", "order_amount", "price", "fare", "car_fare",
            "traffic_fee", "trafficFee", "staff", "staff_names", "service_staff",
        ):
            if item.get(key) in (None, "") and detail.get(key) not in (None, ""):
                item[key] = detail.get(key)
        found.append(item)

    found.sort(key=lambda x: (x.get("service_date", ""), x.get("period", ""), x.get("order_no", "")))
    debug.update({
        "date_period_candidates": len(candidates),
        "memo_matches": len(found),
        "detail_errors": detail_errors,
    })
    if return_debug:
        return found, debug
    return found


def cancel_reserve_orders(
    env_name: str, backend_email: str, backend_password: str,
    reserve_orders: List[dict], cancel_count: int,
) -> List[dict]:
    _assert_supported_env(env_name)
    count = max(0, int(cancel_count or 0))
    if count <= 0:
        raise ValueError("取消張數必須大於 0")

    ordered = sorted(
        [dict(r) for r in (reserve_orders or [])],
        key=lambda x: (x.get("service_date", ""), x.get("period", ""), x.get("order_no", "")),
    )
    selected = ordered[:count]
    if not selected:
        raise ValueError("目前沒有可取消的保留單")

    session, base_url = co._new_logged_in_session(env_name, backend_email, backend_password)
    safe_rows = []
    skipped = []
    for row in selected:
        try:
            detail = co.fetch_order_cancel_details(session, base_url, row["purchase_id"])
            current_memo = str(detail.get("memo") or "").strip()
        except Exception as exc:
            skipped.append({**row, "ok": False, "message": f"取消前讀取客人備註失敗，已跳過：{exc}"})
            continue
        keyword = str(row.get("memo_keyword") or "")
        if keyword:
            if not _is_active_proxy_memo(current_memo, keyword):
                skipped.append({
                    **row, "ok": False, "customer_memo": current_memo,
                    "message": f"客人備註已不含「{keyword}」或已取消過，已跳過。",
                })
                continue
            safe_rows.append({**row, "cancel_memo": CANCELLED_PREFIX + current_memo})
            continue
        if CANCELLED_RESERVE_MEMO in current_memo:
            skipped.append({
                **row, "ok": False, "customer_memo": current_memo,
                "message": "此保留單已取消過，已跳過。",
            })
            continue
        if current_memo and SYSTEM_RESERVE_MEMO not in current_memo:
            skipped.append({
                **row, "ok": False, "customer_memo": current_memo,
                "message": "客人備註已有其他內容，判定可能是人工替客人保留，已跳過不取消。",
            })
            continue
        safe_rows.append(row)

    cancelled = []
    if safe_rows:
        # 系統保留單一律改成「取消系統保留單」；代客保留各張改成「取消」＋原客人備註。
        by_memo = {}
        for row in safe_rows:
            by_memo.setdefault(row.get("cancel_memo") or CANCELLED_RESERVE_MEMO, []).append(row)
        for memo, group in by_memo.items():
            cancelled += co.cancel_orders(
                env_name, backend_email, backend_password, group,
                cancel_status="不需退款", customer_memo=memo,
                charge_note="", refund_note="",
            )
        source_by_order = {str(r.get("order_no") or ""): r for r in safe_rows}
        enriched = []
        for result in cancelled:
            source = source_by_order.get(str(result.get("order_no") or ""), {})
            item = dict(source)
            item.update(result)
            enriched.append(item)
        cancelled = enriched
        try:
            append_log_rows("取消", cancelled)
        except Exception as log_exc:
            for row in cancelled:
                row["sheet_log_error"] = str(log_exc)

    return cancelled + skipped
