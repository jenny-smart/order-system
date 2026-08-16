# -*- coding: utf-8 -*-
"""共用畫面小工具，供 function/ 底下各功能檔案與 ordersapp.py 共用。"""

import html
import json

import streamlit as st
import streamlit.components.v1 as components


def copy_button(label, text, key):
    payload = json.dumps(text, ensure_ascii=False)
    label_payload = json.dumps(label, ensure_ascii=False)
    components.html(
        f"""
        <button id="{key}" style="width:100%;padding:0.65rem 1rem;border:0;border-radius:10px;background:#F5C518;color:#1C1C1E;font-size:15px;font-weight:700;cursor:pointer;">{html.escape(label)}</button>
        <script>
        const btn = document.getElementById({json.dumps(key)});
        const text = {payload};
        const label = {label_payload};
        btn.addEventListener("click", async () => {{
            try {{ await navigator.clipboard.writeText(text); btn.textContent = "已複製"; }}
            catch (err) {{ const ta = document.createElement("textarea"); ta.value = text; document.body.appendChild(ta); ta.select(); document.execCommand("copy"); document.body.removeChild(ta); btn.textContent = "已複製"; }}
            setTimeout(() => {{ btn.textContent = label; }}, 1600);
        }});
        </script>
        """,
        height=54,
    )


def show_duplicate_order_warning(order_no, count, dedup_key=""):
    """
    v8.13：訂單編號重複提醒視窗。
    優先使用 st.dialog 跳出真正的提醒視窗（Streamlit 1.31+）；
    若目前版本不支援 st.dialog，退回使用醒目的 st.error 區塊，
    確保任何 Streamlit 版本都看得到警示，不會被畫面其他內容淹沒。
    dedup_key 用來避免同一筆訂單在同一次畫面重繪中重複跳出視窗。
    """
    _seen_key = f"_dup_order_seen_{dedup_key or order_no}"
    if st.session_state.get(_seen_key):
        return
    st.session_state[_seen_key] = True

    message = (
        f"訂單編號 **{order_no}** 目前查詢到 **{count}** 張不同的訂單卡片，"
        f"這是後台偶發的「訂單編號重複」問題。\n\n"
        f"請務必至後台人工確認這幾張訂單卡片的實際內容，避免訂單資料互相搞混或覆蓋！"
    )

    if hasattr(st, "dialog"):
        @st.dialog("⚠️ 訂單編號重複警示")
        def _dup_order_dialog():
            st.error(message)
            if st.button("我知道了", use_container_width=True, key=f"dup_ack_{dedup_key or order_no}"):
                st.rerun()
        _dup_order_dialog()
    else:
        st.error(f"⚠️ 訂單編號重複警示\n\n{message}")


def step(num, title):
    st.markdown(f'<div class="step-pill"><span class="step-num">{num}</span>{title}</div>', unsafe_allow_html=True)


def info_panel(title, bullets):
    items = "".join(f"<li>{html.escape(str(item))}</li>" for item in bullets)
    st.markdown(f'<div class="hint-box"><b>{html.escape(str(title))}</b><ul style="margin:0.45rem 0 0 1.1rem; padding:0;">{items}</ul></div>', unsafe_allow_html=True)


def auto_lemon_checkbox(key, label="查無班表時自動補檸檬人（不動其他客人已配班專員）"):
    return st.checkbox(label, value=False, key=key)


NJ_MEMO = (
    "**N-J**\n"
    "請現場跟客戶溝通清潔優先順序,並請回報以下內容\n"
    "*工作項目+時間分配\n"
    "*特別注意事項\n"
    "*服務小貼心"
)


def h(value, default="未知"):
    text = str(value or "").strip()
    return html.escape(text if text else default)


def nonzero_money(value):
    try:
        return float(str(value or "0").replace(",", "")) != 0
    except Exception:
        return bool(str(value or "").strip())


def payment_invoice_display(payway, invoice_text):
    if payway == "儲值金":
        return "儲值金客（無付款方式/發票資訊）"
    return f"付款：{payway or '未知'}　發票：{invoice_text or '未知'}"


def booking_route_display(payway):
    if payway == "儲值金":
        return "儲值金客", "/booking/stored_value_routine"
    return "一般客", "/booking/single"


def person_hour_display(person, hour):
    return f"{person}人{hour}小時" if (person or hour) else "未知"


def history_field(label, value):
    return (
        '<div class="history-field">'
        f'<span class="history-label">{h(label, "")}</span>'
        f'<span class="history-value">{h(value)}</span>'
        '</div>'
    )


def order_history_row(order):
    ph_text = person_hour_display(order.get("person"), order.get("hour"))
    payment_text = payment_invoice_display(order.get("payway"), order.get("invoice_text"))
    notice = order.get("service_notice") or "無"
    fare = order.get("fare") or ""
    fare_part = f'<div>車馬費：{h(fare, "")}</div>' if nonzero_money(fare) else ""
    return (
        '<div class="history-order">'
        f'<div class="history-order-main">{h(order.get("order_no"))}　{h(order.get("date"))} {h(order.get("time"), "")}</div>'
        '<div class="history-order-meta">'
        f'<div>人時：{h(ph_text)}</div>'
        f'<div>服務人員：{h(order.get("staff"))}</div>'
        f'<div>地址：{h(order.get("address"))}</div>'
        f'<div>{h(payment_text)}</div>'
        f'<div>客服備註：{h(notice)}</div>'
        f'{fare_part}'
        '</div>'
        '</div>'
    )


def last_summary_card_html(summary):
    ph_text = person_hour_display(summary.get("person"), summary.get("hour"))
    payment_text = payment_invoice_display(summary.get("payway"), summary.get("invoice_text"))
    fields = [
        ("訂單", summary.get("order_no")),
        ("服務時間", f'{summary.get("date") or ""} {summary.get("time") or ""}'.strip()),
        ("地址", summary.get("address") or "無法判斷地址"),
        ("類別", summary.get("clean_type")),
        ("服務人員", summary.get("staff")),
        ("人時", ph_text),
        ("付款/發票", payment_text),
        ("客服備註", summary.get("service_notice") or "無"),
    ]
    if nonzero_money(summary.get("fare")):
        fields.append(("車馬費", summary.get("fare")))
    same_date_orders = summary.get("same_date_orders") or []
    same_date_html = ""
    if len(same_date_orders) > 1:
        same_date_html = (
            f'<div class="history-subtitle">該日期共有 {len(same_date_orders)} 筆已付款訂單</div>'
            + "".join(order_history_row(order) for order in same_date_orders)
        )
    return (
        '<div class="history-card">'
        '<div class="history-title">📌 上次（已付款）服務</div>'
        '<div class="history-grid">'
        + "".join(history_field(label, value) for label, value in fields)
        + '</div>'
        + same_date_html
        + '<div class="history-note">以上已預設帶入，如有變動請手動調整對應欄位。</div>'
        + '</div>'
    )
