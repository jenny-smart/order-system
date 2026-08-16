# -*- coding: utf-8 -*-
"""客服作業（舊客回購備註回填／新成單提醒建立／客服備忘錄整理）。"""

import streamlit as st

from memo_system import memo
from function.ui_common import step
from function.memo_shared import get_session, DEFAULT_RESULT, normalize_result


def safe_get(row, *keys, default=""):
    for k in keys:
        if k in row and row.get(k) is not None:
            return row.get(k)
    return default


def clear_pick_states():
    for k in [k for k in st.session_state.keys() if k.startswith("pick_")]:
        del st.session_state[k]


def reset_mode_state_if_changed(current_mode):
    if st.session_state.last_mode != current_mode:
        st.session_state.preview_rows = []
        st.session_state.sheet_summary = None
        clear_pick_states()
        st.session_state.last_mode = current_mode


def render_preview_blocks(rows):
    step("4", "查詢結果預覽")
    if not rows:
        st.info("查無資料")
        return []

    can_rows = [r for r in rows if r.get("can_autofill")]
    no_rows  = [r for r in rows if not r.get("can_autofill")]

    m1, m2, m3 = st.columns(3)
    m1.metric("查詢總筆數", len(rows))
    m2.metric("可自動回填", len(can_rows))
    m3.metric("無可參照來源", len(no_rows))

    st.markdown(
        '<div class="info-strip">'
        '<b>預覽說明</b><ul>'
        '<li>目前訂單：要回填備註的目標訂單</li>'
        '<li>來源訂單：最近一筆可參照的歷史訂單</li>'
        '<li>新成單：沒有歷史來源時，會帶入預設提醒文字</li>'
        '</ul></div>',
        unsafe_allow_html=True
    )

    selected_ids = []

    def render_section(title, items, section_key, default_checked):
        st.markdown(f"### {title}")
        if not items:
            st.caption("沒有資料")
            return

        c1, c2, c3 = st.columns([1, 1, 4])
        with c1:
            if st.button("本區全選", key=f"sel_{section_key}", use_container_width=True):
                for row in items:
                    oid = str(row.get("order_id", "")).strip()
                    if oid:
                        st.session_state[f"pick_{oid}"] = True
        with c2:
            if st.button("本區全不選", key=f"unsel_{section_key}", use_container_width=True):
                for row in items:
                    oid = str(row.get("order_id", "")).strip()
                    if oid:
                        st.session_state[f"pick_{oid}"] = False
        with c3:
            st.caption(f"本區共 {len(items)} 筆")

        for row in items:
            order_id = str(row.get("order_id", "")).strip()
            checked = st.checkbox(
                f"選取 {order_id}",
                key=f"pick_{order_id}",
                value=st.session_state.get(f"pick_{order_id}", default_checked),
                label_visibility="collapsed"
            )

            card_cls = "preview-card preview-ok" if row.get("can_autofill") else "preview-card preview-ng"
            target_name          = row.get("customer_name", "")
            phone                = row.get("phone", "")
            address              = row.get("address", "")
            service_date         = row.get("service_date", "")
            purchase_status_name = row.get("purchase_status_name", "")
            source_order_id      = row.get("source_order_id", "")
            source_service_date  = row.get("source_service_date", "")
            source_purchase_status_name = row.get("source_purchase_status_name", "")
            source_status_name   = row.get("source_status_name", "")
            source_notice_preview = row.get("source_notice_preview", "")
            is_new_order         = row.get("is_new_order", False)
            can_autofill         = row.get("can_autofill", False)

            if is_new_order:
                source_notice_display_html = "（請於下方欄位編輯要寫入後台的提醒文字）"
                suggestion_text = "新成單，將帶入下方可編輯的提醒文字"
            elif can_autofill:
                source_notice_display_html = source_notice_preview.replace("\n", "<br>") if source_notice_preview else ""
                suggestion_text = "建議執行"
            else:
                source_notice_display_html = source_notice_preview.replace("\n", "<br>") if source_notice_preview else ""
                suggestion_text = "無可參照來源，請人工確認"

            st.markdown(f"""
            <div class="{card_cls}">
                <div class="preview-title">目前訂單：{order_id}</div>
                <div class="preview-sub">
                    <b>客戶 / 電話：</b>{target_name} / {phone}<br>
                    <b>地址：</b>{address}<br>
                    <b>目前服務日期：</b>{service_date}
                    <b>目前付款狀態：</b>{purchase_status_name or "-"}
                </div>
                <hr style="margin:10px 0;">
                <div class="preview-sub">
                    <b>來源訂單：</b>{source_order_id or "無"}<br>
                    <b>來源服務日期：</b>{source_service_date or "-"}
                    <b>來源付款狀態：</b>{source_purchase_status_name or "-"}
                    <b>來源服務狀態：</b>{source_status_name or "-"}<br>
                    <b>來源備註：</b>{source_notice_display_html or "無"}
                </div>
                <div class="preview-sub" style="margin-top:8px;">
                    <b>建議：</b>{suggestion_text}
                </div>
            </div>
            """, unsafe_allow_html=True)

            if is_new_order:
                st.text_area(
                    f"✏️ 新成單提醒文字（{order_id}，可自行編輯，將寫入後台備註）",
                    value=st.session_state.get(f"new_notice_{order_id}", memo.DEFAULT_NEW_ORDER_NOTICE),
                    key=f"new_notice_{order_id}",
                    height=130,
                )

            if checked and order_id:
                selected_ids.append(order_id)

    render_section("可自動回填", can_rows, "can_autofill", True)
    render_section("無可參照來源", no_rows, "no_source", False)

    st.markdown("---")
    step("5", "執行確認")
    st.metric("目前勾選", len(selected_ids))
    st.caption("執行後會把來源客服備註（或新成單固定提醒文字）寫入目標訂單，並把目標訂單服務狀態改為已處理。")
    return selected_ids


def render(backend_email, backend_password, env):
    email, env_option = backend_email, env
    step("3", "設定查詢條件")

    mode = st.radio(
        "",
        ["By Google Sheet", "By 電話", "By 搜尋條件"],
        horizontal=True,
        label_visibility="collapsed",
        key="memo_mode",
    )
    reset_mode_state_if_changed(mode)

    row_spec = ""; force = False; sheet_run_mode = "指定列號"; sheet_limit = 5
    phone_text = ""; date_mode = "服務日期"; purchase_status_name = "全部"
    start_date = None; end_date = None
    sheet_summary_btn = False; search_btn = False; execute_btn = False

    if mode == "By Google Sheet":
        sheet_run_mode = st.radio("處理方式", ["指定列號", "依剩餘筆數處理"], horizontal=True)
        if sheet_run_mode == "指定列號":
            st.markdown('<div class="info-strip"><b>列號格式</b><ul><li>單列：<code>2</code></li><li>多列：<code>2,3,5</code></li><li>區間：<code>2,3,5-7</code></li></ul></div>', unsafe_allow_html=True)
            c1, c2 = st.columns([5, 1])
            with c1:
                row_spec = st.text_input("列號")
            with c2:
                st.markdown("<div style='height:26px'></div>", unsafe_allow_html=True)
                force = st.checkbox("強制重跑")
            execute_btn = st.button("🚀 執行", use_container_width=True, disabled=not st.session_state.credentials_ready)
        else:
            c1, c2 = st.columns(2)
            with c1:
                sheet_summary_btn = st.button("🔍 查詢目前筆數", use_container_width=True, disabled=not st.session_state.credentials_ready)
            with c2:
                sheet_limit = st.number_input("本次處理筆數", min_value=1, value=5)
            if st.session_state.sheet_summary:
                s = st.session_state.sheet_summary
                m1, m2, m3 = st.columns(3)
                m1.metric("總筆數", s.get("total_rows", 0))
                m2.metric("未處理筆數", s.get("pending_rows", 0))
                m3.metric("已處理筆數", s.get("done_rows", 0))
            execute_btn = st.button("🚀 執行前 N 筆未處理資料", use_container_width=True, disabled=not st.session_state.credentials_ready)

    elif mode == "By 電話":
        phone_text = st.text_area("電話號碼", placeholder="可輸入多支，以逗號或換行分隔，例：0912345678,0922345678")
        st.caption("會先找出「目標訂單」，再比對最近一筆可參照的來源訂單。")
        c1, c2 = st.columns(2)
        with c1:
            search_btn = st.button("🔍 查詢列表", use_container_width=True, disabled=not st.session_state.credentials_ready)
        with c2:
            execute_btn = st.button("🚀 執行勾選項目", use_container_width=True, disabled=not st.session_state.credentials_ready)

    else:
        c1, c2 = st.columns(2)
        with c1:
            date_mode = st.selectbox("日期條件", ["服務日期", "購買日期"])
        with c2:
            purchase_status_name = st.selectbox("付款狀態", ["全部", "已付款", "未付款"], index=0)
        c3, c4 = st.columns(2)
        with c3:
            start_date = st.date_input("開始日期", value=None)
        with c4:
            end_date = st.date_input("結束日期", value=None)
        st.caption("搜尋條件固定只撈服務狀態＝未處理的目標訂單，再比對最近的可參照來源。")
        c5, c6 = st.columns(2)
        with c5:
            search_btn = st.button("🔍 查詢列表", use_container_width=True, disabled=not st.session_state.credentials_ready)
        with c6:
            execute_btn = st.button("🚀 執行勾選項目", use_container_width=True, disabled=not st.session_state.credentials_ready)

    with st.expander("執行 LOG", expanded=True):
        log_box = st.empty()
        log_box.text("\n".join(st.session_state.logs[-3000:]) if st.session_state.logs else "尚未執行")

    result_container = st.container()

    def ui_log(msg):
        st.session_state.logs.append(str(msg))
        try:
            log_box.text("\n".join(st.session_state.logs[-3000:]))
        except Exception:
            pass

    def render_result(result):
        r = normalize_result(result)
        with result_container:
            st.markdown("---")
            step("6", "執行結果")
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("執行筆數", r["processed"])
            c2.metric("成功", r["success"])
            c3.metric("失敗", r["failed"])
            c4.metric("略過", r["skipped"])
            c5.metric("回寫筆數", r["updated_orders"])
            if r["errors"]:
                with st.expander(f"⚠️ 錯誤明細（{len(r['errors'])} 筆）", expanded=True):
                    for i, err in enumerate(r["errors"], 1):
                        st.markdown(f"**{i}.** {err}")
            elif r["processed"] > 0:
                st.success(f"✅ 全部完成，共處理 {r['processed']} 筆，成功 {r['success']} 筆。")
            else:
                st.info("執行完成，無資料被處理。")

    def reset_before_action(clear_preview=True, clear_selection=True):
        st.session_state.logs = []
        st.session_state.result = None
        if clear_preview:
            st.session_state.preview_rows = []
            st.session_state.sheet_summary = None
        if clear_selection:
            clear_pick_states()
        try:
            log_box.text("尚未執行")
        except Exception:
            pass

    def reset_before_execute_keep_preview():
        st.session_state.logs = []
        st.session_state.result = None
        try:
            log_box.text("尚未執行")
        except Exception:
            pass

    if st.session_state.result is not None:
        render_result(st.session_state.result)

    if sheet_summary_btn:
        try:
            st.session_state.is_running = True
            reset_before_action(clear_preview=True, clear_selection=True)
            ui_log("===== 查詢目前筆數 =====")
            with st.spinner("查詢中，請稍候…"):
                st.session_state.sheet_summary = memo.get_sheet_summary(ui_logger=ui_log)
            ui_log("✅ 查詢完成")
        except Exception as e:
            ui_log(f"❌ 查詢失敗：{e}")
            st.error(str(e))
        finally:
            st.session_state.is_running = False

    if search_btn:
        try:
            st.session_state.is_running = True
            reset_before_action(clear_preview=True, clear_selection=True)
            ui_log("===== 開始查詢 =====")
            with st.spinner("查詢中，請稍候…"):
                session = get_session(email, env_option, ui_logger=ui_log)
                if mode == "By 電話":
                    if not phone_text.strip():
                        raise ValueError("請輸入至少一支電話")
                    preview_rows = memo.preview_by_phone_multi(phone_text=phone_text.strip(), ui_logger=ui_log, session=session)
                else:
                    start_text = start_date.strftime("%Y/%m/%d") if start_date else ""
                    end_text   = end_date.strftime("%Y/%m/%d") if end_date else ""
                    preview_rows = memo.preview_by_conditions(
                        date_mode=date_mode, date_start=start_text, date_end=end_text,
                        purchase_status_name=purchase_status_name, ui_logger=ui_log, session=session,
                    )
            st.session_state.preview_rows = preview_rows or []
            ui_log(f"✅ 查詢完成，共 {len(st.session_state.preview_rows)} 筆")
            st.rerun()
        except Exception as e:
            ui_log(f"❌ 查詢錯誤：{e}")
            st.error(str(e))
        finally:
            st.session_state.is_running = False

    if mode in ["By 電話", "By 搜尋條件"] and st.session_state.preview_rows:
        st.markdown("---")
        render_preview_blocks(st.session_state.preview_rows)

    if execute_btn:
        try:
            st.session_state.is_running = True
            reset_before_execute_keep_preview()

            if mode == "By Google Sheet":
                ui_log("===== 開始執行 =====")
                with st.spinner("執行中，請稍候…"):
                    session = get_session(email, env_option, ui_logger=ui_log)
                    if sheet_run_mode == "指定列號":
                        result = memo.main(row_spec=row_spec, force=force, ui_logger=ui_log, session=session)
                    else:
                        result = memo.main_first_n_pending(limit=int(sheet_limit), ui_logger=ui_log, session=session)
            else:
                if not st.session_state.preview_rows:
                    raise RuntimeError("請先查詢列表")
                current_selected_ids = []
                custom_notices = {}
                for row in st.session_state.preview_rows:
                    oid = str(safe_get(row, "order_id", default="")).strip()
                    if oid and st.session_state.get(f"pick_{oid}", False):
                        current_selected_ids.append(oid)
                        if row.get("is_new_order"):
                            custom_notices[oid] = st.session_state.get(f"new_notice_{oid}", memo.DEFAULT_NEW_ORDER_NOTICE)
                if not current_selected_ids:
                    raise RuntimeError("請先勾選要執行的資料")
                ui_log("===== 開始執行勾選項目 =====")
                ui_log(f"勾選筆數：{len(current_selected_ids)}")
                with st.spinner("執行中，請稍候…"):
                    session = get_session(email, env_option, ui_logger=ui_log)
                    result = memo.main_by_selected_order_ids(
                        order_ids=current_selected_ids, ui_logger=ui_log,
                        session=session, custom_notices=custom_notices,
                    )

            ui_log("===== 執行完成 =====")
            st.session_state.result = result
            render_result(result)
        except Exception as e:
            ui_log(f"❌ 執行錯誤：{e}")
            st.session_state.result = {**DEFAULT_RESULT, "failed": 1, "errors": [str(e)]}
            render_result(st.session_state.result)
        finally:
            st.session_state.is_running = False
