# -*- coding: utf-8 -*-
"""代客保留：客人還不想先付儲值金時，用檸檬保留帳號替客人先 booking。

排程工作表「代客保留」欄打勾的列：
- 讀工作表時把電話換成檸檬保留帳號手機，之後分組、中斷復原反查、比對新訂單編號
  都跟著檸檬保留帳號走；工作表上的電話不會被改寫。
- 服務地址仍是客人的地址；付款一樣走儲值金建單（扣檸檬保留的儲值金）。
- 客人備註與客服備註都寫「代客保留：客人姓名」，不沿用該地址原本的客服備註；
  檸檬保留單取消頁可用這段文字搜尋並批次取消。
"""
from __future__ import annotations

PROXY_COLUMN = "代客保留"
# 與 reserve_optimizer.RESERVE_PHONE_DEFAULT 相同；這裡不 import，避免 orders 循環匯入。
RESERVE_PHONE = "0939592628"
MEMO_PREFIX = "代客保留："
NAME_KEY = "__proxy_name__"
FLAG_KEY = "__proxy__"
CUSTOMER_PHONE_KEY = "__customer_phone__"
_CHECKED = {"TRUE", "V", "Y", "YES", "1", "是", "✓", "✔", "☑", "勾"}


def is_checked(value) -> bool:
    return str(value or "").strip().upper() in _CHECKED


def memo_for(name) -> str:
    return MEMO_PREFIX + str(name or "").strip()


def apply(df):
    """有「代客保留」欄時，打勾列改用檸檬保留手機；回傳同一個 DataFrame。"""
    if df is None or PROXY_COLUMN not in getattr(df, "columns", []):
        return df
    mask = df[PROXY_COLUMN].map(is_checked)
    df[FLAG_KEY] = mask
    df[NAME_KEY] = ""
    df[CUSTOMER_PHONE_KEY] = ""
    if mask.any():
        df.loc[mask, NAME_KEY] = df.loc[mask, "姓名"].astype(str).str.strip()
        df.loc[mask, CUSTOMER_PHONE_KEY] = df.loc[mask, "電話"]
        df.loc[mask, "電話"] = RESERVE_PHONE
    return df


def proxy_name(row) -> str:
    """代客保留列回傳客人姓名；一般列回傳空字串。打勾但沒有姓名時報錯，不建沒有備註的單。"""
    try:
        name = str(row.get(NAME_KEY, "") or "").strip()
        flagged = bool(row.get(FLAG_KEY, False))
    except AttributeError:
        return ""
    if flagged and not name:
        raise ValueError("代客保留列沒有姓名，無法寫入「代客保留：姓名」備註；請補上姓名後再建單")
    return name


def needs_native_address(row) -> bool:
    """代客保留列：檸檬保留帳號的地址清單通常沒有客人地址，要用後台「查詢地區」取得服務區域，
    否則區域空白會查不到班表（誤判無班表）。"""
    try:
        return bool(row.get(FLAG_KEY, False))
    except AttributeError:
        return False
