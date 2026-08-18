# -*- coding: utf-8 -*-
"""Optimized Google Sheet batch execution engine.

This module intentionally does not modify orders.run_process_web. It reuses the
same lower-level order processing helpers but keeps one worksheet/session open for
the whole selected batch and writes results back in 10-row checkpoints through
BatchWritebackBuffer.
"""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Iterable, Sequence

import pandas as pd
import requests

import orders
from accounts import ACCOUNTS
from shared.batch_writeback import BatchWritebackBuffer, DEFAULT_CHECKPOINT_SIZE
from shared.env_config import apply_env


REQUIRED_COLUMNS = [
    "服務人時", "備註", "姓名", "電話", "地址", "日期",
    "開始時間", "結束時間", "狀態", "購買項目", "訂單編號",
]


def _normalize_rows(row_numbers: Iterable[int]) -> list[int]:
    rows = sorted({int(x) for x in (row_numbers or []) if int(x) > 1})
    if not rows:
        raise ValueError("請至少提供一個 Google Sheet 資料列")
    return rows


def _configure_orders_env(env_name: str) -> None:
    """Update orders.py URL globals from the single shared env source."""
    apply_env(orders, env_name)


def run_optimized_sheet_batch(
    *,
    env_name: str,
    region: str,
    backend_email: str,
    backend_password: str,
    sheet_name: str,
    row_numbers: Sequence[int],
    selected_actions=None,
    logger=print,
    allow_auto_lemon_shift: bool = False,
    checkpoint_size: int = DEFAULT_CHECKPOINT_SIZE,
) -> dict:
    """Process selected Sheet rows using one session and checkpointed writeback.

    Differences from legacy run_process_web:
    - accepts an arbitrary row-number list rather than one start/end call at a time;
    - worksheet is loaded once;
    - backend login/session is created once;
    - all selected rows are grouped/processed in one run;
    - result cells are staged and batch-written every 10 rows by default;
    - final remaining 1-9 rows are flushed once at the end.

    The underlying order creation, confirmation-mail and calendar behavior is still
    provided by the existing orders.py helpers, minimizing behavior drift.
    """
    _configure_orders_env(env_name)
    rows_requested = _normalize_rows(row_numbers)
    selected_actions = list(selected_actions or ["建單", "寄確認信", "改 Google 日曆"])

    logger(f"目前環境：{env_name}")
    logger(f"執行區域：{region}")
    logger(f"執行工作表：{sheet_name}")
    logger(f"優化批次列數：{len(rows_requested)}")
    logger(f"Google Sheet checkpoint：每 {int(checkpoint_size)} 列批次回寫")

    ws, df = orders.load_worksheet(sheet_name)
    for col in REQUIRED_COLUMNS:
        if col not in df.columns:
            raise Exception(f"工作表缺少必要欄位: {col}")

    requested_set = set(rows_requested)
    df = df[df["__sheet_row__"].isin(requested_set)]
    df = df[df.apply(orders.should_process_row, axis=1)]
    if df.empty:
        return {
            "success": True,
            "message": "沒有符合條件的資料",
            "requested_count": len(rows_requested),
            "total_processed": 0,
            "success_count": 0,
            "fail_count": 0,
            "failed_records": [],
            "writeback": {"checkpoint_size": checkpoint_size, "flush_count": 0, "total_flushed_rows": 0, "pending_rows": 0},
        }

    filtered_rows = [
        row for _, row in df.iterrows()
        if orders.get_region_by_address(str(row["地址"]), ACCOUNTS) == region
    ]
    if not filtered_rows:
        return {
            "success": True,
            "message": f"沒有 {region} 區域資料",
            "requested_count": len(rows_requested),
            "total_processed": 0,
            "success_count": 0,
            "fail_count": 0,
            "failed_records": [],
            "writeback": {"checkpoint_size": checkpoint_size, "flush_count": 0, "total_flushed_rows": 0, "pending_rows": 0},
        }

    df = pd.DataFrame(filtered_rows)

    gcal_service = None
    if getattr(orders, "ENABLE_GCAL_COLOR_SYNC", False):
        try:
            gcal_service = orders.build_gcal_service()
            logger("Google Calendar 已啟用")
        except Exception as exc:
            logger(f"Google Calendar 初始化失敗：{exc}")

    session = requests.Session()
    if not orders.login(session, backend_email, backend_password):
        raise Exception("後台登入失敗，請確認帳號密碼")

    grouped_orders = defaultdict(list)
    existing_order_rows = []
    for _, row in df.iterrows():
        row_num = int(row["__sheet_row__"])
        if not orders.has_action(selected_actions, "建單") or not orders.should_create_order(row):
            existing_order_rows.append((row_num, row))
        else:
            grouped_orders[orders.build_group_key(row)].append((row_num, row))

    buffer = BatchWritebackBuffer(ws, checkpoint_size=checkpoint_size, logger=logger)
    all_results = {}
    failed_records = []

    def stage(row_num: int, result: dict) -> None:
        row_num = int(row_num)
        payload = dict(result or {})
        all_results[row_num] = payload
        buffer.add(row_num, payload)
        if payload.get("結果") == "失敗":
            failed_records.append({
                "row": row_num,
                "name": "",
                "error": str(payload.get("原因") or ""),
            })

    # Existing-order-only actions first (confirmation/calendar/status update).
    for row_num, row in existing_order_rows:
        logger(f"▶ 補處理第 {row_num} 列")
        try:
            result = orders.process_existing_order_only(row, gcal_service, region, session, selected_actions)
        except Exception as exc:
            result = orders.build_row_result(
                result="失敗", reason=f"補處理失敗: {exc}", status_value="",
                staff="無人力", service_status="未處理", fare="0",
            )
        stage(row_num, result)

    # Keep a single used-order set across the whole optimized run to avoid duplicate
    # matching across groups, same as the legacy engine intended for one batch.
    used_order_nos = set()
    for group_no, (_, rows_with_idx) in enumerate(grouped_orders.items(), start=1):
        _, first_row = rows_with_idx[0]
        logger(f"▶ 處理第 {group_no} 組：{first_row.get('姓名', '')}，共 {len(rows_with_idx)} 筆")
        try:
            token = orders.get_csrf_token(session)
            row_results = orders.process_one_group(
                session,
                rows_with_idx,
                token,
                gcal_service,
                region,
                None,
                selected_actions,
                allow_auto_lemon_shift=allow_auto_lemon_shift,
                used_order_nos=used_order_nos,
            )
            for row_num, _row in rows_with_idx:
                stage(row_num, row_results.get(row_num, {}))
        except Exception as exc:
            logger(f"❌ 整組失敗：{exc}")
            for row_num, _row in rows_with_idx:
                stage(row_num, orders.build_row_result(
                    result="失敗", reason=str(exc), status_value="",
                    staff="無人力", service_status="未處理", fare="0",
                ))
        delay = float(getattr(orders, "REQUEST_DELAY", 0) or 0)
        if delay:
            time.sleep(delay)

    # Flush final partial checkpoint (1-9 rows). If a previous checkpoint failed,
    # pending rows remain in the buffer and the exception is surfaced to the caller.
    buffer.finalize()

    success_count = sum(1 for v in all_results.values() if v.get("結果") == "成功")
    fail_count = sum(1 for v in all_results.values() if v.get("結果") == "失敗")
    logger("===== 優化批次流程執行完成 =====")

    return {
        "success": True,
        "sheet_name": sheet_name,
        "region": region,
        "env": env_name,
        "requested_count": len(rows_requested),
        "success_count": success_count,
        "fail_count": fail_count,
        "total_processed": len(all_results),
        "failed_records": failed_records,
        "row_results": all_results,
        "writeback": buffer.status(),
    }
