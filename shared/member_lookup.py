# -*- coding: utf-8 -*-
"""會員已付款訂單查詢與歷史服務彙整，供 quick_order.py 建單流程共用。

quick_lookup_member／quick_check_available_slots／get_stored_value 等「獨立登入
入口」仍留在 quick_order.py 原地，因為依賴 quick_order.py 自己的
_configure_environment（env 切換邏輯，屬於 Phase 3 範圍）；這裡只放給定
session/member_payload 後即可運作的純查詢/彙整函式。
"""

from datetime import date, datetime, timedelta

from shared.text_parsing import (
    normalize_addr_for_match, _date_not_after_today, _extract_person_hour_line,
    _extract_payway_line, _extract_invoice_line, _extract_clean_type_line,
    _extract_total_amount_line, _extract_fare_line, _extract_label_value,
    _is_paid_order_text, _parse_service_date_time_loose,
)
from shared.backend_client import (
    PURCHASE_STATUS_PAID, get_last_purchase_fetch_debug, _fetch_purchase_blocks_for_phone,
)

import orders


def get_customer_paid_orders(session, phone, known_addresses=None, name=""):
    known_addresses = known_addresses or []
    blocks = _fetch_purchase_blocks_for_phone(session, phone, name=name, purchase_status=PURCHASE_STATUS_PAID)
    trusted_paid_filter = (
        get_last_purchase_fetch_debug().get("effective_purchase_status_filter") == PURCHASE_STATUS_PAID
    )
    results = []
    for block in blocks:
        lines = block.get("lines", [])
        joined = "\n".join(lines)
        if not _is_paid_order_text(joined, trusted_paid_filter=trusted_paid_filter):
            continue
        service_date, service_time = _parse_service_date_time_loose(joined)
        if not service_date:
            continue
        joined_norm = normalize_addr_for_match(joined)
        matched_addr = ""
        for addr in known_addresses:
            if addr and normalize_addr_for_match(addr) in joined_norm:
                matched_addr = addr
                break
        person, hour = _extract_person_hour_line(joined)
        payway = _extract_payway_line(joined)
        invoice_text = "" if payway == "儲值金" else _extract_invoice_line(joined)
        results.append({
            "order_no": block["order_no"], "date": service_date, "time": service_time,
            "address": matched_addr, "clean_type": _extract_clean_type_line(joined),
            "staff": orders._extract_staff_line(lines), "payway": payway, "invoice_text": invoice_text,
            "service_notice": _extract_label_value(lines, "客服備註", ["財務備註", "客人備註"]),
            "person": person, "hour": hour,
            "total_amount": _extract_total_amount_line(joined),
            "fare": _extract_fare_line(joined),
        })
    results.sort(key=lambda x: (x["date"], x.get("time", "")), reverse=True)
    return results


def _match_person_hour(member_payload, order_no, address):
    if not isinstance(member_payload, dict):
        return "", ""
    last_purchase = member_payload.get("lastPurchase", {}) or {}
    member = member_payload.get("member", {}) or {}
    addr_list = member.get("memberAddressList", []) or []
    candidates = []
    if last_purchase:
        candidates.append(last_purchase)
    target_norm = normalize_addr_for_match(address) if address else ""
    for item in addr_list:
        if target_norm and normalize_addr_for_match(item.get("address", "")) == target_norm:
            item_purchase = item.get("purchase", {})
            if isinstance(item_purchase, dict) and item_purchase:
                candidates.append(item_purchase)
    for c in candidates:
        if str(c.get("order_no", "")).strip() == str(order_no).strip():
            return c.get("person", ""), c.get("hour", "")
    return "", ""


def _order_person_hour(member_payload, order):
    person, hour = _match_person_hour(member_payload, order.get("order_no", ""), order.get("address", ""))
    return person or order.get("person", ""), hour or order.get("hour", "")


def get_last_paid_per_address(session, phone, member_payload, known_addresses, within_days=365):
    cutoff = date.today() - timedelta(days=within_days)
    name = (member_payload.get("member", {}) or {}).get("name", "") if isinstance(member_payload, dict) else ""
    paid_orders = get_customer_paid_orders(session, phone, known_addresses, name=name)
    by_address = {}
    for o in paid_orders:
        addr = o.get("address", "")
        if not addr or addr in by_address:
            continue
        try:
            d = datetime.strptime(o["date"], "%Y-%m-%d").date()
        except Exception:
            continue
        if d > date.today() or d < cutoff:
            continue
        by_address[addr] = o
    result = {}
    for addr in known_addresses:
        order = by_address.get(addr)
        if not order:
            result[addr] = None
            continue
        person, hour = _order_person_hour(member_payload, order)
        result[addr] = {
            "order_no": order["order_no"], "date": order["date"], "time": order["time"],
            "clean_type": order["clean_type"], "staff": order["staff"], "payway": order["payway"],
            "invoice_text": order["invoice_text"], "service_notice": order["service_notice"],
            "person": person, "hour": hour, "fare": order.get("fare", ""),
        }
    return result


def get_last_paid_summary(session, phone, member_payload, known_addresses):
    name = (member_payload.get("member", {}) or {}).get("name", "") if isinstance(member_payload, dict) else ""
    paid_orders = get_customer_paid_orders(session, phone, known_addresses, name=name)
    paid_orders = [o for o in paid_orders if _date_not_after_today(o.get("date", ""))]
    if not paid_orders:
        return None
    latest = paid_orders[0]
    same_date_orders = []
    for order in paid_orders:
        if order["date"] != latest["date"]:
            continue
        person, hour = _order_person_hour(member_payload, order)
        enriched = dict(order)
        enriched["person"] = person
        enriched["hour"] = hour
        same_date_orders.append(enriched)
    person, hour = _order_person_hour(member_payload, latest)
    return {
        "order_no": latest["order_no"], "date": latest["date"], "time": latest["time"],
        "address": latest["address"], "clean_type": latest["clean_type"], "staff": latest["staff"],
        "payway": latest["payway"], "invoice_text": latest["invoice_text"],
        "service_notice": latest["service_notice"], "person": person, "hour": hour,
        "fare": latest.get("fare", ""), "same_date_orders": same_date_orders,
    }


def get_unserved_paid_orders(session, phone, member_payload, known_addresses, today_value=None):
    today_value = today_value or date.today()
    name = (member_payload.get("member", {}) or {}).get("name", "") if isinstance(member_payload, dict) else ""
    blocks = _fetch_purchase_blocks_for_phone(session, phone, name=name, purchase_status=PURCHASE_STATUS_PAID)
    trusted_paid_filter = (
        get_last_purchase_fetch_debug().get("effective_purchase_status_filter") == PURCHASE_STATUS_PAID
    )
    upcoming = []
    for block in blocks:
        lines = block.get("lines", [])
        joined = "\n".join(lines)
        if not _is_paid_order_text(joined, trusted_paid_filter=trusted_paid_filter):
            continue
        service_date, service_time = _parse_service_date_time_loose(joined)
        if not service_date:
            continue
        try:
            d = datetime.strptime(service_date, "%Y-%m-%d").date()
        except Exception:
            continue
        if d < today_value:
            continue
        joined_norm = normalize_addr_for_match(joined)
        matched_addr = ""
        for addr in known_addresses or []:
            if addr and normalize_addr_for_match(addr) in joined_norm:
                matched_addr = addr
                break
        payway = _extract_payway_line(joined)
        parsed_person, parsed_hour = _extract_person_hour_line(joined)
        person, hour = _match_person_hour(member_payload, block["order_no"], matched_addr)
        person = person or parsed_person
        hour = hour or parsed_hour
        upcoming.append({
            "order_no": block["order_no"], "date": service_date, "time": service_time,
            "address": matched_addr, "clean_type": _extract_clean_type_line(joined),
            "staff": orders._extract_staff_line(lines), "payway": payway,
            "invoice_text": "" if payway == "儲值金" else _extract_invoice_line(joined),
            "person": person, "hour": hour, "fare": _extract_fare_line(joined),
        })
    upcoming.sort(key=lambda x: x["date"])
    return upcoming
