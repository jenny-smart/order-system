# -*- coding: utf-8 -*-
"""批次建單 runner（移植自 orders-system hybrid_batch_runner.py）。

- 原「批次建單」：真正逐列處理，不建立 group key、不進 hybrid 分組。
- 「批次建單優化」/雲端：2 筆以上同組先走批次，多筆組完成即回填；單筆組再逐筆。
- 三種模式共用同一個 process_one_group 底層送單與補檸檬人規則
  （shared.selected_row_status_guard.process_one_group_with_lemon_retry）。
- Google Calendar 採 lazy init：先成單、先回填訂單編號，才視需要同步日曆。

order-system 不 monkeypatch orders／ordersapp：function/order_creation.render_batch
直接呼叫 run_process_web_direct_single；function/batch_booking_optimized.render 與
shared/cloud_batch_booking 直接呼叫 run_process_web_hybrid。
"""
from __future__ import annotations

from collections import defaultdict
import requests

import orders as _orders
import shared.batch_booking_safety as _safety
from shared.selected_row_status_guard import (
    _load_worksheet_unique,
    process_one_group_with_lemon_retry,
)
from accounts import ACCOUNTS


RUNNER_VERSION = "v2026.10.17-1"
RUNNER_UPDATED_AT = "2026-10-17"


def _phone_address_group_key(row):
    """優化／雲端模式只依電話＋地址分組。"""
    return (
        _orders.normalize_phone(row.get("電話", "")),
        _orders.normalize_addr_for_match(row.get("地址", "")),
    )


def _without_calendar(actions):
    return [x for x in (actions or []) if x != "改 Google 日曆"]


def _selected_work(df, selected_rows, start_row, end_row, region):
    if selected_rows is None:
        work = df[(df["__sheet_row__"] >= start_row) & (df["__sheet_row__"] <= end_row)].copy()
    else:
        wanted = {int(x) for x in selected_rows}
        work = df[df["__sheet_row__"].isin(wanted)].copy()
    if work.empty:
        return work
    return work[
        work.apply(
            lambda row: _orders.get_region_by_address(str(row.get("地址", "")), ACCOUNTS) == region,
            axis=1,
        )
    ].copy()


def _lazy_calendar_sync(row, result, region, state, logger):
    order_no = str((result or {}).get("訂單編號", "") or "").strip()
    if not order_no:
        return result
    if state.get("service") is None and not state.get("failed"):
        try:
            state["service"] = _orders.build_gcal_service()
            logger("Google Calendar 已啟用（訂單已回填後才初始化）")
        except Exception as exc:
            state["failed"] = True
            logger(f"⚠️ Google Calendar 初始化失敗：{exc}")
    if state.get("service") is None:
        return result

    calendar_info = _orders.stage_calendar_color(row, state["service"], region)
    merged = dict(result or {})
    merged.update(calendar_info)
    try:
        merged.update(_orders.stage_update_status(order_no, merged, calendar_info, merged))
    except Exception as exc:
        logger(f"⚠️ {order_no} 日曆後續狀態同步失敗：{exc}")
    return merged


def _run_one_direct(
    session, ws, row_no, row, region, selected_actions, allow_auto_lemon_shift,
    used_order_nos, gcal_state, logger,
):
    """真正單列送單入口；不建立 grouped_orders / build_group_key。"""
    core_actions = _without_calendar(selected_actions)
    token = _orders.get_csrf_token(session)

    def single_logger(message):
        text = str(message)
        text = text.replace("本組", "單筆").replace("第 None 組", "單筆")
        logger(text)

    # process_one_group 在這裡只作為單筆底層 HTTP 建單實作；傳入永遠只有一列。
    # 不經過 orders.run_process_web 的 grouped_orders orchestration。
    row_results = process_one_group_with_lemon_retry(
        session,
        [(row_no, row)],
        token,
        None,
        region,
        None,
        core_actions,
        allow_auto_lemon_shift=allow_auto_lemon_shift,
        used_order_nos=used_order_nos,
        logger=single_logger,
        group_no=None,
    )
    result = row_results.get(row_no, {})

    # 成單結果先持久化；即使後續日曆/寄信發生問題，也不丟失訂單編號。
    _orders.update_sheet_rows(ws, {row_no: result})

    if "改 Google 日曆" in (selected_actions or []) and str(result.get("訂單編號", "")).strip():
        result = _lazy_calendar_sync(row, result, region, gcal_state, logger)
        _orders.update_sheet_rows(ws, {row_no: result})
    return result


def _run_existing_direct(session, ws, row_no, row, region, selected_actions, gcal_state, logger):
    core_actions = _without_calendar(selected_actions)
    result = _orders.process_existing_order_only(row, None, region, session, core_actions)
    _orders.update_sheet_rows(ws, {row_no: result})
    if "改 Google 日曆" in (selected_actions or []) and str(result.get("訂單編號", "")).strip():
        result = _lazy_calendar_sync(row, result, region, gcal_state, logger)
        _orders.update_sheet_rows(ws, {row_no: result})
    return result


def _result_stats(row_no, row, result, failed_records):
    if str((result or {}).get("結果", "")) == "失敗":
        failed_records.append({
            "row": row_no,
            "name": str(row.get("姓名", "")).strip(),
            "error": str((result or {}).get("原因", "")),
        })
        return 0, 1
    return 1, 0


def _login_once(backend_email, backend_password):
    session = requests.Session()
    if not _orders.login(session, backend_email, backend_password):
        raise RuntimeError("後台登入失敗，無法執行批次建單")
    return session


def run_process_web_direct_single(
    *, env_name, region, backend_email, backend_password, sheet_name,
    start_row, end_row, selected_actions=None, logger=print,
    allow_auto_lemon_shift=False, selected_rows=None,
):
    """原「批次建單」：逐列單筆成單，完全不進 hybrid/grouping。"""
    selected_actions = selected_actions or ["建單", "寄確認信", "改 Google 日曆"]
    core_actions = _without_calendar(selected_actions)
    _safety._configure_runtime(env_name)

    logger(f"程式版本：{RUNNER_VERSION}（更新日期：{RUNNER_UPDATED_AT}）")
    logger(f"目前環境：{env_name}")
    logger(f"BASE_URL：{_orders.BASE_URL}")
    logger(f"執行區域：{region}")
    logger(f"執行工作表：{sheet_name}")
    logger(f"執行列範圍：{start_row} ~ {end_row}")
    if selected_rows is not None:
        logger("指定列號：" + "、".join(map(str, sorted({int(x) for x in selected_rows}))))

    # 先反查後台：已成立但 Sheet 未回填者只補回，不重建。
    ws, remaining, recovered, blocked, _ = _safety._recover_before_create(
        env_name, region, backend_email, backend_password, sheet_name,
        start_row, end_row, selected_rows, core_actions, logger,
    )

    ws, df = _load_worksheet_unique(sheet_name)
    work = _selected_work(df, selected_rows, start_row, end_row, region)
    if work.empty:
        logger("沒有符合條件的資料可執行。")
        return {
            "success": True, "success_count": len(recovered), "fail_count": len(blocked),
            "total_processed": len(recovered) + len(blocked),
            "recovered_count": len(recovered), "blocked_count": len(blocked),
            "failed_records": [],
        }

    remaining_set = {int(x) for x in remaining}
    recovered_set = {int(x) for x in recovered}
    blocked_set = {int(x) for x in blocked}

    session = _login_once(backend_email, backend_password)
    gcal_state = {"service": None, "failed": False}
    used_order_nos = set()
    failed_records = []
    success_count = len(recovered)
    fail_count = len(blocked)
    processed = len(recovered) + len(blocked)

    logger(f"單筆批次：共 {len(work)} 列；依列號逐筆處理，不分組。")

    for _, row in work.sort_values("__sheet_row__").iterrows():
        row_no = int(row["__sheet_row__"])
        if row_no in blocked_set:
            logger(f"⏭️ 第 {row_no} 列：安全檢查已擋下，繼續下一列。")
            continue

        order_no = str(row.get("訂單編號", "") or "").strip()

        # 中斷復原列已由 _recover_before_create 回填；如要求改日曆，再於回填後處理。
        if row_no in recovered_set:
            if "改 Google 日曆" in selected_actions and order_no:
                recovered_result = _orders.build_row_result(order_no=order_no, result="中斷復原", reason="")
                recovered_result = _lazy_calendar_sync(row, recovered_result, region, gcal_state, logger)
                _orders.update_sheet_rows(ws, {row_no: recovered_result})
            logger(f"♻️ 第 {row_no} 列已復原，繼續下一列。")
            continue

        logger(f"▶ 單筆預約：第 {row_no} 列")
        try:
            if order_no:
                result = _run_existing_direct(
                    session, ws, row_no, row, region, selected_actions, gcal_state, logger
                )
            elif row_no in remaining_set:
                _safety._checkpoint(ws, [row_no], message="單筆已建立建單斷點；完成後立即回填")
                result = _run_one_direct(
                    session, ws, row_no, row, region, selected_actions,
                    allow_auto_lemon_shift, used_order_nos, gcal_state, logger,
                )
            else:
                logger(f"⏭️ 第 {row_no} 列不符合建單條件，繼續下一列。")
                continue
        except Exception as exc:
            result = _orders.build_row_result(
                result="失敗", reason=str(exc), status_value="",
                staff="無人力", service_status="未處理", fare="0",
            )
            _orders.update_sheet_rows(ws, {row_no: result})

        ok, bad = _result_stats(row_no, row, result, failed_records)
        success_count += ok
        fail_count += bad
        processed += 1
        logger(f"✅ 第 {row_no} 列已完成並回填，繼續下一列。")

    return {
        "success": fail_count == 0,
        "sheet_name": sheet_name,
        "region": region,
        "env": env_name,
        "success_count": success_count,
        "fail_count": fail_count,
        "total_processed": processed,
        "recovered_count": len(recovered),
        "blocked_count": len(blocked),
        "failed_records": failed_records,
    }


def run_process_web_hybrid(
    *, env_name, region, backend_email, backend_password, sheet_name,
    start_row, end_row, selected_actions=None, logger=print,
    allow_auto_lemon_shift=False, selected_rows=None, progress_callback=None,
):
    """優化/雲端：多筆同組先批次；單筆組直接逐筆。"""
    selected_actions = selected_actions or ["建單", "寄確認信", "改 Google 日曆"]
    core_actions = _without_calendar(selected_actions)
    _safety._configure_runtime(env_name)

    ws, remaining, recovered, blocked, _ = _safety._recover_before_create(
        env_name, region, backend_email, backend_password, sheet_name,
        start_row, end_row, selected_rows, core_actions, logger,
    )

    ws, df = _load_worksheet_unique(sheet_name)
    work = _selected_work(df, selected_rows, start_row, end_row, region)
    recovered_set = set(recovered)
    blocked_set = set(blocked)
    remaining_set = {int(x) for x in remaining}

    existing_rows = []
    create_rows = []
    recovered_rows = []
    for _, row in work.iterrows():
        row_no = int(row["__sheet_row__"])
        if row_no in blocked_set:
            continue
        if row_no in recovered_set:
            recovered_rows.append((row_no, row))
            continue
        order_no = str(row.get("訂單編號", "") or "").strip()
        if order_no:
            existing_rows.append((row_no, row))
        elif row_no in remaining_set:
            create_rows.append((row_no, row))

    session = _login_once(backend_email, backend_password)
    gcal_state = {"service": None, "failed": False}
    used_order_nos = set()
    failed_records = []
    success_count = len(recovered)
    fail_count = len(blocked)
    processed = len(recovered) + len(blocked)

    def report_progress(row_no=''):
        if progress_callback:
            try:
                progress_callback(processed, success_count, fail_count, row_no)
            except Exception:
                logger('進度回報暫時無法更新；成單繼續。')


    if "改 Google 日曆" in selected_actions:
        for row_no, row in recovered_rows:
            order_no = str(row.get("訂單編號", "") or "").strip()
            if order_no:
                result = _orders.build_row_result(order_no=order_no, result="中斷復原", reason="")
                result = _lazy_calendar_sync(row, result, region, gcal_state, logger)
                _orders.update_sheet_rows(ws, {row_no: result})

    report_progress()
    for row_no, row in existing_rows:
        try:
            result = _run_existing_direct(session, ws, row_no, row, region, selected_actions, gcal_state, logger)
        except Exception as exc:
            result = _orders.build_row_result(
                result="失敗", reason=f"既有訂單同步失敗: {exc}", status_value="",
                staff="無人力", service_status="未處理", fare="0",
            )
            _orders.update_sheet_rows(ws, {row_no: result})
        ok, bad = _result_stats(row_no, row, result, failed_records)
        success_count += ok
        fail_count += bad
        processed += 1
        report_progress()

    grouped = defaultdict(list)
    for row_no, row in create_rows:
        grouped[_phone_address_group_key(row)].append((row_no, row))

    # 效率優先：真正有 2 筆以上的組才使用 grouped submit；1 筆組直接走單筆。
    multi_groups = [items for items in grouped.values() if len(items) >= 2]
    single_rows = [items[0] for items in grouped.values() if len(items) == 1]
    multi_groups.sort(key=lambda items: (-len(items), min(row_no for row_no, _ in items)))
    single_rows.sort(key=lambda item: item[0])

    logger(
        f"混合優化：待建 {len(create_rows)} 筆；多筆組 {len(multi_groups)} 組／"
        f"{sum(len(x) for x in multi_groups)} 筆，單筆 {len(single_rows)} 筆。先多筆組，再單筆。"
    )

    for group_no, rows_with_idx in enumerate(multi_groups, 1):
        row_numbers = [row_no for row_no, _ in rows_with_idx]
        _safety._checkpoint(ws, row_numbers, message="多筆組已建立建單斷點；本組完成後立即回填")
        logger(f"▶ 多筆組 {group_no}/{len(multi_groups)}：列號 {'、'.join(map(str, row_numbers))}")
        try:
            token = _orders.get_csrf_token(session)
            row_results = process_one_group_with_lemon_retry(
                session, rows_with_idx, token, None, region, None, core_actions,
                allow_auto_lemon_shift=allow_auto_lemon_shift,
                used_order_nos=used_order_nos, logger=logger, group_no=group_no,
            )
        except Exception as exc:
            row_results = {
                row_no: _orders.build_row_result(
                    result="失敗", reason=str(exc), status_value="",
                    staff="無人力", service_status="未處理", fare="0",
                )
                for row_no, _ in rows_with_idx
            }

        # 同組一次 batch_update 回填，再做日曆。
        _orders.update_sheet_rows(ws, row_results)
        logger(f"✅ 多筆組 {group_no}/{len(multi_groups)} 建單結果已整組回填 Google Sheet。")

        if "改 Google 日曆" in selected_actions:
            for row_no, row in rows_with_idx:
                result = row_results.get(row_no, {})
                if str(result.get("訂單編號", "")).strip():
                    result = _lazy_calendar_sync(row, result, region, gcal_state, logger)
                    row_results[row_no] = result
                    _orders.update_sheet_rows(ws, {row_no: result})

        for row_no, row in rows_with_idx:
            ok, bad = _result_stats(row_no, row, row_results.get(row_no, {}), failed_records)
            success_count += ok
            fail_count += bad
            processed += 1
            report_progress()

    for index, (row_no, row) in enumerate(single_rows, 1):
        report_progress(str(row_no))
        _safety._checkpoint(ws, [row_no], message="單筆已建立建單斷點；完成後立即回填")
        logger(f"▶ 優化單筆 {index}/{len(single_rows)}：第 {row_no} 列")
        try:
            result = _run_one_direct(
                session, ws, row_no, row, region, selected_actions,
                allow_auto_lemon_shift, used_order_nos, gcal_state, logger,
            )
        except Exception as exc:
            result = _orders.build_row_result(
                result="失敗", reason=str(exc), status_value="",
                staff="無人力", service_status="未處理", fare="0",
            )
            _orders.update_sheet_rows(ws, {row_no: result})
        ok, bad = _result_stats(row_no, row, result, failed_records)
        success_count += ok
        fail_count += bad
        processed += 1
        report_progress()

    return {
        "success": fail_count == 0,
        "sheet_name": sheet_name,
        "region": region,
        "env": env_name,
        "success_count": success_count,
        "fail_count": fail_count,
        "total_processed": processed,
        "recovered_count": len(recovered),
        "blocked_count": len(blocked),
        "failed_records": failed_records,
    }
