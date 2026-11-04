"""獨立的已成單預約完成 LINE 通知頁面。"""
import os
import requests
import streamlit as st

import orders
from accounts import ACCOUNTS
from shared import notification_service
from shared.line_notice_sheet import (
    filter_completed_address_groups, filter_groups_by_calendar, groups_from_dataframe,
    write_results_to_source,
)

_CLOUD_REPO = "jenny-smart/order-system"
_CLOUD_WORKFLOW = "completed-notice-cloud.yml"


def _cloud_token():
    token = next((os.getenv(key, "").strip() for key in ("ORDERS_GITHUB_TOKEN", "GITHUB_ACTIONS_TOKEN", "GH_TOKEN") if os.getenv(key, "").strip()), "")
    if not token:
        for key in ("ORDERS_GITHUB_TOKEN", "GITHUB_ACTIONS_TOKEN", "GH_TOKEN"):
            try:
                token = str(st.secrets.get(key, "")).strip()
            except Exception:
                token = ""
            if token: break
    return token


def _dispatch_cloud(sheet, rows, env):
    token = _cloud_token()
    if not token: raise RuntimeError("尚未設定可啟動 GitHub Actions 的 Token")
    response = requests.post(
        f"https://api.github.com/repos/{_CLOUD_REPO}/actions/workflows/{_CLOUD_WORKFLOW}/dispatches",
        headers={"Accept": "application/vnd.github+json", "Authorization": f"Bearer {token}", "X-GitHub-Api-Version": "2022-11-28"},
        json={"ref": "main", "inputs": {"sheet_name": sheet, "rows": rows, "env": env}}, timeout=30,
    )
    if response.status_code != 204: raise RuntimeError(f"啟動雲端失敗：{response.status_code} {response.text[:200]}")


@st.fragment(run_every="15s")
def _render_cloud_progress(sheet, row_spec):
    st.markdown("#### 雲端執行進度")
    try:
        _, df = orders.load_worksheet(sheet)
        groups = groups_from_dataframe(df, row_spec)
        status_by_address = {}
        if "通知處理狀態" in df.columns:
            for _, row in df.iterrows():
                key = (str(row.get("姓名", "") or "").strip(), "".join(str(row.get("地址", "") or "").split()))
                value = str(row.get("通知處理狀態", "") or "").strip()
                if value: status_by_address[key] = value
        keys = {(str(group.get("name") or "").strip(), "".join(str(group.get("address") or "").split())) for group in groups}
        completed = sum(status_by_address.get(key, "").startswith("完成") for key in keys)
        failed = sum(status_by_address.get(key, "").startswith("失敗") for key in keys)
        total = len(keys); pending = max(total - completed - failed, 0)
        columns = st.columns(4)
        for column, label, value in zip(columns, ("總組數", "已完成", "失敗待續跑", "未完成"), (total, completed, failed, pending)):
            column.metric(label, value)
        st.progress(completed / total if total else 0, text=f"已完成 {completed}/{total}（每 15 秒自動更新）")
    except Exception as exc:
        st.caption(f"暫時無法讀取工作表進度：{exc}")
    token = _cloud_token()
    if token:
        try:
            response = requests.get(
                f"https://api.github.com/repos/{_CLOUD_REPO}/actions/workflows/{_CLOUD_WORKFLOW}/runs?event=workflow_dispatch&per_page=10",
                headers={"Accept": "application/vnd.github+json", "Authorization": f"Bearer {token}", "X-GitHub-Api-Version": "2022-11-28"}, timeout=15,
            )
            response.raise_for_status()
            runs = response.json().get("workflow_runs", [])
            run = next((item for item in runs if sheet in str(item.get("display_title") or item.get("name") or "")), runs[0] if runs else None)
            if run:
                labels = {"queued": "排隊中", "in_progress": "執行中", "completed": "已結束"}
                state = labels.get(run.get("status"), run.get("status", ""))
                conclusion = run.get("conclusion") or ""
                st.info(f"GitHub Actions：{state}{'（' + conclusion + '）' if conclusion else ''}")
        except Exception:
            pass


def render(backend_email, backend_password, env):
    st.markdown("### 已成單預約完成通知")
    st.info("只處理 Google 日曆有對應行程的已成單資料；通知會直接寫入原排程工作表每個地址群組的第一列。")
    c1, c2 = st.columns(2)
    sheet_name = c1.text_input("工作表名稱", placeholder="例：台北202611", key="completed_notice_sheet")
    row_spec = c2.text_input("列號（選填）", placeholder="例：2,3,5-20；空白＝全部已成單列", key="completed_notice_rows")
    resume_completed = st.checkbox("略過已完成，從失敗／未完成繼續", value=True, key="completed_notice_resume")
    if st.button("☁️ 交給雲端批次產生並寫回", use_container_width=True, key="completed_notice_cloud"):
        if not sheet_name.strip(): st.error("請輸入工作表名稱")
        else:
            try:
                _dispatch_cloud(sheet_name.strip(), row_spec.strip(), env)
                st.success("已交給雲端執行；可關閉或切換網頁。完成者會直接寫回原列，失敗者下次可續跑。")
                st.markdown(f"[查看雲端執行進度](https://github.com/{_CLOUD_REPO}/actions/workflows/{_CLOUD_WORKFLOW})")
            except Exception as exc: st.error(str(exc))
    if sheet_name.strip():
        _render_cloud_progress(sheet_name.strip(), row_spec.strip())
    if st.button("檢查日曆並產生 LINE 通知", type="primary", use_container_width=True, key="completed_notice_run"):
        if not backend_email.strip() or not backend_password.strip():
            st.error("請先輸入後台帳號密碼")
        elif not sheet_name.strip():
            st.error("請輸入工作表名稱")
        else:
            st.session_state.completed_notice_results = []
            st.session_state.completed_notice_skipped = []
            st.session_state.completed_notice_summary = {}
            st.session_state.completed_notice_writeback = {}
            status = st.status("✅ 已按到按鈕｜正在讀取工作表…", expanded=True)
            progress = st.progress(0, text="準備中")
            live = st.empty()
            try:
                worksheet, df = orders.load_worksheet(sheet_name.strip())
                groups = groups_from_dataframe(df, row_spec)
                already_completed = 0
                if resume_completed:
                    groups, already_completed = filter_completed_address_groups(groups, df)
                source_groups = groups
                total = sum(len(group.get("entries") or []) for group in groups)
                status.write(f"工作表讀取完成：找到 {total} 筆已有訂單編號的資料。")
                if already_completed:
                    status.write(f"續跑模式：已略過 {already_completed} 組先前完成的姓名＋地址。")
                live.markdown(f"**共 {total} 筆｜日曆已檢查 0 筆｜日曆確認 0 筆｜略過 0 筆**")

                def calendar_progress(checked, calendar_total, matched, skipped_count, entry):
                    ratio = checked / calendar_total if calendar_total else 1
                    progress.progress(min(ratio * 0.7, 0.7), text=f"日曆檢查 {checked}/{calendar_total}｜已確認 {matched}｜略過 {skipped_count}")
                    live.markdown(
                        f"**共 {calendar_total} 筆｜日曆已檢查 {checked} 筆｜"
                        f"日曆確認 {matched} 筆｜略過 {skipped_count} 筆**  \n"
                        f"目前：第 {entry.get('row', '')} 列／{entry.get('order_no', '')}"
                    )

                status.write("正在逐筆比對 Google 日曆…")
                groups, skipped = filter_groups_by_calendar(
                    groups, orders, orders.build_gcal_service(), orders.GOOGLE_CALENDAR_MAP, ACCOUNTS,
                    progress_callback=calendar_progress,
                )
                results = []
                confirmed_orders = sum(len(group["order_nos"]) for group in groups)
                status.write(f"日曆比對完成：確認 {confirmed_orders} 筆；開始向後台核對並產生通知。")
                def address_key(group):
                    return (str(group.get("name") or "").strip(), "".join(str(group.get("address") or "").split()))
                source_by_key = {address_key(group): group for group in source_groups}
                matched_keys = {address_key(group) for group in groups}
                skipped_only = [group for group in source_groups if address_key(group) not in matched_keys]
                written_rows = inserted_rows = reduction_count = 0
                if skipped_only:
                    counts = write_results_to_source(worksheet, skipped_only, [], skipped)
                    written_rows += counts[0]; inserted_rows += counts[1]; reduction_count += counts[2]
                groups = sorted(groups, key=lambda group: min(int(entry["row"]) for entry in group.get("entries") or [{}]), reverse=True)
                processed_groups = 0
                for batch_start in range(0, len(groups), 8):
                    batch = groups[batch_start:batch_start + 8]
                    def backend_progress(done, _batch_total, label):
                        overall = processed_groups + done
                        progress.progress(0.7 + 0.3 * (overall / max(len(groups), 1)), text=f"後台批次確認 {overall}/{len(groups)} 組｜{label}")
                    batch_results = notification_service.build_many_combined_line_messages(
                        env, backend_email.strip(), backend_password.strip(), batch,
                        max_workers=4, progress_callback=backend_progress,
                    )
                    batch_keys = {address_key(group) for group in batch}
                    batch_source = [source_by_key[key] for key in batch_keys]
                    batch_skipped = [entry for entry in skipped if (str(entry.get("name") or "").strip(), "".join(str(entry.get("address") or "").split())) in batch_keys]
                    counts = write_results_to_source(worksheet, batch_source, batch_results, batch_skipped)
                    written_rows += counts[0]; inserted_rows += counts[1]; reduction_count += counts[2]
                    results.extend(batch_results); processed_groups += len(batch)
                    status.write(f"已完成並寫回第 {processed_groups}/{len(groups)} 組；可中途離開，下次會自動續跑。")
                backend_confirmed = sum(len(item["group"].get("order_nos") or []) for item in results if not item.get("error"))
                st.session_state.completed_notice_results = results
                st.session_state.completed_notice_skipped = skipped
                st.session_state.completed_notice_writeback = {
                    "sheet": sheet_name.strip(), "written": written_rows,
                    "inserted": inserted_rows, "reduced": reduction_count,
                }
                valid_count = sum(not item.get("error") for item in results)
                failed_count = len(results) - valid_count
                st.session_state.completed_notice_summary = {
                    "total": total, "checked": total, "calendar_confirmed": confirmed_orders,
                    "backend_confirmed": backend_confirmed, "skipped": len(skipped),
                    "notices": valid_count, "failed": failed_count,
                }
                progress.progress(1.0, text="執行完成")
                live.markdown(
                    f"**共 {total} 筆｜日曆已檢查 {total} 筆｜日曆確認 {confirmed_orders} 筆｜"
                    f"後台確認 {backend_confirmed} 筆｜略過 {len(skipped)} 筆｜通知 {valid_count} 組**"
                )
                status.update(label=f"✅ 執行完成｜產生 {valid_count} 組通知｜已直接寫回 {sheet_name.strip()}", state="complete", expanded=False)
            except Exception as exc:
                st.error(f"產生失敗：{exc}")
                status.update(label=f"❌ 執行失敗：{exc}", state="error", expanded=True)

    skipped = st.session_state.get("completed_notice_skipped", [])
    results = st.session_state.get("completed_notice_results", [])
    summary = st.session_state.get("completed_notice_summary") or {}
    writeback = st.session_state.get("completed_notice_writeback") or {}
    if summary:
        columns = st.columns(6)
        for column, label, key in zip(
            columns,
            ("已成單總筆數", "日曆已檢查", "日曆有行程", "後台已確認", "略過", "通知組數"),
            ("total", "checked", "calendar_confirmed", "backend_confirmed", "skipped", "notices"),
        ):
            column.metric(label, summary.get(key, 0))
    if writeback:
        st.success(
            f"已直接寫回原工作表「{writeback['sheet']}」：{writeback['written']} 列；"
            f"新增安排 {writeback['inserted']} 列；減少警示 {writeback['reduced']} 組。"
        )
    if skipped:
        st.info(f"日曆沒有對應行程，已略過 {len(skipped)} 筆，不產生通知。")
    for item in results:
        if item.get("error"):
            st.error(f"訂單 {item['order_no']} 產生失敗：{item['error']}")
