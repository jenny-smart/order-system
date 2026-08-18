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


def render(backend_email: str, backend_password: str, env: str) -> None:
    step("3", "批次建單優化")
    info_panel("功能說明", [
        "此優化功能固定使用 Google Sheet「儲值金訂單」，不另外輸入客人電話或付款方式。",
        "系統會依『姓名＋電話＋地址』自動判斷同一位客人的同一服務地址。",
        "若同一人、同一地址有不同服務日期，可在同一畫面一次複選多個日期／時段一起建單。",
        "仍沿用既有儲值金建單核心：查會員、查班表、餘額判斷、建單、確認信、日曆與 Sheet 回填規則不變。",
        "既有『批次建單（Google Sheet）』完全保留，不受此功能影響。",
    ])
    info_panel("效率設計", [
        "工作表只載入一次，再由程式自動把相同客人／地址分組。",
        "選取多筆時，連續列會合併成同一批次範圍交給既有批次核心執行，減少重複初始化。",
        "只列出『訂單編號空白』的資料，已有訂單編號的列不會進入優化建單清單。",
    ])

    if not backend_email.strip() or not backend_password.strip():
        st.warning("請先輸入上方後台帳號與密碼。")
        return

    st.caption(f"固定資料來源：{STORED_VALUE_SHEET_TITLE}｜Sheet ID：{STORED_VALUE_SHEET_ID}")

    c1, c2 = st.columns([2.2, 1])
    with c1:
        sheet_name = st.text_input(
            "工作表名稱",
            value=st.session_state.get("batch_opt_sheet_name", ""),
            placeholder="例如：台北202609、台中202609",
            key="batch_opt_sheet_name",
        )
    with c2:
        load_clicked = st.button("載入儲值金訂單", width="stretch", key="batch_opt_load_sheet")

    if load_clicked:
        if not sheet_name.strip():
            st.error("請輸入工作表名稱。")
            return
        try:
            with st.spinner("讀取儲值金訂單並分析同客人／同地址資料..."):
                candidates = _load_candidates(sheet_name.strip())
                groups = _build_groups(candidates)
            st.session_state.batch_opt_candidates = candidates
            st.session_state.batch_opt_groups = groups
            st.session_state.pop("batch_opt_selected_options", None)
            st.session_state.pop("batch_opt_results", None)
            multi_groups = sum(1 for g in groups if g["date_count"] > 1)
            st.success(f"載入完成：可處理 {len(candidates)} 列；共 {len(groups)} 組客人／地址，其中 {multi_groups} 組有多個日期。")
        except Exception as exc:
            st.session_state.batch_opt_candidates = None
            st.session_state.batch_opt_groups = None
            st.error(f"載入失敗：{exc}")
            return

    groups = st.session_state.get("batch_opt_groups") or []
    if not groups:
        return

    label_map = OrderedDict((_group_label(g), g) for g in groups)
    selected_group_label = st.selectbox(
        "選擇客人／地址",
        list(label_map.keys()),
        key="batch_opt_group_select",
    )
    group = label_map[selected_group_label]
    rows_df = group["rows"].copy()

    region = get_region_by_address(group["address"], ACCOUNTS) or "台北"
    st.info(
        f"姓名：{group['name']}｜電話：{group['phone']}｜區域：{region}\n\n"
        f"地址：{group['address']}"
    )
    if group["date_count"] > 1:
        st.success(f"偵測到同一人同一地址共有 {group['date_count']} 個不同日期，可一次複選多個日期／時段。")
    else:
        st.caption("此客人／地址目前只有 1 個待處理日期，仍可使用本功能建單。")

    display_cols = [c for c in ["__sheet_row__", "日期顯示", "時段顯示", "服務人時", "狀態", "購買項目", "備註"] if c in rows_df.columns]
    preview = rows_df[display_cols].rename(columns={
        "__sheet_row__": "列號",
        "日期顯示": "日期",
        "時段顯示": "時段",
    })
    st.dataframe(preview, width="stretch", hide_index=True)

    option_to_row = OrderedDict()
    for _, row in rows_df.iterrows():
        label = _option_label(row)
        option_to_row[label] = int(row["__sheet_row__"])

    selected_options = st.multiselect(
        "選擇要建立的日期／時段（可複選）",
        options=list(option_to_row.keys()),
        key="batch_opt_selected_options",
        placeholder="可一次勾選同一人同一地址的多個日期／時段",
    )
    selected_rows = [option_to_row[x] for x in selected_options]
    ranges = _contiguous_ranges(selected_rows)

    default_actions = ["建單", "寄確認信", "改 Google 日曆"] if env == "prod" else ["建單"]
    selected_actions = st.multiselect(
        "執行項目",
        ["建單", "寄確認信", "改 Google 日曆"],
        default=default_actions,
        key="batch_opt_actions",
    )

    st.info(
        f"目前選擇 {len(selected_rows)} 筆日期／時段；"
        f"程式會合併成 {len(ranges)} 個批次範圍執行。"
    )
    if ranges:
        st.caption("執行列範圍：" + "、".join(str(a) if a == b else f"{a}-{b}" for a, b in ranges))

    confirm = st.checkbox(
        f"我確認要在{'正式機 prod' if env == 'prod' else '測試機 dev'}執行以上 {len(selected_rows)} 筆儲值金訂單",
        key="batch_opt_confirm",
    )

    run_clicked = st.button(
        "確認批次建立選取訂單",
        type="primary",
        width="stretch",
        disabled=not confirm or not selected_rows or not selected_actions,
        key="batch_opt_execute",
    )

    log_box = st.empty()
    if run_clicked:
        logs = []
        total_success = 0
        total_fail = 0
        total_processed = 0
        range_results = []

        def ui_log(msg):
            logs.append(_format_log(msg))
            log_box.text("\n\n".join(logs[-120:]))

        with st.spinner("依選取日期／時段批次執行中..."):
            for start_row, end_row in ranges:
                ui_log(f"▶ 執行第 {start_row} 列" if start_row == end_row else f"▶ 執行第 {start_row}-{end_row} 列")
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
                    )
                    result = result if isinstance(result, dict) else {}
                    success = int(result.get("success_count", 0) or 0)
                    fail = int(result.get("fail_count", 0) or 0)
                    processed = int(result.get("total_processed", 0) or 0)
                    total_success += success
                    total_fail += fail
                    total_processed += processed
                    range_results.append({
                        "列範圍": str(start_row) if start_row == end_row else f"{start_row}-{end_row}",
                        "處理筆數": processed,
                        "成功": success,
                        "失敗": fail,
                    })
                except Exception as exc:
                    total_fail += end_row - start_row + 1
                    range_results.append({
                        "列範圍": str(start_row) if start_row == end_row else f"{start_row}-{end_row}",
                        "處理筆數": 0,
                        "成功": 0,
                        "失敗": end_row - start_row + 1,
                        "錯誤": str(exc),
                    })
                    ui_log(f"❌ 執行失敗：{exc}")

        st.session_state.batch_opt_results = range_results
        st.session_state.batch_opt_summary = {
            "selected": len(selected_rows),
            "processed": total_processed,
            "success": total_success,
            "fail": total_fail,
        }
        if total_fail:
            st.warning(f"執行完成：成功 {total_success}，失敗 {total_fail}。")
        else:
            st.success(f"執行完成：成功 {total_success} 筆。")

        # 重新讀取一次 Sheet，讓已成功回填訂單編號的列自動從清單消失。
        try:
            candidates = _load_candidates(sheet_name.strip())
            st.session_state.batch_opt_candidates = candidates
            st.session_state.batch_opt_groups = _build_groups(candidates)
        except Exception as exc:
            st.warning(f"建單已完成，但重新整理工作表清單失敗：{exc}")

    summary = st.session_state.get("batch_opt_summary") or {}
    if summary:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("選取", summary.get("selected", 0))
        c2.metric("實際處理", summary.get("processed", 0))
        c3.metric("成功", summary.get("success", 0))
        c4.metric("失敗", summary.get("fail", 0))
    results = st.session_state.get("batch_opt_results") or []
    if results:
        st.dataframe(pd.DataFrame(results), width="stretch", hide_index=True)
