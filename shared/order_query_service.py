# ============================================================
# 檔名：shared/order_query_service.py
# 功能：後台訂單查詢／解析服務相容層；逐步隔離 orders.py 查詢邏輯。
# 更新時間：2026-08-19
# ============================================================
# -*- coding: utf-8 -*-
from __future__ import annotations
import orders as _legacy


def extract_order_cards(html_text: str):
    return _legacy.extract_order_cards_from_purchase_html(html_text)


def get_region(address: str, accounts):
    return _legacy.get_region_by_address(address, accounts)


def legacy_query_call(function_name: str, *args, **kwargs):
    fn = getattr(_legacy, function_name, None)
    if fn is None:
        raise AttributeError(f"orders 找不到查詢函式：{function_name}")
    return fn(*args, **kwargs)
