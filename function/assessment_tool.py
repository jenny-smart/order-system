# ============================================================
# 檔名：function/assessment_tool.py
# 功能：相容包裝。評估文字工具的畫面與邏輯已統一改用 memo_system/ui.py
#       （與 orders-system 相同的單一實作），這裡不再自行實作。
# 更新時間：2026-10-17
# ============================================================
# -*- coding: utf-8 -*-
from __future__ import annotations

SECTION = "📐 評估文字工具"


def render(backend_email, backend_password, env):
    from function.memo_router import render as _render_memo

    _render_memo(SECTION, backend_email, backend_password, env)
