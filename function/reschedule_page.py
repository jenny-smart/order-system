# -*- coding: utf-8 -*-
"""服務訂單系統內的「訂單批次調班」UI。"""

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
        "原日期": r["orig_date"], "原時段": r["orig_period"], "原專員": "、".join(r["orig_staff"]),
        "目前日期": r["now_date"], "目前時段": r["now_period"], "目前專員": "、".join(r["now_staff"]),
        "狀態": r["status"], "返回時間": r.get("restored_at", ""),
    }


def render(backend_email, backend_password, env, copy_button=None):
    st.caption(
        "排班要調班時使用：查執行日期區間的已付款訂單，一筆一筆用「修改日期」移到返回日期區間的同時段"
        "（第一天排不下才換下一天），馬上到「排班修改」配回原本的專員並確認姓名，才做下一筆。"
        "配不回原專員的位置改配不影響其他訂單的人，全部跑完後再補試；仍無法完成的列出請手動處理。"
    )
    c1, c2 = st.columns(2)
    with c1:
        source_text = st.text_input("執行日期區間（目前訂單所在日期）", placeholder="2027/04/12-2027/04/15", key="rs_source")
    with c2:
        target_text = st.text_input("返回日期區間（要移到的日期）", placeholder="2026/10/29-2026/10/30", key="rs_target")
    day_type = st.selectbox("返回日別", tt.DAY_TYPES, index=len(tt.DAY_TYPES) - 1, key="rs_day_type",
                            help="預設不限；也可只排平日或週末（平日、週末價格不同）。")

    if st.button("🔍 查詢執行日期區間的訂單（不修改）", type="primary", use_container_width=True, key="rs_search"):
        if not backend_email.strip() or not backend_password.strip():
            st.error("請先在上方輸入後台帳號密碼")
            return
        try:
            source_start, source_end = tt.parse_date_range(source_text, allow_single=True)
        except Exception:
            st.error("執行日期區間格式請輸入：2027/04/12 或 2027/04/12-2027/04/15")
            return
        try:
            with st.spinner("登入後台並查詢訂單…"):
                found, debug = tt.find_typhoon_orders(
                    env, backend_email.strip(), backend_password.strip(), source_start, source_end,
                )
        except Exception as exc:
            st.error(f"查詢失敗：{exc}")
            return
        st.session_state.rs_rows = rs.rows_from_orders(found)
        st.session_state.rs_debug = debug
        st.session_state.rs_source_range = (source_start.strftime("%Y-%m-%d"), source_end.strftime("%Y-%m-%d"))
        st.session_state.pop("rs_results", None)
        st.session_state.pop("rs_editor", None)

    rows = st.session_state.get("rs_rows")
    if rows is None:
        return
    debug = st.session_state.get("rs_debug", {})
    if debug.get("hit_page_limit"):
        st.warning("查詢已達頁數上限，名單可能不完整，請到後台確認。")
    if not rows:
        st.success("執行日期區間沒有已付款的服務訂單。")
        return

    results = st.session_state.get("rs_results")
    if results is not None:
        done = sum(r["status"].startswith("已調班並配回") for r in results)
        (st.success if done == len(results) else st.warning)(f"調班完成：{done}／{len(results)} 筆已調班並配回原專員，其餘請看狀態")
        st.dataframe(pd.DataFrame([_fmt(r) for r in results]), hide_index=True, use_container_width=True)
        _copy(copy_button, "複製執行後結果（含標題列，貼到 Google Sheets 會自動分欄）",
              tss.restore_tsv(results), "rs_copy_after")
        _copy(copy_button, "複製執行前名單（含標題列）", tss.restore_tsv(st.session_state.get("rs_plan", rows)),
              "rs_copy_before_done")
        return

    st.markdown("**執行前名單**（可取消勾選，或改「順序」調整先後）")
    frame = pd.DataFrame([{"調班": True, "順序": r["row"], **_fmt(r)} for r in rows]).drop(columns=["#", "返回時間"])
    edited = st.data_editor(
        frame, hide_index=True, use_container_width=True, key="rs_editor",
        disabled=[c for c in frame.columns if c not in ("調班", "順序")],
        column_config={
            "調班": st.column_config.CheckboxColumn("調班"),
            "順序": st.column_config.NumberColumn("順序", min_value=1, step=1),
        },
    )
    by_order = {r["order_no"]: r for r in rows}
    selected = edited[edited["調班"]].sort_values("順序", kind="stable")
    plan = [by_order[no] for no in selected["訂單編號"]]
    _copy(copy_button, f"複製執行前名單 {len(plan)} 筆（含標題列，貼到 Google Sheets 會自動分欄）",
          tss.restore_tsv(plan), "rs_copy_before")

    try:
        target_start, target_end = tt.parse_date_range(target_text, allow_single=True)
    except Exception as exc:
        st.info("請輸入返回日期區間，例如 2026/10/29-2026/10/30" if not target_text.strip() else f"返回日期區間：{exc}")
        return
    dates_by_day = tt.candidate_dates_by_day([r["orig_date"] for r in plan], target_start, target_end, day_type)
    for day, dates in dates_by_day.items():
        st.caption(f"{day} 的訂單候選日期（依序嘗試）：" + ("、".join(dates) or "無符合日別的日期"))
    all_dates = sorted({d for dates in dates_by_day.values() for d in dates})
    if not all_dates:
        st.error("返回日期區間內沒有符合日別的日期")
        return
    source_start, source_end = st.session_state.get("rs_source_range", ("", ""))
    overlap = [d for d in all_dates if source_start <= d <= source_end]
    if overlap:
        st.warning(f"返回日期和執行日期區間重疊（{'、'.join(overlap)}），請確認是否正確。")

    confirm = st.checkbox(
        f"確認把 {len(plan)} 筆訂單移到 {all_dates[0]}～{all_dates[-1]}（時段不變）並配回原專員", key="rs_confirm",
    )
    if st.button("🔁 開始調班", type="primary", use_container_width=True, disabled=not (confirm and plan), key="rs_run"):
        bar = st.progress(0.0)
        status = st.empty()

        def _progress(index, total, row):
            bar.progress((index - 1) / max(total, 1))
            status.write(f"調班第 {index}/{total} 筆：{row['order_no']} {row['orig_date']} {row['orig_period']}")

        try:
            st.session_state.rs_results = rs.execute_reschedule(
                env, backend_email.strip(), backend_password.strip(), plan, dates_by_day, progress=_progress,
            )
            st.session_state.rs_plan = plan
        except Exception as exc:
            st.error(f"調班失敗：{exc}")
            return
        st.rerun()
