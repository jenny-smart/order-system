# -*- coding: utf-8 -*-
"""服務訂單系統內的「訂單班表記錄與返回」UI。"""

import pandas as pd
import streamlit as st

from function import reschedule as rs
from function import typhoon_sheet_sync as tss
from function import typhoon_transfer as tt


def _copy(copy_button, label, text, key):
    if copy_button:
        copy_button(label, text, key)
    else:
        st.caption(label)
        st.code(text, language=None)


def _fmt(r):
    return {
        "#": r["row"], "訂單編號": r["order_no"], "姓名": r.get("name", ""),
        "記錄日期": r["orig_date"], "記錄時段": r["orig_period"], "記錄專員": "、".join(r["orig_staff"]),
        "目前日期": r["now_date"], "目前時段": r["now_period"], "目前專員": "、".join(r["now_staff"]),
        "核對": tss.check_mark(r), "狀態": r["status"], "返回時間": r.get("restored_at", ""),
    }


def render(backend_email, backend_password, env, copy_button=None):
    st.caption(
        "排班要調班前，先記錄目前班表（每筆訂單的日期／時段／專員）；之後人員或日期被調整過，"
        "可把訂單返回記錄的班表：只換人的單在排班修改配回記錄的專員，日期時段也變了的單先改回記錄的日期時段再配回專員。"
    )
    tab_record, tab_return = st.tabs(["📸 記錄目前班表", "↩️ 返回記錄的班表"])
    with tab_record:
        _render_record(backend_email, backend_password, env, copy_button)
    with tab_return:
        _render_return(backend_email, backend_password, env, copy_button)


def _render_record(backend_email, backend_password, env, copy_button=None):
    source_text = st.text_input("執行日期區間（要記錄班表的日期，一天或區間）",
                                placeholder="2026/10/29 或 2026/10/29-2026/10/30", key="rs_source")
    if st.button("🔍 查詢目前班表（不修改）", type="primary", use_container_width=True, key="rs_search"):
        if not backend_email.strip() or not backend_password.strip():
            st.error("請先在上方輸入後台帳號密碼")
            return
        try:
            start, end = tt.parse_date_range(source_text, allow_single=True)
        except Exception:
            st.error("執行日期區間格式請輸入：2026/10/29 或 2026/10/29-2026/10/30")
            return
        try:
            with st.spinner("登入後台並查詢訂單…"):
                found, debug = tt.find_typhoon_orders(env, backend_email.strip(), backend_password.strip(), start, end)
        except Exception as exc:
            st.error(f"查詢失敗：{exc}")
            return
        label = start.strftime("%Y-%m-%d") if start == end else f"{start:%Y-%m-%d}～{end:%Y-%m-%d}"
        st.session_state.rs_record_rows = rs.rows_from_orders(found)
        st.session_state.rs_record_label = label
        st.session_state.rs_record_debug = debug
        st.session_state.pop("rs_saved_id", None)

    rows = st.session_state.get("rs_record_rows")
    if rows is None:
        return
    if st.session_state.get("rs_record_debug", {}).get("hit_page_limit"):
        st.warning("查詢已達頁數上限，名單可能不完整，請到後台確認。")
    label = st.session_state.get("rs_record_label", "")
    st.caption(f"{label} 共 {len(rows)} 筆已付款服務訂單")
    if not rows:
        return
    st.dataframe(pd.DataFrame([_fmt(r) for r in rows]).drop(columns=["目前日期", "目前時段", "目前專員", "核對", "返回時間"]),
                 hide_index=True, use_container_width=True)
    _copy(copy_button, "複製目前班表（含標題列，貼到 Google Sheets 會自動分欄）", tss.restore_tsv(rows), "rs_copy_record")

    saved_id = st.session_state.get("rs_saved_id")
    if saved_id:
        st.success(f"已存成班表記錄 {saved_id}（{label}，{len(rows)} 筆）；要返回時到「↩️ 返回記錄的班表」選這份記錄。")
    elif st.button("💾 存成班表記錄", type="primary", use_container_width=True, key="rs_save"):
        try:
            st.session_state.rs_saved_id = rs.save_snapshot(backend_email.strip(), label, rows)
            st.session_state.pop("rs_snapshots", None)
        except Exception as exc:
            st.error(f"儲存失敗：{exc}")
            return
        st.rerun()


def _render_return(backend_email, backend_password, env, copy_button=None):
    try:
        snapshots = st.session_state.get("rs_snapshots")
        if snapshots is None:
            snapshots = rs.list_snapshots()
            st.session_state.rs_snapshots = snapshots
    except Exception as exc:
        st.warning(f"讀取班表記錄失敗：{exc}")
        return
    if not snapshots:
        st.info("還沒有班表記錄，請先到「📸 記錄目前班表」存一份。")
        return
    labels = {
        s["id"]: f"{s['recorded_at']}｜{s['range']}｜{s['count']} 筆｜{s['account']}" for s in snapshots
    }
    c1, c2 = st.columns([3, 1])
    with c1:
        snapshot_id = st.selectbox("選擇班表記錄", list(labels), format_func=labels.get, key="rs_snapshot")
    with c2:
        if st.button("🔄 重新整理", use_container_width=True, key="rs_refresh"):
            st.session_state.pop("rs_snapshots", None)
            st.rerun()
    target_text = st.text_input("返回日期區間（只返回記錄日期在這區間的訂單，空白＝整份記錄）",
                                placeholder="2026/10/29-2026/10/30", key="rs_target")

    if st.button("🔎 檢查要返回的訂單（不修改）", type="primary", use_container_width=True, key="rs_plan"):
        if not backend_email.strip() or not backend_password.strip():
            st.error("請先在上方輸入後台帳號密碼")
            return
        date_start = date_end = None
        if target_text.strip():
            try:
                start, end = tt.parse_date_range(target_text, allow_single=True)
            except Exception:
                st.error("返回日期區間格式請輸入：2026/10/29 或 2026/10/29-2026/10/30")
                return
            date_start, date_end = start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
        bar = st.progress(0.0)
        try:
            items = rs.load_snapshot_items(snapshot_id, date_start, date_end)
            st.session_state.rs_return_rows = rs.plan_return(
                env, backend_email.strip(), backend_password.strip(), items,
                progress=lambda i, total, item: bar.progress((i - 1) / max(total, 1)),
            )
            st.session_state.pop("rs_return_results", None)
        except Exception as exc:
            st.error(f"檢查失敗：{exc}")
            return
        bar.progress(1.0)

    rows = st.session_state.get("rs_return_rows")
    if rows is None:
        return
    results = st.session_state.get("rs_return_results")
    shown = results if results is not None else rows
    if results is None:
        pending = [r for r in rows if r["status"] in tss.RESTORE_PENDING]
        (st.warning if pending else st.success)(
            f"共 {len(rows)} 筆：待返回（日期時段也變了）{sum(r['status'] == '待返回' for r in rows)} 筆、"
            f"待配回原專員（只換了人）{sum(r['status'] == '待配回原專員' for r in rows)} 筆、"
            f"已在原班表 {sum(r['status'] == '已在原班表' for r in rows)} 筆"
        )
    else:
        done = sum(r["status"].startswith("已返回原班表") for r in results)
        (st.success if done == len(results) else st.warning)(f"返回完成：{done}／{len(results)} 筆已返回記錄的班表，其餘請看狀態")
    st.dataframe(pd.DataFrame([_fmt(r) for r in shown]), hide_index=True, use_container_width=True)
    _copy(copy_button,
          "複製執行後結果（含標題列，貼到 Google Sheets 會自動分欄）" if results is not None
          else "複製執行前名單（含標題列，貼到 Google Sheets 會自動分欄）",
          tss.restore_tsv(shown), "rs_copy_return")

    if results is None:
        pending = [r for r in rows if r["status"] in tss.RESTORE_PENDING]
        if not pending:
            return
        confirm = st.checkbox(f"確認把 {len(pending)} 筆訂單返回記錄的班表（日期／時段／專員）", key="rs_return_confirm")
        if st.button("↩️ 開始返回", type="primary", use_container_width=True, disabled=not confirm, key="rs_return_run"):
            bar = st.progress(0.0)
            status = st.empty()

            def _progress(index, total, row):
                bar.progress((index - 1) / max(total, 1))
                status.write(f"返回第 {index}/{total} 筆：{row['order_no']} → {row['orig_date']} {row['orig_period']}")

            try:
                st.session_state.rs_return_results = rs.execute_return(
                    env, backend_email.strip(), backend_password.strip(), rows, progress=_progress,
                )
            except Exception as exc:
                st.error(f"返回失敗：{exc}")
                return
            st.rerun()
