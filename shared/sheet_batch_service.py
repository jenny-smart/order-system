# ============================================================
# 檔名：shared/sheet_batch_service.py
# 功能：Google Sheet 批次建單服務入口；區隔舊版與新版 10 筆 checkpoint 引擎。
# 更新時間：2026-08-19
# ============================================================
# -*- coding: utf-8 -*-
from __future__ import annotations
import orders as _legacy
from shared.optimized_sheet_batch import run_optimized_sheet_batch


def run_legacy(*args, **kwargs):
    """既有批次建單，不改行為。"""
    return _legacy.run_process_web(*args, **kwargs)


def run_optimized(**kwargs):
    """新版批次建單；預設每 10 列批次回寫。"""
    kwargs.setdefault("checkpoint_size", 10)
    return run_optimized_sheet_batch(**kwargs)
