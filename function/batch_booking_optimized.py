# ============================================================
# 檔名：function/batch_booking_optimized.py
# 功能：儲值金訂單批次建單優化；依同一人＋同一地址自動分組，可一次複選多個日期／時段建立訂單。
# 更新時間：2026-08-19
# ============================================================
# -*- coding: utf-8 -*-
from __future__ import annotations

from collections import OrderedDict
from datetime import datetime

import pandas as pd
import streamlit as st

from accounts import ACCOUNTS
from function.ui_common import step, info_panel
from orders import get_region_by_address, load_worksheet, run_process_web

STORED_VALUE_SHEET_ID = "1de41gNvBZCGdfy0qNouRNEaQD7R019VAvz2cfq88ZrE"
STORED_VALUE_SHEET_TITLE = "儲值金訂單"

REQUIRED_COLUMNS = ["姓名", "電話", "地址", "日期", "開始時間", "結束時間", "狀態", "訂單編號"]


def _text(value) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    return str(value).strip()


def _date_text(value) -> str:
    raw = _text(value)
    if not raw:
        return ""
    for fmt in ("%Y/%m/%d", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except Exception:
            pass
    return raw.replace("/", "-")


def _time_text(value) -> str:
    raw = _text(value)
    if not raw:
        return ""
    if len(raw) >= 5 and ":" in raw:
        return raw[:5]
    return raw


def _ensure_sheet_row(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if "__sheet_row__" not in df.columns:
        # 第 1 列是標題，因此 DataFrame 第 1 筆資料對應 Sheet 第 2 列。
        df["__sheet_row__"] = range(2, len(df) + 2)
    return df


def _load_candidates(sheet_name: str) -> pd.DataFrame:
    _, df = load_worksheet(sheet_name)
    df = _ensure_sheet_row(df)
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise RuntimeError("工作表缺少必要欄位：" + "、".join(missing))

    work = df.copy()
    for c in REQUIRED_COLUMNS:
        work[c] = work[c].map(_text)

    # 優化版只處理尚未有訂單編號的列；既有訂單完全不碰。
    work = work[work["訂單編號"].eq("")]
    work = work[
        work["姓名"].ne("")
        & work["電話"].ne("")
        & work["地址"].ne("")
        & work["日期"].ne("")
        & work["開始時間"].ne("")
        & work["結束時間"].ne("")
    ]
    work["日期顯示"] = work["日期"].map(_date_text)
    work["時段顯示"] = work.apply(lambda r: f"{_time_text(r['開始時間'])}-{_time_text(r['結束時間'])}", axis=1)
    work["群組鍵"] = work.apply(lambda r: (_text(r["姓名"]), _text(r["電話"]), _text(r["地址"])), axis=1)
    return work


def _build_groups(df: pd.DataFrame):
    groups = []
    for key, g in df.groupby("群組鍵", sort=False):
        name, phone, address = key
        g = g.sort_values(["日期顯示", "開始時間", "__sheet_row__"])
        dates = [x for x in g["日期顯示"].tolist() if x]
        groups.append({
            "key": key,
            "name": name,
            "phone": phone,
            "address": address,
            "count": len(g),
            "date_count": len(set(dates)),
            "rows": g,
        })
    # 有多個日期者排前面，方便優先處理真正需要批次優化的客人。
    groups.sort(key=lambda x: (x["date_count"] <= 1, -x["date_count"], -x["count"], x["name"]))
    return groups


def _group_label(group) -> str:
    address = group["address"]
    short_addr = address if len(address) <= 28 else address[:28] + "…"
    suffix = "多日期" if group["date_count"] > 1 else "單日期"
    return f"{group['name']}｜{group['phone']}｜{short_addr}｜{group['count']} 筆 / {group['date_count']} 日期（{suffix}）"


def _option_label(row) -> str:
    return (
        f"第 {int(row['__sheet_row__'])} 列｜{row['日期顯示']} {row['時段顯示']}"
        f"｜狀態：{_text(row.get('狀態')) or '空白'}"
        f"｜{_text(row.get('購買項目')) or '未填購買項目'}"
    )


def _contiguous_ranges(row_numbers):
    rows = sorted({int(x) for x in row_numbers})
    if not rows:
        return []
    result = []
    start = prev = rows[0]
    for current in rows[1:]:
        if current == prev + 1:
            prev = current
            continue
        result.append((start, prev))
        start = prev = current
    result.append((start, prev))
    return result


def _format_log(msg) -> str:
    text = str(msg or "").replace("\\n", "\n")
    return text.strip()


def _parse_row_spec(row_spec: str) -> list[int]:
    text = str(row_spec or "").strip().replace("，", ",")
    if not text:
        raise ValueError("請輸入列號，例如：241,242 或 241-245。")

    rows = set()
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            bounds = [x.strip() for x in part.split("-", 1)]
            if len(bounds) != 2 or not all(x.isdigit() for x in bounds):
                raise ValueError(f"列號格式錯誤：{part}")
            start, end = map(int, bounds)
            if start <= 0 or end < start:
                raise ValueError(f"列號範圍錯誤：{part}")
            rows.update(range(start, end + 1))
        elif part.isdigit() and int(part) > 0:
            rows.add(int(part))
        else:
            raise ValueError(f"列號格式錯誤：{part}")

    if not rows:
        raise ValueError("請輸入有效列號。")
    return sorted(rows)


def render(backend_email: str, backend_password: str, env: str) -> None:
    step("3", "批次建單優化")
    info_panel("操作方式", [
        "輸入工作表名稱及列號即可批次執行，不需先載入或逐筆勾選。",
        "列號支援單列、逗號及區間，例如：241、241,242、241-245、241,243-245。",
        "系統會依地址自動判斷地區，同一人、同一地址及相同服務條件會集中執行。",
        "同地址若服務人數、時數、時段、購買項目或備註不同，會自動拆成不同組。",
        "只處理訂單編號空白且必要資料完整的列；已有訂單編號的列不會重複建單。",
    ])

    if not backend_email.strip() or not backend_password.strip():
        st.warning("請先輸入上方後台帳號與密碼。")
        return

    st.caption(f"固定資料來源：{STORED_VALUE_SHEET_TITLE}｜Sheet ID：{STORED_VALUE_SHEET_ID}")

    c1, c2 = st.columns([2, 1])
    with c1:
        sheet_name = st.text_input(
            "工作表名稱",
            value=st.session_state.get("batch_opt_sheet_name", ""),
            placeholder="例如：台北202609、台中202609",
            key="batch_opt_sheet_name",
        )
    with c2:
        row_spec = st.text_input(
            "列號",
            placeholder="例如：241,242 或 241-245",
            key="batch_opt_row_spec",
        )

    default_actions = ["建單", "寄確認信", "改 Google 日曆"] if env == "prod" else ["建單"]
    selected_actions = st.multiselect(
        "執行項目",
        ["建單", "寄確認信", "改 Google 日曆"],
        default=default_actions,
        key="batch_opt_actions",
    )

    try:
        requested_rows = _parse_row_spec(row_spec) if row_spec.strip() else []
    except ValueError as exc:
        requested_rows = []
        st.error(str(exc))

    if requested_rows:
        st.info(
            f"預計處理 {len(requested_rows)} 列："
            + "、".join(str(a) if a == b else f"{a}-{b}" for a, b in _contiguous_ranges(requested_rows))
        )

    confirm = st.checkbox(
        f"我確認要在{'正式機 prod' if env == 'prod' else '測試機 dev'}執行以上列號",
        key="batch_opt_confirm",
    )
    run_clicked = st.button(
        "確認批次建立指定列",
        type="primary",
        width="stretch",
        disabled=not confirm or not requested_rows or not sheet_name.strip() or not selected_actions,
        key="batch_opt_execute",
    )

    log_box = st.empty()
    if not run_clicked:
        summary = st.session_state.get("batch_opt_summary") or {}
        if summary:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("指定", summary.get("selected", 0))
            c2.metric("實際處理", summary.get("processed", 0))
            c3.metric("成功", summary.get("success", 0))
            c4.metric("失敗", summary.get("fail", 0))
        results = st.session_state.get("batch_opt_results") or []
        if results:
            st.dataframe(pd.DataFrame(results), width="stretch", hide_index=True)
        return

    logs = []

    def ui_log(msg):
        logs.append(_format_log(msg))
        log_box.text("\n\n".join(logs[-120:]))

    try:
        candidates = _load_candidates(sheet_name.strip())
        candidate_map = {int(row["__sheet_row__"]): row for _, row in candidates.iterrows()}
        invalid_rows = [row for row in requested_rows if row not in candidate_map]
        if invalid_rows:
            raise ValueError(
                "以下列號不存在、必要資料不完整，或已有訂單編號："
                + "、".join(map(str, invalid_rows))
            )

        rows_by_region = {}
        for row_no in requested_rows:
            address = _text(candidate_map[row_no].get("地址"))
            region = get_region_by_address(address, ACCOUNTS)
            if not region:
                raise ValueError(f"第 {row_no} 列無法依地址判斷地區：{address}")
            rows_by_region.setdefault(region, []).append(row_no)

        jobs = [(region, sorted(row_numbers)) for region, row_numbers in rows_by_region.items()]

        total_success = 0
        total_fail = 0
        total_processed = 0
        range_results = []

        with st.spinner("依指定列號批次執行中..."):
            for region, row_numbers in jobs:
                start_row, end_row = min(row_numbers), max(row_numbers)
                row_label = "、".join(map(str, row_numbers))
                ui_log(f"▶ {region}：執行指定列 {row_label}")
                try:
                    result = run_process_web(
                        env_name=env,
                        region=region,
                        backend_email=backend_email.strip(),
                        backend_password=backend_password.strip(),
                        sheet_name=sheet_name.strip(),
                        start_row=start_row,
                        end_row=end_row,
                        selected_actions=selected_actions,
                        logger=ui_log,
                        allow_auto_lemon_shift=False,
                        selected_rows=row_numbers,
                    )
                    result = result if isinstance(result, dict) else {}
                    success = int(result.get("success_count", 0) or 0)
                    fail = int(result.get("fail_count", 0) or 0)
                    processed = int(result.get("total_processed", 0) or 0)
                    total_success += success
                    total_fail += fail
                    total_processed += processed
                    range_results.append({
                        "地區": region,
                        "指定列": row_label,
                        "處理筆數": processed,
                        "成功": success,
                        "失敗": fail,
                    })
                except Exception as exc:
                    failed = len(row_numbers)
                    total_fail += failed
                    range_results.append({
                        "地區": region,
                        "指定列": row_label,
                        "處理筆數": 0,
                        "成功": 0,
                        "失敗": failed,
                        "錯誤": str(exc),
                    })
                    ui_log(f"❌ 執行失敗：{exc}")

        st.session_state.batch_opt_results = range_results
        st.session_state.batch_opt_summary = {
            "selected": len(requested_rows),
            "processed": total_processed,
            "success": total_success,
            "fail": total_fail,
        }
        if total_fail:
            st.warning(f"執行完成：成功 {total_success}，失敗 {total_fail}。")
        else:
            st.success(f"執行完成：成功 {total_success} 筆。")
    except Exception as exc:
        st.error(str(exc))
        return

    summary = st.session_state.get("batch_opt_summary") or {}
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("指定", summary.get("selected", 0))
    c2.metric("實際處理", summary.get("processed", 0))
    c3.metric("成功", summary.get("success", 0))
    c4.metric("失敗", summary.get("fail", 0))
    results = st.session_state.get("batch_opt_results") or []
    if results:
        st.dataframe(pd.DataFrame(results), width="stretch", hide_index=True)
