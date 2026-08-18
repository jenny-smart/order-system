# ============================================================
# 檔名：shared/optimized_sheet_batch.py
# 功能：新版 Google Sheet 批次建單引擎；單一 session，每 10 列 checkpoint 回寫。
# 更新時間：2026-08-19
# ============================================================
# -*- coding: utf-8 -*-
from __future__ import annotations
import time
from collections import defaultdict
from typing import Iterable, Sequence
import pandas as pd
import orders
from accounts import ACCOUNTS
from shared.batch_writeback import BatchWritebackBuffer, DEFAULT_CHECKPOINT_SIZE
from shared.env_config import apply_env
from shared import (
    backend_session_service,
    calendar_service,
    order_group_service,
    order_query_service,
    order_status_service,
)

REQUIRED_COLUMNS = ["服務人時", "備註", "姓名", "電話", "地址", "日期", "開始時間", "結束時間", "狀態", "購買項目", "訂單編號"]


def _normalize_rows(row_numbers: Iterable[int]) -> list[int]:
    rows = sorted({int(x) for x in (row_numbers or []) if int(x) > 1})
    if not rows:
        raise ValueError("請至少提供一個 Google Sheet 資料列")
    return rows


def run_optimized_sheet_batch(*, env_name: str, region: str, backend_email: str, backend_password: str, sheet_name: str, row_numbers: Sequence[int], selected_actions=None, logger=print, allow_auto_lemon_shift: bool=False, checkpoint_size: int=DEFAULT_CHECKPOINT_SIZE) -> dict:
    apply_env(orders, env_name)
    rows_requested = _normalize_rows(row_numbers)
    selected_actions = list(selected_actions or ["建單", "寄確認信", "改 Google 日曆"])
    logger(f"優化批次：{len(rows_requested)} 列；Sheet 每 {checkpoint_size} 列批次回寫")

    ws, df = orders.load_worksheet(sheet_name)
    for col in REQUIRED_COLUMNS:
        if col not in df.columns:
            raise Exception(f"工作表缺少必要欄位: {col}")
    df = df[df["__sheet_row__"].isin(set(rows_requested))]
    df = df[df.apply(order_group_service.should_process_row, axis=1)]
    filtered = [r for _, r in df.iterrows() if order_query_service.get_region(str(r["地址"]), ACCOUNTS) == region]
    if not filtered:
        return {"success": True, "message": "沒有符合條件的資料", "total_processed": 0, "writeback": {"checkpoint_size": checkpoint_size, "flush_count": 0}}
    df = pd.DataFrame(filtered)

    gcal = None
    if getattr(orders, "ENABLE_GCAL_COLOR_SYNC", False):
        try:
            gcal = calendar_service.build_service()
        except Exception as exc:
            logger(f"Google Calendar 初始化失敗：{exc}")

    session = backend_session_service.create_logged_in_session(backend_email, backend_password)
    groups, existing = defaultdict(list), []
    for _, row in df.iterrows():
        row_num = int(row["__sheet_row__"])
        if not order_group_service.has_action(selected_actions, "建單") or not order_group_service.should_create_order(row):
            existing.append((row_num, row))
        else:
            groups[order_group_service.build_group_key(row)].append((row_num, row))

    buffer = BatchWritebackBuffer(ws, checkpoint_size=checkpoint_size, logger=logger)
    results, failed = {}, []

    def stage(row_num, payload):
        payload = dict(payload or {})
        results[int(row_num)] = payload
        buffer.add(int(row_num), payload)
        if payload.get("結果") == "失敗":
            failed.append({"row": int(row_num), "error": str(payload.get("原因") or "")})

    for row_num, row in existing:
        try:
            result = order_status_service.process_existing_order(row, gcal, region, session, selected_actions)
        except Exception as exc:
            result = order_status_service.build_row_result(result="失敗", reason=f"補處理失敗: {exc}", status_value="", staff="無人力", service_status="未處理", fare="0")
        stage(row_num, result)

    used_order_nos = set()
    for _, rows_with_idx in groups.items():
        try:
            token = backend_session_service.get_csrf_token(session)
            row_results = order_group_service.process_group(session, rows_with_idx, token, gcal, region, None, selected_actions, allow_auto_lemon_shift=allow_auto_lemon_shift, used_order_nos=used_order_nos)
            for row_num, _ in rows_with_idx:
                stage(row_num, row_results.get(row_num, {}))
        except Exception as exc:
            for row_num, _ in rows_with_idx:
                stage(row_num, order_status_service.build_row_result(result="失敗", reason=str(exc), status_value="", staff="無人力", service_status="未處理", fare="0"))
        delay = float(getattr(orders, "REQUEST_DELAY", 0) or 0)
        if delay:
            time.sleep(delay)

    buffer.finalize()
    success_count = sum(v.get("結果") == "成功" for v in results.values())
    fail_count = sum(v.get("結果") == "失敗" for v in results.values())
    return {"success": True, "sheet_name": sheet_name, "region": region, "env": env_name, "requested_count": len(rows_requested), "success_count": success_count, "fail_count": fail_count, "total_processed": len(results), "failed_records": failed, "row_results": results, "writeback": buffer.status()}
