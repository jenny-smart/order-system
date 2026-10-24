# ============================================================
# 檔名：function/batch_booking_optimized.py
# 功能：儲值金訂單批次建單優化；依電話＋地址分組，多筆組先批次、每組完成即回填，
#       單筆組再逐筆；日曆在訂單回填後才 lazy 初始化（shared/hybrid_batch_runner.py）。
# 更新時間：2026-10-17
# ============================================================
# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
import traceback
from collections import OrderedDict
from datetime import datetime

import pandas as pd
import streamlit as st

from accounts import ACCOUNTS
from function.ui_common import step, info_panel
from orders import (
    get_region_by_address,
    load_worksheet,
    normalize_addr_for_match,
    normalize_phone,
)
from shared.execution_log_service import log_execution

STORED_VALUE_SHEET_ID = "1de41gNvBZCGdfy0qNouRNEaQD7R019VAvz2cfq88ZrE"
STORED_VALUE_SHEET_TITLE = "儲值金訂單"

REQUIRED_COLUMNS = ["服務人時", "備註", "姓名", "電話", "地址", "日期", "開始時間", "結束時間", "狀態", "購買項目", "訂單編號"]


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
    try:
        _, df = load_worksheet(sheet_name)
    except Exception as exc:
        if type(exc).__name__ == "WorksheetNotFound":
            raise ValueError(f"找不到工作表分頁「{sheet_name}」，請確認輸入的是分頁名稱，例如：台北202609。") from exc
        raise
    df = _ensure_sheet_row(df)
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise RuntimeError("工作表缺少必要欄位：" + "、".join(missing))

    work = df.copy()
    for c in REQUIRED_COLUMNS:
        work[c] = work[c].map(_text)

    # 建單候選：I 欄未安排、M 欄訂單編號空白、預約條件空白或在本次預約對象內（三種批次共用）。
    from shared.booking_eligibility import can_create_order
    work = work[work.apply(can_create_order, axis=1).astype(bool)] if len(work) else work
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
    work["群組鍵"] = work.apply(
        lambda r: (normalize_phone(r["電話"]), normalize_addr_for_match(r["地址"])), axis=1
    )
    return work


def _build_groups(df: pd.DataFrame):
    groups = []
    for key, g in df.groupby("群組鍵", sort=False):
        g = g.sort_values(["日期顯示", "開始時間", "__sheet_row__"])
        name = _text(g.iloc[0].get("姓名"))
        phone = _text(g.iloc[0].get("電話"))
        address = _text(g.iloc[0].get("地址"))
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
    """批次建單優化畫面（移植 orders-system batch_ui_consistency.render_optimized_like_batch）。

    畫面與原「批次建單」一致；執行改走 shared.hybrid_batch_runner.run_process_web_hybrid：
    依電話＋地址分組，2 筆以上同組先批次、每組完成即回填，單筆組再逐筆；日曆 lazy init。
    """
    from shared import dev_sheet_copy
    from shared.batch_ui_consistency import region_credentials, resolve_target_rows
    from shared.hybrid_batch_runner import run_process_web_hybrid
    from shared.selected_row_status_guard import held_message, render_o_text_filter, render_stage_filter

    step("4", "執行設定")
    c1, c2, c3 = st.columns(3)
    regions = list(ACCOUNTS.keys()) or ["台北"]
    default_index = regions.index("台北") if "台北" in regions else 0
    with c1:
        region = st.selectbox("執行區域", regions, index=default_index, key="batch_opt_region")
    with c2:
        sheet_name = st.text_input("工作表名稱", placeholder="例：台北202610", key="batch_opt_sheet_name").strip()
    with c3:
        row_spec = st.text_input("執行列號", placeholder="例：2,3,5-7", key="batch_opt_row_spec").strip()
    st.markdown('<div class="hint-box">💡 列號支援：單列 <code>2</code>、逗號分隔 <code>2,3,5</code>、區間 <code>2,3,5-7</code>。範圍內不符合條件的列會略過，不會中止整批。</div>', unsafe_allow_html=True)
    st.markdown("<hr>", unsafe_allow_html=True)

    step("3", "執行項目")
    selected_actions = st.multiselect(
        "執行項目", dev_sheet_copy.action_options(env),
        default=dev_sheet_copy.default_actions(env), key="batch_opt_actions_same_ui", label_visibility="collapsed",
    )
    st.markdown('<div class="hint-box">建單與回填優先；只有勾選改日曆且該筆已有訂單編號後，才初始化 Google Calendar。</div>', unsafe_allow_html=True)
    allow_auto_lemon = st.checkbox("查無班表時自動補檸檬人（不動其他客人已配班專員）", value=False, key="batch_opt_allow_auto_lemon")
    st.caption("指定範圍及自動篩選可包含失敗列；調整後可直接重試，不必清空 N 欄結果。")
    st.caption("三種批次共用建單條件：訂單編號空白＋狀態未安排＋「預約條件」空白或在本次預約對象內；其他列會略過並在執行過程註明原因。")
    render_stage_filter(st, "batch_opt_booking_stages")
    auto_no_slot = st.checkbox("自動篩選：狀態未安排＋訂單編號空白＋無班表", value=False, key="batch_opt_auto_no_slot")
    auto_missing_o = st.checkbox("自動篩選：狀態未安排＋訂單編號空白＋O欄找不到訂單編號", value=False, key="batch_opt_auto_missing_o")
    o_texts = render_o_text_filter(st, sys.modules[__name__], dev_sheet_copy.read_sheet(st, env, sheet_name), region, "batch_opt_o_texts") if auto_missing_o else []
    dev_sheet_copy.render_notice(st, env, sheet_name, "batch_opt")

    run_clicked = st.button("🚀  開始執行", use_container_width=True, key="batch_opt_same_ui_run")
    with st.expander("📄  執行過程", expanded=True):
        log_box = st.empty()
        if not run_clicked:
            log_box.text("尚未執行")
    if not run_clicked:
        return
    if not sheet_name:
        st.error("請輸入工作表名稱。")
        return
    if not selected_actions:
        st.error("請至少選擇一個執行項目。")
        return
    if dev_sheet_copy.is_dev(env):
        # 測試機：先複製分頁，後續篩選、建單、回填都改用副本。
        source_sheet = sheet_name
        try:
            sheet_name = dev_sheet_copy.resolve_run_sheet(st, env, source_sheet)
        except Exception as exc:
            st.error(f"建立測試副本失敗：{exc}")
            return
        st.info(f"🧪 測試機 dev：本次使用測試副本「{sheet_name}」（原分頁「{source_sheet}」不受影響）。")

    logs = []

    def ui_log(msg):
        logs.append(_format_log(msg))
        log_box.text("\n\n".join(logs[-160:]))

    target_rows = []
    try:
        batch_opt = sys.modules[__name__]
        target_rows, invalid, region_mismatch, held = resolve_target_rows(
            batch_opt, sheet_name, region, row_spec,
            auto_no_slot=auto_no_slot, auto_missing_o=auto_missing_o, o_texts=o_texts,
        )
        if held:
            ui_log(f"⏭️ {held_message(batch_opt, sheet_name, held)}：" + "、".join(map(str, held)))
        if invalid:
            ui_log("⏭️ 略過不符合執行條件列：" + "、".join(map(str, invalid)))
        if region_mismatch:
            ui_log(f"⏭️ 略過非{region}列：" + "、".join(map(str, region_mismatch)))
        if not target_rows:
            if held:
                st.info(f"{held_message(batch_opt, sheet_name, held)}，沒有其他符合執行條件的列。")
                return
            raise ValueError("指定範圍內沒有符合執行條件的列。")

        email, password = region_credentials(region, backend_email, backend_password)
        if not email or not password:
            raise RuntimeError(f"{region} 尚未設定後台帳號密碼")
        ui_log(f"實際執行列號：{'、'.join(map(str, target_rows))}")
        ui_log("批次優化：2 筆以上同組先批次；單筆組改走逐筆。每個多筆組建單完成後一次 batch_update 回填該組結果，再處理日曆。")
        result = run_process_web_hybrid(
            env_name=env, region=region, backend_email=email, backend_password=password,
            sheet_name=sheet_name, start_row=min(target_rows), end_row=max(target_rows),
            selected_actions=selected_actions, logger=ui_log,
            allow_auto_lemon_shift=allow_auto_lemon, selected_rows=target_rows,
        ) or {}
        success = int(result.get("success_count", 0) or 0)
        fail = int(result.get("fail_count", 0) or 0)
        st.success(f"執行完成：成功 {success}，失敗 {fail}，"
                   f"未選對象略過 {len(held)}，其他略過 {len(invalid) + len(region_mismatch)}。")
        log_execution(
            function_name="批次建單優化", status="失敗" if fail else "成功",
            area=region, date=sheet_name, target="、".join(map(str, target_rows)),
            message=f"處理{int(result.get('total_processed', 0) or 0)}筆，成功{success}筆，失敗{fail}筆",
        )
    except Exception as exc:
        ui_log(f"❌ 執行失敗：{exc}")
        st.error(f"執行失敗：{exc}")
        log_execution(
            function_name="批次建單優化", status="失敗", area=region,
            date=sheet_name, target="、".join(map(str, target_rows)) or row_spec,
            message=str(exc), traceback_text=traceback.format_exc(),
        )
