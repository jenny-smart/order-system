# -*- coding: utf-8 -*-
"""批次建單斷點保護與中斷復原。

移植自 orders-system batch_booking_safety.py：

- 原批次建單：逐列執行，一列完成/回填後才處理下一列。
- 優化/雲端批次：每一組完成即回填。
- 重跑時先把後台已成立、Sheet 尚未回填的訂單補回，避免重複成單。
- 「每月確認」只做 Sheet 狀態防呆：Google 日曆不改色，表單狀態寫成「待確認」。

order-system 不再 monkeypatch orders：
- 每月確認防呆直接寫在 orders.stage_calendar_color；
- 「待確認」允許寫入 I 欄直接寫在 shared/gsheet.update_sheet_rows；
- Streamlit 入口由頁面直接呼叫 shared/hybrid_batch_runner 的 runner。
"""
from __future__ import annotations

import re
from collections import defaultdict

import requests

import orders as _orders
from accounts import ACCOUNTS
from shared.booking_eligibility import create_block_reason
from shared.env_config import apply_env
from shared.selected_row_status_guard import _load_worksheet_unique

_CHECKPOINT_RESULT = "處理中"
_RECOVERED_RESULT = "中斷復原"
_BLOCKED_RESULT = "待確認"

# 每月確認防呆已併入 orders.stage_calendar_color；保留名稱供呼叫端/測試使用。
_is_monthly_confirm_event = _orders.is_monthly_confirm_event


def _configure_runtime(env_name: str) -> None:
    apply_env(_orders, env_name)


def _selected_df(df, selected_rows, start_row, end_row, region):
    if selected_rows is None:
        work = df[(df["__sheet_row__"] >= start_row) & (df["__sheet_row__"] <= end_row)].copy()
    else:
        wanted = {int(x) for x in selected_rows}
        work = df[df["__sheet_row__"].isin(wanted)].copy()
    if work.empty:
        return work
    return work[work.apply(lambda row: _orders.get_region_by_address(str(row.get("地址", "")), ACCOUNTS) == region, axis=1)]


def _row_key(row):
    try:
        date_s = _orders.get_date_str(row["日期"])
        actual_period = _orders.normalize_period_text(row["開始時間"], row["結束時間"])
        system_period = _orders.map_to_system_slot(
            row["開始時間"], row["結束時間"], row.get("服務人時", "")
        )["system_slot"]
    except Exception:
        return None
    return (
        _orders.normalize_phone(row.get("電話", "")),
        _orders.normalize_addr_for_match(row.get("地址", "")),
        date_s,
        actual_period.replace(" ", ""),
        system_period.replace(" ", ""),
    )


def _block_key(block):
    lines = block.get("lines", [])
    joined = "\n".join(lines)
    phone = ""
    for line in lines:
        raw = str(line).strip()
        if re.fullmatch(r"09\d{8}", raw):
            phone = _orders.normalize_phone(raw)
            break
    try:
        service_date, service_period = _orders._calchk_service_date_time_from_lines(lines)
    except Exception:
        service_date = service_period = ""
    try:
        address = _orders._calchk_address_from_lines(lines)
    except Exception:
        address = ""
    return {
        "order_no": str(block.get("order_no") or "").strip(),
        "phone": phone,
        "date": service_date,
        "period": str(service_period or "").replace(" ", ""),
        "address": _orders.normalize_addr_for_match(address),
        "joined_address": _orders.normalize_addr_for_match(joined),
        "void": _orders.is_void_card(lines),
    }


def _address_matches(target: str, parsed: dict) -> bool:
    if not target:
        return True
    core = target[:10] if len(target) >= 10 else target
    return bool(core) and (core in parsed.get("address", "") or core in parsed.get("joined_address", ""))


def _fetch_phone_blocks(session, phone: str, max_pages: int = 8):
    blocks = []
    for page in range(1, max_pages + 1):
        params = dict(_orders.PURCHASE_FILTER_PARAMS_TEMPLATE)
        params["phone"] = phone
        params["page"] = str(page)
        resp = session.get(_orders.PURCHASE_URL, params=params, headers=_orders.HEADERS, allow_redirects=True)
        if resp.status_code != 200:
            break
        page_blocks = _orders.extract_order_cards_from_purchase_html(resp.text)
        if not page_blocks:
            break
        blocks.extend(page_blocks)
        if len(page_blocks) < 20:
            break
    return blocks


def _calendar_recover(row, region, gcal_service):
    if gcal_service is None:
        return {
            "日曆改色結果": "未執行",
            "日曆改色原因": "Google Calendar 未啟用或初始化失敗",
            "日曆原色": "",
            "日曆新色": "",
        }
    info = _orders.stage_calendar_color(row, gcal_service, region)
    if str(info.get("狀態", "")).strip() == "待確認":
        return info
    old_color = str(info.get("日曆原色", "")).strip()
    new_color = str(info.get("日曆新色", "")).strip()
    if old_color == "香蕉黃" or new_color == "香蕉黃":
        return {
            "日曆改色結果": "成功",
            "日曆改色原因": "中斷復原：日曆已是香蕉黃，無需重複修改",
            "日曆原色": old_color or "香蕉黃",
            "日曆新色": "香蕉黃",
        }
    return info


def _checkpoint(ws, row_numbers, message="已建立建單斷點；若程式中斷，下次會先反查後台再決定是否建單"):
    payload = {
        int(row_no): {"結果": _CHECKPOINT_RESULT, "原因": message}
        for row_no in row_numbers
    }
    if payload:
        _orders.update_sheet_rows(ws, payload)


def _build_recovered_result(session, row, order_no):
    """既有訂單命中後建立 K:AA 的完整回填資料（服務人員等依訂單編號精確查後台）。"""
    meta = _orders.fetch_order_meta_by_order_no(session, order_no)
    try:
        fetched_notice = _orders._fetch_order_edit_notice(session, order_no)
    except Exception:
        fetched_notice = None
    service_notice = (
        str(row.get("客服備註", "") or "") if fetched_notice is None else str(fetched_notice)
    )
    mapped = _orders.map_to_system_slot(
        row.get("開始時間", ""), row.get("結束時間", ""), row.get("服務人時", "")
    )
    sms_time = mapped.get("original_slot", "") if mapped.get("need_note") else ""
    return _orders.build_row_result(
        order_no=order_no,
        result=_RECOVERED_RESULT,
        reason="偵測到後台已成立但工作表尚未回填；已補回完整資料，避免重複成單。",
        sms_time=sms_time,
        customer_note=f"服務時間：{sms_time}" if sms_time else "",
        service_notice=service_notice,
        staff=meta.get("服務人員", "無人力"),
        service_status=meta.get("服務狀態", "未處理"),
        fare=meta.get("車馬費", "0"),
    )


def _recover_before_create(
    env_name, region, backend_email, backend_password, sheet_name,
    start_row, end_row, selected_rows, selected_actions, logger,
):
    _configure_runtime(env_name)
    ws, df = _load_worksheet_unique(sheet_name)
    work = _selected_df(df, selected_rows, start_row, end_row, region)
    if work.empty:
        return ws, [], [], [], 0

    blanks = []
    # 三種批次共用：訂單編號空白但不能建單的列（狀態非未安排、預約條件不在本次預約對象）
    # 只註明原因後略過，不建新單，也不反查後台。
    not_creatable = {}
    for _, row in work.iterrows():
        row_no = int(row["__sheet_row__"])
        if str(row.get("訂單編號", "") or "").strip():
            continue
        reason = create_block_reason(row)
        if reason:
            not_creatable[row_no] = reason
            continue
        key = _row_key(row)
        if key:
            blanks.append((row_no, row, key))
    for row_no, reason in sorted(not_creatable.items()):
        logger(f"⏭️ 第 {row_no} 列不建單：{reason}")

    if not blanks:
        return ws, [], [], [], 0

    session = requests.Session()
    if not _orders.login(session, backend_email, backend_password):
        raise RuntimeError("後台登入失敗，無法執行批次建單斷點檢查")

    gcal_service = None
    if "改 Google 日曆" in (selected_actions or []):
        try:
            gcal_service = _orders.build_gcal_service()
        except Exception as exc:
            logger(f"⚠️ 中斷復原：Google Calendar 初始化失敗：{exc}")

    rows_by_key = defaultdict(list)
    for row_no, row, key in blanks:
        rows_by_key[key].append((row_no, row))

    blocks_by_phone = {}
    claimed_order_nos = set()
    recovered = []
    blocked = []
    remaining = []

    for key, row_items in rows_by_key.items():
        phone, address, date_s, actual_period, system_period = key
        if phone not in blocks_by_phone:
            blocks_by_phone[phone] = [_block_key(b) for b in _fetch_phone_blocks(session, phone)]

        candidates = []
        for parsed in blocks_by_phone[phone]:
            order_no = parsed.get("order_no")
            if not order_no or order_no in claimed_order_nos:
                continue
            # 已退款／取消訂單不算已成單，不能拿來補回工作表。
            if parsed.get("void"):
                continue
            if parsed.get("phone") and parsed.get("phone") != phone:
                continue
            if parsed.get("date") != date_s:
                continue
            if parsed.get("period") not in {actual_period, system_period}:
                continue
            if not _address_matches(address, parsed):
                continue
            candidates.append(order_no)

        candidates = list(dict.fromkeys(candidates))
        if len(candidates) > len(row_items):
            msg = (
                f"後台找到 {len(candidates)} 筆未回填訂單，但工作表只有 {len(row_items)} 筆相同條件空白列；"
                "為避免誤配或重複成單，已停止這些列，請先人工確認。"
            )
            for row_no, _ in row_items:
                blocked.append(row_no)
                _orders.update_sheet_rows(ws, {row_no: {"結果": _BLOCKED_RESULT, "原因": msg}})
            logger(f"⚠️ {msg}")
            continue

        for (row_no, row), order_no in zip(row_items, candidates):
            result = _build_recovered_result(session, row, order_no)
            if "寄確認信" in (selected_actions or []):
                result["確認信"] = "待確認（中斷復原不自動重寄）"
            if "改 Google 日曆" in (selected_actions or []):
                result.update(_calendar_recover(row, region, gcal_service))
            _orders.update_sheet_rows(ws, {row_no: result})
            recovered.append(row_no)
            claimed_order_nos.add(order_no)
            logger(f"♻️ 第 {row_no} 列：後台已有 {order_no}，已補回工作表；不重複建單、不自動重寄確認信。")

        recovered_set = set(recovered)
        blocked_set = set(blocked)
        for row_no, _ in row_items:
            if row_no not in recovered_set and row_no not in blocked_set and row_no not in not_creatable:
                remaining.append(row_no)

    return ws, sorted(remaining), sorted(recovered), sorted(blocked), len(blanks)


def _merge_counts(results, recovered_count=0, blocked_count=0):
    success = recovered_count
    fail = blocked_count
    processed = recovered_count + blocked_count
    failed_records = []
    for result in results:
        result = result or {}
        success += int(result.get("success_count", 0) or 0)
        fail += int(result.get("fail_count", 0) or 0)
        processed += int(result.get("total_processed", 0) or 0)
        failed_records.extend(result.get("failed_records", []) or [])
    return {
        "success": fail == 0,
        "success_count": success,
        "fail_count": fail,
        "total_processed": processed,
        "recovered_count": recovered_count,
        "blocked_count": blocked_count,
        "failed_records": failed_records,
    }
