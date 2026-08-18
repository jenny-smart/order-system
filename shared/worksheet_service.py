# ============================================================
# 檔名：shared/worksheet_service.py
# 功能：Google Sheet 工作表讀取服務相容層；隔離 orders.py 的 Sheet 載入實作。
# 更新時間：2026-08-19
# ============================================================
# -*- coding: utf-8 -*-
from __future__ import annotations
import orders as _legacy


def load_worksheet(sheet_name: str):
    return _legacy.load_worksheet(sheet_name)
