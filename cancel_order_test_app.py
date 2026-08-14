# -*- coding: utf-8 -*-
import streamlit as st

from cancel_order import render_cancel_order

st.set_page_config(page_title="取消訂單測試", layout="wide")
st.title("取消訂單測試")

c1, c2, c3 = st.columns([3.2, 3.2, 1.2])
with c1:
    backend_email = st.text_input("後台帳號")
with c2:
    backend_password = st.text_input("後台密碼", type="password")
with c3:
    env_label = st.selectbox(
        "環境",
        ["prod（正式機 backend）", "dev（測試機 backend-dev）"],
        index=1,
    )
    env = "dev" if env_label.startswith("dev") else "prod"

st.divider()
render_cancel_order(backend_email.strip(), backend_password.strip(), env)
