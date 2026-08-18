# ============================================================
# 檔名：memo_system/ui.py
# 功能：舊 memo UI 相容入口；實際路由已移至 function/memo_router.py。
# 更新時間：2026-08-19
# 狀態：過渡相容層，待 ordersapp.py import 切換後即可刪除。
# ============================================================
# -*- coding: utf-8 -*-
from __future__ import annotations

from function.memo_router import render as _render_memo


def render_memo_system(
    forced_main_section=None,
    shared_backend_email=None,
    shared_backend_password=None,
    shared_env="prod",
):
    """維持 ordersapp.py 舊呼叫介面，轉送到新的 function router。"""
    if forced_main_section is None:
        raise ValueError("整合版 memo 功能必須由 ordersapp.py 指定 forced_main_section")
    _render_memo(
        forced_main_section,
        shared_backend_email or "",
        shared_backend_password or "",
        shared_env or "prod",
    )
