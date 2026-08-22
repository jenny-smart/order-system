# -*- coding: utf-8 -*-
"""建立訂單相關流程：批次建單／建立舊客訂單／建立新客訂單／建立儲值金訂單／訂單轉換／儲值金補價差。

這幾個功能都是「建立訂單」，共用同一組 quick_order 建單引擎與畫面小工具（見
function/ui_common.py），因此合併在同一個檔案維護。
"""

import re
import traceback
from datetime import date, timedelta

import streamlit as st

from orders import get_region_by_address, load_worksheet, run_process_web
from accounts import ACCOUNTS
from function.ui_common import (
    step, info_panel, copy_button, show_duplicate_order_warning, auto_lemon_checkbox,
    NJ_MEMO, h, nonzero_money, payment_invoice_display, booking_route_display,
    person_hour_display, last_summary_card_html,
)
from shared.execution_log_service import log_execution

import quick_order as qo

_REQUIRED_QUICK_ORDER_NAMES = [
    "quick_lookup_member",
    "quick_create_order",
    "quick_check_available_slots",
    "send_confirmation",
    "build_line_message",
    "build_line_message_from_order_no",
    "build_combined_line_message_from_order_nos",
    "get_last_paid_summary",
    "get_last_paid_per_address",
    "get_unserved_paid_orders",
    "get_last_purchase_fetch_debug",
    "build_equivalent_plans",
    "search_available_service_dates",
    "parse_new_customer_order_text",
    "create_coupon",
    "convert_order",
    "convert_order_multi",
    "convert_order_stage1_reassign_original",
    "convert_order_stage2_create_new_orders",
    "get_stored_value",
    "calc_stored_value_plan",
    "stored_value_makeup_convert",
    "stored_value_makeup_create_stored_order",
    "stored_value_makeup_create_paid_order",
    "create_stored_value_purchase_order",
    "COUPON_COMPANY_ID_MAP",
    "COUPON_SERVICE_ITEM_MAP",
    "COUPON_TYPE_MAP",
]

if not hasattr(qo, "stored_value_makeup_convert") and hasattr(qo, "stored_value_makeup"):
    qo.stored_value_makeup_convert = qo.stored_value_makeup

for _name in _REQUIRED_QUICK_ORDER_NAMES:
    globals()[_name] = getattr(qo, _name)

CLEAN_TYPE_ID_MAP = {"居家清潔": "1", "辦公室清潔": "2", "裝修細清": "3"}

PERIOD_OPTIONS = [
    "08:30-12:30", "09:00-11:00", "09:00-12:00",
    "14:00-16:00", "14:00-17:00", "14:00-18:00",
    "09:00-16:00", "09:00-18:00",
]

PERIOD_HOUR_MAP = {
    "08:30-12:30": 4, "09:00-11:00": 2, "09:00-12:00": 3,
    "14:00-16:00": 2, "14:00-17:00": 3, "14:00-18:00": 4,
    "09:00-16:00": 6, "09:00-18:00": 8,
}


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


def render_batch(backend_email, backend_password, env):
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
    batch_allow_auto_lemon = auto_lemon_checkbox("batch_allow_auto_lemon")
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
            row_label = "、".join(map(str, target_rows))
            ui_log(f"▶ 一次送入指定列 {row_label}，先依姓名／電話／地址／人數時數分組…")
            try:
                result = run_process_web(
                    env_name=env, region=region,
                    backend_email=backend_email.strip(), backend_password=backend_password.strip(),
                    sheet_name=sheet_name.strip(), start_row=min(target_rows), end_row=max(target_rows),
                    selected_actions=selected_actions, logger=ui_log,
                    allow_auto_lemon_shift=batch_allow_auto_lemon,
                    selected_rows=target_rows,
                )
                if isinstance(result, dict):
                    total_success += result.get("success_count", 0)
                    total_fail += result.get("fail_count", 0)
                    total_processed += result.get("total_processed", 0)
            except Exception as e:
                total_fail += len(target_rows)
                ui_log(f"❌ 批次執行失敗：{e}")
                log_execution(
                    function_name="批次建單", status="失敗", area=region,
                    date=sheet_name.strip(), target=row_label,
                    message=str(e), traceback_text=traceback.format_exc(),
                )
            else:
                log_execution(
                    function_name="批次建單", status="失敗" if total_fail else "成功",
                    area=region, date=sheet_name.strip(), target=row_label,
                    message=f"處理{total_processed}筆，成功{total_success}筆，失敗{total_fail}筆",
                )
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


def render_old_customer(backend_email, backend_password, env):
    step("3", "建立舊客訂單")
    info_panel("功能說明", ["用電話查詢會員與歷史已付款服務。", "多地址客人會顯示各地址近一年紀錄，請先跟客人確認地址。", "可選已知日期查班表，也可依客人需求搜尋可服務日期。"])
    q1, q2 = st.columns(2)
    with q1:
        q_phone = st.text_input("客人電話", key="old_phone")
    with q2:
        q_clean_type = st.selectbox("購買項目", list(CLEAN_TYPE_ID_MAP.keys()), key="old_clean_type")
    if st.button("🔍  查詢會員", use_container_width=True, key="old_lookup_btn"):
        if not backend_email.strip() or not backend_password.strip():
            st.error("請先輸入後台帳號密碼"); st.stop()
        if not q_phone.strip():
            st.error("請輸入客人電話"); st.stop()
        try:
            with st.spinner("查詢中…"):
                st.session_state.q_lookup = quick_lookup_member(env_name=env, backend_email=backend_email.strip(), backend_password=backend_password.strip(), phone=q_phone.strip(), clean_type_id=CLEAN_TYPE_ID_MAP[q_clean_type])
            st.session_state.q_order_result = {}
        except Exception as e:
            st.error(f"查詢失敗：{e}")
            st.session_state.q_lookup = None
    lookup = st.session_state.get("q_lookup")
    if lookup is not None:
        member_payload = lookup.get("member_payload")
        st.markdown("<hr>", unsafe_allow_html=True)
        if not member_payload:
            st.warning("查無此會員，請填寫下方資料建立新客訂單。")
            st.markdown("**新客資料**")
            nc1, nc2, nc3 = st.columns(3)
            with nc1:
                nc_name = st.text_input("姓名", key="nc_name")
            with nc2:
                nc_email = st.text_input("Email", key="nc_email")
            with nc3:
                nc_tel = st.text_input("市內電話（選填）", key="nc_tel")
            nc_address = st.text_input("服務地址", key="nc_address")
            na1, na2, na3, na4 = st.columns(4)
            with na1:
                nc_date = st.date_input("服務日期", value=date.today() + timedelta(days=1), key="nc_date")
            with na2:
                nc_period = st.selectbox("時段", PERIOD_OPTIONS, key="nc_period")
            with na3:
                nc_person = st.number_input("人數", min_value=1, max_value=8, value=2, key="nc_person")
            with na4:
                nc_hour = PERIOD_HOUR_MAP.get(nc_period, 3)
                st.markdown(f"<br><b>{nc_hour} 小時</b>", unsafe_allow_html=True)
            nb1, nb2 = st.columns(2)
            with nb1:
                nc_payway = st.selectbox("付款方式", ["信用卡", "ATM"], key="nc_payway")
            with nb2:
                nc_invoice = st.selectbox("發票", ["會員載具（email）", "手機載具", "三聯式統編"], key="nc_invoice")
            nc_carrier = ""
            nc_company_title = ""
            nc_company_no = ""
            if nc_invoice == "手機載具":
                nc_carrier = st.text_input("手機條碼", placeholder="/ABC1234", key="nc_carrier")
            elif nc_invoice == "三聯式統編":
                nci1, nci2 = st.columns(2)
                with nci1:
                    nc_company_title = st.text_input("公司抬頭", key="nc_company_title")
                with nci2:
                    nc_company_no = st.text_input("統一編號", key="nc_company_no")
            nc_clean_type = st.selectbox("服務類別", list(CLEAN_TYPE_ID_MAP.keys()), key="nc_clean_type")
            nc_allow_auto_lemon = auto_lemon_checkbox("nc_allow_auto_lemon")
            if st.button("🚀 建立新客訂單", use_container_width=True, key="nc_create_btn"):
                # v8.15：開始新的一次建單嘗試前，先清空上一次殘留在畫面下方的舊結果，
                # 避免這次失敗時，舊的成功訊息還留在畫面上跟新的錯誤訊息重疊混淆。
                st.session_state.q_order_result = {}
                if not nc_name.strip() or not nc_email.strip() or not nc_address.strip():
                    st.error("請填寫姓名、Email、服務地址")
                elif not backend_email.strip() or not backend_password.strip():
                    st.error("請先輸入後台帳號密碼")
                else:
                    try:
                        with st.spinner("建立會員 → 查詢地址 → 建立訂單…"):
                            nc_result = qo.quick_create_new_customer_order(
                                env_name=env,
                                backend_email=backend_email.strip(),
                                backend_password=backend_password.strip(),
                                allow_auto_lemon_shift=nc_allow_auto_lemon,
                                customer={
                                    "name": nc_name.strip(),
                                    "phone": q_phone.strip(),
                                    "email": nc_email.strip(),
                                    "tel": nc_tel.strip(),
                                    "address": nc_address.strip(),
                                    "payway": nc_payway,
                                    "clean_type_id": CLEAN_TYPE_ID_MAP[nc_clean_type],
                                    "date_s": nc_date.strftime("%Y-%m-%d"),
                                    "period_s": nc_period,
                                    "hour": str(nc_hour),
                                    "person": str(int(nc_person)),
                                    "carrier": nc_carrier,
                                    "company_title": nc_company_title,
                                    "company_no": nc_company_no,
                                }
                            )
                            # 不立即發確認信，等 user 確認後再發
                            nc_result["mail_sent"] = False
                            nc_result["mail_msg"] = "尚未發送"
                        st.session_state.q_order_result = nc_result
                        if nc_result.get("lemon_assignment_ok") is False:
                            st.error(nc_result.get("lemon_assignment_warning") or "訂單已建立，但樸檬人置換失敗，請先處理班表。")
                            log_execution(
                                function_name="建立新客訂單", status="失敗",
                                date=nc_date.strftime("%Y-%m-%d"), target=nc_result.get("order_no", ""),
                                message=nc_result.get("lemon_assignment_warning") or "樸檬人置換失敗",
                            )
                        else:
                            st.success(f"✅ 訂單建立成功：{nc_result['order_no']}")
                            log_execution(
                                function_name="建立新客訂單", status="成功",
                                date=nc_date.strftime("%Y-%m-%d"), target=nc_result.get("order_no", ""),
                                message=f"姓名：{nc_name.strip()}",
                            )
                    except Exception as e:
                        st.error(f"建單失敗：{e}")
                        log_execution(
                            function_name="建立新客訂單", status="失敗",
                            date=nc_date.strftime("%Y-%m-%d"), target=nc_name.strip(),
                            message=str(e), traceback_text=traceback.format_exc(),
                        )
        else:
            member = member_payload.get("member", {})
            addr_list = member_payload.get("member", {}).get("memberAddressList", [])
            addr_options = [a.get("address", "") for a in addr_list if a.get("address")]
            st.markdown(f"**會員姓名：** {member.get('name', '')}　|　**會員電話：** {lookup.get('phone', '')}")
            step("3", "舊客服務資訊")
            info_panel("使用說明", ["先確認服務地址。", "確認服務類別、付款方式與區域。", "依客人狀況選擇『已知日期』或『依需求搜尋』。"])
            if not addr_options:
                # v2026.07.06 修正：原本會員沒有留存地址就直接擋下、要求改走
                # 新客建單，但後端（quick_create_order／quick_check_available_slots）
                # 現在已經支援舊客約新地址，這裡改成給一個文字輸入框讓客服直接輸入。
                st.warning("此會員沒有留存地址，請直接輸入本次服務的新地址。")
                q_address = st.text_input("服務地址（新地址）", key="old_address_new_only").strip()
                last_summary = None
            else:
                last_summary = get_last_paid_summary(lookup["session"], lookup["phone"], member_payload, addr_options)
                default_addr_index = addr_options.index(last_summary["address"]) if last_summary and last_summary.get("address") in addr_options else 0
                NEW_ADDRESS_OPTION = "➕ 輸入新地址（不在下面清單裡）"
                q_address_choice = st.selectbox(
                    "服務地址", addr_options + [NEW_ADDRESS_OPTION],
                    index=default_addr_index, key="old_address",
                )
                if q_address_choice == NEW_ADDRESS_OPTION:
                    # v2026.07.06 修正：原本這裡只能從會員既有地址清單挑選，
                    # 舊客要約沒約過的新地址完全沒有輸入管道，只能被迫走新客
                    # 建單流程。現在加一個「輸入新地址」選項，選了之後給文字
                    # 輸入框，讓客服直接打新地址，後端會用 geocode+查詢區域
                    # 的方式處理（跟新客建單新地址邏輯一致）。
                    q_address = st.text_input("新服務地址", key="old_address_new").strip()
                else:
                    q_address = q_address_choice
            if not q_address:
                st.info("請輸入或選擇服務地址。")
            elif True:
                if len(addr_options) > 1:
                    st.caption(f"⚠️ 此客人留存 {len(addr_options)} 個地址，請務必跟客人確認本次地點是否正確。")
                    per_addr_summary = get_last_paid_per_address(lookup["session"], lookup["phone"], member_payload, addr_options, within_days=365)
                    addr_rows = []
                    for addr in addr_options:
                        info = per_addr_summary.get(addr)
                        if not info:
                            addr_rows.append(f"・{addr}　——　近一年內查無已付款服務紀錄")
                        else:
                            ph_text = f"{info['person']}人{info['hour']}小時" if (info["person"] or info["hour"]) else "未知"
                            payment_text = payment_invoice_display(info.get("payway"), info.get("invoice_text"))
                            addr_rows.append(f"・{addr}　——　{info['date']} {info['time']}　類別：{info['clean_type'] or '未知'}　人時：{ph_text}　{payment_text}")
                    st.markdown('<div class="hint-box">📍 <b>各地址近一年內最近一次已付款服務</b>：<br>' + "<br>".join(addr_rows) + '</div>', unsafe_allow_html=True)
                default_clean_type = last_summary["clean_type"] if last_summary and last_summary.get("clean_type") in CLEAN_TYPE_ID_MAP else "居家清潔"
                default_person = int(last_summary["person"]) if last_summary and str(last_summary.get("person", "")).isdigit() else 2
                q_clean_type_confirm = st.selectbox("服務類別", list(CLEAN_TYPE_ID_MAP.keys()), index=list(CLEAN_TYPE_ID_MAP.keys()).index(default_clean_type), key="old_clean_confirm")
                # v8.63：付款方式混合選項改為「信用卡/ATM/儲值金」——維持上次付款方式
                # 選單顯示：信用卡/ATM/儲值金、信用卡、ATM、儲值金
                # 實際送單時一律解析成「信用卡」「ATM」或「儲值金」三者之一
                _payway_ui_options = ["信用卡/ATM/儲值金", "信用卡", "ATM", "儲值金"]
                _last_payway = last_summary.get("payway") if last_summary else ""
                _default_ui_payway = "信用卡/ATM/儲值金"
                _q_payway_ui = st.selectbox(
                    "付款方式",
                    _payway_ui_options,
                    index=_payway_ui_options.index(_default_ui_payway),
                    key="old_payway",
                )
                if _q_payway_ui == "信用卡/ATM/儲值金":
                    # 沿用上次付款方式；若查無可用紀錄，預設信用卡
                    q_payway = _last_payway if _last_payway in ("信用卡", "ATM", "儲值金") else "信用卡"
                    _payway_note = f"（沿用上次：{q_payway}）"
                else:
                    q_payway = _q_payway_ui
                    _payway_note = ""
                q_region = get_region_by_address(q_address, ACCOUNTS) or "台北"
                _route_label, _route_url = booking_route_display(q_payway)
                st.caption(f"建單介面：{_route_label}　｜　送單網址：{_route_url}　｜　實際付款方式：{q_payway}{_payway_note}　｜　區域：{q_region}")
                if last_summary:
                    st.markdown(last_summary_card_html(last_summary), unsafe_allow_html=True)

                # 舊客原本只能沿用歷史訂單的發票設定，無法在本次建單時修正。
                # 儲值金訂單本身不開立發票，因此只在信用卡／ATM 顯示此功能。
                q_invoice_mode = "沿用上次發票設定"
                q_invoice_carrier = ""
                q_invoice_company_title = ""
                q_invoice_company_no = ""
                if q_payway != "儲值金":
                    q_invoice_mode = st.selectbox(
                        "本次發票資訊",
                        ["沿用上次發票設定", "會員載具", "手機載具", "三聯式"],
                        key="old_invoice_mode",
                        help="選擇非「沿用上次」時，會以本次填寫資料覆蓋歷史發票設定。",
                    )
                    if q_invoice_mode == "手機載具":
                        q_invoice_carrier = st.text_input(
                            "手機載具條碼",
                            placeholder="/ABC1234",
                            key="old_invoice_carrier",
                        )
                    elif q_invoice_mode == "三聯式":
                        _old_inv_c1, _old_inv_c2 = st.columns(2)
                        with _old_inv_c1:
                            q_invoice_company_title = st.text_input(
                                "公司抬頭", key="old_invoice_company_title"
                            )
                        with _old_inv_c2:
                            q_invoice_company_no = st.text_input(
                                "統一編號", key="old_invoice_company_no"
                            )
                else:
                    st.caption("發票資訊：儲值金訂單不開立發票")

                upcoming_orders = get_unserved_paid_orders(lookup["session"], lookup["phone"], member_payload, addr_options, today_value=date.today())
                if upcoming_orders:
                    st.markdown('<div class="hint-box"><b>⚠️ 目前已付款但尚未服務訂單</b><br>請先確認客人是否要異動既有訂單，避免重複建單。</div>', unsafe_allow_html=True)
                    for idx, order in enumerate(upcoming_orders, start=1):
                        ph_text = person_hour_display(order.get("person"), order.get("hour"))
                        payment_text = payment_invoice_display(order.get("payway"), order.get("invoice_text"))
                        address_text = order.get("address") or "未能對應留存地址，請至後台確認"
                        staff_text = order.get("staff") or "待確認"
                        fare_text = f"｜車馬費：{order.get('fare')}" if nonzero_money(order.get("fare")) else ""
                        st.markdown(f'<div class="history-order"><div class="history-order-main">{idx}. {h(order.get("order_no"))}　{h(order.get("date"))} {h(order.get("time"), "")}</div><div class="history-order-meta"><div>地址：{h(address_text)}</div><div>類別：{h(order.get("clean_type"))}</div><div>服務人員：{h(staff_text)}</div><div>人時：{h(ph_text)}{h(fare_text, "")}</div><div>{h(payment_text)}</div></div></div>', unsafe_allow_html=True)
                date_mode = st.radio("日期/班表查詢方式", ["已知日期", "依需求搜尋可服務日期"], horizontal=True, key="old_date_mode")
                if date_mode == "已知日期":
                    info_panel("已知日期使用說明", ["客人已指定某一天時使用。", "此模式才需要選服務日期與時段。", "若客人只說平日、週末、不限或幾小時，請改選『依需求搜尋可服務日期』。", "同一個客人/地址要一次約多筆（例如每週固定服務），可以調整下面的「建立筆數」，各自設定日期/時段/人數。"])
                    old_n_orders = st.number_input("建立筆數", min_value=1, max_value=10, value=1, key="old_n_orders")
                    old_entries = []
                    for _i in range(int(old_n_orders)):
                        if int(old_n_orders) > 1:
                            st.markdown(f"**第 {_i + 1} 筆**")
                        d1, d2, d3, d4 = st.columns(4)
                        with d1:
                            _q_date = st.date_input("服務日期", value=date.today(), key=f"old_known_date_{_i}")
                        with d2:
                            _q_period = st.selectbox("時段", PERIOD_OPTIONS, key=f"old_known_period_{_i}")
                        with d3:
                            _q_person = st.number_input("人數", min_value=1, max_value=8, value=default_person, key=f"old_known_person_{_i}")
                        with d4:
                            _q_hour = PERIOD_HOUR_MAP.get(_q_period, 3)
                            st.markdown(f'<br><b>{_q_hour} 小時</b>（依時段自動帶出）<br><span style="color:#8E8E93;font-size:13px;">人時：{int(_q_person) * int(_q_hour)}</span>', unsafe_allow_html=True)
                        old_entries.append({"date": _q_date, "period": _q_period, "person": _q_person, "hour": _q_hour})
                    # v2026.07.07：多筆時沿用第一筆的設定去查班表預覽，實際各筆送單時
                    # 各自帶自己的日期/時段/人數；查班表這裡只是先讓客服有個底，
                    # 真正是否可排班仍以送單當下的實際結果為準。
                    q_date, q_period, q_person, q_hour = (
                        old_entries[0]["date"], old_entries[0]["period"],
                        old_entries[0]["person"], old_entries[0]["hour"],
                    )
                    if st.button("🔎 查詢該日班表", use_container_width=True, key="old_check_known"):
                        try:
                            with st.spinner("查詢班表中…"):
                                rows = quick_check_available_slots(env_name=env, payway=q_payway, lookup_result=lookup, address=q_address, clean_type_id=CLEAN_TYPE_ID_MAP[q_clean_type_confirm], date_s=q_date.strftime("%Y-%m-%d"), hour=q_hour, person=q_person, periods=[q_period], period_hours=PERIOD_HOUR_MAP)
                            st.session_state.old_known_slots = rows
                        except Exception as e:
                            st.session_state.old_known_slots = []
                            st.error(f"查詢班表失敗：{e}")
                    rows = st.session_state.get("old_known_slots")
                    if rows:
                        if any(r.get("available") for r in rows):
                            for r in rows:
                                st.success(f"{r.get('date')} {r.get('period')} 可安排　服務人員：{r.get('staff') or '待確認'}")
                        else:
                            st.warning("此日期/時段目前無可安排班表。")
                    old_allow_auto_lemon = auto_lemon_checkbox("old_allow_auto_lemon")
                    _old_create_label = "🚀 建立訂單" if int(old_n_orders) == 1 else f"🚀 建立 {int(old_n_orders)} 筆訂單"
                    if st.button(_old_create_label, use_container_width=True, key="old_create_known"):
                        # v8.15：開始新的一次建單嘗試前，先清空上一次殘留的舊結果。
                        st.session_state.q_order_result = {}
                        st.session_state.old_results_multi = []
                        _multi_results = []
                        try:
                            _old_invoice_kwargs = (
                                {}
                                if q_invoice_mode == "沿用上次發票設定"
                                else qo._invoice_payload(
                                    q_invoice_mode,
                                    member_email=member.get("email") or "",
                                    mobile_carrier=q_invoice_carrier,
                                    company_title=q_invoice_company_title,
                                    company_no=q_invoice_company_no,
                                )
                            )
                        except Exception as e:
                            st.error(f"發票資訊錯誤：{e}")
                            _old_invoice_kwargs = None
                        if _old_invoice_kwargs is None:
                            st.stop()
                        for _i, entry in enumerate(old_entries, start=1):
                            try:
                                with st.spinner(f"建單中（第 {_i}/{len(old_entries)} 筆），請稍候…"):
                                    result = quick_create_order(env_name=env, payway=q_payway, region=q_region, lookup_result=lookup, address=q_address, clean_type_id=CLEAN_TYPE_ID_MAP[q_clean_type_confirm], date_s=entry["date"].strftime("%Y-%m-%d"), period_s=entry["period"], hour=entry["hour"], person=entry["person"], allow_auto_lemon_shift=old_allow_auto_lemon, **_old_invoice_kwargs)
                                    # 不立即發確認信，等 user 確認後再發
                                    result["mail_sent"] = False
                                    result["mail_msg"] = "尚未發送"
                                    try:
                                        result["line_message"] = build_line_message(result)
                                    except Exception:
                                        result["line_message"] = ""
                                _multi_results.append({"ok": True, "result": result})
                                log_execution(
                                    function_name="建立舊客訂單", status="成功", area=q_region,
                                    date=entry["date"].strftime("%Y-%m-%d"), target=result.get("order_no", ""),
                                    message=f"地址：{q_address}",
                                )
                            except Exception as e:
                                _multi_results.append({"ok": False, "error": str(e), "date": entry["date"].strftime("%Y-%m-%d"), "period": entry["period"]})
                                log_execution(
                                    function_name="建立舊客訂單", status="失敗", area=q_region,
                                    date=entry["date"].strftime("%Y-%m-%d"), target=q_address,
                                    message=str(e), traceback_text=traceback.format_exc(),
                                )
                        st.session_state.old_results_multi = _multi_results
                        if len(_multi_results) == 1 and _multi_results[0]["ok"]:
                            # 只有 1 筆時，沿用原本單筆的詳細結果卡呈現方式
                            st.session_state.q_order_result = _multi_results[0]["result"]
                else:
                    info_panel("依需求搜尋使用說明", ["客人尚未指定日期時使用。", "可選平日 / 週末 / 不限，也可選上午 / 下午 / 不限。"])
                    a1, a2, a3, a4 = st.columns(4)
                    with a1:
                        day_type = st.selectbox("日期類型", ["平日", "週末", "不限"], key="old_day_type")
                    with a2:
                        time_pref = st.selectbox("時段偏好", ["上午", "下午", "不限"], key="old_time_pref")
                    with a3:
                        base_person = st.number_input("人數", min_value=1, max_value=8, value=2, key="old_search_person")
                    with a4:
                        base_hour = st.number_input("每人時數", min_value=2, max_value=8, value=4, key="old_search_hour")
                    search_days = st.slider("往後搜尋天數", min_value=7, max_value=60, value=30, step=1, key="old_search_days")
                    plans = build_equivalent_plans(base_person, base_hour)
                    total_ph = int(base_person) * int(base_hour)
                    st.caption(f"人時 = {int(base_person)} 人 × {int(base_hour)} 小時 = {total_ph} 人時")
                    st.caption("將查詢方案：" + "、".join([f"{p['person']}人{p['hour']}小時" for p in plans]))
                    if st.button("🔎 搜尋可服務日期", use_container_width=True, key="old_search_dates"):
                        try:
                            with st.spinner("搜尋可服務日期中…"):
                                rows = search_available_service_dates(env_name=env, payway=q_payway, lookup_result=lookup, address=q_address, clean_type_id=CLEAN_TYPE_ID_MAP[q_clean_type_confirm], start_date=date.today(), days=search_days, day_type=day_type, time_preference=time_pref, plans=plans, periods=PERIOD_OPTIONS, period_hours=PERIOD_HOUR_MAP)
                            st.session_state.old_search_results = rows
                        except Exception as e:
                            st.session_state.old_search_results = []
                            st.error(f"搜尋失敗：{e}")
                    rows = st.session_state.get("old_search_results")
                    if rows is not None:
                        if rows:
                            st.markdown("**可服務日期搜尋結果**")
                            for idx, r in enumerate(rows[:20]):
                                st.write(f"{idx+1}. 方案：{r['person']}人{r['hour']}小時　{r['date']} {r['period']}　服務人員：{r.get('staff') or '待確認'}")
                        else:
                            st.warning("目前依條件搜尋不到可服務日期，請放寬日期類型、時段偏好或延長搜尋天數。")

    old_results_multi = st.session_state.get("old_results_multi")
    if old_results_multi and not (len(old_results_multi) == 1 and old_results_multi[0]["ok"]):
        st.markdown("<hr>", unsafe_allow_html=True)
        step("5", "執行結果（多筆）")
        _ok_count = sum(1 for r in old_results_multi if r["ok"])
        st.info(f"共 {len(old_results_multi)} 筆，成功 {_ok_count} 筆，失敗 {len(old_results_multi) - _ok_count} 筆。")
        for _i, r in enumerate(old_results_multi, start=1):
            if r["ok"]:
                res = r["result"]
                st.success(f"✅ 第{_i}筆：{res['order_no']}　{res.get('date')} {res.get('period')}　專員：{res.get('staff') or '（無班表資料）'}")
                if res.get("address_mismatch_warning"):
                    st.warning(res["address_mismatch_warning"])
                if res.get("line_message"):
                    copy_button(f"複製第{_i}筆 LINE 訊息", res["line_message"], f"copy_old_multi_line_{_i}")
            else:
                st.error(f"❌ 第{_i}筆（{r.get('date')} {r.get('period')}）失敗：{r.get('error')}")

    order_result = st.session_state.get("q_order_result")
    if order_result:
        st.markdown("<hr>", unsafe_allow_html=True)
        step("5", "執行結果")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("訂單編號", order_result["order_no"])
        c2.metric("金額（含稅）", order_result.get("service_amount") or order_result.get("price_with_tax") or "—")
        c3.metric("車馬費", order_result.get("fare") or "0")
        c4.metric("確認信", "已發送" if order_result.get("mail_sent") else "未發送")
        _order_lemon_failed = order_result.get("lemon_assignment_ok") is False
        if _order_lemon_failed:
            st.error(order_result.get("lemon_assignment_warning") or "訂單已建立，但樸檬人置換失敗。")
        else:
            st.success(f"✅ 訂單建立成功：{order_result['order_no']}　👤 專員：{order_result.get('staff') or '（無班表資料）'}")
        if order_result.get("price_mismatch_warning"):
            st.warning(order_result["price_mismatch_warning"])
        if order_result.get("address_mismatch_warning"):
            st.warning(order_result["address_mismatch_warning"])
        if order_result.get("order_no_duplicated"):
            show_duplicate_order_warning(order_result.get("order_no"), order_result.get("order_no_duplicate_count", 2), dedup_key=f"old_{order_result.get('order_no')}")
        if _order_lemon_failed:
            st.warning("樸檬人置換完成前，不可發送確認信。")
        elif not order_result.get("mail_sent"):
            if st.button("📧 發送確認信", key="send_mail_btn", type="primary"):
                try:
                    ok_m, msg_m = send_confirmation(order_result)
                    if ok_m:
                        order_result["mail_sent"] = True
                        st.session_state.q_order_result = order_result
                        st.success("✅ 確認信已發送")
                        log_execution(
                            function_name="發送確認信", status="成功",
                            target=order_result.get("order_no", ""), message="舊客建單確認信",
                        )
                        st.rerun()
                    else:
                        st.error(f"確認信發送失敗：{msg_m}")
                        log_execution(
                            function_name="發送確認信", status="失敗",
                            target=order_result.get("order_no", ""), message=str(msg_m),
                        )
                except Exception as e:
                    st.error(f"確認信發送失敗：{e}")
                    log_execution(
                        function_name="發送確認信", status="失敗",
                        target=order_result.get("order_no", ""), message=str(e),
                        traceback_text=traceback.format_exc(),
                    )
        else:
            st.success("✅ 確認信已發送")
        line_message = build_line_message(order_result)
        col_msg, col_memo = st.columns([3, 1])
        with col_msg:
            st.text_area("LINE 訊息內容", line_message, height=420, label_visibility="collapsed")
            copy_button("複製 LINE 訊息", line_message, "copy-line-message")
        with col_memo:
            st.text_area("N-J Memo", NJ_MEMO, height=200, label_visibility="collapsed", key="nj_memo_order_result")


def render_new_customer(backend_email, backend_password, env):
    step("3", "建立新客訂單")
    info_panel("功能說明", [
        "貼上客人提供的完整資料（含姓名/電話/email/地址/坪數/付款/發票），",
        "填入服務日期與人時後按建單，系統自動拆解、建會員、建單，",
        "班表無人時自動勾檸檬人，完成後顯示訂單資訊與 LINE 訊息。",
    ])

    step("1", "貼上客人資料")
    nc_raw = st.text_area(
        "客人提供的資料（直接整段貼入）",
        height=200, key="nc_raw_input",
        placeholder="訂購人姓名：XXX\n訂購人電話：09XXXXXXXX\n訂購人Email：xxx@xxx.com\n服務地址：台北市...\n室內坪數：約25坪\n付款方式：信用卡\n發票載具：手機載具 /XXXXXXX",
    )

    # v8.12：不管有沒有「訂購人姓名：」等標籤都要能辨識欄位，貼上後即時拆解預覽。
    # 付款方式若判斷不出來，不可默默預設，直接請客服在這裡手動選擇。
    _nc_live_parsed = {}
    if nc_raw.strip():
        try:
            _nc_live_parsed = qo.parse_new_customer_text(nc_raw)
        except Exception:
            _nc_live_parsed = {}
    if _nc_live_parsed:
        _preview_bits = []
        if _nc_live_parsed.get("name"):
            _preview_bits.append(f"姓名：{_nc_live_parsed['name']}")
        if _nc_live_parsed.get("phone"):
            _preview_bits.append(f"電話：{_nc_live_parsed['phone']}")
        if _nc_live_parsed.get("address"):
            _preview_bits.append(f"地址：{_nc_live_parsed['address']}")
        if _preview_bits:
            st.caption("已辨識　" + "　".join(_preview_bits))
        if _nc_live_parsed.get("need_ask_payway"):
            st.warning("⚠️ 無法從貼上的資料中判斷付款方式，請手動選擇：")
            st.selectbox("付款方式（手動選擇）", ["信用卡", "ATM"], key="nc_payway_manual_select")
        elif _nc_live_parsed.get("payway"):
            st.caption(f"✅ 已偵測付款方式：{_nc_live_parsed['payway']}")

    step("2", "服務設定")
    sc1, sc2, sc3 = st.columns(3)
    with sc1:
        nc_clean_type = st.selectbox("服務類別", list(CLEAN_TYPE_ID_MAP.keys()), key="nc_clean_type_d")
    with sc2:
        nc_service_type = ""
        if nc_clean_type == "裝修細清":
            _stype_map = {"裝修細清": "1", "搬出清潔": "2", "搬入清潔": "3"}
            _stype_sel = st.selectbox("裝修類型", list(_stype_map.keys()), key="nc_stype_d")
            nc_service_type = _stype_map[_stype_sel]
    with sc3:
        pass

    # 清潔項目細節
    with st.expander("🏠 清潔項目細節（選填，用於計算時數）", expanded=False):
        _ci1, _ci2, _ci3, _ci4, _ci5, _ci6 = st.columns(6)
        with _ci1:
            nc_room = st.number_input("房間", min_value=0, value=0, key="nc_room_d")
        with _ci2:
            nc_bathroom = st.number_input("衛浴", min_value=0, value=0, key="nc_bathroom_d")
        with _ci3:
            nc_balcony = st.number_input("陽台", min_value=0, value=0, key="nc_balcony_d")
        with _ci4:
            nc_livingroom = st.number_input("客廳", min_value=0, value=0, key="nc_livingroom_d")
        with _ci5:
            nc_kitchen = st.number_input("廚房", min_value=0, value=0, key="nc_kitchen_d")
        with _ci6:
            nc_window = st.text_input("窗戶", value="", placeholder="數量", key="nc_window_d")
        _ci7, _ci8 = st.columns([1, 5])
        with _ci7:
            nc_shutter = st.text_input("百葉窗", value="", placeholder="數量", key="nc_shutter_d")
        st.markdown("**加購項目**")
        _bv1, _bv2, _bv3, _bv4, _bv5, _bv6, _bv7, _bv8, _bv9 = st.columns(9)
        with _bv1:
            nc_clothes = "1" if st.checkbox("衣物洗晾", key="nc_clothes_d") else "0"
        with _bv2:
            nc_dyson = "1" if st.checkbox("DYSON除蟎", key="nc_dyson_d") else "0"
        with _bv3:
            nc_refrigerator = "1" if st.checkbox("冰箱清理", key="nc_fridge_d") else "0"
        with _bv4:
            nc_disinfection = "1" if st.checkbox("簡易消毒", key="nc_disinfect_d") else "0"
        with _bv5:
            nc_go_abroad = "1" if st.checkbox("30日內出國", key="nc_abroad_d") else "0"
        with _bv6:
            nc_home_move = "1" if st.checkbox("搬家打包", key="nc_move_d") else "0"
        with _bv7:
            nc_storage = "1" if st.checkbox("收納整理", key="nc_storage_d") else "0"
        with _bv8:
            nc_cabinet = "1" if st.checkbox("櫥櫃清潔", key="nc_cabinet_d") else "0"
        with _bv9:
            nc_quintuple = "1" if st.checkbox("五倍券", key="nc_quintuple_d") else "0"

    step("3", "日期與人時")
    nc_n_orders = st.number_input("建立筆數", min_value=1, max_value=10, value=1, key="nc_n_orders_d")
    nc_entries = []
    for _i in range(int(nc_n_orders)):
        if int(nc_n_orders) > 1:
            st.markdown(f"**第 {_i + 1} 筆**")
        sd1, sd2, sd3, sd4 = st.columns(4)
        with sd1:
            _nc_date = st.date_input("服務日期", value=date.today() + timedelta(days=1), key=f"nc_date_d_{_i}")
        with sd2:
            _nc_period = st.selectbox("時段", PERIOD_OPTIONS, key=f"nc_period_d_{_i}")
        with sd3:
            _nc_person = st.number_input("人數", min_value=1, max_value=8, value=2, key=f"nc_person_d_{_i}")
        with sd4:
            _nc_hour = PERIOD_HOUR_MAP.get(_nc_period, 3)
            _day_type_nc = "週末" if _nc_date.weekday() >= 5 else "平日"
            _unit_nc = 700 if _day_type_nc == "週末" else 600
            _total_nc = int(_nc_person) * _nc_hour * _unit_nc
            st.markdown(f"**{_nc_hour}小時 / {_day_type_nc}**")
            st.markdown(f"預估：**{_total_nc:,}元**")
        nc_entries.append({"date": _nc_date, "period": _nc_period, "person": _nc_person, "hour": _nc_hour})
    # 沿用第一筆設定作為備註/發票等共用欄位的預設情境（人時試算已在上面各自顯示）
    nc_date, nc_period, nc_person, nc_hour = (
        nc_entries[0]["date"], nc_entries[0]["period"], nc_entries[0]["person"], nc_entries[0]["hour"],
    )

    step("4", "備註欄位（選填）")
    nb1, nb2, nb3 = st.columns(3)
    with nb1:
        nc_actual_time = st.text_input("簡訊實際服務時間", placeholder="例：09:00-12:00", key="nc_actual_time_d")
    with nb2:
        nc_memo = st.text_area("客人備註", height=80, key="nc_memo_d")
    with nb3:
        nc_notice = st.text_area("客服備註", height=80, key="nc_notice_d")

    nc_d_allow_auto_lemon = auto_lemon_checkbox("nc_d_allow_auto_lemon")

    if st.button("🚀 建立新客訂單", use_container_width=True, key="nc_create_d", type="primary"):
        # v8.15：開始新的一次建單嘗試前，先清空上一次殘留在畫面下方的舊結果
        # （包含成功訊息、LINE 訊息），避免這次失敗/拆解失敗時，
        # 舊的成功結果還留在畫面上跟新的錯誤訊息重疊混淆。
        st.session_state.nc_result = {}
        st.session_state.nc_results_multi = []
        st.session_state.nc_pending_old = None
        if not nc_raw.strip():
            st.error("請貼上客人資料")
        elif not backend_email.strip() or not backend_password.strip():
            st.error("請先在上方輸入後台帳號密碼")
        else:
            # 拆解客人資料
            try:
                _parsed = qo.parse_new_customer_text(nc_raw)
            except Exception:
                _parsed = {}
            _nc_name = _parsed.get("name", "")
            _nc_phone = _parsed.get("phone", "")
            _nc_email = _parsed.get("email", "")
            _nc_address = _parsed.get("address", "")
            _nc_ping = _parsed.get("ping", "4")
            # v8.12：付款方式偵測不到時，改用上方手動選擇的值；兩者皆無則擋下建單，
            # 不可默默預設成信用卡。
            _nc_payway = _parsed.get("payway", "") or st.session_state.get("nc_payway_manual_select", "")
            _nc_carrier = _parsed.get("carrier", "")
            _nc_company_title = _parsed.get("company_title", "")
            _nc_company_no = _parsed.get("company_no", "")

            _missing = [k for k, v in [("姓名", _nc_name), ("電話", _nc_phone), ("Email", _nc_email), ("地址", _nc_address)] if not v.strip()]
            if not _nc_payway:
                st.error("無法判斷付款方式，請於上方「付款方式（手動選擇）」選單選擇信用卡或ATM後再建單。")
            elif _missing:
                st.error(f"資料拆解失敗，請確認以下欄位：{'、'.join(_missing)}\n\n拆解結果：{_parsed}")
            else:
                # v2026.07.07：送出前先查這支電話是不是既有會員，不再需要另外手動查詢。
                # 是既有會員的話，不繼續走新客建立流程（避免漏看歷史訂單/地址），
                # 改成把已收集到的電話/地址/人時/付款/發票資訊存起來，讓客服按下面
                # 的按鈕直接用舊客身份送出這筆預約。
                try:
                    with st.spinner("查詢電話是否為既有會員…"):
                        _nc_lookup = qo.quick_lookup_member(
                            env_name=env, backend_email=backend_email.strip(),
                            backend_password=backend_password.strip(),
                            phone=_nc_phone.strip(),
                            clean_type_id=CLEAN_TYPE_ID_MAP[nc_clean_type],
                        )
                except Exception as e:
                    st.error(f"查詢會員失敗：{e}")
                    _nc_lookup = None

                if _nc_lookup is not None and _nc_lookup.get("member_payload"):
                    _m_existing = _nc_lookup["member_payload"].get("member", {})
                    _addrs_existing = [a.get("address", "") for a in _nc_lookup["member_payload"].get("member", {}).get("memberAddressList", []) if a.get("address")]
                    st.session_state.nc_pending_old = {
                        "lookup": _nc_lookup,
                        "member_name": _m_existing.get("name", ""),
                        "existing_addresses": _addrs_existing,
                        "phone": _nc_phone.strip(),
                        "address": _nc_address.strip(),
                        "clean_type_id": CLEAN_TYPE_ID_MAP[nc_clean_type],
                        "date_s": nc_date.strftime("%Y-%m-%d"),
                        "period_s": nc_period,
                        "hour": str(nc_hour),
                        "person": str(int(nc_person)),
                        "payway": _nc_payway,
                        "carrier": _nc_carrier,
                        "company_title": _nc_company_title,
                        "company_no": _nc_company_no,
                        "member_email": _m_existing.get("email", ""),
                        "allow_auto_lemon_shift": nc_d_allow_auto_lemon,
                    }
                    st.rerun()
                elif _nc_lookup is not None:
                    try:
                        st.session_state.nc_results_multi = []
                        _nc_multi_results = []
                        for _ei, _entry in enumerate(nc_entries, start=1):
                            with st.spinner(f"建立會員 → 查詢地址 → 建單（第 {_ei}/{len(nc_entries)} 筆：{_entry['date']} {_entry['period']} {_entry['person']}人{_entry['hour']}小時）…"):
                                try:
                                    nc_result = qo.quick_create_new_customer_order(
                                        env_name=env,
                                        backend_email=backend_email.strip(),
                                        backend_password=backend_password.strip(),
                                        allow_auto_lemon_shift=nc_d_allow_auto_lemon,
                                        customer={
                                            "name": _nc_name, "phone": _nc_phone,
                                            "email": _nc_email, "address": _nc_address,
                                            "ping": _nc_ping, "payway": _nc_payway,
                                            "clean_type_id": CLEAN_TYPE_ID_MAP[nc_clean_type],
                                            "service_type": nc_service_type,
                                            "room": str(nc_room), "bathroom": str(nc_bathroom),
                                            "balcony": str(nc_balcony), "livingroom": str(nc_livingroom),
                                            "kitchen": str(nc_kitchen), "window": nc_window,
                                            "shutter": nc_shutter, "clothes": nc_clothes,
                                            "dyson": nc_dyson, "refrigerator": nc_refrigerator,
                                            "disinfection": nc_disinfection, "go_abord": nc_go_abroad,
                                            "home_move": nc_home_move, "storage": nc_storage,
                                            "cabinet": nc_cabinet, "quintuple": nc_quintuple,
                                            "date_s": _entry["date"].strftime("%Y-%m-%d"),
                                            "period_s": _entry["period"],
                                            "hour": str(_entry["hour"]),
                                            "person": str(int(_entry["person"])),
                                            "carrier": _nc_carrier,
                                            "company_title": _nc_company_title,
                                            "company_no": _nc_company_no,
                                            "memo": nc_memo,
                                            "notice": nc_notice,
                                            "actual_time": nc_actual_time,
                                        }
                                    )
                                    # 不立即發確認信，等 user 確認後再發
                                    nc_result["mail_sent"] = False
                                    nc_result["mail_msg"] = "尚未發送"
                                    # v8.6：quick_create_new_customer_order 已回傳 build_line_message
                                    # 所需的完整欄位（date/period/region/fare 等），這裡直接組出 LINE 訊息，
                                    # 修正原本此流程從未產生 line_message、畫面永遠不顯示的問題。
                                    try:
                                        nc_result["line_message"] = build_line_message(nc_result)
                                    except Exception:
                                        nc_result["line_message"] = ""
                                    _nc_multi_results.append({"ok": True, "result": nc_result})
                                    log_execution(
                                        function_name="建立新客訂單", status="成功",
                                        date=_entry["date"].strftime("%Y-%m-%d"), target=nc_result.get("order_no", ""),
                                        message=f"姓名：{_nc_name}　地址：{_nc_address}",
                                    )
                                except Exception as _e_entry:
                                    _nc_multi_results.append({"ok": False, "error": str(_e_entry), "date": _entry["date"].strftime("%Y-%m-%d"), "period": _entry["period"]})
                                    log_execution(
                                        function_name="建立新客訂單", status="失敗",
                                        date=_entry["date"].strftime("%Y-%m-%d"), target=_nc_name,
                                        message=str(_e_entry), traceback_text=traceback.format_exc(),
                                    )
                        st.session_state.nc_results_multi = _nc_multi_results
                        if len(_nc_multi_results) == 1 and _nc_multi_results[0]["ok"]:
                            # 只有 1 筆時，沿用原本單筆的詳細結果卡呈現方式
                            st.session_state.nc_result = _nc_multi_results[0]["result"]
                        st.rerun()
                    except Exception as e:
                        st.error(f"建單失敗：{e}")
                        log_execution(
                            function_name="建立新客訂單", status="失敗",
                            date=nc_date.strftime("%Y-%m-%d"), target=_nc_name,
                            message=str(e), traceback_text=traceback.format_exc(),
                        )

    # v2026.07.07：查到既有會員時，顯示在「建立新客訂單」按鈕下方，
    # 提供一個按鈕直接改用舊客身份、帶著已收集的電話/地址/人時/付款/
    # 發票資訊送出這筆預約，不用客服重新輸入一次。
    _nc_pending = st.session_state.get("nc_pending_old")
    if _nc_pending:
        st.warning(
            f"⚠️ 這支電話（{_nc_pending['phone']}）其實已經是舊客會員"
            f"（姓名：{_nc_pending['member_name']}），不是新客！"
            + (f" 既有地址：{'、'.join(_nc_pending['existing_addresses'])}" if _nc_pending['existing_addresses'] else "")
        )
        if st.button("➡️ 用舊客身份送出此預約", use_container_width=True, key="nc_to_old_submit_btn", type="primary"):
            try:
                with st.spinner("以舊客身份建立訂單…"):
                    _invoice = qo._invoice_payload(
                        "三聯式" if (_nc_pending["company_title"] and _nc_pending["company_no"]) else ("手機載具" if _nc_pending["carrier"] else "會員載具"),
                        member_email=_nc_pending["member_email"] or "",
                        mobile_carrier=_nc_pending["carrier"],
                        company_title=_nc_pending["company_title"],
                        company_no=_nc_pending["company_no"],
                    )
                    _region_pending = get_region_by_address(_nc_pending["address"], ACCOUNTS) or "台北"
                    old_result = qo.quick_create_order(
                        env_name=env, payway=_nc_pending["payway"], region=_region_pending,
                        lookup_result=_nc_pending["lookup"], address=_nc_pending["address"],
                        clean_type_id=_nc_pending["clean_type_id"],
                        date_s=_nc_pending["date_s"], period_s=_nc_pending["period_s"],
                        hour=_nc_pending["hour"], person=_nc_pending["person"],
                        carrier_info=_invoice["carrier_info"], company_no=_invoice["company_no"],
                        company_title=_invoice["company_title"],
                        invoice_type_override=_invoice["invoice_type_override"],
                        carrier_type_id_override=_invoice["carrier_type_id_override"],
                        allow_auto_lemon_shift=_nc_pending["allow_auto_lemon_shift"],
                    )
                    old_result["mail_sent"] = False
                    try:
                        old_result["line_message"] = build_line_message(old_result)
                    except Exception as _e_line_old:
                        old_result["line_message"] = ""
                st.session_state.nc_result = old_result
                st.session_state.nc_pending_old = None
                log_execution(
                    function_name="建立舊客訂單", status="成功", area=_region_pending,
                    date=_nc_pending["date_s"], target=old_result.get("order_no", ""),
                    message=f"地址：{_nc_pending['address']}",
                )
                st.rerun()
            except Exception as e:
                st.error(f"以舊客身份建單失敗：{e}")
                log_execution(
                    function_name="建立舊客訂單", status="失敗",
                    date=_nc_pending.get("date_s", ""), target=_nc_pending.get("address", ""),
                    message=str(e), traceback_text=traceback.format_exc(),
                )

    # v2026.07.07：多筆訂單結果顯示（建立筆數 > 1，或有任何一筆失敗時）
    _nc_multi = st.session_state.get("nc_results_multi") or []
    if _nc_multi and not (len(_nc_multi) == 1 and _nc_multi[0]["ok"]):
        st.markdown("<hr>", unsafe_allow_html=True)
        _nc_ok_count = sum(1 for r in _nc_multi if r["ok"])
        st.info(f"共 {len(_nc_multi)} 筆，成功 {_nc_ok_count} 筆，失敗 {len(_nc_multi) - _nc_ok_count} 筆。")
        for _i, r in enumerate(_nc_multi, start=1):
            if r["ok"]:
                res = r["result"]
                if res.get("lemon_assignment_ok") is False:
                    st.error(f"⚠️ 第{_i}筆訂單已建立：{res.get('order_no')}，{res.get('lemon_assignment_warning') or '樸檬人置換失敗'}")
                else:
                    st.success(f"✅ 第{_i}筆：{res.get('order_no')}　{res.get('date_s')} {res.get('period_s')}")
                if res.get("existing_member_warning"):
                    st.warning(res["existing_member_warning"])
                if res.get("address_mismatch_warning"):
                    st.warning(res["address_mismatch_warning"])
                if res.get("line_message"):
                    copy_button(f"複製第{_i}筆 LINE 訊息", res["line_message"], f"copy_nc_multi_line_{_i}")
            else:
                st.error(f"❌ 第{_i}筆（{r.get('date')} {r.get('period')}）失敗：{r.get('error')}")

    # 顯示建單結果
    _r = st.session_state.get("nc_result", {})
    if _r.get("order_no"):
        _lemon_failed = _r.get("lemon_assignment_ok") is False
        _result_msg = (
            f"訂單：{_r['order_no']}　{_r.get('date_s')} {_r.get('period_s')}　"
            f"{_r.get('person')}人{_r.get('hour')}小時　{_r.get('price_with_tax', 0):,}元　"
            f"👤 專員：{_r.get('staff') or '（無班表資料）'}"
        )
        if _lemon_failed:
            st.error(f"⚠️ {_result_msg}\n\n{_r.get('lemon_assignment_warning') or '樸檬人置換失敗'}")
        else:
            st.success(f"✅ {_result_msg}")
        if _r.get("price_mismatch_warning"):
            st.warning(_r["price_mismatch_warning"])
        if _r.get("address_mismatch_warning"):
            st.warning(_r["address_mismatch_warning"])
        if _r.get("existing_member_warning"):
            st.warning(_r["existing_member_warning"])
        if _r.get("order_no_duplicated"):
            show_duplicate_order_warning(_r.get("order_no"), _r.get("order_no_duplicate_count", 2), dedup_key=f"nc_{_r.get('order_no')}")
        if _lemon_failed:
            st.warning("樸檬人置換完成前，不可發送確認信。")
        elif not _r.get("mail_sent"):
            if st.button("📧 發送確認信", key="nc_send_mail_btn", type="primary"):
                try:
                    ok_m2, msg_m2 = send_confirmation(_r)
                    if ok_m2:
                        _r["mail_sent"] = True
                        st.session_state.nc_result = _r
                        st.success("✅ 確認信已發送")
                        log_execution(
                            function_name="發送確認信", status="成功",
                            target=_r.get("order_no", ""), message="新客建單確認信",
                        )
                        st.rerun()
                    else:
                        st.error(f"確認信發送失敗：{msg_m2}")
                        log_execution(
                            function_name="發送確認信", status="失敗",
                            target=_r.get("order_no", ""), message=str(msg_m2),
                        )
                except Exception as e:
                    st.error(f"確認信發送失敗：{e}")
                    log_execution(
                        function_name="發送確認信", status="失敗",
                        target=_r.get("order_no", ""), message=str(e),
                        traceback_text=traceback.format_exc(),
                    )
        else:
            st.success("✅ 確認信已發送")
        if _r.get("line_message"):
            col_nc_msg, col_nc_memo = st.columns([3, 1])
            with col_nc_msg:
                # v8.17：拿掉固定 key——帶 key 的 st.text_area 一旦畫過一次，
                # 之後即使傳入新的 value 也不會更新畫面，只會顯示 session_state
                # 裡的舊內容，導致新訂單成立後 LINE 訊息還停留在上一張訂單。
                st.text_area("LINE 訊息", _r["line_message"], height=320, label_visibility="collapsed")
                copy_button("複製 LINE 訊息", _r["line_message"], "copy_nc_line_d")
            with col_nc_memo:
                st.text_area("N-J Memo", NJ_MEMO, height=200, label_visibility="collapsed", key="nj_memo_nc_result")
                copy_button("複製 N-J Memo", NJ_MEMO, "copy-nj-memo-nc-result")


def render_order_conversion(backend_email, backend_password, env):
    step("3", "訂單轉換")
    info_panel(
        "流程說明",
        [
            "此功能拆成兩段：先修改原訂單A的日期並使用既有班表換成檸檬人，再建立新訂單（優惠券折抵原訂單金額）。",
            "舊單A與新單B均可勾選安全自動補檸檬人；已有任何班別的專員一律跳過，不動其他客人已配班專員。",
            "第二段：逐筆新訂單建立折價券，所有新單券額加總必須等於原訂單A服務金額；若新單金額超過原單，超出部分保留為應付差額。",
            "備註自動寫入：A+B1+B2+B3 合併服務。",
        ],
    )

    step("4", "第一段：原訂單A 改日期＋全部換檸檬人")
    col_a1, col_a2, col_a3 = st.columns(3)
    with col_a1:
        conv_order_no_a = st.text_input("原訂單A編號", placeholder="LC002115551", key="conv_order_no_a")
    with col_a2:
        conv_clean_type = st.selectbox("服務類別", list(CLEAN_TYPE_ID_MAP.keys()), key="conv_clean_type")
    with col_a3:
        conv_target_date = st.date_input("原訂單A要改到的新日期", value=date.today() + timedelta(days=1), key="conv_target_date")
    conv_stage1_allow_lemon = True
    st.caption("原訂單 A 固定全部換成檸檬人；不足時系統會自動補檸檬人班表。")

    if st.button("① 修改原訂單日期並全部換成檸檬人", use_container_width=True, key="conv_stage1_btn"):
        # 開始新的一次轉換前，先清空上一次殘留的舊結果（含第二、三段）。
        st.session_state.conv_stage1 = {}
        st.session_state.conv_stage2 = {}
        if not backend_email.strip() or not backend_password.strip():
            st.error("請先輸入後台帳號密碼")
        elif not conv_order_no_a.strip():
            st.error("請輸入原訂單A編號")
        else:
            try:
                with st.spinner("第一段執行中：查原訂單A → 改日期 → 用既有班表換成檸檬人…"):
                    stage1 = convert_order_stage1_reassign_original(
                        env_name=env,
                        backend_email=backend_email.strip(),
                        backend_password=backend_password.strip(),
                        order_no_a=conv_order_no_a.strip(),
                        target_date_s=conv_target_date.strftime("%Y-%m-%d"),
                        clean_type_id=CLEAN_TYPE_ID_MAP[conv_clean_type],
                        allow_auto_lemon_shift=conv_stage1_allow_lemon,
                    )
                st.session_state.conv_stage1 = stage1
                st.session_state.conv_stage2 = {}
                log_execution(
                    function_name="訂單轉換（第一段：改日期換檸檬人）", status="成功",
                    date=conv_target_date.strftime("%Y-%m-%d"), target=conv_order_no_a.strip(),
                    message="原訂單A改日期並全部換成檸檬人",
                )
            except Exception as e:
                st.session_state.conv_stage1 = {}
                st.error(f"第一段執行失敗：{e}")
                log_execution(
                    function_name="訂單轉換（第一段：改日期換檸檬人）", status="失敗",
                    date=conv_target_date.strftime("%Y-%m-%d"), target=conv_order_no_a.strip(),
                    message=str(e), traceback_text=traceback.format_exc(),
                )

    conv_stage1 = st.session_state.get("conv_stage1")
    if conv_stage1:
        lr_a = conv_stage1.get("lemon_result_a", {}) or {}
        lemon_names = lr_a.get("assigned", [])
        actual_count = int(lr_a.get("actual_person_count", 0) or len(lemon_names) or conv_stage1.get("person_a", 0) or 0)
        new_svc_date = lr_a.get("new_service_date", "")
        date_ok = lr_a.get("date_change_ok", True)
        orig_date = conv_stage1.get("service_date_a", "")
        period_a = str(conv_stage1.get("period_a_raw", "")).replace(" ", "")

        if date_ok and new_svc_date:
            date_str = f"{orig_date} → {new_svc_date}"
        elif not date_ok:
            date_str = f"❌ 日期修改失敗，請手動改為 {new_svc_date}"
        else:
            date_str = orig_date

        if lr_a.get("success") and lemon_names:
            lemon_str = "X".join(lemon_names)
            st.success(
                f"✅ 第一段完成：原訂單 {conv_stage1['order_no_a']} 服務日期 {date_str} {period_a}，"
                f"{lemon_str}，{actual_count}人，全部為檸檬人"
            )
        else:
            st.warning(f"⚠️ 第一段：原訂單配班未完全成功 — {lr_a.get('message', '未知')}，請至後台確認排班狀況。")
        with st.expander("🔗 原訂單A後台連結", expanded=False):
            st.markdown(f"[開啟原訂單A後台]({conv_stage1.get('base_url', '')}/purchase?orderNo={conv_stage1['order_no_a']})")

    st.markdown("<hr>", unsafe_allow_html=True)
    step("5", "第二段：建立新訂單（優惠券折抵）")

    if not conv_stage1:
        st.info("請先完成第一段，才能建立新訂單。")
    else:
        conv_order_count = st.number_input("新訂單筆數", min_value=1, max_value=6, value=2, step=1, key="conv_order_count")
        st.markdown('<div class="hint-box">💡 每筆新訂單各自選日期、時段、人數。時數由時段自動帶出。折價券會依序折抵原訂單A服務金額；新單超過原單時，超出部分會留在新單應付。</div>', unsafe_allow_html=True)

        new_orders_input = []
        for i in range(int(conv_order_count)):
            st.markdown(f"**新訂單 B{i+1}**")
            b1, b2, b3, b4 = st.columns(4)
            with b1:
                b_date = st.date_input(f"B{i+1} 日期", value=date.today() + timedelta(days=1), key=f"conv_date_{i}")
            with b2:
                b_period = st.selectbox(f"B{i+1} 時段", PERIOD_OPTIONS, key=f"conv_period_{i}")
            with b3:
                b_person = st.number_input(f"B{i+1} 人數", min_value=1, max_value=8, value=2, key=f"conv_person_{i}")
            with b4:
                b_hour = PERIOD_HOUR_MAP.get(b_period, 4)
                st.markdown(f"<br><b>{b_hour} 小時</b>（依時段帶出）", unsafe_allow_html=True)
            b_allow_lemon = st.checkbox(
                f"B{i+1} 若無人力，自動補檸檬人（不動其他客人已配班專員）",
                value=False, key=f"conv_allow_lemon_{i}",
            )
            new_orders_input.append({
                "date_s": b_date.strftime("%Y-%m-%d"),
                "period_s": b_period,
                "hour": b_hour,
                "person": int(b_person),
                "allow_lemon": bool(b_allow_lemon),
            })

        _conv_stage1_result = conv_stage1.get("lemon_result_a", {}) or {}
        _conv_stage1_ready = bool(
            _conv_stage1_result.get("success")
            and _conv_stage1_result.get("date_change_ok", True)
        )
        if not _conv_stage1_ready:
            st.error("原訂單A還沒有用既有班表完成配班，已鎖定第二段；請先由人工處理班表。")

        if st.button("② 建立新訂單（優惠券折抵）", use_container_width=True, key="conv_stage2_btn", disabled=not _conv_stage1_ready):
            st.session_state.conv_stage2 = {}
            try:
                with st.spinner("第二段執行中：建折價券 → 建新訂單 → 標記已付款 → 標註發票…"):
                    stage2 = convert_order_stage2_create_new_orders(conv_stage1, new_orders_input)
                st.session_state.conv_stage2 = stage2
                _conv_ok_nos = [r.get("order_no", "") for r in stage2.get("new_order_results", []) if r.get("order_no")]
                log_execution(
                    function_name="訂單轉換（第二段：建新訂單折抵）", status="成功",
                    target=conv_order_no_a.strip(),
                    message=f"新訂單：{'、'.join(_conv_ok_nos) or '（無）'}",
                )
            except Exception as e:
                st.session_state.conv_stage2 = {}
                st.error(f"第二段執行失敗：{e}")
                log_execution(
                    function_name="訂單轉換（第二段：建新訂單折抵）", status="失敗",
                    target=conv_order_no_a.strip(),
                    message=str(e), traceback_text=traceback.format_exc(),
                )

    conv_stage2 = st.session_state.get("conv_stage2")
    if conv_stage2:
        new_orders_ok = [r for r in conv_stage2.get("new_order_results", []) if r.get("order_no")]

        for r in new_orders_ok:
            ph_str = f"{r['person']}人{r['hour']}小時"
            _r_order_result = r.get("order_result") or {}
            _coupon_discount = int(r.get("coupon_discount", r.get("price_with_tax", 0)) or 0)
            _customer_due = int(r.get("customer_due", max(int(r.get("price_with_tax", 0) or 0) - _coupon_discount, 0)) or 0)
            _coupon_text = f"折價券 {r['coupon_code']}（折{_coupon_discount}元）" if r.get("coupon_code") else "未建立折價券"
            st.success(
                f"✅ 第二段：新訂單 {r['order_no']}，{r['date_s']} {r['period_s']} {ph_str}，"
                f"{_coupon_text}，應付{_customer_due}元　"
                f"👤 專員：{_r_order_result.get('staff') or '（無班表資料）'}"
            )
            if r.get("mark_paid_ok") is True:
                st.caption(f"✅ {r['order_no']} 已標記為已付款")
            elif r.get("mark_paid_ok") is None:
                st.caption(f"ℹ️ {r['order_no']} {r.get('mark_paid_msg', '未自動標記已付款')}")
            else:
                st.warning(f"⚠️ {r['order_no']} 標記已付款失敗：{r.get('mark_paid_msg', '')}")
            if r.get("invoice_note_ok"):
                st.caption(f"✅ {r['order_no']} 發票號碼欄位已標註「不開立發票」")
            else:
                st.warning(f"⚠️ {r['order_no']} 發票欄位標註失敗，請至後台手動填寫「不開立發票」：{r.get('invoice_note_msg', '')}")
            if _r_order_result.get("order_no_duplicated"):
                show_duplicate_order_warning(
                    r.get("order_no"), _r_order_result.get("order_no_duplicate_count", 2),
                    dedup_key=f"conv_{r.get('order_no')}",
                )
        for r in [r for r in conv_stage2.get("new_order_results", []) if r.get("error")]:
            st.error(f"❌ 第二段 B{r['index']}（{r['date_s']} {r['period_s']}）失敗：{r['error']}")

        with st.expander("🔍 細項", expanded=False):
            st.markdown(f"[🔗 開啟原訂單A後台]({conv_stage2['purchase_url_a']})")

            st.markdown("**備註文字**")
            note_a_status = "✅ 已自動寫入" if conv_stage2.get("note_a_ok") else f"⚠️ 需手動貼上（{conv_stage2.get('note_a_msg', '')}）"
            st.markdown(f"原訂單A備註 {note_a_status}")
            st.text_area("原訂單A備註", conv_stage2.get("note_a", ""), height=70, label_visibility="collapsed", key="conv_note_a_out")
            copy_button("複製原訂單A備註", conv_stage2.get("note_a", ""), "copy_note_a")
            st.caption(f"全單備註：{conv_stage2.get('note', '')}")

        st.markdown("<hr>", unsafe_allow_html=True)
        step("6", "第三階段：比對原訂單與新訂單金額差額")
        _orig_amount = conv_stage2.get("service_amount_a_display", 0)
        _new_amount = conv_stage2.get("new_amount_total", 0)
        _new_amt_detail = "＋".join(f"{r['price_with_tax']}元" for r in new_orders_ok) if new_orders_ok else "0元"
        if conv_stage2.get("ph_warning"):
            st.warning(conv_stage2["ph_warning"])
        elif _orig_amount:
            st.success(f"✅ 金額比對：原訂單A {_orig_amount}元 ＝ 新訂單合計 {_new_amt_detail} = {_new_amount}元")
        else:
            st.warning(f"⚠️ 金額比對：原訂單A金額解析失敗，無法自動比較，新訂單合計 {_new_amt_detail} = {_new_amount}元，請手動核對。")

        # 2026-07-08：先顯示第三階段金額比對，再顯示 LINE 訊息。
        combined_msg = conv_stage2.get("combined_line_message", "")
        if combined_msg:
            st.markdown("#### 💬 合併 LINE 訊息（全部新訂單）")
            st.text_area("合併 LINE 訊息", combined_msg, height=380, label_visibility="collapsed")
            copy_button("複製合併 LINE 訊息", combined_msg, "copy_conv_combined_line")
        else:
            st.markdown("#### 💬 新訂單 LINE 訊息")
            for r in new_orders_ok:
                if r.get("line_message"):
                    st.text_area(f"B{r['index']} LINE（{r['order_no']}）", r["line_message"], height=320, label_visibility="collapsed")
                    copy_button(f"複製 B{r['index']} LINE 訊息", r["line_message"], f"copy_conv_line_{r['index']}")


def render_topup_diff(backend_email, backend_password, env):
    step("3", "儲值金補價差")
    info_panel("流程說明", [
        "此功能拆成兩段：先成立儲值金折抵單，再成立客付補價差訂單。",
        "兩段都可勾選安全自動補檸檬人；已有任何班別的專員一律跳過，不動其他客人已配班專員。",
        "日期類型由服務日期自動判斷：週一到週五為平日，週六日為週末。",
        "儲值金清零單走 /booking/stored_value_routine，優惠券A = 服務總額 - 儲值金餘額；剩餘額用儲值金扣掉後歸零。",
        "補差價訂單走 /booking/single，優惠券B = 原儲值金餘額，付款方式限 ATM / 信用卡。",
    ])
    step("4", "客人與服務資料")
    sv1, sv2, sv3 = st.columns(3)
    with sv1:
        sv_phone = st.text_input("客人手機號碼", key="sv_auto_phone")
    with sv2:
        sv_ctype = st.selectbox("服務類別", list(CLEAN_TYPE_ID_MAP.keys()), key="sv_auto_ctype")
    with sv3:
        sv_svc_date = st.date_input("服務日期", value=date.today() + timedelta(days=7), key="sv_auto_date")
        sv_day_type_auto = "週末" if sv_svc_date.weekday() >= 5 else "平日"
        st.caption(f"日期類型：{sv_day_type_auto}（自動判斷）")
    sd1, sd2, sd3, sd4 = st.columns(4)
    with sd1:
        sv_svc_period = st.selectbox("服務時段", PERIOD_OPTIONS, key="sv_auto_period")
    with sd2:
        sv_svc_person = st.number_input("人數", min_value=1, max_value=8, value=2, key="sv_auto_person")
    with sd3:
        sv_svc_hour = PERIOD_HOUR_MAP.get(sv_svc_period, 4)
        sv_person_hours = int(sv_svc_person) * int(sv_svc_hour)
        st.markdown(f"<br><b>{sv_svc_hour} 小時</b><br><span style='color:#8E8E93;font-size:13px;'>人時：{sv_person_hours}</span>", unsafe_allow_html=True)
    with sd4:
        sv_unit_price = 700 if sv_day_type_auto == "週末" else 600
        st.markdown(f"<br><b>{sv_unit_price} 元 / 人時</b><br><span style='color:#8E8E93;font-size:13px;'>儲值金單目標金額：{sv_unit_price * sv_person_hours}</span>", unsafe_allow_html=True)
    st.markdown("<hr>", unsafe_allow_html=True)
    step("4", "客付訂單付款與發票")
    pay1, pay2 = st.columns(2)
    with pay1:
        sv_customer_payway = st.selectbox("付款方式", ["ATM", "信用卡"], key="sv_auto_customer_payway")
    with pay2:
        sv_invoice_mode = st.selectbox("發票", ["會員載具", "手機載具", "三聯式"], key="sv_auto_invoice_mode")
    sv_mobile_carrier = ""
    sv_company_title = ""
    sv_company_no = ""
    if sv_invoice_mode == "手機載具":
        sv_mobile_carrier = st.text_input("手機條碼", placeholder="例：/ABC1234", key="sv_auto_mobile_carrier")
    elif sv_invoice_mode == "三聯式":
        inv_a, inv_b = st.columns(2)
        with inv_a:
            sv_company_title = st.text_input("發票抬頭", key="sv_auto_company_title")
        with inv_b:
            sv_company_no = st.text_input("統一編號", key="sv_auto_company_no")
    else:
        st.caption("二聯會員載具會使用會員 email。")
    st.markdown("<hr>", unsafe_allow_html=True)
    step("4", "選填設定")
    opt1, opt2 = st.columns(2)
    with opt1:
        sv_address = st.text_input("指定服務地址（留空則用會員第一個地址）", key="sv_auto_address")
    with opt2:
        sv_region = st.selectbox("適用地區", [""] + list(COUPON_COMPANY_ID_MAP.keys()), format_func=lambda x: x or "依地址自動判斷", key="sv_auto_region")
    sv_allow_auto_lemon = auto_lemon_checkbox("sv_allow_auto_lemon", "查無檸檬人時自動補檸檬人（不動其他客人已配班專員）")
    st.markdown("<hr>", unsafe_allow_html=True)
    step("5", "第一段：建立儲值金清零訂單")
    sv_stored_total_preview = sv_unit_price * sv_person_hours
    st.markdown(f'<div class="hint-box">儲值金清零訂單會送到 <b>/booking/stored_value_routine</b>。服務總額為 <b>{sv_unit_price} × {sv_person_hours} = {sv_stored_total_preview}</b>；優惠券A會用「服務總額 - 儲值金餘額」計算，剩餘金額由儲值金扣抵後歸零。</div>', unsafe_allow_html=True)
    if st.button("① 建立儲值金清零訂單（stored_value_routine）", use_container_width=True, key="sv_create_stored_btn"):
        # v8.15：開始新的一次嘗試前，先清空上一次殘留的舊結果（含第二段）。
        st.session_state.sv_stored_stage = {}
        st.session_state.sv_paid_stage = {}
        if not backend_email.strip() or not backend_password.strip():
            st.error("請先輸入後台帳號密碼")
        elif not sv_phone.strip():
            st.error("請輸入客人手機號碼")
        else:
            try:
                with st.spinner("第一段執行中：查儲值金 → 建優惠券A → 建儲值金清零訂單 → 用既有班表換檸檬人…"):
                    stored_stage = stored_value_makeup_create_stored_order(
                        env_name=env, backend_email=backend_email.strip(), backend_password=backend_password.strip(),
                        phone=sv_phone.strip(), clean_type_id=CLEAN_TYPE_ID_MAP[sv_ctype],
                        service_date=sv_svc_date.strftime("%Y-%m-%d"), period_s=sv_svc_period,
                        hour=str(sv_svc_hour), person=str(int(sv_svc_person)),
                        address=sv_address.strip(), region=sv_region, coupon_prefix_base=sv_phone.strip(),
                        allow_auto_lemon_shift=sv_allow_auto_lemon,
                    )
                st.session_state.sv_stored_stage = stored_stage
                st.session_state.sv_paid_stage = {}
                log_execution(
                    function_name="儲值金補價差（第一段：建儲值金清零單）", status="成功",
                    date=sv_svc_date.strftime("%Y-%m-%d"),
                    target=stored_stage.get("stored_order", {}).get("order_no", ""),
                    message=f"手機：{sv_phone.strip()}",
                )
            except Exception as e:
                st.error(f"第一段建立失敗：{e}")
                log_execution(
                    function_name="儲值金補價差（第一段：建儲值金清零單）", status="失敗",
                    date=sv_svc_date.strftime("%Y-%m-%d"), target=sv_phone.strip(),
                    message=str(e), traceback_text=traceback.format_exc(),
                )
    stored_stage = st.session_state.get("sv_stored_stage")
    if stored_stage:
        plan = stored_stage["plan"]
        so = stored_stage["stored_order"]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("儲值金餘額", f"{stored_stage['balance']} 元")
        c2.metric("日期類型", stored_stage.get("day_type", sv_day_type_auto))
        c3.metric("優惠券A", f"{plan['coupon_a']} 元")
        st.caption(f"計算式：{plan['dummy_price']} - {stored_stage['balance']} = {plan['coupon_a']}；剩餘 {plan.get('stored_value_applied', stored_stage['balance'])} 扣儲值金。")
        c4.metric("儲值金單", so.get("order_no", "—"))
        ca = stored_stage.get("coupon_a", {})
        st.success(
            f"✅ 第一段完成：儲值金清零訂單 {so.get('order_no', '—')}；"
            f"優惠券A {ca.get('coupon_code') or ca.get('coupon_prefix')}，面額 {plan['coupon_a']} 元。　"
            f"👤 專員：{so.get('staff') or '（無班表資料）'}"
        )
        if so.get("order_no_duplicated"):
            show_duplicate_order_warning(so.get("order_no"), so.get("order_no_duplicate_count", 2), dedup_key=f"sv_stored_{so.get('order_no')}")
        lemon_r = stored_stage.get("lemon_result", {})
        if lemon_r.get("success"):
            st.success(lemon_r.get("message", "已改為檸檬人"))
        else:
            st.error(lemon_r.get("message", "現有班表無足夠檸檬人，已停止第二段，請手動處理"))
        step("6", "第二段：建立客付補價差訂單")
        st.markdown(f'<div class="hint-box">客付補價差單會建立優惠券B，面額為原儲值金餘額 <b>{stored_stage["balance"]}</b> 元，付款方式為 <b>{sv_customer_payway}</b>。</div>', unsafe_allow_html=True)
        _sv_stage_ready = bool(lemon_r.get("success"))
        if st.button("② 建立客付補價差訂單（single）", use_container_width=True, key="sv_create_paid_btn", disabled=not _sv_stage_ready):
            # v8.15：開始新的一次嘗試前，先清空上一次殘留的舊結果。
            st.session_state.sv_paid_stage = {}
            try:
                with st.spinner("第二段執行中：建優惠券B → 建客付補價差訂單…"):
                    paid_stage = stored_value_makeup_create_paid_order(
                        env_name=env, backend_email=backend_email.strip(), backend_password=backend_password.strip(),
                        phone=stored_stage.get("phone") or sv_phone.strip(),
                        clean_type_id=stored_stage.get("clean_type_id") or CLEAN_TYPE_ID_MAP[sv_ctype],
                        service_date=stored_stage.get("service_date") or sv_svc_date.strftime("%Y-%m-%d"),
                        period_s=stored_stage.get("period_s") or sv_svc_period,
                        hour=stored_stage.get("hour") or str(sv_svc_hour),
                        person=stored_stage.get("person") or str(int(sv_svc_person)),
                        customer_payway=sv_customer_payway, invoice_mode=sv_invoice_mode,
                        mobile_carrier=sv_mobile_carrier, company_title=sv_company_title, company_no=sv_company_no,
                        address=stored_stage.get("address") or sv_address.strip(),
                        region=stored_stage.get("region") or sv_region,
                        coupon_prefix_base=stored_stage.get("coupon_prefix_base") or sv_phone.strip(),
                        stored_order_no=stored_stage.get("stored_order", {}).get("order_no", ""),
                        balance_override=stored_stage.get("balance"),
                        allow_auto_lemon_shift=sv_allow_auto_lemon,
                    )
                st.session_state.sv_paid_stage = paid_stage
                log_execution(
                    function_name="儲值金補價差（第二段：建客付補價差單）", status="成功",
                    target=paid_stage.get("paid_order", {}).get("order_no", ""),
                    message=f"手機：{sv_phone.strip()}",
                )
            except Exception as e:
                st.error(f"第二段建立失敗：{e}")
                log_execution(
                    function_name="儲值金補價差（第二段：建客付補價差單）", status="失敗",
                    target=sv_phone.strip(),
                    message=str(e), traceback_text=traceback.format_exc(),
                )
    paid_stage = st.session_state.get("sv_paid_stage")
    if paid_stage:
        po = paid_stage["paid_order"]
        cb = paid_stage.get("coupon_b", {})
        st.success(
            f"✅ 第二段完成：客付補價差訂單 {po.get('order_no', '—')}；"
            f"優惠券B {cb.get('coupon_code') or cb.get('coupon_prefix')}。　"
            f"👤 專員：{po.get('staff') or '（無班表資料）'}"
        )
        if paid_stage.get("mark_paid_ok") is True:
            st.caption("✅ 已標記為已付款")
        elif paid_stage.get("mark_paid_ok") is None:
            st.caption(f"ℹ️ {paid_stage.get('mark_paid_msg', '未自動標記已付款')}")
        else:
            st.warning(f"⚠️ 標記已付款失敗：{paid_stage.get('mark_paid_msg', '')}")
        if paid_stage.get("invoice_note_ok"):
            st.caption("✅ 發票號碼欄位已標註「不開立發票」")
        else:
            st.warning(f"⚠️ 發票欄位標註失敗，請至後台手動填寫「不開立發票」：{paid_stage.get('invoice_note_msg', '')}")
        if po.get("order_no_duplicated"):
            show_duplicate_order_warning(po.get("order_no"), po.get("order_no_duplicate_count", 2), dedup_key=f"sv_paid_{po.get('order_no')}")
        st.markdown("#### 📋 備註文字")
        combined_note = ""
        if stored_stage:
            combined_note += stored_stage.get("note", "")
        combined_note += "\n" + paid_stage.get("note", "")
        st.text_area("備註", combined_note.strip(), height=110, label_visibility="collapsed")
        copy_button("複製備註", combined_note.strip(), "copy_sv_stage_note")
        if paid_stage.get("line_message"):
            st.markdown("#### 💬 客付訂單 LINE 訊息")
            st.text_area("LINE 訊息", paid_stage["line_message"], height=320, label_visibility="collapsed")
            copy_button("複製 LINE 訊息", paid_stage["line_message"], "copy_sv_paid_line")


def render_stored_value_order(backend_email, backend_password, env):
    step("3", "建立儲值金訂單")
    info_panel("流程說明", [
        "地區＝登入帳號本身所屬地區（例如用台北帳號登入，就會建在台北）。",
        "付款方式與發票不用手動選：自動抓這支電話最近一次 VIP 或儲值金購買訂單的設定，"
        "都找不到才退回抓最近一次一般服務訂單的設定，兩者都沒有則不會自動送出，"
        "改請你人工確認後至後台手動建立。",
    ])
    sv2_col1, sv2_col2 = st.columns(2)
    with sv2_col1:
        sv2_phone = st.text_input("客人手機號碼", key="sv2_phone")
    with sv2_col2:
        sv2_region = st.selectbox("地區（登入帳號所屬地區）", ["台北", "桃園", "新竹", "台中"], key="sv2_region")

    sv2_amount_labels = {
        "儲值金20,000（贈購物金800）": 20000,
        "儲值金50,000（贈購物金2,500）": 50000,
        "儲值金9,900（無贈送）": 9900,
        "儲值金17,000（無贈送）": 17000,
        "儲值金18,900（無贈送）": 18900,
        "儲值金19,400（無贈送）": 19400,
        "儲值金36,000（無贈送）": 36000,
    }
    sv2_amount_label = st.selectbox("儲值金金額", list(sv2_amount_labels.keys()), key="sv2_amount_label")
    sv2_amount = sv2_amount_labels[sv2_amount_label]
    sv2_notice = st.text_area("備註（選填）", height=80, key="sv2_notice")

    if st.button("🚀 建立儲值金購買訂單", use_container_width=True, key="sv2_create_btn", type="primary"):
        # v8.21：開始新的一次嘗試前，先清空上一次殘留的舊結果。
        st.session_state.sv2_result = {}
        if not backend_email.strip() or not backend_password.strip():
            st.error("請先輸入後台帳號密碼")
        elif not sv2_phone.strip():
            st.error("請輸入客人手機號碼")
        else:
            try:
                with st.spinner("查詢會員 → 判斷付款方式/發票 → 建立儲值金訂單…"):
                    sv2_result = qo.create_stored_value_purchase_order(
                        env_name=env,
                        backend_email=backend_email.strip(),
                        backend_password=backend_password.strip(),
                        phone=sv2_phone.strip(),
                        stored_value_amount=sv2_amount,
                        region=sv2_region,
                        notice=sv2_notice.strip(),
                    )
                st.session_state.sv2_result = sv2_result
                log_execution(
                    function_name="建立儲值金購買訂單",
                    status="失敗" if sv2_result.get("need_manual_confirm") or sv2_result.get("success") is False else "成功",
                    area=sv2_region, target=sv2_result.get("order_no", sv2_phone.strip()),
                    message=sv2_result.get("message", f"金額：{sv2_amount}"),
                )
            except Exception as e:
                st.error(f"建立失敗：{e}")
                log_execution(
                    function_name="建立儲值金購買訂單", status="失敗", area=sv2_region,
                    target=sv2_phone.strip(), message=str(e), traceback_text=traceback.format_exc(),
                )

    sv2_result = st.session_state.get("sv2_result") or {}
    if sv2_result:
        if sv2_result.get("need_manual_confirm"):
            st.warning(f"⚠️ {sv2_result.get('message', '')}")
            _dbg = sv2_result.get("search_debug") or {}
            with st.expander("🔍 查詢明細（點開看實際查到什麼，不用再用猜的）", expanded=True):
                if _dbg.get("error"):
                    st.error(f"查詢時發生例外：{_dbg['error']}")
                _queries_dbg = _dbg.get("queries") or []
                if _queries_dbg:
                    st.table([
                        {
                            "查詢類別": q.get("label", ""),
                            "HTTP狀態碼": q.get("http_status", q.get("error", "")),
                            "查到筆數（已付款）": q.get("count", 0),
                            "訂單編號": "、".join(q.get("order_nos", [])) or "（無）",
                        }
                        for q in _queries_dbg
                    ])
                    _skipped_dbg = _dbg.get("skipped_stored_value_payway") or []
                    if _skipped_dbg:
                        st.caption("以下訂單因為付款方式是「儲值金」（既有餘額折抵消費，非真正付款）已跳過：")
                        st.table([{"類別": s.get("label", ""), "訂單編號": s.get("order_no", "")} for s in _skipped_dbg])
                    st.caption(
                        "依序查詢「儲值金」→「VIP券」→「專業清潔」三個類別（都只查已付款的訂單），"
                        "查到就直接用該類別裡最新一筆「付款方式是信用卡/ATM」的訂單，不會混在一起比日期，"
                        "也不會用付款方式是儲值金的訂單當範本。如果上表看起來明明有查到訂單、"
                        "卻還是被判定查無資料，麻煩把這個表格截圖給開發人員確認。"
                    )
                else:
                    st.info("查詢過程沒有回傳任何結果，請檢查上方是否有例外訊息。")
        elif sv2_result.get("success"):
            st.success(
                f"✅ 訂單：{sv2_result.get('order_no') or '（已送出，但查不到訂單編號，請至後台確認）'}　"
                f"儲值金額：{sv2_result.get('stored_value_amount')}元　"
                f"贈購物金：{sv2_result.get('bonus')}元　"
                f"付款方式：{sv2_result.get('payway')}"
            )
            _invoice_type_label = {"1": "捐贈發票", "2": "二聯式", "3": "三聯式"}.get(sv2_result.get("invoice_type", ""), "")
            if _invoice_type_label:
                st.caption(
                    f"發票設定沿用自會員歷史訂單：{_invoice_type_label}"
                    + (f"（{sv2_result.get('company_title')} / {sv2_result.get('company_no')}）" if sv2_result.get("invoice_type") == "3" else "")
                    + (f"（{sv2_result.get('carrier_info')}）" if sv2_result.get("invoice_type") == "2" and sv2_result.get("carrier_info") else "")
                )
            # v8.23：跟其他成單流程一致，訂單建立後不自動發確認信，
            # 由客服確認資料無誤後手動按下「發送確認信」再送出。
            if sv2_result.get("order_no"):
                if not sv2_result.get("mail_sent"):
                    if st.button("📧 發送確認信", key="sv2_send_mail_btn", type="primary"):
                        try:
                            ok_m, msg_m = send_confirmation(sv2_result)
                            if ok_m:
                                sv2_result["mail_sent"] = True
                                st.session_state.sv2_result = sv2_result
                                st.success("✅ 確認信已發送")
                                log_execution(
                                    function_name="發送確認信", status="成功",
                                    target=sv2_result.get("order_no", ""), message="儲值金購買確認信",
                                )
                                st.rerun()
                            else:
                                st.error(f"確認信發送失敗：{msg_m}")
                                log_execution(
                                    function_name="發送確認信", status="失敗",
                                    target=sv2_result.get("order_no", ""), message=str(msg_m),
                                )
                        except Exception as e:
                            st.error(f"確認信發送失敗：{e}")
                            log_execution(
                                function_name="發送確認信", status="失敗",
                                target=sv2_result.get("order_no", ""), message=str(e),
                                traceback_text=traceback.format_exc(),
                            )
                else:
                    st.success("✅ 確認信已發送")
            else:
                st.info("查不到訂單編號，無法自動發送確認信，請至後台確認訂單後手動發送。")
            if sv2_result.get("line_message"):
                st.markdown("#### 💬 LINE 訊息")
                st.text_area("LINE 訊息", sv2_result["line_message"], height=380, label_visibility="collapsed")
                copy_button("複製 LINE 訊息", sv2_result["line_message"], "copy_sv2_line")
            else:
                st.info("此地區/付款方式組合目前沒有現成 LINE 通知文案，請至「LINE 通知產生器」用訂單編號查詢並人工確認內容。")
        else:
            st.error(f"❌ 建立失敗：{sv2_result.get('message', '未知錯誤')}")
