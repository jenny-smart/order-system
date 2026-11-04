# ============================================================
# 檔名：shared/notification_service.py
# 功能：LINE／客戶通知訊息服務；集中管理建單後訊息產生入口。
# 更新時間：2026-08-19
# ============================================================
# -*- coding: utf-8 -*-

"""客戶通知訊息服務。

先建立穩定介面並保持 legacy 輸出完全一致，避免拆解期間改變既有 LINE 文案。
"""

from __future__ import annotations

import quick_order as _legacy


def build_line_message(*args, **kwargs):
    return _legacy.build_line_message(*args, **kwargs)


def build_line_message_from_order_no(*args, **kwargs):
    return _legacy.build_line_message_from_order_no(*args, **kwargs)


def build_combined_line_message_from_order_nos(*args, **kwargs):
    return _legacy.build_combined_line_message_from_order_nos(*args, **kwargs)


def prepare_notification_session(*args, **kwargs):
    return _legacy.prepare_notification_session(*args, **kwargs)


def build_many_combined_line_messages(*args, **kwargs):
    return _legacy.build_many_combined_line_messages(*args, **kwargs)


def prefetch_purchase_blocks(*args, **kwargs):
    return _legacy.prefetch_purchase_blocks(*args, **kwargs)


def prefetch_notice_blocks(env_name, backend_email, backend_password, groups, logger=print):
    """依群組服務日期範圍一次列出後台訂單；失敗時回傳空 dict（改回逐張查詢，結果不變）。"""
    from shared.text_parsing import get_date_str

    dates = []
    for group in groups or []:
        for entry in group.get("entries") or []:
            try:
                value = get_date_str(entry.get("date"))
            except Exception:
                value = ""
            if value:
                dates.append(value)
    dates.sort()
    if not dates:
        return {}
    try:
        session = _legacy.prepare_notification_session(env_name, backend_email, backend_password)
        blocks = _legacy.prefetch_purchase_blocks(session, dates[0], dates[-1])
        logger(f"後台區間清單 {dates[0]}～{dates[-1]}：{len(blocks)} 張訂單")
        return blocks
    except Exception as exc:
        logger(f"後台區間清單讀取失敗，改逐張查詢：{exc}")
        return {}
