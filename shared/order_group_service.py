# ============================================================
# 檔名：shared/order_group_service.py
# 功能：批次訂單分組／單組處理相容層；逐步隔離 orders.py 核心建單流程。
# 更新時間：2026-08-19
# ============================================================
# -*- coding: utf-8 -*-
from __future__ import annotations
import orders as _legacy


def build_group_key(row):
    return _legacy.build_group_key(row)


def should_process_row(row):
    return _legacy.should_process_row(row)


def should_create_order(row):
    return _legacy.should_create_order(row)


def has_action(selected_actions, action: str):
    return _legacy.has_action(selected_actions, action)


def process_group(*args, **kwargs):
    return _legacy.process_one_group(*args, **kwargs)
