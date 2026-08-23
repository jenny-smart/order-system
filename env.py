# -*- coding: utf-8 -*-
"""非敏感設定；帳密與 API Key 由環境、Streamlit Secrets 或本機設定讀取。"""
import os

from accounts import (
    GOOGLE_MAPS_API_KEY as LOCAL_GOOGLE_MAPS_API_KEY,
    GOOGLE_SERVICE_ACCOUNT_FILE as LOCAL_GOOGLE_SERVICE_ACCOUNT_FILE,
)

try:
    import streamlit as st
except Exception:
    st = None


def _secret(name, default=""):
    value = os.getenv(name)
    if value is not None and str(value).strip():
        return value
    if st is not None:
        try:
            value = st.secrets.get(name, "")
            if value is not None and str(value).strip():
                return value
        except Exception:
            pass
    return default


ENV = str(_secret("ENV", "dev"))
BASE_URL_DEV = str(_secret("BASE_URL_DEV", "https://backend-dev.lemonclean.com.tw"))
BASE_URL_PROD = str(_secret("BASE_URL_PROD", "https://backend.lemonclean.com.tw"))
ORDER_PREFIX_DEV = str(_secret("ORDER_PREFIX_DEV", "TT"))
ORDER_PREFIX_PROD = str(_secret("ORDER_PREFIX_PROD", "LC"))
GOOGLE_SHEET_ID = str(
    _secret("GOOGLE_SHEET_ID", "1de41gNvBZCGdfy0qNouRNEaQD7R019VAvz2cfq88ZrE")
)
ENABLE_GCAL_COLOR_SYNC = True
GOOGLE_SERVICE_ACCOUNT_FILE = str(
    _secret("GOOGLE_SERVICE_ACCOUNT_FILE", LOCAL_GOOGLE_SERVICE_ACCOUNT_FILE)
)
GOOGLE_CALENDAR_MAP = {
    "台北": "lemonclean925@gmail.com",
    "台中": "lemonclean.com.tw_8soa7prkegf34tjp5b3okl6rqs@group.calendar.google.com",
}
COLOR_PURPLE = "3"
COLOR_YELLOW = "5"
REQUEST_DELAY = 1
GOOGLE_MAPS_API_KEY = str(
    _secret("GOOGLE_MAPS_API_KEY", LOCAL_GOOGLE_MAPS_API_KEY)
).strip()
