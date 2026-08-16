# -*- coding: utf-8 -*-
"""服務異動（階段 A：查詢試算／階段 B：回填系統）。"""

from datetime import date

import streamlit as st

from memo_system import change_order
from function.ui_common import step
from function.memo_shared import get_session

SCENARIO_OPTIONS = [
    "僅開車馬費發票", "異動費(待收款)", "異動費(待退款)",
    "異動平日轉週末(待收款)", "異動週末轉平日(待退款)",
    "加時(待收款)", "減時(待退款)", "客訴(待退款)", "物損(待退款)",
]


def _order_money(order, key, default=0):
    try: return int(round(float((order or {}).get(key, default) or 0)))
    except: return default

def _format_money_for_ui(amount):
    try: return str(int(round(float(amount or 0))))
    except: return str(amount or "")

def _refund_rate_by_workdays(workdays):
    if workdays >= 4: return 5
    if workdays <= 1: return 50
    return 30

def apply_time_change_label(row, scenario, timing):
    prefix = f"{timing}加時" if scenario == "加時(待收款)" else f"{timing}減時"
    j = str(row.get("J", ""))
    for old in ("服務前加時", "當天加時", "服務後加時", "專員回報加時", "服務前減時", "當天減時", "服務後減時", "專員回報減時"):
        j = j.replace(old, prefix)
    if j: row["J"] = j
    note = str(row.get("_calc_note", ""))
    if note: row["_calc_note"] = f"{prefix}，{note}"
    return row

def apply_refund_fee_on_service_amount(order, fee_info):
    info = dict(fee_info or {})
    workdays = int(info.get("workdays", 0) or 0)
    if (order or {}).get("payway") == "儲值金":
        return info
    total = _order_money(order, "total", 0)
    travel_fee = _order_money(order, "travel_fee", 0)
    service_amount = max(total - travel_fee, 0)
    rate_percent = _refund_rate_by_workdays(workdays)
    change_fee = round(service_amount * rate_percent / 100)
    refund_amount = max(service_amount - change_fee, 0)
    info.update({
        "tier": f"refund_{rate_percent}_percent", "change_fee": change_fee,
        "billing_units": None, "rate_amount": None, "rate_percent": rate_percent,
        "service_amount": service_amount, "travel_fee": travel_fee,
        "refund_amount": refund_amount,
        "calc_note": (f"服務前{workdays}個工作天異動，退款情境收 {rate_percent}% 異動費："
                      f"總金額{total} - 車馬費{travel_fee} = 服務費{service_amount}；"
                      f"服務費{service_amount} × {rate_percent}% = 異動費${change_fee}；退款${refund_amount}"),
    })
    return info

def apply_refund_j_note(row, fee_info):
    workdays = int((fee_info or {}).get("workdays", 0) or 0)
    rate_percent = (fee_info or {}).get("rate_percent")
    change_fee = _format_money_for_ui((fee_info or {}).get("change_fee", row.get("_change_fee", 0)))
    refund_amount = _format_money_for_ui(row.get("_refund_amount", row.get("_calc_amount", 0)))
    if rate_percent:
        row["J"] = f"服務前{workdays}個工作天異動，收{rate_percent}%異動費${change_fee}，退款${refund_amount}"
    else:
        row["J"] = f"服務前{workdays}個工作天異動，收異動費${change_fee}，退款${refund_amount}"
    return row

def render_calc_amount_html(row):
    if str(row.get("B", "")) == "待退款":
        parts = []
        if row.get("_service_amount", "") != "": parts.append(f"<b>服務費基礎：</b>${row['_service_amount']}")
        if row.get("_travel_fee", "") != "": parts.append(f"<b>車馬費：</b>${row['_travel_fee']}")
        if row.get("_change_fee", "") != "": parts.append(f"<b>扣除異動費：</b>${row['_change_fee']}")
        parts.append(f"<b>退款金額：</b>${row.get('_refund_amount', row.get('_calc_amount', ''))}")
        return "<br>".join(parts) + "<br>"
    return f"<b>試算金額：</b>${row.get('_calc_amount','')}<br>"


def render_change_order_stage_a(email, env_option):
    step("4", "查詢訂單")
    q1, q2 = st.columns([1, 1.5])
    with q1: region = st.selectbox("地區", ["台北", "台中", "桃園", "新竹", "高雄"], key="co_region_a")
    with q2: query_by = st.radio("查詢方式", ["電話", "訂單編號"], horizontal=True, key="co_query_by")
    if query_by == "電話":
        keyword_input = st.text_input("電話", placeholder="例：0912345678", key="co_phone_keyword")
    else:
        keyword_input = st.text_input("訂單編號", placeholder="例：LC00211483", key="co_orderno_keyword")

    search_btn = st.button("🔍 查詢訂單", use_container_width=True, disabled=not (st.session_state.credentials_ready and keyword_input.strip()))

    with st.expander("執行 LOG", expanded=True):
        log_box_local = st.empty()
        log_box_local.text("\n".join(st.session_state.logs[-3000:]) if st.session_state.logs else "尚未執行")

    def co_log(msg):
        st.session_state.logs.append(str(msg))
        try: log_box_local.text("\n".join(st.session_state.logs[-3000:]))
        except: pass

    if search_btn:
        try:
            st.session_state.logs = []; st.session_state.co_phone_orders = []; st.session_state.co_calc_rows = []
            co_log("===== 開始查詢訂單 =====")
            with st.spinner("查詢中，請稍候…"):
                session = get_session(email, env_option, ui_logger=co_log)
                if query_by == "電話":
                    orders = change_order.fetch_upcoming_paid_orders_by_phone(keyword_input.strip(), session=session, ui_logger=co_log)
                else:
                    single = change_order.fetch_order_basic(keyword_input.strip(), session=session, ui_logger=co_log, by="orderNo")
                    orders = [single] if single else []
            st.session_state.co_phone_orders = orders
            co_log(f"✅ 查詢完成，共 {len(orders)} 筆"); st.rerun()
        except Exception as e:
            co_log(f"❌ 查詢失敗：{e}"); st.error(str(e))

    orders = st.session_state.get("co_phone_orders", [])
    if not orders: return

    st.markdown("---"); step("5", "目前已付款未服務的訂單列表")
    selected_orders = []
    for o in orders:
        service_date_text = o["service_date"].strftime("%Y-%m-%d") if o.get("service_date") else "（無日期資訊）"
        label = f"{o['order_no']}　{o.get('customer_name','')}　服務日期：{service_date_text}　時數：{o.get('service_hours',0)}小時　人數：{o.get('cleaner_count',0)}人　總金額：${o.get('total',0)}"
        if st.checkbox(label, value=True, key=f"co_order_pick_{o['order_no']}"): selected_orders.append(o)

    if not selected_orders:
        st.info("請至少勾選一筆訂單再繼續。"); return

    st.markdown("---"); step("6", "選擇異動情境")
    c1, c2 = st.columns([1, 1.5])
    with c1:
        scenario = st.radio("情境", SCENARIO_OPTIONS, key="co_scenario")
        is_time_change = scenario in ("加時(待收款)", "減時(待退款)")
        is_manual_refund = scenario in ("客訴(待退款)", "物損(待退款)")
        time_change_timing = "服務前"; change_hours = None; change_person = None
        if is_time_change:
            # 先從 session state 取服務日（c2 的 date_input 還沒渲染時用訂單預設值）
            _svc = st.session_state.get("co_service_date") or (selected_orders[0].get("service_date") if selected_orders else date.today())
            if hasattr(_svc, "strftime"):
                _svc_date = _svc
            else:
                try: _svc_date = date.fromisoformat(str(_svc))
                except: _svc_date = date.today()
            _auto_timing = "專員回報" if _svc_date <= date.today() else "服務前"
            _auto_idx = 1 if _auto_timing == "專員回報" else 0
            st.caption(f"⚡ 依服務日 {_svc_date} 自動判斷：{_auto_timing}（可手動調整）")
            time_change_timing = st.radio("加減時發生時間", ["服務前", "專員回報"], index=_auto_idx, horizontal=True, key="co_time_change_timing")
            change_hours = st.number_input("異動時數（小時）", min_value=0.0, step=0.5, value=1.0, key="co_time_hours")
            change_person = st.number_input("異動人數", min_value=1, step=1, value=1, key="co_time_person")
        manual_amount = None
        if is_manual_refund: manual_amount = st.number_input("退款金額", min_value=0, step=50, value=0, key="co_manual_amount")
    with c2:
        customer_type = st.selectbox("客戶類別", ["一般", "VIP"], key="co_customer_type")
        default_service_date = selected_orders[0].get("service_date") or date.today()
        service_date_input = st.date_input("服務日期（用於計算工作天數／平日假日）", value=default_service_date, key="co_service_date")
        service_note = st.text_input("後台備註（寫入 K 欄）", placeholder="例：客通知停水異動服務", key="co_service_note")

    calc_btn = st.button("🧮 試算", use_container_width=True, disabled=not st.session_state.credentials_ready)

    if calc_btn:
        try:
            co_log("===== 開始試算 ====="); calc_rows = []
            for order in selected_orders:
                if scenario == "僅開車馬費發票":
                    calc_rows.append(change_order.build_fare_row(order, service_date=service_date_input)); continue
                if scenario == "加時(待收款)":
                    time_fee_info = change_order.calc_time_change_fee(service_date_input, hours=change_hours, person=change_person)
                    row = change_order.build_addtime_row(order, time_fee_info, service_note, customer_type=customer_type, service_date=service_date_input)
                    calc_rows.append(apply_time_change_label(row, scenario, time_change_timing)); continue
                if scenario == "減時(待退款)":
                    time_fee_info = change_order.calc_time_change_fee(service_date_input, hours=change_hours, person=change_person)
                    row = change_order.build_reducetime_row(order, time_fee_info, service_note, customer_type=customer_type, service_date=service_date_input)
                    calc_rows.append(apply_time_change_label(row, scenario, time_change_timing)); continue
                if scenario == "異動平日轉週末(待收款)":
                    time_fee_info = change_order.calc_flat_person_hour_fee(hours=order.get("service_hours", 0), person=order.get("cleaner_count", 0), rate=change_order.TIME_RATE_DAY_TYPE_DIFF, label="平日轉週末每人時差額")
                    calc_rows.append(change_order.build_weekday_to_weekend_row(order, time_fee_info, service_note, customer_type=customer_type, service_date=service_date_input)); continue
                if scenario == "異動週末轉平日(待退款)":
                    time_fee_info = change_order.calc_flat_person_hour_fee(hours=order.get("service_hours", 0), person=order.get("cleaner_count", 0), rate=change_order.TIME_RATE_DAY_TYPE_DIFF, label="週末轉平日每人時差額")
                    calc_rows.append(change_order.build_weekend_to_weekday_row(order, time_fee_info, service_note, customer_type=customer_type, service_date=service_date_input)); continue
                if scenario == "客訴(待退款)":
                    calc_rows.append(change_order.build_manual_refund_row(order, manual_amount, change_order.TYPE_COMPLAINT_REFUND, service_note, customer_type=customer_type, service_date=service_date_input)); continue
                if scenario == "物損(待退款)":
                    calc_rows.append(change_order.build_manual_refund_row(order, manual_amount, change_order.TYPE_DAMAGE_REFUND, service_note, customer_type=customer_type, service_date=service_date_input)); continue
                fee_info = change_order.calc_change_fee(order, service_date=service_date_input)
                if scenario == "異動費(待收款)":
                    calc_rows.append(change_order.build_charge_row(order, fee_info, service_note, customer_type=customer_type, service_date=service_date_input))
                else:
                    fee_info = apply_refund_fee_on_service_amount(order, fee_info)
                    row = change_order.build_refund_row(order, fee_info, service_note, customer_type=customer_type, service_date=service_date_input)
                    calc_rows.append(apply_refund_j_note(row, fee_info))
            st.session_state.co_calc_rows = calc_rows
            co_log(f"✅ 試算完成，共 {len(calc_rows)} 筆"); st.rerun()
        except Exception as e:
            co_log(f"❌ 試算失敗：{e}"); st.error(str(e))

    calc_rows = st.session_state.get("co_calc_rows", [])
    if calc_rows:
        st.markdown("---"); step("7", "試算結果預覽（尚未寫入 Sheet）")
        for idx, row in enumerate(calc_rows):
            j_key = f"co_j_edit_{idx}_{row.get('G', '')}"
            if j_key not in st.session_state: st.session_state[j_key] = row.get("J", "")
            st.markdown(f"""
            <div class="preview-card preview-ok">
                <div class="preview-title">{row.get('G','')}　{row.get('H','')}</div>
                <div class="preview-sub">
                    <b>類型：</b>{row.get('C','')}　<b>狀態：</b>{row.get('B','')}<br>
                    <b>原服務時間：</b>{row.get('I','')}<br>
                    {render_calc_amount_html(row)}
                    <b>K 欄後台備註：</b>{row.get('K','')}<br>
                    <b>計算依據：</b>{row.get('_calc_note','')}
                </div>
            </div>""", unsafe_allow_html=True)
            st.text_area(f"J 欄內容（可編輯）｜{row.get('G','')}", key=j_key, height=90)

        st.markdown(f'<div class="warn-strip">⚠️ 確認後會把以上 {len(calc_rows)} 筆寫入「{region}」清潔異動工作表最後一列之後；J 欄會採用上方編輯後內容。</div>', unsafe_allow_html=True)
        if st.button("🚀 確認寫入清潔異動工作表", type="primary", use_container_width=True):
            try:
                rows_to_write = []
                for idx, row in enumerate(calc_rows):
                    writable = dict(row)
                    writable["J"] = st.session_state.get(f"co_j_edit_{idx}_{row.get('G', '')}", row.get("J", ""))
                    rows_to_write.append(writable)
                co_log("===== 開始寫入 Sheet =====")
                with st.spinner("寫入中，請稍候…"):
                    result = change_order.append_rows_to_sheet(region, rows_to_write, ui_logger=co_log)
                if result["errors"]: st.error("；".join(result["errors"]))
                else:
                    st.success(f"✅ 已寫入 {result['written']} 筆，從第 {result['start_row']} 列開始")
                    st.session_state.co_calc_rows = []; st.session_state.co_phone_orders = []
                    for key in [k for k in st.session_state.keys() if str(k).startswith("co_j_edit_")]:
                        del st.session_state[key]
            except Exception as e:
                error_message = str(e).strip() or f"{type(e).__name__}: {e!r}"
                co_log(f"❌ 寫入失敗：{error_message}"); st.error(error_message)


def render_change_order_stage_b(email, env_option):
    step("3", "讀取清潔異動工作表待處理列")
    st.markdown('<div class="info-strip"><b>掃描條件</b><ul><li>B 欄為待收款、待退款、已收款、已退款，或專員服務時間異動、車馬費發票、VIP待退券/VIP已退券、待扣/已扣/待返/已返儲值金</li><li>收退款列需有對應金額；備註型列需有 K 欄備註</li></ul><b>列號篩選（選填）</b><ul><li>不填 → 掃描整個工作表全部符合條件的列</li><li>填寫 → 只掃描指定列號，例如 <code>19</code>、<code>19,21</code>、<code>19-22</code></li></ul><b>回填結果</b><ul><li>依 Sheet 狀態寫回後台加收/退款/備註欄位</li><li>AD 欄寫入系統回填時間，AE 欄寫入更新狀態</li><li>不會自動修改 B 欄狀態</li></ul></div>', unsafe_allow_html=True)
    c_region, c_rows = st.columns([1, 3])
    with c_region:
        region = st.selectbox("地區", ["台北", "台中", "桃園", "新竹", "高雄"], key="co_region_b")
    with c_rows:
        row_spec = st.text_input("列號篩選（選填，不填掃全部）", placeholder="例如：19 或 19,21 或 19-22，留白則掃描全部", key="co_stage_b_row_spec")
    scan_btn = st.button("🔍 掃描待處理清單", use_container_width=True, disabled=not st.session_state.credentials_ready)

    with st.expander("執行 LOG", expanded=True):
        log_box_local = st.empty()
        log_box_local.text("\n".join(st.session_state.logs[-3000:]) if st.session_state.logs else "尚未執行")

    def co_log(msg):
        st.session_state.logs.append(str(msg))
        try: log_box_local.text("\n".join(st.session_state.logs[-3000:]))
        except: pass

    if scan_btn:
        try:
            st.session_state.logs = []; st.session_state.co_pending_rows = []
            co_log("===== 開始掃描清潔異動工作表 =====")
            with st.spinner("掃描中，請稍候…"):
                pending = change_order.get_pending_rows(region, row_spec=row_spec.strip() or None, ui_logger=co_log)
            st.session_state.co_pending_rows = pending
            co_log(f"✅ 掃描完成，共 {len(pending)} 筆"); st.rerun()
        except Exception as e:
            co_log(f"❌ 掃描失敗：{e}"); st.error(str(e))

    pending = st.session_state.get("co_pending_rows", [])
    if pending:
        st.markdown("---"); step("4", "待處理清單（請勾選要回填的項目）")
        selected = []
        for item in pending:
            status = item.get("status") or ("待收款" if item["kind"] == "charge" else "待退款")
            checked = st.checkbox(f"{item['order_no']}（{status}，Sheet 第 {item['sheet_row']} 列）", value=True, key=f"co_pick_{item['sheet_row']}")
            detail = f"H 欄姓名：{item.get('customer_name','')}　｜　J 欄：{item.get('j_note','')}"
            if item.get("kind") == "refund": detail += f"　｜　Y 欄：{item.get('refund_invoice_type','')}"
            st.caption(detail)
            if checked: selected.append(item)
        st.metric("已勾選筆數", len(selected))
        st.markdown('<div class="warn-strip"><b>送出前請確認</b><ul><li>金額正確</li><li>日期正確</li><li>B 欄狀態正確</li></ul></div>', unsafe_allow_html=True)
        if st.button("🚀 確認回填系統", type="primary", use_container_width=True, disabled=not selected):
            try:
                co_log(f"===== 開始回填 {len(selected)} 筆 =====")
                with st.spinner("回填中，請稍候…"):
                    session = get_session(email, env_option, ui_logger=co_log)
                    result = change_order.sync_pending_rows(region, selected, session=session, ui_logger=co_log)
                co_log("===== 回填完成 ====="); st.session_state.co_pending_rows = []
                c1, c2, c3 = st.columns(3)
                c1.metric("執行筆數", result["processed"]); c2.metric("成功", result["success"]); c3.metric("失敗", result["failed"])
                if result["errors"]:
                    with st.expander(f"⚠️ 錯誤明細（{len(result['errors'])} 筆）", expanded=True):
                        for i, err in enumerate(result["errors"], 1): st.markdown(f"**{i}.** {err}")
                else: st.success("✅ 全部回填完成")
            except Exception as e:
                co_log(f"❌ 回填失敗：{e}"); st.error(str(e))


def render(backend_email, backend_password, env):
    email, env_option = backend_email, env
    step("3", "選擇服務異動步驟")
    co_mode = st.radio("", ["階段 A：查詢試算（寫入清潔異動工作表）", "階段 B：回填系統（讀工作表寫回後台）"], horizontal=True, label_visibility="collapsed", key="change_order_mode")
    if co_mode.startswith("階段 A"):
        render_change_order_stage_a(email, env_option)
    else:
        render_change_order_stage_b(email, env_option)
