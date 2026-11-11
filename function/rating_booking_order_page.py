# -*- coding: utf-8 -*-
"""評價預約成單：內勤工作表單「評價預約」分頁的指定列，先預覽判讀結果，再交給雲端成單。

更新記錄：
2026-11-12（新增）
- 預覽：用畫面上的後台帳密判讀指定列（要約哪幾天、時段、人時、付款方式，或無法成單的原因），不成單、不寫回。
- 交給雲端成單：啟動 .github/workflows/rating-booking-order.yml（python -m shared.rating_booking_order），
  成單後 A 欄寫訂單編號、L 欄寫成單日期時段或無法成單原因。
- 查無時段時補勾檸檬人：預設不勾。
"""
import json
from datetime import datetime, timedelta, timezone

import requests
import streamlit as st

from function.ui_common import step, info_panel, auto_lemon_checkbox

REPO = "jenny-smart/order-system"
WORKFLOW = "rating-booking-order.yml"


def _headers():
    from function.cloud_batch_booking import _token

    token = _token()
    if not token:
        raise RuntimeError("尚未設定 ORDERS_GITHUB_TOKEN；需提供可啟動 order-system Actions 的 GitHub Token。")
    return {"Accept": "application/vnd.github+json", "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28"}


def _dispatch(region, rows, allow_auto_lemon, env):
    from service_pricing import load_config

    response = requests.post(
        f"https://api.github.com/repos/{REPO}/actions/workflows/{WORKFLOW}/dispatches", headers=_headers(),
        json={"ref": "main", "inputs": {
            "region": region, "rows": rows, "allow_auto_lemon": "true" if allow_auto_lemon else "false",
            "dry_run": "false", "pricing_json": json.dumps(load_config()), "env": env}},
        timeout=30)
    if response.status_code != 204:
        raise RuntimeError(f"啟動雲端成單失敗：{response.status_code} {response.text[:300]}")


def _latest_run():
    response = requests.get(f"https://api.github.com/repos/{REPO}/actions/workflows/{WORKFLOW}/runs?per_page=1",
                            headers=_headers(), timeout=15)
    response.raise_for_status()
    runs = response.json().get("workflow_runs", [])
    return runs[0] if runs else None


def _run_text(run):
    try:
        started = datetime.fromisoformat(run["created_at"].replace("Z", "+00:00")).astimezone(
            timezone(timedelta(hours=8))).strftime("%m/%d %H:%M")
    except (KeyError, ValueError):
        started = ""
    state = {"queued": "排隊中", "in_progress": "執行中", "completed": "已結束"}.get(run.get("status"), run.get("status"))
    if run.get("status") == "completed":
        state += "（成功）" if run.get("conclusion") == "success" else f"（{run.get('conclusion')}）"
    return f"最近一次雲端執行：{started} 啟動，{state}｜{run.get('display_title', '')}"


def render(backend_email, backend_password, env):
    from shared import rating_booking_order as rbo

    step("1", "評價預約成單")
    info_panel("使用說明", [
        "把內勤工作表單「評價預約」分頁指定列約成訂單，目前只支援台北。A 欄已有內容的列會略過。",
        "F、G 欄的日期：「、，和及＋」＝每個日期各約一單；「或」「.」「12/2-12/4」＝擇一，依序查班表，第一個有時段的成單。",
        "表上沒寫的人數／時數、時段、購買項目、付款方式與發票，沿用該客人同地址上一張已付款訂單；"
        "大掃除期間沿用的時數不足 3 小時改為 3 小時。",
        "只寫月份（12月、1月底）、沒有電話、表上還有判讀不了的文字、同一天同地址已有訂單，都不成單，原因寫在 L 欄。",
        "先按預覽確認，再交給雲端成單。成單後 A 欄寫訂單編號，L 欄寫成單日期與時段。",
        "只建立訂單，不寄確認信、不改 Google 日曆、不發 LINE。",
    ])
    region = st.selectbox("地區（內勤工作表單）", list(rbo.REGIONS), key="rbo_region")
    rows_spec = st.text_input("執行列號（例：226-254 或 230,233,240-245）", key="rbo_rows")
    allow_lemon = auto_lemon_checkbox("rbo_allow_lemon")

    if st.button("🔍 預覽", key="rbo_preview", use_container_width=True):
        st.session_state.pop("rbo_plan", None)
        try:
            if not backend_email.strip() or not backend_password.strip():
                raise ValueError("請先在上方輸入後台帳號密碼")
            rbo.parse_rows(rows_spec)
            with st.spinner("讀取工作表並查詢後台中…"):
                summary = rbo.run(region, rows_spec, env=env, dry_run=True, email=backend_email.strip(),
                                  password=backend_password.strip(), logger=lambda *a, **k: None)
            st.session_state.rbo_plan = {"summary": summary, "region": region, "rows": rows_spec.strip()}
        except Exception as exc:
            st.error(f"預覽失敗：{exc}")

    started = st.session_state.pop("rbo_started", None)
    if started:
        st.success(started)
    state = st.session_state.get("rbo_plan")
    if state:
        summary = state["summary"]
        st.caption(f"{state['region']}｜列 {state['rows']}｜可成單 {summary['ready_rows']} 列、"
                   f"無法成單 {summary['failed_rows']} 列、略過 {summary['skipped_rows']} 列")
        st.dataframe(summary["preview"], use_container_width=True, hide_index=True)
        if summary["sheet_url"]:
            st.markdown(f"[開啟評價預約分頁]({summary['sheet_url']})")
        if env == "dev":
            st.info("dev：會在測試機成單，結果不寫回正式工作表。")
        if state["region"] != region or state["rows"] != rows_spec.strip():
            st.warning("地區或列號已修改，請重新預覽。")
        elif summary["ready_rows"] or summary["failed_rows"]:
            label = f"☁️ 交給雲端成單（可成單 {summary['ready_rows']} 列；無法成單的 {summary['failed_rows']} 列會把原因寫在 L 欄）"
            if st.button(label, key="rbo_start", type="primary", use_container_width=True):
                try:
                    _dispatch(region, state["rows"], allow_lemon, env)
                    st.session_state.rbo_started = "✅ 已交給雲端成單，完成後訂單編號會出現在 A 欄、結果在 L 欄。"
                    st.session_state.pop("rbo_plan", None)
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))
        else:
            st.info("這些列沒有要處理的資料。")

    st.markdown("<hr>", unsafe_allow_html=True)
    if st.button("🔄 查看雲端執行狀態", key="rbo_status"):
        try:
            run = _latest_run()
            if run:
                st.info(_run_text(run))
                st.markdown(f"[開啟執行紀錄]({run.get('html_url')})")
            else:
                st.info("還沒有雲端執行紀錄。")
        except Exception as exc:
            st.error(f"讀取雲端狀態失敗：{exc}")
