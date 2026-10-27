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

from datetime import date, datetime
import pandas as pd

from shared.booking_eligibility import (DEFAULT_STAGES, HOLD_COLUMN, STAGES, booking_stage, can_create_order, can_process_row,
                                        hold_reason, normalize_status, set_booking_stages)

import orders


def _scalar(value):
    if isinstance(value, pd.Series): return value.iloc[0] if len(value) else ""
    if isinstance(value, (list, tuple)): return value[0] if value else ""
    return value


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


def _service_date(value, batch_opt=None):
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = batch_opt._date_text(value) if batch_opt is not None else str(value).strip().replace("/", "-")
    try:
        return date.fromisoformat(str(text)[:10])
    except (TypeError, ValueError):
        return None


def validate_service_date_range(service_start=None, service_end=None):
    start = _service_date(service_start)
    end = _service_date(service_end)
    if service_start not in (None, "") and start is None:
        raise ValueError("服務起日格式錯誤。")
    if service_end not in (None, "") and end is None:
        raise ValueError("服務迄日格式錯誤。")
    if start and end and end < start:
        raise ValueError("服務迄日不可早於服務起日。")
    return start, end


def _filter_service_dates(batch_opt, work, service_start=None, service_end=None):
    start, end = validate_service_date_range(service_start, service_end)
    if not start and not end:
        return work.copy()
    dates = work.get("日期", pd.Series("", index=work.index)).map(lambda value: _service_date(value, batch_opt))
    mask = dates.notna()
    if start:
        mask &= dates.map(lambda value: value is not None and value >= start)
    if end:
        mask &= dates.map(lambda value: value is not None and value <= end)
    return work[mask].copy()


def filter_row_numbers_by_service_date(batch_opt, sheet_name, rows, service_start=None, service_end=None):
    rows = [int(row) for row in rows]
    if service_start in (None, "") and service_end in (None, ""):
        return rows, []
    _, df = _load_worksheet_unique(sheet_name)
    selected = df[df["__sheet_row__"].astype(int).isin(set(rows))].copy()
    allowed = set(_filter_service_dates(batch_opt, selected, service_start, service_end)["__sheet_row__"].astype(int).tolist())
    return [row for row in rows if row in allowed], [row for row in rows if row not in allowed]


def render_service_date_filter(st, key):
    c1, c2 = st.columns(2)
    start = c1.date_input("服務起日（F欄，空白＝不限）", value=None, key=f"{key}_start")
    end = c2.date_input("服務迄日（F欄，空白＝不限）", value=None, key=f"{key}_end")
    st.caption("日期篩選含起日與迄日；只填迄日時，F 欄日期在迄日以前（含當日）皆可成單。")
    return start, end


def _safe_load_candidates(batch_opt, sheet_name, allow_failed=False, service_start=None, service_end=None):
    try: _, df = _load_worksheet_unique(sheet_name)
    except Exception as exc:
        if type(exc).__name__ == "WorksheetNotFound": raise ValueError(f"找不到工作表分頁「{sheet_name}」") from exc
        raise
    work = pd.DataFrame(index=df.index); work["__sheet_row__"] = _first_series(df, "__sheet_row__")
    for col in batch_opt.REQUIRED_COLUMNS: work[col] = _first_series(df, col).map(batch_opt._text)
    work["__o_col__"] = df.iloc[:, 14].map(batch_opt._text) if df.shape[1] > 14 else ""
    for col in ("結果", "原因", "沒班表日期", HOLD_COLUMN): work[col] = _first_series(df, col).map(batch_opt._text) if col in df.columns else ""
    required_ok = work["姓名"].ne("") & work["電話"].ne("") & work["地址"].ne("") & work["日期"].ne("") & work["開始時間"].ne("") & work["結束時間"].ne("")
    # 雲端預設排除失敗列；本機入口或雲端明確確認重試時傳入 allow_failed=True。
    create_ok = (work.apply(can_create_order, axis=1).astype(bool)
                 & (allow_failed | work["結果"].map(normalize_status).ne("失敗")))
    work = work[required_ok & (create_ok | work["訂單編號"].ne(""))].copy().reset_index(drop=True)
    if service_start not in (None, "") or service_end not in (None, ""):
        work = _filter_service_dates(batch_opt, work, service_start, service_end).reset_index(drop=True)
    work["日期顯示"] = work["日期"].map(batch_opt._date_text)
    work["時段顯示"] = work.apply(lambda r: f"{batch_opt._time_text(r['開始時間'])}-{batch_opt._time_text(r['結束時間'])}", axis=1)
    work["群組鍵"] = work.apply(lambda r: (batch_opt._text(r["姓名"]), batch_opt._text(r["電話"]), batch_opt._text(r["地址"])), axis=1)
    return work


# 「O欄找不到訂單編號」：O 欄沒有單號；可再依 O 欄目前的文字勾選（都不選＝全部）。
O_BLANK_OPTION = "（O欄空白）"
_ORDER_NO_PATTERN = r"(?:LC|TT|KK)\d+"


def _creatable(batch_opt, work, region=None):
    work = work[work.apply(can_create_order, axis=1).astype(bool)].copy() if len(work) else work.copy()
    if region and len(work):
        work = work[work.apply(lambda row: batch_opt.get_region_by_address(batch_opt._text(row.get("地址")), __import__("accounts").ACCOUNTS) == region, axis=1).astype(bool)].copy()
    return work


def _auto_filter_rows(batch_opt, sheet_name, mode, region=None, allow_failed=False, candidates=None, o_texts=None,
                      service_start=None, service_end=None):
    work = candidates if candidates is not None else _safe_load_candidates(
        batch_opt, sheet_name, allow_failed=allow_failed, service_start=service_start, service_end=service_end)
    work = _creatable(batch_opt, work, region)
    if not len(work): return []
    mask = _mode_mask(batch_opt, work, mode, o_texts)
    return sorted(work.loc[mask, "__sheet_row__"].astype(int).tolist())


def _o_label(text):
    return text or O_BLANK_OPTION


def _o_text_options(batch_opt, sheet_name, region=None, allow_failed=True):
    """目前可建單、O 欄沒有單號的列，其 O 欄文字與列數，供畫面勾選。"""
    work = _creatable(batch_opt, _safe_load_candidates(batch_opt, sheet_name, allow_failed=allow_failed), region)
    if not len(work): return []
    o_col = work["__o_col__"].map(batch_opt._text)
    o_col = o_col[~o_col.str.contains(_ORDER_NO_PATTERN, regex=True, na=False)]
    counts = o_col.map(_o_label).value_counts()
    return sorted(counts.items(), key=lambda item: (item[0] != O_BLANK_OPTION, -item[1], item[0]))


def _mode_mask(batch_opt, work, mode, o_texts=None):
    reason = work.get("原因", pd.Series("", index=work.index)).map(batch_opt._text)
    no_schedule_date = work.get("沒班表日期", pd.Series("", index=work.index)).map(batch_opt._text)
    no_schedule = reason.str.contains("無班表|沒班表", regex=True, na=False) | no_schedule_date.ne("")
    o_col = work.get("__o_col__", pd.Series("", index=work.index)).map(batch_opt._text)
    missing_order = ~o_col.str.contains(_ORDER_NO_PATTERN, regex=True, na=False)
    if o_texts:
        missing_order &= o_col.map(_o_label).isin(set(o_texts))
    if mode == "all": return pd.Series(True, index=work.index)
    if mode == "no_schedule": return no_schedule
    if mode == "missing_order": return missing_order
    if mode == "both": return no_schedule | missing_order
    return pd.Series(False, index=work.index)


def _held_for_request(batch_opt, sheet_name, region, rows=(), modes=(), mode_scope=None, allow_failed=True, o_texts=None,
                      service_start=None, service_end=None):
    """指定列號＋自動篩選中，因預約條件不在本次預約對象而略過的列；三種批次共用。"""
    held = set(_held_rows(batch_opt, sheet_name, "all", region, allow_failed, rows=rows,
                          service_start=service_start, service_end=service_end)) if rows else set()
    for mode in modes:
        held.update(_held_rows(batch_opt, sheet_name, mode, region, allow_failed, rows=mode_scope, o_texts=o_texts,
                               service_start=service_start, service_end=service_end))
    return sorted(held)


def _held_rows(batch_opt, sheet_name, mode="all", region=None, allow_failed=False, rows=None, o_texts=None,
               service_start=None, service_end=None):
    """若預約條件在本次預約對象內就會成為建單候選的列號；三種批次用來顯示略過筆數。"""
    _, df = _load_worksheet_unique(sheet_name)
    if df.empty: return []
    work = df.copy()
    work["__o_col__"] = df.iloc[:, 14].map(batch_opt._text) if df.shape[1] > 14 else ""
    if rows is not None: work = work[work["__sheet_row__"].astype(int).isin({int(x) for x in rows})]
    # 與實際候選列使用相同的必要資料門檻，避免把資料不完整、原本就不會
    # 進批次的列算成「未選對象」，造成待成單數＋略過數大於畫面總數。
    required = ("姓名", "電話", "地址", "日期", "開始時間", "結束時間")
    required_ok = pd.Series(True, index=work.index)
    for column in required:
        required_ok &= work.get(column, pd.Series("", index=work.index)).map(batch_opt._text).ne("")
    work = work[required_ok].copy()
    work = _filter_service_dates(batch_opt, work, service_start, service_end)
    held = work.apply(lambda row: bool(hold_reason(row)) and can_create_order({**row.to_dict(), HOLD_COLUMN: ""}), axis=1) if len(work) else pd.Series(dtype=bool)
    work = work[held.astype(bool)] if len(work) else work
    if not allow_failed and "結果" in work.columns: work = work[work["結果"].map(normalize_status).ne("失敗")]
    if region: work = work[work.apply(lambda row: batch_opt.get_region_by_address(batch_opt._text(row.get("地址")), __import__("accounts").ACCOUNTS) == region, axis=1).astype(bool)] if len(work) else work
    if not len(work): return []
    return sorted(work.loc[_mode_mask(batch_opt, work, mode, o_texts), "__sheet_row__"].astype(int).tolist())


def _held_stage_text(batch_opt, sheet_name, rows):
    """略過列依預約條件分類，例如「改加 3、未回覆 5」。"""
    if not rows: return ""
    _, df = _load_worksheet_unique(sheet_name)
    wanted = {int(x) for x in rows}
    counts = {}
    for _, row in df.iterrows():
        if int(row["__sheet_row__"]) in wanted:
            stage = booking_stage(row) or "其他"
            counts[stage] = counts.get(stage, 0) + 1
    order = list(STAGES)
    return "、".join(f"{k} {v}" for k, v in sorted(counts.items(), key=lambda kv: order.index(kv[0]) if kv[0] in order else 99))


def held_message(batch_opt, sheet_name, rows):
    try:
        detail = _held_stage_text(batch_opt, sheet_name, rows)
    except Exception:
        detail = ""
    return f"未選入本次預約對象略過 {len(rows)} 列" + (f"（{detail}）" if detail else "")


def render_stage_filter(st, key):
    """三種批次共用：勾選本次要約排程「預約條件」的哪些階段（預設只有可約）。"""
    stages = st.multiselect(
        "本次預約對象（排程「預約條件」欄；空白的列一律照常判斷）", list(STAGES),
        default=list(DEFAULT_STAGES), key=key,
    )
    st.caption("建議順序：可約 → 改加 → 人時不足 → 已確認 → 未回覆。單一客人要例外處理，可直接改該列「預約條件」。")
    set_booking_stages(stages)
    return stages


def render_o_text_filter(st, batch_opt, sheet_name, region, key, allow_failed=True):
    """三種批次共用：列出 O 欄目前文字讓使用者單選／多選／不選；回傳所選文字。"""
    if not sheet_name:
        st.caption("輸入工作表名稱後，會列出 O 欄目前的內容可勾選。")
        return []
    cache_key, scope = f"{key}_options", (sheet_name, region, allow_failed)
    if st.button("重新讀取 O 欄內容", key=f"{key}_reload") or st.session_state.get(f"{cache_key}_scope") != scope:
        try:
            st.session_state[cache_key] = _o_text_options(batch_opt, sheet_name, region, allow_failed)
            st.session_state[f"{cache_key}_scope"] = scope
        except Exception as exc:
            st.warning(f"無法讀取 O 欄內容：{exc}")
            return []
    options = st.session_state.get(cache_key) or []
    counts = dict(options)
    if not options:
        st.caption("目前沒有 O 欄無單號的可建單列。")
        return []
    selected = st.multiselect(
        "O 欄內容（可單選、多選；都不選＝全部沒有單號的列）", [text for text, _ in options],
        format_func=lambda text: f"{text[:60]}{'…' if len(text) > 60 else ''}（{counts.get(text, 0)} 列）",
        key=f"{key}_selected",
    )
    return [text for text in selected if text in counts]


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
