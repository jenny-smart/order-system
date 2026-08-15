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
