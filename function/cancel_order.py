# ============================================================
# File: cancel_order.py
# Module: Cancel orders by phone + service month/date range + payment status
# Created: 2026-08-07
# Updated: 2026-08-08
#
# This module is intentionally independent from quick_order.py.
# It is designed to be rendered by ordersapp.py.
# ============================================================
# -*- coding: utf-8 -*-

import calendar
import html
import json
import re
from datetime import date

import requests
import streamlit as st
from bs4 import BeautifulSoup

import orders
from env import BASE_URL_DEV, BASE_URL_PROD


PURCHASE_FILTER_PARAMS_TEMPLATE = {
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
    "purchase_status": "",
    "progress_status": "",
    "invoiceStatus": "",
    "otherFee": "",
    "orderBy": "date_clean:asc",
}

CANCEL_STATUS_MAP = {
    "不需退款": "1",
    "待退款": "2",
    "待收異動": "3",
}

JSON_BACKED_EDIT_FIELDS = [
    "isCharge",
    "chargeDate",
    "chargePayment",
    "chargeInvoiceDate",
    "chargeAmount",
    "chargeInvoice",
    "chargeNote",
    "isRefund",
    "refundDate",
    "refundPayment",
    "refundAmount",
    "refundNumber",
    "refundInvoiceDate",
    "refundInvoiceAmount",
    "refundInvoice",
    "refundNote",
    "progress",
]


def _base_url(env_name: str) -> str:
    return BASE_URL_DEV if env_name == "dev" else BASE_URL_PROD


def _configure_orders_env(env_name: str) -> str:
    """Keep orders.login() on the same backend selected in ordersapp.py."""
    base_url = _base_url(env_name)
    orders.BASE_URL = base_url
    orders.LOGIN_URL = f"{base_url}/login"
    orders.PURCHASE_URL = f"{base_url}/purchase"
    return base_url


def _new_logged_in_session(env_name: str, email: str, password: str):
    base_url = _configure_orders_env(env_name)
    session = requests.Session()
    if not orders.login(session, email, password):
        raise RuntimeError("後台登入失敗，請確認帳號密碼")
    return session, base_url


def _csrf_from_html(page_html: str) -> str:
    m = re.search(r'<meta\s+name="csrf-token"\s+content="([^"]+)"', page_html or "", re.I)
    return m.group(1) if m else ""


def _parse_purchase_json(page_html: str) -> dict:
    """Read the real Vue purchase object from /purchase/edit/{id}."""
    m = re.search(r"purchase:\s*(\{.*?\})\s*\n?\s*\}\s*\n?\s*\}", page_html or "", re.S)
    if not m:
        return {}
    try:
        return json.loads(m.group(1))
    except Exception:
        return {}


def _edit_payload_from_page(page_html: str) -> tuple[dict, dict]:
    """
    Build a safe POST payload for the purchase edit page.

    Important: charge/refund fields are Vue-rendered. Static HTML contains template
    placeholders, so their real values must come from the embedded purchase JSON.
    """
    soup = BeautifulSoup(page_html, "html.parser")
    payload = {}

    form = soup.find("form", attrs={"method": re.compile("post", re.I)}) or soup.find("form")
    if form:
        for node in form.find_all(["input", "textarea", "select"]):
            name = node.get("name")
            if not name:
                continue
            if node.name == "textarea":
                payload[name] = node.get_text()
                continue
            if node.name == "select":
                selected = node.find("option", selected=True)
                if selected is not None:
                    payload[name] = selected.get("value", "")
                continue
            input_type = str(node.get("type") or "text").lower()
            if input_type in {"radio", "checkbox"}:
                if node.has_attr("checked"):
                    payload[name] = node.get("value", "1")
                continue
            if input_type in {"submit", "button", "file"}:
                continue
            payload[name] = node.get("value", "")

    purchase = _parse_purchase_json(page_html)
    for key in JSON_BACKED_EDIT_FIELDS:
        if key in purchase:
            value = purchase.get(key)
            payload[key] = "" if value is None else str(value)

    csrf = _csrf_from_html(page_html)
    if csrf:
        payload["_token"] = csrf
    payload.pop("_method", None)
    return payload, purchase


def _order_from_row(row):
    checkbox = row.find("input", attrs={"name": "purchase_id[]"})
    if checkbox is None:
        return None
    purchase_id = str(checkbox.get("value") or "").strip()
    if not purchase_id:
        return None

    text = "\n".join(
        ln.strip() for ln in row.get_text("\n", strip=True).splitlines() if ln.strip()
    )
    order_m = re.search(r"\b(?:LC|TT|KK)\d+\b", text)
    order_no = order_m.group(0) if order_m else ""

    phone_m = re.search(r"\b09\d{8}\b", text)
    phone = phone_m.group(0) if phone_m else ""

    service_date = ""
    for m in re.finditer(r"\b(20\d{2}-\d{2}-\d{2})\b", text):
        candidate = m.group(1)
        before = text[max(0, m.start() - 8):m.start()]
        if "付款日期" not in before and "取消時間" not in before:
            service_date = candidate
            break

    period_m = re.search(r"\b(\d{2}:\d{2})\s*-\s*(\d{2}:\d{2})\b", text)
    period = f"{period_m.group(1)}-{period_m.group(2)}" if period_m else ""

    status_m = re.search(r"付款狀態[：:]\s*([^\n]+)", text)
    payment_status = status_m.group(1).strip() if status_m else ""

    name = ""
    if phone:
        lines = [x.strip() for x in text.splitlines() if x.strip()]
        try:
            idx = lines.index(phone)
            if idx > 0:
                candidate = lines[idx - 1]
                if candidate not in {"LINE", order_no}:
                    name = candidate
        except ValueError:
            pass

    return {
        "purchase_id": purchase_id,
        "order_no": order_no,
        "name": name,
        "phone": phone,
        "service_date": service_date,
        "period": period,
        "payment_status": payment_status,
    }


def find_orders_for_cancel(
    env_name: str,
    backend_email: str,
    backend_password: str,
    phone: str,
    clean_date_s: str,
    clean_date_e: str,
    payment_status: str = "已付款",
    max_pages: int = 30,
):
    """Search backend orders by phone + service date range + payment status."""
    phone = re.sub(r"\D", "", str(phone or ""))
    if not re.fullmatch(r"09\d{8}", phone):
        raise ValueError("手機號碼需為 09 開頭共 10 碼")
    if not clean_date_s or not clean_date_e:
        raise ValueError("請輸入完整服務日期區間")
    if clean_date_s > clean_date_e:
        raise ValueError("服務日期起日不可晚於迄日")

    status_map = {"待付款": "0", "已付款": "1"}
    if payment_status not in status_map:
        raise ValueError("付款狀態僅支援：已付款／待付款")

    session, base_url = _new_logged_in_session(env_name, backend_email, backend_password)
    purchase_url = f"{base_url}/purchase"
    found = []
    seen = set()

    for page in range(1, max_pages + 1):
        params = dict(PURCHASE_FILTER_PARAMS_TEMPLATE)
        params.update({
            "phone": phone,
            "clean_date_s": clean_date_s,
            "clean_date_e": clean_date_e,
            "purchase_status": status_map[payment_status],
            "page": str(page),
        })
        resp = session.get(purchase_url, params=params, headers=orders.HEADERS, allow_redirects=True)
        if resp.status_code != 200:
            raise RuntimeError(f"訂單搜尋失敗：HTTP {resp.status_code}")
        soup = BeautifulSoup(resp.text, "html.parser")
        rows = soup.select("table tbody tr")
        if not rows:
            break

        page_added = 0
        for row in rows:
            item = _order_from_row(row)
            if not item or item["purchase_id"] in seen:
                continue
            if item["phone"] and item["phone"] != phone:
                continue
            if item["service_date"] and not (clean_date_s <= item["service_date"] <= clean_date_e):
                continue
            if item["payment_status"] and item["payment_status"] != payment_status:
                continue
            seen.add(item["purchase_id"])
            found.append(item)
            page_added += 1

        if len(rows) < 20 or page_added == 0:
            break

    return found


# Backward-compatible name for any existing caller.
def find_paid_orders_for_cancel(
    env_name: str,
    backend_email: str,
    backend_password: str,
    phone: str,
    clean_date_s: str,
    clean_date_e: str,
    max_pages: int = 30,
):
    return find_orders_for_cancel(
        env_name,
        backend_email,
        backend_password,
        phone,
        clean_date_s,
        clean_date_e,
        payment_status="已付款",
        max_pages=max_pages,
    )

def fetch_order_cancel_details(session, base_url: str, purchase_id: str) -> dict:
    edit_url = f"{base_url}/purchase/edit/{purchase_id}"
    resp = session.get(edit_url, headers=orders.HEADERS, allow_redirects=True)
    if resp.status_code != 200:
        raise RuntimeError(f"無法開啟訂單修改頁：HTTP {resp.status_code}")
    _, purchase = _edit_payload_from_page(resp.text)
    return {
        "memo": str(purchase.get("memo") or ""),
        "charge_note": str(purchase.get("chargeNote") or ""),
        "refund_note": str(purchase.get("refundNote") or ""),
    }


def _update_cancel_notes(
    session,
    base_url: str,
    purchase_id: str,
    customer_memo: str,
    charge_note: str,
    refund_note: str,
):
    """Re-open edit page after cancel, preserve all current values, and save notes."""
    edit_url = f"{base_url}/purchase/edit/{purchase_id}"
    resp = session.get(edit_url, headers=orders.HEADERS, allow_redirects=True)
    if resp.status_code != 200:
        return False, f"取消成功，但讀取備註頁失敗：HTTP {resp.status_code}"

    payload, _purchase = _edit_payload_from_page(resp.text)
    if not payload.get("_token"):
        return False, "取消成功，但無法取得修改頁 CSRF token，備註尚未寫入"

    payload["memo"] = str(customer_memo or "")
    payload["chargeNote"] = str(charge_note or "")
    payload["refundNote"] = str(refund_note or "")

    post = session.post(
        edit_url,
        data=payload,
        headers={**orders.HEADERS, "Content-Type": "application/x-www-form-urlencoded"},
        allow_redirects=True,
    )
    if post.status_code not in (200, 302):
        return False, f"取消成功，但備註寫入失敗：HTTP {post.status_code}"
    return True, ""


def cancel_orders(
    env_name: str,
    backend_email: str,
    backend_password: str,
    orders_to_cancel: list[dict],
    cancel_status: str,
    customer_memo: str,
    charge_note: str,
    refund_note: str,
):
    if cancel_status not in CANCEL_STATUS_MAP:
        raise ValueError("請選擇取消處理方式")
    if not orders_to_cancel:
        raise ValueError("請至少選擇一筆訂單")

    session, base_url = _new_logged_in_session(env_name, backend_email, backend_password)

    purchase_page = session.get(f"{base_url}/purchase", headers=orders.HEADERS, allow_redirects=True)
    csrf = _csrf_from_html(purchase_page.text)
    if not csrf:
        raise RuntimeError("無法取得取消訂單所需 CSRF token")

    results = []
    for item in orders_to_cancel:
        purchase_id = str(item.get("purchase_id") or "").strip()
        try:
            cancel_url = f"{base_url}/purchase/cancel/{purchase_id}"
            cancel_resp = session.post(
                cancel_url,
                json={
                    "status": CANCEL_STATUS_MAP[cancel_status],
                    "newMemo": str(customer_memo or ""),
                    "_token": csrf,
                },
                headers={**orders.HEADERS, "X-CSRF-TOKEN": csrf, "Referer": f"{base_url}/purchase"},
                allow_redirects=True,
            )
            if cancel_resp.status_code not in (200, 201, 204, 302):
                raise RuntimeError(f"取消失敗：HTTP {cancel_resp.status_code}")

            note_ok, note_msg = _update_cancel_notes(
                session,
                base_url,
                purchase_id,
                customer_memo,
                charge_note,
                refund_note,
            )
            results.append({
                **item,
                "ok": True,
                "note_ok": note_ok,
                "message": "取消成功" if note_ok else note_msg,
            })
        except Exception as exc:
            results.append({**item, "ok": False, "note_ok": False, "message": str(exc)})

    return results


def _date_value(value):
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def render_cancel_order(backend_email: str, backend_password: str, env_name: str):
    st.markdown("### 取消訂單")
    st.caption("依手機號碼＋服務月份／日期區間＋付款狀態搜尋訂單；勾選後可批次取消。")

    query_mode = st.radio(
        "服務日期查詢方式",
        ["月份", "日期區間"],
        horizontal=True,
        key="cancel_order_query_mode",
    )

    today = date.today()
    if query_mode == "月份":
        y1, y2 = st.columns(2)
        year_options = list(range(today.year - 1, today.year + 3))
        with y1:
            query_year = st.selectbox(
                "年份",
                year_options,
                index=year_options.index(today.year),
                key="cancel_order_query_year",
            )
        with y2:
            query_month = st.selectbox(
                "月份",
                list(range(1, 13)),
                index=today.month - 1,
                format_func=lambda m: f"{m} 月",
                key="cancel_order_query_month",
            )
        last_day = calendar.monthrange(int(query_year), int(query_month))[1]
        start_date = date(int(query_year), int(query_month), 1)
        end_date = date(int(query_year), int(query_month), last_day)
    else:
        d1, d2 = st.columns(2)
        with d1:
            start_date = st.date_input(
                "服務日期－起",
                value=today,
                key="cancel_order_date_s",
            )
        with d2:
            end_date = st.date_input(
                "服務日期－迄",
                value=today,
                key="cancel_order_date_e",
            )
        if start_date > end_date:
            st.error("服務日期起日不可晚於迄日")
            return

    c1, c2 = st.columns([1.4, 1])
    with c1:
        phone = st.text_input("手機號碼", key="cancel_order_phone", placeholder="09xxxxxxxx")
    with c2:
        payment_status = st.selectbox(
            "付款狀態",
            ["已付款", "待付款"],
            index=0,
            key="cancel_order_payment_status",
        )

    st.caption(f"查詢範圍：{_date_value(start_date)} ～ {_date_value(end_date)}")

    if st.button(
        f"🔎 搜尋{payment_status}訂單",
        key="cancel_order_search",
        type="primary",
        use_container_width=True,
    ):
        if not backend_email or not backend_password:
            st.error("請先輸入後台帳號與密碼")
        else:
            try:
                with st.spinner("搜尋訂單中…"):
                    rows = find_orders_for_cancel(
                        env_name,
                        backend_email,
                        backend_password,
                        phone,
                        _date_value(start_date),
                        _date_value(end_date),
                        payment_status=payment_status,
                    )
                st.session_state.cancel_order_results = rows
                st.session_state.cancel_order_selected = {r["purchase_id"]: True for r in rows}
                st.session_state.cancel_order_search_status = payment_status
                if not rows:
                    st.warning(
                        f"查無符合『手機號碼＋{query_mode}＋{payment_status}』的訂單"
                    )
            except Exception as exc:
                st.session_state.cancel_order_results = []
                st.error(str(exc))

    rows = st.session_state.get("cancel_order_results") or []
    if not rows:
        return

    searched_status = st.session_state.get("cancel_order_search_status", payment_status)
    st.markdown(f"#### 搜尋結果：{len(rows)} 筆")
    st.caption(f"本次付款狀態：{searched_status}")
    st.warning("取消屬於高影響操作，送出前請再次確認訂單編號與服務日期。")

    selected = []
    for i, row in enumerate(rows):
        label = (
            f"{row.get('order_no') or row.get('purchase_id')}　"
            f"{row.get('service_date')} {row.get('period')}　"
            f"{row.get('name')} {row.get('phone')}　付款狀態：{row.get('payment_status') or searched_status}"
        )
        checked = st.checkbox(
            label,
            value=st.session_state.get("cancel_order_selected", {}).get(row["purchase_id"], True),
            key=f"cancel_order_pick_{row['purchase_id']}_{i}",
        )
        if checked:
            selected.append(row)

    if not selected:
        st.info("請至少勾選一筆要取消的訂單")
        return

    if st.button("🛑 取消選取訂單", key="cancel_order_open_dialog", type="primary", use_container_width=True):
        st.session_state.cancel_order_pending = selected
        st.session_state.cancel_order_dialog_open = True
        st.rerun()

    last_result = st.session_state.get("cancel_order_last_result") or []
    if last_result:
        st.markdown("#### 最近一次取消結果")
        for item in last_result:
            if item.get("ok") and item.get("note_ok"):
                st.success(f"✅ {item.get('order_no') or item.get('purchase_id')}：取消成功，備註已寫入")
            elif item.get("ok"):
                st.warning(f"⚠️ {item.get('order_no') or item.get('purchase_id')}：{item.get('message')}")
            else:
                st.error(f"❌ {item.get('order_no') or item.get('purchase_id')}：{item.get('message')}")

    if not st.session_state.get("cancel_order_dialog_open"):
        return

    pending = st.session_state.get("cancel_order_pending") or []
    first = pending[0] if pending else None
    if not first:
        st.session_state.cancel_order_dialog_open = False
        return

    try:
        session, base_url = _new_logged_in_session(env_name, backend_email, backend_password)
        defaults = fetch_order_cancel_details(session, base_url, first["purchase_id"])
    except Exception as exc:
        defaults = {"memo": "", "charge_note": "", "refund_note": ""}
        st.error(f"讀取原訂單備註失敗：{exc}")

    def _dialog_body():
        st.markdown(f"**已選 {len(pending)} 筆訂單**")
        for item in pending[:8]:
            st.caption(f"{item.get('order_no')}　{item.get('service_date')} {item.get('period')}")
        if len(pending) > 8:
            st.caption(f"…另有 {len(pending) - 8} 筆")

        status = st.radio(
            "取消處理方式",
            ["不需退款", "待退款", "待收異動"],
            index=None,
            key="cancel_order_status",
        )
        memo = st.text_area(
            "客人備註",
            value=defaults.get("memo", ""),
            height=140,
            key="cancel_order_memo",
        )
        charge_note = st.text_area(
            "加收備註",
            value=defaults.get("charge_note", ""),
            height=110,
            key="cancel_order_charge_note",
            help="不論是否選『待收異動』都會顯示；有填就寫入訂單加收備註。",
        )
        refund_note = st.text_area(
            "待退備註",
            value=defaults.get("refund_note", ""),
            height=110,
            key="cancel_order_refund_note",
            help="不論是否選『待退款』都會顯示；有填就寫入訂單待退備註。",
        )

        col_cancel, col_ok = st.columns(2)
        with col_cancel:
            if st.button("取消", key="cancel_order_dialog_cancel", use_container_width=True):
                st.session_state.cancel_order_dialog_open = False
                st.rerun()
        with col_ok:
            if st.button("確定取消訂單", key="cancel_order_dialog_confirm", type="primary", use_container_width=True):
                if not status:
                    st.error("請先選擇：不需退款／待退款／待收異動")
                    return
                try:
                    with st.spinner("取消訂單並寫入備註中…"):
                        result = cancel_orders(
                            env_name,
                            backend_email,
                            backend_password,
                            pending,
                            status,
                            memo,
                            charge_note,
                            refund_note,
                        )
                    st.session_state.cancel_order_last_result = result
                    st.session_state.cancel_order_dialog_open = False
                    st.session_state.cancel_order_results = []
                    st.session_state.cancel_order_pending = []
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))

    if hasattr(st, "dialog"):
        @st.dialog("確定要取消訂單？", width="large")
        def _cancel_dialog():
            _dialog_body()
        _cancel_dialog()
    else:
        st.markdown("---")
        st.error("確定要取消訂單？")
        _dialog_body()
