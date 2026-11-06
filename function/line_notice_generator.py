# ============================================================
# 檔名：function/line_notice_generator.py
# 功能：LINE 通知產生器；依單筆／多筆訂單編號產生客戶通知訊息。
# 更新時間：2026-11-06
# 2026-11-06：預設改為手動輸入訂單編號；單筆儲值金購買單號也可直接產生；
#             日曆改為可選的「標記」，不再影響手動輸入的通知產生。
# ============================================================
# -*- coding: utf-8 -*-
import streamlit as st
import orders
from accounts import ACCOUNTS
from shared import notification_service
from shared.line_notice_sheet import (
    CALENDAR_FOUND, CALENDAR_NOT_CHECKED, calendar_status_for_result,
    filter_groups_by_calendar, groups_from_dataframe, results_tsv,
)
from function.ui_common import step, info_panel, copy_button, NJ_MEMO
from shared import calendar_phone_search as cps
from orders import load_worksheet


def render(backend_email, backend_password, env):
    step("3", "LINE 通知產生器")
    col_left, col_right = st.columns([3, 1])
    with col_left:
        info_panel("使用說明", [
            "預設手動輸入訂單編號：每行一組，同組用逗號合併；日期、時段、地址、金額一律以後台訂單為準。",
            "儲值金購買單（例：客人自行儲值）也可直接輸入單號產生通知；儲值金購買單請單獨一行，不可和服務單合併。",
            "勾選「同時查詢 Google 日曆」只會在結果上標記有無行程，不影響通知產生。",
            "切換成「Google Sheet 已成單列」時，會先以日曆篩選，日曆沒有的列不通知。",
            "VIP 客人（儲值金餘額 > 0）會自動用電話查日曆：有行程顯示日曆連結，沒有顯示「無日曆」。",
        ])
        source = st.radio("資料來源", ["手動輸入訂單編號", "Google Sheet 已成單列"], horizontal=True, key="line_notice_source")
        if source == "Google Sheet 已成單列":
            c1, c2 = st.columns(2)
            sheet_name = c1.text_input("工作表名稱", placeholder="例：台北202611", key="line_notice_sheet")
            row_spec = c2.text_input("列號（選填）", placeholder="例：2,3,5-20；空白＝全部已成單列", key="line_notice_rows")
            line_order_nos_input = ""
            check_calendar = False
        else:
            sheet_name = row_spec = ""
            line_order_nos_input = st.text_area("訂單編號（每行一組；同組用逗號）", value="", height=120, placeholder="LC00211537,LC00211538\nLC00219825", key="line_order_nos")
            check_calendar = st.checkbox("同時查詢 Google 日曆（只標記有無行程，不影響通知產生）", value=False, key="line_notice_check_calendar")
        if st.button("產生 LINE 訊息", width="stretch", key="make-line-from-order-no"):
            if not backend_email.strip() or not backend_password.strip():
                st.error("請先輸入後台帳號密碼")
            else:
                st.session_state.line_notice_skipped = []
                st.session_state.line_notice_mode = source
                groups = []
                if source == "Google Sheet 已成單列":
                    if not sheet_name.strip():
                        st.error("請輸入工作表名稱")
                    else:
                        try:
                            _, df = load_worksheet(sheet_name.strip())
                            groups = groups_from_dataframe(df, row_spec)
                            service = orders.build_gcal_service()
                            groups, skipped = filter_groups_by_calendar(
                                groups, orders, service, orders.GOOGLE_CALENDAR_MAP, ACCOUNTS,
                            )
                            st.session_state.line_notice_skipped = skipped
                        except Exception as exc:
                            st.error(f"讀取工作表失敗：{exc}")
                else:
                    for line in [x.strip() for x in line_order_nos_input.splitlines() if x.strip()]:
                        nos = [n.strip() for n in line.split(",") if n.strip()]
                        if nos:
                            groups.append({"name": "", "address": "", "service": "", "order_nos": nos, "rows": []})
                order_groups = [group["order_nos"] for group in groups]
                if not order_groups:
                    st.error("找不到已成單的訂單編號")
                else:
                    st.session_state.line_from_order_nos_results = []
                    for _k in list(st.session_state.keys()):
                        if _k.startswith("line_text_") or _k.startswith("nj_memo_"): del st.session_state[_k]
                    results_list = []
                    vip_cache = {}
                    for group, nos in zip(groups, order_groups):
                        label = "、".join(nos)
                        try:
                            with st.spinner(f"查詢訂單 {label}…"):
                                line_result, line_text = _build_line_for_group(env, backend_email.strip(), backend_password.strip(), nos)
                            vip_info = _vip_calendar_for_result(line_result, vip_cache)
                            safe_result = {k: v for k, v in line_result.items() if k != "session"}
                            status = CALENDAR_FOUND if source == "Google Sheet 已成單列" else CALENDAR_NOT_CHECKED
                            results_list.append({"order_no": label, "group": group, "result": safe_result, "text": line_text, "error": None, "calendar_status": status, "vip_calendar": vip_info})
                        except Exception as e:
                            results_list.append({"order_no": label, "group": group, "result": None, "text": "", "error": str(e)})
                    if check_calendar and any(not item["error"] for item in results_list):
                        _mark_calendar(results_list)
                    st.session_state.line_from_order_nos_results = results_list
                    st.rerun()
    with col_right:
        st.markdown('<div class="sec-label">N-J Memo</div>', unsafe_allow_html=True)
        st.text_area("N-J Memo", NJ_MEMO, height=220, key="nj_memo_fixed", label_visibility="collapsed")
        copy_button("複製 N-J Memo", NJ_MEMO, "copy-nj-memo-fixed")
    results_list = st.session_state.get("line_from_order_nos_results", [])
    skipped = st.session_state.get("line_notice_skipped", [])
    if skipped:
        st.info(f"日曆沒有對應行程，已略過 {len(skipped)} 筆，不產生通知。")
    if any(not item.get("error") for item in results_list):
        if st.session_state.get("line_notice_mode") == "Google Sheet 已成單列":
            st.caption("以下皆已通過日曆存在檢查；日期／時段內容以後台訂單為準。整段可直接貼到 Google Sheet。")
        else:
            st.caption("日期／時段內容以後台訂單為準；「日曆檢查」欄為標記用，不影響通知。整段可直接貼到 Google Sheet。")
        st.code(results_tsv(results_list), language=None)
    for idx, item in enumerate(results_list):
        if item["error"]:
            st.error(f"訂單 {item['order_no']} 產生失敗：{item['error']}"); continue
        line_result, line_text = item["result"], item["text"]
        all_nos = line_result.get("all_order_nos") or [line_result.get("order_no")]
        order_no_display = "、".join(str(n) for n in all_nos if n)
        is_combined, is_multi_date = len(all_nos) > 1, line_result.get("multi_date", False)
        combined_note = "　⚠️ 跨日合併單" if (is_combined and is_multi_date) else ("　⚠️ 同日合併單" if is_combined else "")
        if line_result.get("is_stored_value_purchase"):
            amount_text = f"儲值金購買 {line_result.get('stored_value_amount') or '—'}"
            if line_result.get("stored_value_bonus"):
                amount_text += f"（贈 {line_result.get('stored_value_bonus')}）"
            st.caption(f"訂單：{order_no_display}　💰 儲值金購買單　付款方式：{line_result.get('payway')}　區域：{line_result.get('region')}　金額：{amount_text}")
        else:
            st.caption(f"訂單：{order_no_display}{combined_note}　付款方式：{line_result.get('payway')}　區域：{line_result.get('region')}　金額：{line_result.get('service_amount') or '—'}　車馬費：{line_result.get('fare') or '0'}")
        _calendar_badge(item.get("calendar_status") or CALENDAR_NOT_CHECKED)
        if item.get("vip_calendar"):
            st.caption("⭐ VIP")
            cps.render_calendar_link(st, item["vip_calendar"], key=f"vip-cal-{idx}")
        st.text_area(f"LINE 訊息（{line_result.get('order_no')}）", line_text, height=380, label_visibility="collapsed")
        copy_button("複製 LINE 訊息", line_text, f"copy-line-msg-{idx}")
        if idx < len(results_list) - 1: st.markdown("<hr>", unsafe_allow_html=True)


_STORED_VALUE_HINT = "儲值金購買訂單"


def _build_line_for_group(env, backend_email, backend_password, nos):
    """一般服務單走合併邏輯；單筆儲值金購買單改走單筆查詢（儲值金專用範本）。"""
    try:
        return notification_service.build_combined_line_message_from_order_nos(
            env_name=env, backend_email=backend_email, backend_password=backend_password, order_nos=nos,
        )
    except Exception as exc:
        if len(nos) == 1 and _STORED_VALUE_HINT in str(exc):
            return notification_service.build_line_message_from_order_no(
                env_name=env, backend_email=backend_email, backend_password=backend_password, order_no=nos[0],
            )
        if _STORED_VALUE_HINT in str(exc):
            raise Exception(f"{exc}（儲值金購買單請單獨一行輸入）") from exc
        raise


def _mark_calendar(results_list):
    try:
        with st.spinner("查詢 Google 日曆…"):
            service = orders.build_gcal_service()
            for item in results_list:
                if item.get("error"):
                    continue
                try:
                    item["calendar_status"] = calendar_status_for_result(
                        item["result"], orders, service, orders.GOOGLE_CALENDAR_MAP, ACCOUNTS,
                    )
                except Exception as exc:
                    item["calendar_status"] = f"⚠️ 日曆檢查失敗：{exc}"
    except Exception as exc:
        for item in results_list:
            if not item.get("error"):
                item["calendar_status"] = f"⚠️ 日曆檢查失敗：{exc}"


def _calendar_badge(status):
    if status == CALENDAR_NOT_CHECKED:
        st.caption("📅 日曆：未檢查")
    elif status.startswith("✅"):
        st.success(f"📅 {status}")
    elif status.startswith("⚠️"):
        st.warning(f"📅 {status}")
    else:
        st.caption(f"📅 日曆：{status}")


def _vip_calendar_for_result(line_result, cache):
    """VIP（會員儲值金餘額 > 0）才用電話查日曆；非 VIP 回傳 None。"""
    phone = cps.normalize_phone(line_result.get("phone"))
    if not phone:
        return None
    if phone in cache:
        return cache[phone]
    vip = False
    session = line_result.get("session")
    if session is not None:
        try:
            token = orders.get_csrf_token(session)
            vip = cps.is_vip_balance(cps.member_balance(orders.get_member(session, phone, token, "1")))
        except Exception:
            vip = False
    if not vip and (line_result.get("payway") == "儲值金" or line_result.get("is_stored_value_purchase")):
        vip = True  # 查不到餘額時，以儲值金付款／儲值金購買單視為 VIP
    cache[phone] = cps.lookup_calendar_by_phone(phone) if vip else None
    return cache[phone]
