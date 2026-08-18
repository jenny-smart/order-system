# ============================================================
# 檔名：function/vip_calendar_patch_bundle.py
# 功能：VIP Calendar 過渡期單一 patch 入口；集中套用既有 patch 1~5，避免各入口自行管理順序。
# 更新時間：2026-08-19
# 注意：此檔為過渡相容層，最終會將內容收斂進 vip_calendar_sync.py 後移除。
# ============================================================
# -*- coding: utf-8 -*-
from __future__ import annotations


def apply_all(vcs) -> None:
    """依既有相依順序一次套用 VIP Calendar patch 1~5。"""
    import function.vip_calendar_patch as patch1
    from function.vip_calendar_patch2 import apply_patch as apply_patch2
    from function.vip_calendar_patch3 import apply_patch as apply_patch3
    from function.vip_calendar_patch4 import apply_patch as apply_patch4
    from function.vip_calendar_patch5 import apply_patch as apply_patch5

    patch1.apply_patch(vcs)
    apply_patch2(vcs, patch1)
    apply_patch3(vcs, patch1)
    apply_patch4(vcs, patch1)
    apply_patch5(vcs, patch1)
