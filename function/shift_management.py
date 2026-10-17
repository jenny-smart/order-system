# ============================================================
# 檔名：function/shift_management.py
# 功能：相容包裝。排班管理的畫面與邏輯已統一改用 memo_system/shift.py
#       （與 orders-system 相同的單一實作），這裡不再自行實作。
# 更新時間：2026-10-17
# ============================================================
# -*- coding: utf-8 -*-
from __future__ import annotations

from memo_system.shift import *  # noqa: F401,F403  舊程式 import 本模組名稱時仍可取用

SECTION = "📅 排班管理"


def render(backend_email, backend_password, env):
    from function.memo_router import render as _render_memo

    _render_memo(SECTION, backend_email, backend_password, env)
