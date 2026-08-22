# -*- coding: utf-8 -*-
"""儲值獎金備註。"""

import re
import traceback
from datetime import datetime

import streamlit as st

from orders import find_pending_stored_value_orders, apply_bonus_notes
from function.ui_common import step, info_panel
from shared.execution_log_service import log_execution


def render(backend_email, backend_password, env):
    step("3", "儲值獎金備註")
    info_panel("功能說明", [
        "同一個功能內完成「搜尋儲值金訂單 → 確認名單 → 套用獎金客服備註」。",
        "搜尋結果會暫存在畫面狀態裡，確認獎金內容後可直接套用，不需要再重新搜尋一次。",
        "套用時會依姓名比對，把「獎金：獎金人員1X獎金人員2」加進該筆訂單的客服備註，保留原本內容，並把服務狀態改為「已處理」。",
    ])

    st.markdown("**訂購日期區間**")
    bn_col1, bn_col2 = st.columns(2)
    with bn_col1:
        bn_date_s = st.date_input("訂購日期-起", value=None, key="bn_date_s")
    with bn_col2:
        bn_date_e = st.date_input("訂購日期-迄", value=None, key="bn_date_e")

    st.markdown("**付款日期區間**")
    bn_col3, bn_col4 = st.columns(2)
    with bn_col3:
        bn_paid_s = st.date_input("付款日期-起", value=None, key="bn_paid_s")
    with bn_col4:
        bn_paid_e = st.date_input("付款日期-迄", value=None, key="bn_paid_e")

    bn_status_map = {
        "待付款": "0", "已付款": "1",
        "待付款＋已付款": ["0", "1"],
    }
    bn_status_label = st.selectbox("付款狀態", list(bn_status_map.keys()), index=1, key="bn_status")

    if st.button("🔍 搜尋儲值金訂單", use_container_width=True, key="bn_search_btn", type="primary"):
        st.session_state.bn_apply_results = []
        st.session_state.bn_parse_errors = []
        if not backend_email.strip() or not backend_password.strip():
            st.error("請先在上方輸入後台帳號密碼")
        else:
            try:
                with st.spinner("登入後台 → 搜尋客服備註空白的儲值金訂單中…"):
                    bn_results, bn_debug = find_pending_stored_value_orders(
                        env_name=env,
                        backend_email=backend_email.strip(),
                        backend_password=backend_password.strip(),
                        date_s=bn_date_s.strftime("%Y-%m-%d") if bn_date_s else None,
                        date_e=bn_date_e.strftime("%Y-%m-%d") if bn_date_e else None,
                        paid_at_s=bn_paid_s.strftime("%Y-%m-%d") if bn_paid_s else None,
                        paid_at_e=bn_paid_e.strftime("%Y-%m-%d") if bn_paid_e else None,
                        purchase_status=bn_status_map[bn_status_label],
                        notice_status="blank",
                        return_debug=True,
                    )
                st.session_state.bn_results = bn_results
                st.session_state.bn_debug = bn_debug
                st.session_state.bn_search_meta = {
                    "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "date_s": bn_date_s.strftime("%Y-%m-%d") if bn_date_s else "",
                    "date_e": bn_date_e.strftime("%Y-%m-%d") if bn_date_e else "",
                    "paid_at_s": bn_paid_s.strftime("%Y-%m-%d") if bn_paid_s else "",
                    "paid_at_e": bn_paid_e.strftime("%Y-%m-%d") if bn_paid_e else "",
                    "purchase_status": bn_status_label,
                }
            except Exception as e:
                st.error(f"搜尋失敗：{e}")

    bn_results = st.session_state.get("bn_results")
    bn_debug = st.session_state.get("bn_debug")
    bn_search_meta = st.session_state.get("bn_search_meta") or {}

    if bn_debug is not None:
        st.caption(
            f"🔧 除錯資訊：後台掃描到候選訂單 {bn_debug['scanned_candidates']} 筆，"
            f"符合條件（客服備註空白）{bn_debug['matched']} 筆。"
        )
        if bn_debug.get("hit_page_limit"):
            st.warning("⚠️ 掃描撞到頁數上限（80 頁）就停了，結果可能不完整，建議縮小日期範圍。")

    if bn_results is not None:
        st.markdown("#### 搜尋結果")
        if bn_search_meta.get("time"):
            st.caption(
                f"使用搜尋結果：{len(bn_results)} 筆｜搜尋時間：{bn_search_meta.get('time')}｜"
                f"付款狀態：{bn_search_meta.get('purchase_status', '')}"
            )

        if not bn_results:
            st.info("這個篩選範圍內沒有客服備註空白的儲值金訂單。")
        else:
            st.success(f"✅ 找到 {len(bn_results)} 筆客服備註空白的儲值金訂單：")
            st.dataframe(
                [
                    {
                        "訂單編號": r["order_no"],
                        "客戶姓名": r["name"],
                        "電話": r.get("phone", ""),
                        "付款狀態": r.get("purchase_status", ""),
                        "客服備註": r.get("notice", ""),
                    }
                    for r in bn_results
                ],
                use_container_width=True,
                hide_index=True,
            )

    st.markdown("**貼上獎金名單**（格式：客戶姓名：獎金人員1X獎金人員2，一行一筆）")
    bn_mapping_text = st.text_area(
        "獎金名單", height=150, key="bn_mapping_text",
        placeholder="李怡萱：李佩蓉X宋品鈞\n王小明：陳大文X林小華",
    )

    if st.button("✅ 套用到上方搜尋結果", use_container_width=True, key="bn_apply_btn", type="primary"):
        if bn_results is None:
            st.error("請先按「搜尋儲值金訂單」，確認名單後再套用。")
        elif not bn_results:
            st.error("目前搜尋結果沒有可套用的訂單。")
        elif not bn_mapping_text.strip():
            st.error("請先貼上獎金名單")
        elif not backend_email.strip() or not backend_password.strip():
            st.error("請先在上方輸入後台帳號密碼")
        else:
            name_to_order = {r["name"]: r for r in bn_results if r.get("name")}
            mapping = []
            parse_errors = []
            for line in bn_mapping_text.splitlines():
                line = line.strip()
                if not line:
                    continue
                sep = "：" if "：" in line else (":" if ":" in line else None)
                if not sep:
                    parse_errors.append(f"❌ {line}：格式錯誤，找不到「：」分隔")
                    continue
                cust_name, bonus_part = line.split(sep, 1)
                cust_name = cust_name.strip()
                bonus_names = [n.strip() for n in re.split(r"[XxＸ]", bonus_part.strip()) if n.strip()]
                matched = name_to_order.get(cust_name)
                if not matched:
                    parse_errors.append(f"❌ {line}：上方搜尋結果裡找不到客戶「{cust_name}」")
                    continue
                if not bonus_names:
                    parse_errors.append(f"❌ {line}：沒有解析到獎金人員名字")
                    continue
                mapping.append({
                    "order_no": matched["order_no"],
                    "edit_id": matched.get("edit_id", ""),
                    "cust_name": cust_name,
                    "bonus_names": bonus_names,
                })

            apply_results = []
            if mapping:
                try:
                    with st.spinner("寫入客服備註中…"):
                        apply_results = apply_bonus_notes(env, backend_email.strip(), backend_password.strip(), mapping)
                    _bn_fail = sum(1 for r in apply_results if not r.get("ok"))
                    log_execution(
                        function_name="套用儲值獎金客服備註",
                        status="失敗" if _bn_fail else "成功",
                        target="、".join(m["order_no"] for m in mapping),
                        message=f"套用 {len(mapping)} 筆，失敗 {_bn_fail} 筆",
                    )
                except Exception as e:
                    st.error(f"套用失敗：{e}")
                    log_execution(
                        function_name="套用儲值獎金客服備註", status="失敗",
                        target="、".join(m["order_no"] for m in mapping),
                        message=str(e), traceback_text=traceback.format_exc(),
                    )
            st.session_state.bn_apply_results = apply_results
            st.session_state.bn_parse_errors = parse_errors

    for err in st.session_state.get("bn_parse_errors", []) or []:
        st.error(err)

    bn_apply_results = st.session_state.get("bn_apply_results")
    if bn_apply_results:
        st.markdown("#### 套用結果")
        for r in bn_apply_results:
            if r["ok"]:
                st.success(f"✅ {r['order_no']}（{r['cust_name']}）：已寫入「獎金：{'X'.join(r['bonus_names'])}」，服務狀態已改為已處理")
            else:
                st.error(f"❌ {r['order_no']}（{r['cust_name']}）：{r['msg']}")
