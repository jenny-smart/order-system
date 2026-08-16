# -*- coding: utf-8 -*-
"""批次建單（Google Sheet）。"""

import re

import streamlit as st

from orders import run_process_web, get_region_by_address, load_worksheet
from accounts import ACCOUNTS
from function.ui_common import step, info_panel


def parse_row_input(row_text: str):
    if not row_text or not row_text.strip():
        raise ValueError("請輸入列號，例如：2,3,5-7")
    rows = set()
    for part in [p.strip() for p in row_text.split(",") if p.strip()]:
        if "-" in part:
            s, e = part.split("-", 1)
            s, e = int(s.strip()), int(e.strip())
            if s <= 0 or e <= 0:
                raise ValueError("列號必須大於 0")
            if s > e:
                raise ValueError(f"區間錯誤：{part}")
            rows.update(range(s, e + 1))
        else:
            n = int(part)
            if n <= 0:
                raise ValueError("列號必須大於 0")
            rows.add(n)
    return sorted(rows)


def find_no_slot_rows(sheet_name, region, candidate_rows=None):
    _, df = load_worksheet(sheet_name)
    candidate_set = set(candidate_rows or [])
    if candidate_set:
        df = df[df["__sheet_row__"].isin(candidate_set)]
    rows = []
    for _, row in df.iterrows():
        status = str(row.get("狀態", "")).strip()
        order_no = str(row.get("訂單編號", "")).strip()
        reason_text = f"{row.get('原因', '')} {row.get('沒班表日期', '')}"
        if status == "未安排" and not order_no and "無班表" in str(reason_text):
            if get_region_by_address(str(row.get("地址", "")), ACCOUNTS) == region:
                rows.append(int(row["__sheet_row__"]))
    return rows


def find_missing_order_in_o_rows(sheet_name, region, candidate_rows=None):
    _, df = load_worksheet(sheet_name)
    candidate_set = set(candidate_rows or [])
    if candidate_set:
        df = df[df["__sheet_row__"].isin(candidate_set)]
    rows = []
    for _, row in df.iterrows():
        status = str(row.get("狀態", "")).strip()
        order_no = str(row.get("訂單編號", "")).strip()
        o_text = str(row.iloc[14] if len(row) > 14 else "")
        if status == "未安排" and not order_no and not re.search(r"(LC|TT|KK)\d+", o_text):
            if get_region_by_address(str(row.get("地址", "")), ACCOUNTS) == region:
                rows.append(int(row["__sheet_row__"]))
    return rows


def format_log_message(msg):
    text = str(msg)
    text = text.replace("\\n", "\n")
    text = text.replace("目前環境：", "\n目前環境：")
    text = text.replace("BASE_URL：", "\nBASE_URL：")
    text = text.replace("執行區域：", "\n執行區域：")
    text = text.replace("執行工作表：", "\n執行工作表：")
    text = text.replace("執行列範圍：", "\n執行列範圍：")
    text = text.replace("處理第", "\n處理第")
    text = text.replace("已回填 Google Sheet。", "\n已回填 Google Sheet。")
    if text.startswith("▶"):
        text = "\n" + text
    return text.strip()


def render(backend_email, backend_password, env):
    step("3", "批次建單")
    info_panel("功能說明", [
        "適合已將多筆訂單整理在 Google Sheet 的批次處理情境。",
        "可依列號建立訂單、寄確認信、改 Google 日曆，並回填結果。",
        "勾自動篩選時，可在輸入的列號範圍內篩出「未安排、訂單編號空白、無班表」或「O欄找不到訂單編號」的列。",
    ])
    info_panel("使用說明", ["先選擇執行區域與工作表名稱。", "輸入要執行的列號，例如 2、2,3,5 或 5-10。", "勾選要執行的項目後按開始執行。"])
    step("4", "執行設定")
    c1, c2, c3 = st.columns(3)
    with c1:
        region = st.selectbox("執行區域", ["台北", "台中", "桃園", "新竹", "高雄"])
    with c2:
        sheet_name = st.text_input("工作表名稱", value="", placeholder="例：202604")
    with c3:
        row_input = st.text_input("執行列號", value="", placeholder="例：2,3,5-7")
    st.markdown('<div class="hint-box">💡 列號支援：單列 <code>2</code>、逗號分隔 <code>2,3,5</code>、區間 <code>2,3,5-7</code></div>', unsafe_allow_html=True)
    st.markdown("<hr>", unsafe_allow_html=True)
    step("3", "執行項目")
    default_actions = (["建單", "寄確認信", "改 Google 日曆"] if env == "prod" else ["建單"])
    selected_actions = st.multiselect("執行項目", options=["建單", "寄確認信", "改 Google 日曆"], default=default_actions, label_visibility="collapsed")
    st.markdown('<div class="hint-box">可自由組合，例如只寄確認信、只改日曆，或全流程一起跑。</div>', unsafe_allow_html=True)
    batch_allow_auto_lemon = st.checkbox("查無班表時自動補檸檬人（不動其他客人已配班專員）", value=False, key="batch_allow_auto_lemon")
    auto_no_slot_rows = st.checkbox("自動篩選：狀態未安排＋訂單編號空白＋無班表", value=False, key="auto_no_slot_rows")
    auto_missing_o_rows = st.checkbox("自動篩選：狀態未安排＋訂單編號空白＋O欄找不到訂單編號", value=False, key="auto_missing_o_rows")
    st.markdown("<hr>", unsafe_allow_html=True)
    run_clicked = st.button("🚀  開始執行", use_container_width=True)
    with st.expander("📄  執行過程", expanded=True):
        log_box = st.empty()
        log_box.text("尚未執行")
    result_container = st.container()
    if run_clicked:
        if not backend_email.strip():
            st.error("請輸入後台帳號"); st.stop()
        if not backend_password.strip():
            st.error("請輸入後台密碼"); st.stop()
        if not sheet_name.strip():
            st.error("請輸入工作表名稱"); st.stop()
        if not selected_actions:
            st.error("請至少選擇一個執行項目"); st.stop()
        if auto_no_slot_rows or auto_missing_o_rows:
            try:
                candidate_rows = parse_row_input(row_input) if row_input.strip() else []
            except Exception as e:
                st.error(f"列號格式錯誤：{e}"); st.stop()
            try:
                target_set = set()
                if auto_no_slot_rows:
                    target_set.update(find_no_slot_rows(sheet_name.strip(), region, candidate_rows))
                if auto_missing_o_rows:
                    target_set.update(find_missing_order_in_o_rows(sheet_name.strip(), region, candidate_rows))
                target_rows = sorted(target_set)
            except Exception as e:
                st.error(f"自動篩選列號失敗：{e}"); st.stop()
            if not target_rows:
                st.info("沒有符合自動篩選條件的列。"); st.stop()
        else:
            try:
                target_rows = parse_row_input(row_input)
            except Exception as e:
                st.error(f"列號格式錯誤：{e}"); st.stop()
        logs = []
        def ui_log(msg):
            logs.append(format_log_message(msg))
            display_text = "\n\n".join(logs[-120:])
            log_box.text(display_text)
        total_success = 0
        total_fail = 0
        total_processed = 0
        with st.spinner("執行中，請稍候…"):
            for row_no in target_rows:
                ui_log(f"▶ 開始執行第 {row_no} 列…")
                try:
                    result = run_process_web(
                        env_name=env, region=region,
                        backend_email=backend_email.strip(), backend_password=backend_password.strip(),
                        sheet_name=sheet_name.strip(), start_row=row_no, end_row=row_no,
                        selected_actions=selected_actions, logger=ui_log,
                        allow_auto_lemon_shift=batch_allow_auto_lemon,
                    )
                    if isinstance(result, dict):
                        total_success += result.get("success_count", 0)
                        total_fail += result.get("fail_count", 0)
                        total_processed += result.get("total_processed", 0)
                except Exception as e:
                    total_fail += 1
                    ui_log(f"❌ 第 {row_no} 列失敗：{e}")
        ui_log("===== 建單流程執行完成 =====")
        ui_log("===== 全部執行完成 =====")

        with result_container:
            st.markdown("<hr>", unsafe_allow_html=True)
            step("4", "執行結果")
            c1, c2, c3 = st.columns(3)
            c1.metric("執行筆數", total_processed)
            c2.metric("成功", total_success)
            c3.metric("失敗", total_fail)
            if total_fail == 0 and total_processed > 0:
                st.success(f"✅ 全部完成，共處理 **{total_processed}** 筆，成功 **{total_success}** 筆。")
            elif total_fail > 0:
                st.warning(f"⚠️ 執行完成，但有 **{total_fail}** 筆失敗，請查看執行過程。")
            else:
                st.info("執行完成，無資料被處理。")
