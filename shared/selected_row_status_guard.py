# -*- coding: utf-8 -*-
"""批次建單共用防呆：欄位去重、候選條件、回填欄位定位、無班表補檸檬人重試。

移植自 orders-system selected_row_status_guard.py。原版在 install_patch() 以
monkeypatch 改寫 orders.load_worksheet／update_sheet_rows／should_process_row／
should_create_order／process_one_group 與 ordersapp 的 run_process_web；
order-system 改為：

- should_process_row／should_create_order（狀態正規化）直接改在 orders.py；
- 回填第一個同名欄位、允許「待確認」直接改在 shared/gsheet.update_sheet_rows；
- 讀表去重、候選列、自動篩選、補檸檬人重試由本模組提供明確函式，
  由 shared/hybrid_batch_runner.py 與各批次頁面直接呼叫；
- 檸檬人補班衝突判斷已在 shared/cleaner_shift.py（第一批移植），不再 monkeypatch。
"""
from __future__ import annotations

import re

import pandas as pd

import orders


def _scalar(value):
    if isinstance(value, pd.Series): return value.iloc[0] if len(value) else ""
    if isinstance(value, (list, tuple)): return value[0] if value else ""
    return value


def normalize_status(value) -> str:
    text = str(_scalar(value) or "").replace(" ", " ").replace("﻿", "").replace("​", "")
    return re.sub(r"\s+", "", text)


def _dedupe_dataframe(df):
    return df if df.columns.is_unique else df.loc[:, ~df.columns.duplicated(keep="first")].copy()


def _load_worksheet_unique(sheet_name):
    ws, df = orders.load_worksheet(sheet_name)
    return ws, _dedupe_dataframe(df)


load_worksheet_unique = _load_worksheet_unique


def _first_series(df, name):
    selected = df.loc[:, df.columns == name]
    if selected.shape[1] == 0: raise RuntimeError(f"工作表缺少必要欄位：{name}")
    return selected.iloc[:, 0]


def _should_process_row(row):
    return orders.should_process_row(row)


def _should_create_order(row):
    return orders.should_create_order(row)


def _safe_load_candidates(batch_opt, sheet_name, allow_failed=False):
    try: _, df = _load_worksheet_unique(sheet_name)
    except Exception as exc:
        if type(exc).__name__ == "WorksheetNotFound": raise ValueError(f"找不到工作表分頁「{sheet_name}」") from exc
        raise
    work = pd.DataFrame(index=df.index); work["__sheet_row__"] = _first_series(df, "__sheet_row__")
    for col in batch_opt.REQUIRED_COLUMNS: work[col] = _first_series(df, col).map(batch_opt._text)
    work["__o_col__"] = df.iloc[:, 14].map(batch_opt._text) if df.shape[1] > 14 else ""
    for col in ("結果", "原因", "沒班表日期"): work[col] = _first_series(df, col).map(batch_opt._text) if col in df.columns else ""
    required_ok = work["姓名"].ne("") & work["電話"].ne("") & work["地址"].ne("") & work["日期"].ne("") & work["開始時間"].ne("") & work["結束時間"].ne("")
    # 雲端預設排除失敗列；本機入口或雲端明確確認重試時傳入 allow_failed=True。
    create_ok = (work["狀態"].map(normalize_status).eq("未安排")
                 & work["訂單編號"].eq("")
                 & (allow_failed | work["結果"].map(normalize_status).ne("失敗")))
    work = work[required_ok & (create_ok | work["訂單編號"].ne(""))].copy().reset_index(drop=True)
    work["日期顯示"] = work["日期"].map(batch_opt._date_text)
    work["時段顯示"] = work.apply(lambda r: f"{batch_opt._time_text(r['開始時間'])}-{batch_opt._time_text(r['結束時間'])}", axis=1)
    work["群組鍵"] = work.apply(lambda r: (batch_opt._text(r["姓名"]), batch_opt._text(r["電話"]), batch_opt._text(r["地址"])), axis=1)
    return work


def _auto_filter_rows(batch_opt, sheet_name, mode, region=None, allow_failed=False, candidates=None):
    work = candidates if candidates is not None else _safe_load_candidates(batch_opt, sheet_name, allow_failed=allow_failed)
    work = work[work["狀態"].map(normalize_status).eq("未安排") & work["訂單編號"].eq("")].copy()
    if region:
        work = work[work.apply(lambda row: batch_opt.get_region_by_address(batch_opt._text(row.get("地址")), __import__("accounts").ACCOUNTS) == region, axis=1)].copy()
    reason = work.get("原因", pd.Series("", index=work.index)).map(batch_opt._text)
    no_schedule_date = work.get("沒班表日期", pd.Series("", index=work.index)).map(batch_opt._text)
    if mode == "no_schedule": mask = reason.str.contains("無班表|沒班表", regex=True, na=False) | no_schedule_date.ne("")
    elif mode == "missing_order": mask = reason.str.contains("找不到訂單編號|未產生新訂單編號", regex=True, na=False)
    else: mask = pd.Series(False, index=work.index)
    return sorted(work.loc[mask, "__sheet_row__"].astype(int).tolist())


def update_sheet_rows_first_header(ws, row_results):
    """回填第一個同名欄位、允許「待確認」；實作已併入 shared/gsheet.update_sheet_rows。"""
    return orders.update_sheet_rows(ws, row_results)


def process_one_group_with_lemon_retry(session, rows_with_idx, token, gcal_service, region, backend_user_id=None, selected_actions=None, allow_auto_lemon_shift=False, used_order_nos=None, logger=print, group_no=None):
    """先以既有班表送單；只有結果為「無班表」的列才補檸檬人，補成功後整組重試一次。"""
    result = orders.process_one_group(
        session, rows_with_idx, token, gcal_service, region, backend_user_id,
        selected_actions, allow_auto_lemon_shift=False,
        used_order_nos=used_order_nos, logger=logger, group_no=group_no,
    )
    if not allow_auto_lemon_shift:
        return result
    row_map = {int(row_no): row for row_no, row in rows_with_idx}
    no_slot_rows = []
    for row_no, info in (result or {}).items():
        reason = str((info or {}).get("原因", "") or "")
        if "無班表" in reason or "沒班表" in reason:
            no_slot_rows.append(int(row_no))
    if not no_slot_rows:
        return result
    any_shift_added = False
    for row_no in no_slot_rows:
        row = row_map.get(row_no)
        if row is None: continue
        date_s = orders.get_date_str(row["日期"])
        mapped = orders.map_to_system_slot(row["開始時間"], row["結束時間"], row["服務人時"])
        period_s = mapped["system_slot"]
        people, _hours = orders.parse_service_human_hour(row.get("服務人時", ""), row.get("開始時間", ""), row.get("結束時間", ""))
        pre = orders.ensure_lemon_cleaner_shifts(session=session, base_url=orders.BASE_URL, service_date=date_s, period_s=period_s, person_count=people) or {}
        assigned = pre.get("assigned", []) or []
        skipped = pre.get("skipped", []) or []
        skipped_detail = "；".join(f"{item.get('name', '')}:{item.get('reason', '')}" for item in skipped[:8] if isinstance(item, dict))
        logger(f"🍋 第 {row_no} 列補檸檬人：成功 {len(assigned)} 人；略過 {len(skipped)} 人；{pre.get('message', '')}" + (f"；略過明細：{skipped_detail}" if skipped_detail else ""))
        if pre.get("success"): any_shift_added = True
    if not any_shift_added:
        return result
    retry_token = orders.get_csrf_token(session)
    logger("🍋 已補檸檬人，重新查班表並再次嘗試本筆／本組。")
    return orders.process_one_group(
        session, rows_with_idx, retry_token, gcal_service, region, backend_user_id,
        selected_actions, allow_auto_lemon_shift=False,
        used_order_nos=used_order_nos, logger=logger, group_no=group_no,
    )
