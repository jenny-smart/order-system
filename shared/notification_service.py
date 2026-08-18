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
