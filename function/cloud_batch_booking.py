# -*- coding: utf-8 -*-
"""批次建單優化＋雲端批次成單（Streamlit 頁面）。

移植自 orders-system cloud_batch_booking_ui.py。按下開始後以 GitHub Actions
workflow_dispatch 觸發 .github/workflows/optimized-cloud-batch-booking.yml，
由 `python -m shared.cloud_batch_booking` 在雲端背景持續成單；頁面每 15 秒讀取
`_雲端成單進度` 工作表與 Actions 狀態顯示進度。

原版 import 時安裝 selected_row_status_guard／batch_recovery_meta／
batch_booking_safety 的 monkeypatch；order-system 已將這些行為直接寫入
orders.py／shared/gsheet.py／shared/hybrid_batch_runner.py，這裡不再安裝 patch。
"""
from __future__ import annotations
import os
import json
import re
from datetime import datetime, timezone, timedelta
from service_pricing import load_config
import requests
import streamlit as st
from accounts import ACCOUNTS
from shared import dev_sheet_copy
from shared.cloud_booking_progress import PAUSED_PHASE
from shared.selected_row_status_guard import (render_o_text_filter, render_service_date_filter, render_stage_filter,
                                              validate_service_date_range)

REPO = "jenny-smart/order-system"
WORKFLOW = "optimized-cloud-batch-booking.yml"


def _token():
    for key in ("ORDERS_GITHUB_TOKEN", "GITHUB_ACTIONS_TOKEN", "GH_TOKEN"):
        value = os.getenv(key, "").strip()
        if value:
            return value
        try:
            value = str(st.secrets.get(key, "")).strip()
            if value:
                return value
        except Exception:
            pass
    return ""


def _dispatch(sheet, chunk_size, max_rows, filter_mode, region, allow_auto_lemon, retry_failed=False, o_texts=(),
              stages=("可約",), env="prod", service_start=None, service_end=None):
    token = _token()
    if not token:
        raise RuntimeError("尚未設定 ORDERS_GITHUB_TOKEN；需提供可啟動 order-system Actions 的 GitHub Token。")
    try:
        previous = _latest_run()
    except Exception:
        previous = None
    requested_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    r = requests.post(
        f"https://api.github.com/repos/{REPO}/actions/workflows/{WORKFLOW}/dispatches",
        headers={"Accept":"application/vnd.github+json", "Authorization":f"Bearer {token}", "X-GitHub-Api-Version":"2022-11-28"},
        json={"ref":"main", "inputs":{
            "sheet_name":sheet, "chunk_size":str(chunk_size), "max_rows":str(max_rows),
            "filter_mode":filter_mode, "region":region,
            "allow_auto_lemon":"true" if allow_auto_lemon else "false",
            "retry_failed":"true" if retry_failed else "false",
            "o_texts": json.dumps(list(o_texts or []), ensure_ascii=False),
            "stages": json.dumps(list(stages), ensure_ascii=False),
            "service_start": service_start.isoformat() if hasattr(service_start, "isoformat") else str(service_start or ""),
            "service_end": service_end.isoformat() if hasattr(service_end, "isoformat") else str(service_end or ""),
            "pricing_json": json.dumps(load_config()),
            "env": "dev" if dev_sheet_copy.is_dev(env) else "prod",
        }},
        timeout=30,
    )
    if r.status_code != 204:
        raise RuntimeError(f"啟動雲端批次失敗：{r.status_code} {r.text[:300]}")
    return {"previous_run_id": previous['id'] if previous else None, "requested_at": requested_at}



def _github_get(path):
    response = requests.get(
        f"https://api.github.com/repos/{REPO}/{path}",
        headers={"Accept": "application/vnd.github+json", "Authorization": f"Bearer {_token()}",
                 "X-GitHub-Api-Version": "2022-11-28"},
        timeout=15,
    )
    response.raise_for_status()
    return response


def _latest_run():
    runs = _github_get(
        f"actions/workflows/{WORKFLOW}/runs?per_page=1&branch=main&event=workflow_dispatch"
    ).json().get("workflow_runs", [])
    if not runs:
        # GitHub 的篩選查詢偶爾會暫時回傳空清單（執行中的也一樣）；改查不篩選的最新一筆。
        runs = _github_get(f"actions/workflows/{WORKFLOW}/runs?per_page=1").json().get("workflow_runs", [])
    return runs[0] if runs else None


def _run_label(run):
    created = run.get("created_at", "")
    try:
        local = datetime.fromisoformat(created.replace("Z", "+00:00")).astimezone(timezone(timedelta(hours=8)))
        started = local.strftime("%Y-%m-%d %H:%M:%S") + "（台北時間）"
    except (ValueError, TypeError):
        started = "啟動時間未提供"
    return f"第 {run['run_number']} 次執行・{started}・第 {run.get('run_attempt', 1)} 次嘗試"


def _run_summary(run_id):
    jobs = _github_get(f"actions/runs/{run_id}/jobs").json().get("jobs", [])
    for job in jobs:
        if job.get("name") == "booking":
            log = _github_get(f"actions/jobs/{job['id']}/logs").text
            matches = re.findall(r"FINISH attempted=(\d+) success=(\d+) fail=(\d+) remaining=(\d+)", log)
            if matches:
                return tuple(map(int, matches[-1]))
    return None


def _render_live_progress(run):
    from shared.cloud_booking_progress import read_progress
    key = f"cloud_live_{run['id']}_{run.get('run_attempt', 1)}"
    try:
        snapshot = read_progress(run['id'], run.get('run_attempt', 1))
        if snapshot:
            st.session_state[key] = snapshot
    except Exception:
        snapshot = None
    snapshot = snapshot or st.session_state.get(key)
    if not snapshot:
        st.caption("尚未取得成單進度；可能仍在準備環境，或尚未成功讀取工作表。")
        return
    st.caption(f"工作表：{snapshot['sheet']}｜最後更新：{snapshot['updated_at']}（台北時間）")
    columns = st.columns(4)
    for column, label, field in zip(columns, ['已處理', '成功', '失敗', '剩餘'],
                                    ['processed', 'success', 'failed', 'remaining']):
        column.metric(label, f"{snapshot[field]} 列")
    total = snapshot['total']
    if total:
        st.progress(min(snapshot['processed'] / total, 1.0),
                    text=f"本次處理 {snapshot['processed']}／{total} 列")
    if snapshot.get('held'):
        st.info(f"未選入本次預約對象略過 {snapshot['held']} 列（各階段筆數與列號見日誌）")
    if run.get('status') != 'completed' and snapshot['rows']:
        st.write(f"目前處理列號：{snapshot['rows']}")
    if run.get('status') == 'completed' and run.get('conclusion') != 'success':
        st.caption("以上為中止前最後回報的進度；未回報部分請核對工作表，勿視為零筆。")


def _render_running_steps(run_id, dev=False):
    jobs = _github_get(f"actions/runs/{run_id}/jobs").json().get("jobs", [])
    if not jobs:
        st.caption("正在等待雲端執行環境。")
        return
    labels = {
        "Set up job": "準備執行環境",
        "Run actions/checkout@v4": "準備成單程式",
        "Run actions/setup-python@v5": "準備執行環境",
        "Run pip install -r requirements.txt": "安裝執行所需套件",
        "Run optimized cloud batch booking": "批次成單、回填、寄確認信及同步日曆",
        "Complete job": "完成工作流程",
    }
    for job in jobs:
        active = [step for step in job.get("steps", []) if step.get("status") == "in_progress"]
        for step in active:
            name = step.get("name", "")
            label = labels.get(name, name)
            if dev and name == "Run optimized cloud batch booking":
                label = "批次成單、回填（測試機 dev 只建單）"
            st.write("目前步驟：" + label)
        completed = sum(step.get("status") == "completed" for step in job.get("steps", []))
        total = len(job.get("steps", []))
        if total:
            st.caption(f"工作流程步驟：已結束 {completed}／{total} 個；此數字不是成單筆數。")
    st.caption("進度筆數在每組處理完成後更新；逐筆細節可點「查看日誌」。")


def _sync_cloud_settings(settings):
    previous = st.session_state.get('optimized_cloud_settings')
    if previous != settings:
        for key in ('optimized_cloud_current_run', 'optimized_cloud_dispatch', 'optimized_cloud_history'):
            st.session_state.pop(key, None)
        st.session_state['optimized_cloud_settings'] = settings


def _clear_pending_preview():
    """送出後移除檢查快取；執行會改寫工作表，舊筆數不能再標成目前筆數。"""
    for key in ('optimized_cloud_pending', 'optimized_cloud_pending_rows', 'optimized_cloud_pending_key'):
        st.session_state.pop(key, None)


def _is_current_run(run):
    return st.session_state.get('optimized_cloud_current_run') == (run['id'], run.get('run_attempt', 1))


def _cancel_run(run_id):
    """直接取消 GitHub Actions 執行（舊版程式啟動、看不到暫停要求的執行也停得了）。"""
    r = requests.post(
        f"https://api.github.com/repos/{REPO}/actions/runs/{run_id}/cancel",
        headers={"Accept": "application/vnd.github+json", "Authorization": f"Bearer {_token()}",
                 "X-GitHub-Api-Version": "2022-11-28"},
        timeout=15,
    )
    if r.status_code not in (202, 409):  # 409：已經結束或正在取消
        raise RuntimeError(f"停止失敗：HTTP {r.status_code} {r.text[:200]}")


def _render_stop_button(run):
    box = st.expander("⏹ 立即停止（暫停沒反應時使用）")
    box.caption("直接停止雲端執行，可能停在一組建單中途。已成立但還沒回填的訂單，下次執行會先到後台找回並補回工作表，"
                "不會重複建單；中斷復原的列不會自動補寄確認信。停止後請等 1～2 分鐘再重新開始。")
    confirm = box.checkbox("我確認要立即停止這次雲端執行", key=f"optimized_cloud_stop_confirm_{run['id']}")
    if box.button("⏹ 立即停止", key=f"optimized_cloud_stop_{run['id']}", disabled=not confirm):
        try:
            _cancel_run(run['id'])
            box.warning("已送出停止，雲端會在數秒內停止；請等 1～2 分鐘後再重新開始。")
        except Exception as exc:
            box.error(str(exc))


def _render_pause_button(run):
    """雲端執行中可暫停：寫入暫停要求，雲端做完目前這一組、回填後就停，不會停在建單一半。"""
    from shared.cloud_booking_progress import PAUSE, request_pause
    key = f"cloud_live_{run['id']}_{run.get('run_attempt', 1)}"
    requested = (st.session_state.get(key) or {}).get('control') == PAUSE
    if requested:
        st.warning("⏸ 已要求暫停：雲端做完目前這一組並回填後就會停止（不會停在建單一半）。")
        return
    if st.button("⏸ 暫停成單", key=f"optimized_cloud_pause_{run['id']}"):
        try:
            if request_pause(run['id'], run.get('run_attempt', 1)):
                st.session_state.setdefault(key, {})['control'] = PAUSE
                st.warning("⏸ 已要求暫停：雲端做完目前這一組並回填後就會停止（不會停在建單一半）。")
            else:
                st.info("雲端尚未開始成單，請稍後再按暫停。")
        except Exception as exc:
            st.error(f"暫停要求送出失敗：{exc}")


@st.fragment(run_every="15s")
def _render_cloud_status():
    st.markdown("#### 雲端成單進度")
    st.markdown(f"[開啟雲端執行紀錄](https://github.com/{REPO}/actions/workflows/{WORKFLOW})")
    if not _token():
        st.warning("尚未設定 GitHub Token，頁面無法取得執行狀態；請開啟雲端執行紀錄查看。")
        return
    st.button("更新執行狀態", key="optimized_cloud_refresh")
    try:
        run = _latest_run()
        dispatch = st.session_state.get("optimized_cloud_dispatch")
        if dispatch:
            created_at = (run or {}).get("created_at", "")
            is_previous = run and run['id'] == dispatch.get('previous_run_id')
            is_older = bool(created_at and datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                            < datetime.fromisoformat(dispatch['requested_at']))
            if not run or is_previous or is_older:
                st.info("啟動要求已送出，等待雲端建立本次執行紀錄；每 15 秒更新。")
                return
            st.session_state['optimized_cloud_current_run'] = (run['id'], run.get('run_attempt', 1))
            del st.session_state['optimized_cloud_dispatch']
        # 頁面上方的「執行中」提醒讀這個值；下一次整頁重繪時更新。
        if run and run.get('status') != 'completed':
            st.session_state['optimized_cloud_active'] = _run_label(run)
        else:
            st.session_state.pop('optimized_cloud_active', None)
        if not run:
            st.info("尚無雲端批次執行紀錄。")
            return
        if run.get('status') == 'completed' and not _is_current_run(run):
            st.caption('目前設定尚未啟動雲端成單。')
            if not st.checkbox('顯示上次執行結果（歷史紀錄）', key='optimized_cloud_history'):
                return
            st.caption('以下為上次執行結果，與目前設定無關。')
        elif not _is_current_run(run):
            st.caption('另有雲端工作仍在執行；以下為該工作的進度，與目前新設定無關。')
        st.markdown(f"[{_run_label(run)}・查看日誌]({run['html_url']})")
        _render_live_progress(run)
        if run.get("status") != "completed":
            if run.get("status") == "in_progress":
                st.info("雲端批次執行中；每 15 秒更新狀態。")
                _render_pause_button(run)
                _render_stop_button(run)
                try:
                    _render_running_steps(run['id'], dev="(dev)" in str(run.get("display_title") or ""))
                except Exception:
                    st.caption("暫時無法取得目前步驟，請查看日誌；執行狀態仍會每 15 秒更新。")
            else:
                st.info("雲端批次排隊或準備中；每 15 秒更新狀態。")
            return
        conclusion = run.get("conclusion")
        cache_key = f"optimized_cloud_summary_{run['id']}_{run.get('run_attempt', 1)}"
        summary = st.session_state.get(cache_key)
        if summary is None:
            try:
                summary = _run_summary(run['id'])
                if summary is not None:
                    st.session_state[cache_key] = summary
            except Exception:
                st.caption("暫時無法取得筆數，請查看執行日誌。")
        live = st.session_state.get(f"cloud_live_{run['id']}_{run.get('run_attempt', 1)}") or {}
        if summary is not None and live.get('phase') == PAUSED_PHASE:
            attempted, success, failed, remaining = summary
            st.info(f"⏸ 已暫停：處理 {attempted} 列，成功 {success} 列，失敗 {failed} 列，尚待處理 {remaining} 列。"
                    "要繼續，按上方「開始雲端批次成單」；已建立的訂單不會重做。")
            return
        if summary is not None:
            attempted, success, failed, remaining = summary
            message = f"已執行完成：處理 {attempted} 列，成功 {success} 列，失敗 {failed} 列，尚待處理 {remaining} 列。"
            held = (st.session_state.get(f"cloud_live_{run['id']}_{run.get('run_attempt', 1)}") or {}).get('held', 0)
            if held:
                message += f"未選入本次預約對象略過 {held} 列。"
            if conclusion == "cancelled":
                st.warning("雲端批次已取消。" + message)
            elif failed:
                st.warning(message)
            elif conclusion == "success":
                st.success(message)
            else:
                st.error(message + " 工作流程仍有錯誤，請查看日誌。")
        elif conclusion == "success":
            st.success("雲端批次已執行完成。")
        elif conclusion == "cancelled":
            st.warning("雲端批次已取消。")
        else:
            st.error(f"這次雲端執行已失敗或中止（{conclusion}）。未取得最終 FINISH 摘要；上方如有筆數，是最後回報的進度，完整結果請核對工作表。")
    except Exception:
        st.warning("暫時無法取得雲端狀態，請稍後更新或至 GitHub Actions 查看。")


def render(env: str):
    st.subheader("批次建單優化＋雲端批次成單")
    is_dev = dev_sheet_copy.is_dev(env)
    if is_dev:
        st.warning("🧪 測試機 dev：雲端會連 backend-dev 建單，只執行「建單」，不寄確認信、不改 Google 日曆，並在工作表副本回填。")

    active = st.session_state.get('optimized_cloud_active')
    if active:
        st.info(f"⏳ 雲端成單執行中（{active}），進度見頁面最下方「雲端成單進度」；同一環境一次只跑一個，新送出的會排隊。")

    st.markdown("#### 4　執行設定")
    c1, c2, c3 = st.columns(3)
    regions = list(ACCOUNTS.keys()) or ["台北"]
    default_index = regions.index("台北") if "台北" in regions else 0
    region = c1.selectbox("執行區域", regions, index=default_index, key="optimized_cloud_region")
    sheet = c2.text_input("工作表名稱", placeholder="例：台北202610", key="optimized_cloud_sheet").strip()
    c3.text_input("執行列號", value="雲端依下方篩選自動取得", disabled=True, key="optimized_cloud_rows_hint")
    st.info("💡 雲端版由篩選條件自動取得列號；中斷重跑會先反查後台，避免重複建單。")

    st.markdown("#### 3　執行項目")
    cloud_actions = ["建單"] if is_dev else ["建單", "寄確認信", "改 Google 日曆"]
    st.multiselect(
        "執行項目", cloud_actions,
        default=cloud_actions, disabled=True,
        key="optimized_cloud_actions", label_visibility="collapsed",
    )
    allow_auto_lemon = st.checkbox(
        "查無班表時自動補檸檬人（不動其他客人已配班專員）",
        value=False, key="optimized_cloud_allow_auto_lemon",
    )
    retry_failed = st.checkbox(
        "我確認已調整，重試失敗列",
        value=False, key="optimized_cloud_retry_failed",
        help="已補班、要自動補檸檬人，或客人已重新儲值時勾選；仍依區域及篩選條件選取未安排、訂單編號空白的列。",
    )
    st.caption("三種批次共用建單條件：訂單編號空白＋狀態未安排＋「預約條件」空白或在本次預約對象內；其他列會略過並在執行過程註明原因。")
    stages = render_stage_filter(st, "optimized_cloud_booking_stages")
    service_start, service_end = render_service_date_filter(st, "optimized_cloud_service_date")
    auto_no_slot = st.checkbox(
        "自動篩選：狀態未安排＋訂單編號空白＋無班表",
        value=False, key="optimized_cloud_no_schedule",
    )
    auto_missing_o = st.checkbox(
        "自動篩選：狀態未安排＋訂單編號空白＋O欄找不到訂單編號",
        value=False, key="optimized_cloud_missing_o",
    )
    if auto_missing_o:
        import function.batch_booking_optimized as batch_opt
        o_texts = render_o_text_filter(st, batch_opt, dev_sheet_copy.read_sheet(st, env, sheet), region, "optimized_cloud_o_texts", allow_failed=retry_failed)
    else:
        o_texts = []
    c1, c2 = st.columns(2)
    chunk = c1.number_input("每輪最多處理列數", 1, 200, 50, 10, key="optimized_cloud_chunk")
    max_rows = c2.number_input("本次最多處理列數（0＝全部）", 0, 5000, 0, 10, key="optimized_cloud_max")

    modes = []
    if auto_no_slot:
        modes.append("no_schedule")
    if auto_missing_o:
        modes.append("missing_order")
    filter_mode = "both" if len(modes) == 2 else (modes[0] if modes else "all")
    pending_key = (sheet, region, filter_mode, allow_auto_lemon, retry_failed, tuple(o_texts), tuple(stages),
                   str(service_start or ""), str(service_end or ""))
    _sync_cloud_settings(pending_key + (int(chunk), int(max_rows)))
    st.caption("雲端預設略過 N 欄結果為「失敗」的列；調整後勾選「重試失敗列」，不必清空結果。要補檸檬人時請同時勾選上方補檸檬人選項。同一次執行中，每列處理後不會在下一輪重複執行。")

    dev_sheet_copy.render_notice(st, env, sheet, "optimized_cloud")
    if st.button("檢查待成單筆數", disabled=not sheet, key="optimized_cloud_check"):
        try:
            validate_service_date_range(service_start, service_end)
            from shared.cloud_batch_booking import load_pending
            rows = [row_no for row_no, _, _ in load_pending(
                dev_sheet_copy.read_sheet(st, env, sheet), filter_mode=filter_mode, selected_region=region, allow_auto_lemon=allow_auto_lemon,
                retry_failed=retry_failed, o_texts=o_texts, service_start=service_start, service_end=service_end,
            )]
            st.session_state.optimized_cloud_pending = len(rows)
            st.session_state.optimized_cloud_pending_rows = rows
            st.session_state.optimized_cloud_pending_key = pending_key
        except Exception as exc:
            st.error(f"讀取工作表失敗：{exc}")
    if st.session_state.get("optimized_cloud_pending_key") == pending_key:
        st.metric("目前符合所選條件", f"{st.session_state.optimized_cloud_pending} 列")
        rows = st.session_state.get("optimized_cloud_pending_rows") or []
        if rows:
            st.caption("列號：" + "、".join(map(str, rows[:100])) + ("…" if len(rows) > 100 else ""))

    confirm_label = "我確認在測試機 dev 執行：只建單（工作表副本回填）" if is_dev else "我確認執行：建單＋寄確認信＋同步 Google 日曆"
    confirm = st.checkbox(confirm_label, key="optimized_cloud_confirm")
    if st.button("🚀  開始雲端批次成單", type="primary", use_container_width=True, disabled=not(sheet and confirm), key="optimized_cloud_start"):
        try:
            validate_service_date_range(service_start, service_end)
            run_sheet = dev_sheet_copy.resolve_run_sheet(st, env, sheet)
            if is_dev:
                st.info(f"🧪 測試機 dev：本次使用測試副本「{run_sheet}」（原分頁「{sheet}」不受影響）。")
                st.session_state['optimized_cloud_dispatch'] = _dispatch(
                    run_sheet, int(chunk), int(max_rows), filter_mode, region, allow_auto_lemon, retry_failed,
                    o_texts, stages, env="dev", service_start=service_start, service_end=service_end)
            else:
                st.session_state['optimized_cloud_dispatch'] = _dispatch(
                    run_sheet, int(chunk), int(max_rows), filter_mode, region, allow_auto_lemon, retry_failed,
                    o_texts, stages, service_start=service_start, service_end=service_end)
            _clear_pending_preview()
            st.success("已交給 GitHub Actions 雲端執行；可關閉瀏覽器或電腦。")
            st.markdown(f"[查看雲端執行進度](https://github.com/{REPO}/actions/workflows/{WORKFLOW})")
        except Exception as exc:
            st.error(str(exc))

    st.markdown("<hr>", unsafe_allow_html=True)
    _render_cloud_status()
    # 頁面底部留白：進度區每 15 秒更新時高度會變，且右下角有 Streamlit 浮動列，
    # 留白讓進度一定能完整捲到畫面內。
    st.markdown('<div style="height:240px"></div>', unsafe_allow_html=True)
