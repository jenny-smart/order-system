# -*- coding: utf-8 -*-
"""批次三入口（批次建單／批次建單優化／雲端批次成單）共用的列號選取與帳號規則。

移植自 orders-system batch_ui_consistency.py。原版以 monkeypatch 把
ordersapp.run_process_web 固定成單筆 runner、把 batch_booking_optimized.render
換成 render_optimized_like_batch；order-system 改為：

- function/order_creation.render_batch 直接呼叫
  shared.hybrid_batch_runner.run_process_web_direct_single（原批次固定單筆）；
- function/batch_booking_optimized.render 本身就是原版 render_optimized_like_batch
  的畫面，直接呼叫 run_process_web_hybrid（優化版分組 runner）；
- 本模組只保留與畫面無關、可測試的選列邏輯。
"""
from __future__ import annotations

from accounts import ACCOUNTS
from shared.selected_row_status_guard import _auto_filter_rows, _held_for_request, _safe_load_candidates


def _parse_rows(batch_opt, raw: str) -> list[int]:
    raw = str(raw or "").strip()
    return [] if not raw else batch_opt._parse_row_spec(raw)


def _region_credentials(region: str, fallback_email: str, fallback_password: str):
    account = ACCOUNTS.get(region) or {}
    return (
        str(account.get("email") or fallback_email or "").strip(),
        str(account.get("password") or fallback_password or "").strip(),
    )


region_credentials = _region_credentials


def resolve_target_rows(batch_opt, sheet_name, region, row_spec="", auto_no_slot=False, auto_missing_o=False, o_texts=None,
                        service_start=None, service_end=None):
    """依列號＋自動篩選取得要執行的列；範圍內不符合條件或非本區的列略過，不中止整批。

    回傳 (target_rows, invalid_rows, region_mismatch_rows, held_rows)。held_rows 是
    「預約條件」不在本次預約對象而略過的列（三種批次共用）。本機入口一律允許失敗列重試。
    o_texts：「O欄無單號」自動篩選時只取 O 欄目前內容為這些文字的列（空＝全部）。
    """
    explicit_rows = _parse_rows(batch_opt, row_spec)
    requested_rows = set(explicit_rows)
    if auto_no_slot:
        requested_rows.update(_auto_filter_rows(batch_opt, sheet_name, "no_schedule", region=region, allow_failed=True,
                                                service_start=service_start, service_end=service_end))
    if auto_missing_o:
        requested_rows.update(_auto_filter_rows(batch_opt, sheet_name, "missing_order", region=region, allow_failed=True,
                                                o_texts=o_texts, service_start=service_start, service_end=service_end))
    requested_rows = sorted(requested_rows)
    if not requested_rows and not (auto_no_slot or auto_missing_o):
        raise ValueError("沒有指定列號，也沒有自動篩選到符合條件的列。")

    candidates = _safe_load_candidates(batch_opt, sheet_name, allow_failed=True,
                                       service_start=service_start, service_end=service_end)
    candidate_map = {int(row["__sheet_row__"]): row for _, row in candidates.iterrows()}
    target_rows, invalid, region_mismatch = [], [], []
    for row_no in requested_rows:
        row = candidate_map.get(row_no)
        if row is None:
            invalid.append(row_no)
            continue
        if batch_opt.get_region_by_address(batch_opt._text(row.get("地址")), ACCOUNTS) != region:
            region_mismatch.append(row_no)
            continue
        target_rows.append(row_no)

    modes = [mode for mode, on in (("no_schedule", auto_no_slot), ("missing_order", auto_missing_o)) if on]
    held = _held_for_request(batch_opt, sheet_name, region, explicit_rows, modes, o_texts=o_texts,
                             service_start=service_start, service_end=service_end)
    held_set = set(held)
    invalid = [row_no for row_no in invalid if row_no not in held_set]
    return target_rows, invalid, region_mismatch, held
