# -*- coding: utf-8 -*-
"""財務對帳（ATM 待付款清單查詢／配對銀行明細／更新系統對帳）。"""

import importlib
from datetime import date

import streamlit as st

from memo_system import atm

from function.ui_common import step
from function.memo_shared import get_session, DEFAULT_RESULT, normalize_result


def default_region_from_email(email_value):
    text = str(email_value or "").strip().lower()
    if ".tc@" in text or "+tc@" in text or text.startswith("jenny.tc@"):
        return "台中"
    return "台北"


def region_selectbox(label, key, email_value=None):
    options = ["台北", "台中", "桃園", "新竹", "高雄"]
    default_region = default_region_from_email(email_value)
    marker_key = f"{key}_default_email"
    current_email = str(email_value or "").strip().lower()
    if st.session_state.get(marker_key) != current_email:
        st.session_state[key] = default_region
        st.session_state[marker_key] = current_email
    return st.selectbox(label, options, index=options.index(default_region), key=key)


def render_atm_result(result, container):
    r = normalize_result(result)
    with container:
        st.markdown("---")
        step("4", "執行結果")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("執行筆數", r["processed"])
        c2.metric("成功", r["success"])
        c3.metric("失敗", r["failed"])
        c4.metric("略過", r["skipped"])
        if r["errors"]:
            with st.expander(f"⚠️ 錯誤明細（{len(r['errors'])} 筆）", expanded=True):
                for i, err in enumerate(r["errors"], 1):
                    st.markdown(f"**{i}.** {err}")
        elif r["processed"] > 0:
            st.success(f"✅ 全部完成，共處理 {r['processed']} 筆，成功 {r['success']} 筆。")
        else:
            st.info("執行完成，無資料被處理。")


def render_atm_list_mode(email, env_option):
    step("3", "待付款清單查詢")
    c1, c2 = st.columns([1, 2])
    with c1: region = region_selectbox("要貼到哪個地區的工作表", "atm_list_region", email)
    with c2: date_until = st.date_input("訂購日期-迄（預設為前一天）", value=date.fromisoformat(atm.default_date_until_tw()), key="atm_list_date_until")

    search_btn = st.button("🔍 查詢待付款 ATM 名單", use_container_width=True, disabled=not st.session_state.credentials_ready)

    with st.expander("執行 LOG", expanded=True):
        log_box_local = st.empty()
        log_box_local.text("\n".join(st.session_state.logs[-3000:]) if st.session_state.logs else "尚未執行")

    def atm_list_ui_log(msg):
        st.session_state.logs.append(str(msg))
        try: log_box_local.text("\n".join(st.session_state.logs[-3000:]))
        except: pass

    if search_btn:
        try:
            st.session_state.logs = []; st.session_state.atm_list_rows = None; st.session_state.atm_list_paste_result = None
            atm_list_ui_log("===== 開始查詢 ATM 待付款名單 =====")
            with st.spinner("查詢中，請稍候…"):
                session = get_session(email, env_option, ui_logger=atm_list_ui_log)
                rows = atm.search_atm_unpaid_orders(session=session, date_until=date_until.strftime("%Y-%m-%d"), ui_logger=atm_list_ui_log)
            st.session_state.atm_list_rows = rows
            atm_list_ui_log("===== 查詢完成 =====")
            st.rerun()
        except Exception as e:
            atm_list_ui_log(f"❌ 查詢失敗：{e}"); st.error(str(e))

    rows = st.session_state.get("atm_list_rows")
    if rows is not None:
        st.markdown("---"); step("4", "查詢結果")
        if not rows:
            st.info("查無符合條件的待付款 ATM 訂單。")
        else:
            st.metric("查到筆數", len(rows))
            st.text("\n".join(f"{r['year_month']}　{r['order_no']}　{r['name']}　${r['net_amount']}" for r in rows))
            st.markdown(f'<div class="warn-strip">⚠️ 確認貼上後，會把以上 {len(rows)} 筆資料寫入「{region}」ATM 對帳工作表的 I~L 欄。</div>', unsafe_allow_html=True)
            if st.button(f"🚀 貼上到「{region}」ATM 對帳工作表", type="primary", use_container_width=True):
                try:
                    atm_list_ui_log(f"===== 開始貼上到「{region}」ATM 對帳工作表 =====")
                    with st.spinner("貼上中，請稍候…"):
                        paste_result = atm.paste_atm_unpaid_list(region=region, rows=rows, ui_logger=atm_list_ui_log)
                    st.session_state.atm_list_paste_result = paste_result
                    atm_list_ui_log("===== 貼上完成 =====")
                    st.rerun()
                except Exception as e:
                    atm_list_ui_log(f"❌ 貼上失敗：{e}"); st.error(str(e))

    if st.session_state.get("atm_list_paste_result") is not None:
        st.markdown("---"); step("5", "貼上結果")
        pr = st.session_state.get("atm_list_paste_result")
        if pr.get("errors"): st.error("；".join(pr["errors"]))
        else: st.success(f"✅ 已從第 {pr.get('start_row')} 列開始，貼上 {pr.get('pasted', 0)} 筆資料到 I~L 欄。")


def render_atm_auto_match_mode(email, env_option):
    step("4", "配對銀行明細")
    st.markdown('<div class="info-strip"><b>配對依據</b><ul><li>金額 + 末碼</li><li>金額 + 姓名</li><li>金額 + 備註或時間</li><li>一筆收入可配對 2～5 筆訂單加總；須有末碼/姓名依據且組合唯一</li></ul></div>', unsafe_allow_html=True)
    st.markdown('<div class="warn-strip"><b>配對限制</b><ul><li>只靠金額不會自動配對</li><li>必須有末碼、姓名、備註或時間依據</li></ul></div>', unsafe_allow_html=True)

    row_spec = st.text_input("指定銀行列號", placeholder="例如：762-764,767-771")
    c1, c2, c3, c4 = st.columns([1, 1, 1, 1])
    with c1: region = region_selectbox("地區", "atm_match_region", email)
    with c2: default_service_type = st.text_input("預設服務類別", value="清潔", key="atm_match_service_type")
    with c3: default_fee_type = st.text_input("預設費用類別", value="服務費用", key="atm_match_fee_type")
    with c4:
        st.markdown("<div style='height:26px'></div>", unsafe_allow_html=True)
        overwrite_existing = st.checkbox("覆蓋已配對列", value=False, key="atm_match_overwrite")
    allow_review_prefill = st.checkbox("允許需確認候選預填", value=True, key="atm_match_allow_review_prefill")

    execute_btn = st.button("🚀 配對銀行明細", use_container_width=True, disabled=not st.session_state.credentials_ready)

    with st.expander("執行 LOG", expanded=True):
        log_box_local = st.empty()
        log_box_local.text("\n".join(st.session_state.logs[-3000:]) if st.session_state.logs else "尚未執行")

    def atm_match_ui_log(msg):
        st.session_state.logs.append(str(msg))
        try: log_box_local.text("\n".join(st.session_state.logs[-3000:]))
        except: pass

    result_container_local = st.container()
    if st.session_state.get("atm_match_result") is not None:
        render_atm_result(st.session_state.atm_match_result, result_container_local)

    if execute_btn:
        try:
            st.session_state.logs = []; st.session_state.atm_match_result = None
            atm_match_ui_log(f"===== 開始配對銀行明細（{region}）=====")
            with st.spinner("配對中，請稍候…"):
                result = atm.auto_match_bank_rows(region=region, row_spec=row_spec.strip(), overwrite_existing=overwrite_existing, default_service_type=default_service_type.strip() or "清潔", default_fee_type=default_fee_type.strip() or "服務費用", allow_review_prefill=allow_review_prefill, ui_logger=atm_match_ui_log)
            atm_match_ui_log("===== 配對銀行明細完成 =====")
            st.session_state.atm_match_result = result
            render_atm_result(result, result_container_local)
        except Exception as e:
            atm_match_ui_log(f"❌ 自動配對失敗：{e}")
            st.session_state.atm_match_result = {**DEFAULT_RESULT, "failed": 1, "errors": [str(e)]}
            render_atm_result(st.session_state.atm_match_result, result_container_local)


def render_atm_reconcile_mode(email, env_option):
    step("5", "更新系統對帳")
    st.markdown('<div class="warn-strip"><b>注意</b><ul><li>執行後會立即更新系統</li><li>發確認信會直接寄出</li><li>請確認列號正確後再執行</li></ul></div>', unsafe_allow_html=True)
    c1, c2 = st.columns([1, 3])
    with c1: region = region_selectbox("地區", "atm_reconcile_region", email)
    with c2: row_spec = st.text_input("列號", placeholder="支援：單列 2、逗號分隔 2,3,5、區間 2,3,5-7")
    c3, c4, c5 = st.columns(3)
    with c3: do_mark_paid = st.checkbox("按已付款", value=True)
    with c4: do_issue_invoice = st.checkbox("開立發票", value=True)
    with c5: do_send_mail = st.checkbox("發確認信", value=True)
    execute_btn = st.button("🚀 執行", use_container_width=True, disabled=not (st.session_state.credentials_ready and bool(row_spec.strip())))

    with st.expander("執行 LOG", expanded=True):
        log_box_local = st.empty()
        log_box_local.text("\n".join(st.session_state.logs[-3000:]) if st.session_state.logs else "尚未執行")

    def atm_ui_log(msg):
        st.session_state.logs.append(str(msg))
        try: log_box_local.text("\n".join(st.session_state.logs[-3000:]))
        except: pass

    atm_result_container = st.container()
    if st.session_state.get("atm_result") is not None:
        render_atm_result(st.session_state.atm_result, atm_result_container)

    if execute_btn:
        try:
            st.session_state.logs = []; st.session_state.atm_result = None
            atm_ui_log(f"===== 開始更新系統對帳（{region}）=====")
            if not (do_mark_paid or do_issue_invoice or do_send_mail):
                raise ValueError("請至少勾選一項要執行的動作")
            with st.spinner("執行中，請稍候…"):
                session = get_session(email, env_option, ui_logger=atm_ui_log)
                result = atm.process_atm_rows(region=region, row_spec=row_spec, do_mark_paid=do_mark_paid, do_issue_invoice=do_issue_invoice, do_send_mail=do_send_mail, ui_logger=atm_ui_log, session=session)
            atm_ui_log("===== 執行完成 =====")
            st.session_state.atm_result = result
            render_atm_result(result, atm_result_container)
        except Exception as e:
            atm_ui_log(f"❌ 執行錯誤：{e}")
            st.session_state.atm_result = {**DEFAULT_RESULT, "failed": 1, "errors": [str(e)]}
            render_atm_result(st.session_state.atm_result, atm_result_container)


def render(backend_email, backend_password, env):
    global atm
    atm = importlib.reload(atm)
    email, env_option = backend_email, env
    step("3", "選擇 ATM 對帳步驟")
    atm_mode = st.radio("", ["① 待付款清單查詢", "② 配對銀行明細", "③ 更新系統對帳"], horizontal=True, label_visibility="collapsed", key="atm_mode")
    if "待付款" in atm_mode:
        render_atm_list_mode(email, env_option)
    elif "配對" in atm_mode:
        render_atm_auto_match_mode(email, env_option)
    else:
        render_atm_reconcile_mode(email, env_option)
