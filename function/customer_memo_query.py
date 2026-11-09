# -*- coding: utf-8 -*-
# ============================================================
# 檔名：function/customer_memo_query.py
# 功能：客人備註查詢（獨立功能，不屬於訂單客服備註）
#   依購買日期區間＋全部付款狀態查詢訂單，排除代客預訂，
#   列出客人備註非空白的訂單：訂單號碼／客人姓名／電話／地址／
#   付款狀態／客人備註／客服備註。只查詢，不修改後台。
# 更新記錄：
# 2026-11-10
# - 新增 created_from／created_to：依訂購時間（列表卡片的 YYYY-MM-DD HH:MM:SS）
#   篩選時間區間，給每日 10:00 排程（shared/customer_memo_schedule.py）使用。
# - 結果新增「服務日期」欄。
# 2026-11-09
# - 新增。後台列表翻頁、訂單明細解析沿用 memo_system/memo.py 的共用函式。
# ============================================================
import re
from datetime import datetime
from typing import Dict, List, Optional

import streamlit as st

from function.ui_common import step, info_panel
from memo_system import memo as _memo

# 代客預訂判斷：列表卡片會出現「代客預訂：專員名」；
# 客人備註為代客保留／系統保留單也是代客替客人先訂的單，一併排除。
PROXY_ROW_KEYWORDS = ("代客預訂", "代客預約")
PROXY_MEMO_KEYWORDS = ("代客保留", "系統保留單")


def is_proxy_order(item: Dict, customer_memo: str = "") -> bool:
    row_text = str(item.get("row_text", "") or "")
    if any(k in row_text for k in PROXY_ROW_KEYWORDS):
        return True
    memo_text = str(customer_memo or "")
    return any(k in memo_text for k in PROXY_MEMO_KEYWORDS)


def order_created_at(item: Dict) -> Optional[datetime]:
    """列表卡片「訂購資訊」的訂購時間（第一個 YYYY-MM-DD HH:MM:SS）。"""
    m = re.search(r"(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2}(?::\d{2})?)", str(item.get("row_text", "") or ""))
    if not m:
        return None
    text = f"{m.group(1)} {m.group(2)}"
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def search_customer_memo_orders(date_start: str, date_end: str, ui_logger=None, session=None,
                                created_from: Optional[datetime] = None,
                                created_to: Optional[datetime] = None) -> List[Dict]:
    """
    購買日期區間＋全部付款狀態，排除代客預訂，只留客人備註非空白的訂單。
    有給 created_from／created_to（naive，台北時間）時，再依訂購時間篩選 [created_from, created_to)。
    """
    log = ui_logger or (lambda m: None)

    if not date_start or not date_end:
        raise RuntimeError("請選擇完整的購買日期區間")
    start_dt, end_dt = _memo.parse_date(date_start), _memo.parse_date(date_end)
    if start_dt and end_dt and start_dt > end_dt:
        raise RuntimeError("開始日期不可晚於結束日期")

    log("===== 客人備註查詢 =====")
    log(f"購買日期區間: {date_start} ~ {date_end}")
    log("付款狀態: 全部｜排除代客預訂｜只列客人備註非空白")

    session = session or _memo.login(ui_logger=ui_logger)

    params = _memo.blank_list_params()
    params["date_s"] = date_start.replace("/", "-")
    params["date_e"] = date_end.replace("/", "-")

    log("[查詢列表] 開始抓購買日期區間內全部訂單（自動翻頁）")
    items = _memo.fetch_purchase_list_all_pages(session, params, log=log)
    log(f"[查詢列表] 主列表共 {len(items)} 筆")

    candidates = []
    proxy_count = 0
    for x in items:
        if is_proxy_order(x):
            proxy_count += 1
            continue
        dt = x.get("raw_date_obj")
        if dt and start_dt and end_dt and not (start_dt <= dt <= end_dt):
            continue
        if created_from or created_to:
            created = order_created_at(x)
            if created is None:
                continue
            if created_from and created < created_from:
                continue
            if created_to and created >= created_to:
                continue
            x["created_at"] = created
        candidates.append(x)
    log(f"[篩選] 排除代客預訂 {proxy_count} 筆，需讀取明細 {len(candidates)} 筆")

    candidates = _memo.enrich_items_from_detail(session, candidates, log=log, context_label="讀取客人備註")

    result = []
    for x in candidates:
        memo_text = str(x.get("customer_memo", "") or "").strip()
        if not memo_text or is_proxy_order(x, memo_text):
            continue
        result.append({
            "訂單號碼": x.get("order_no", ""),
            "客人姓名": x.get("name", ""),
            "電話": x.get("phone", ""),
            "地址": x.get("address", ""),
            "付款狀態": x.get("purchase_status_name", ""),
            "服務日期": _memo.display_service_date(x),
            "客人備註": memo_text,
            "客服備註": str(x.get("notice", "") or "").strip(),
        })

    result.sort(key=lambda r: r["訂單號碼"])
    log(f"✅ 客人備註非空白共 {len(result)} 筆")
    return result


def render(backend_email, backend_password, env):
    step("3", "客人備註查詢")
    info_panel("功能說明", [
        "依購買日期區間查詢，付款狀態為全部（含取消／退款）。",
        "排除代客預訂（含代客保留、系統保留單）。",
        "只列客人備註非空白的訂單，並顯示客服備註。",
        "只查詢，不會修改後台。",
    ])

    c1, c2 = st.columns(2)
    with c1:
        start = st.date_input("購買日期（開始）", value=None, key="cmq_start")
    with c2:
        end = st.date_input("購買日期（結束）", value=None, key="cmq_end")

    ready = bool(str(backend_email or "").strip()) and bool(str(backend_password or "").strip())
    run = st.button("🔍 查詢客人備註", use_container_width=True, disabled=not ready, key="cmq_run")

    if "cmq_logs" not in st.session_state:
        st.session_state.cmq_logs = []
    with st.expander("執行 LOG", expanded=True):
        log_box = st.empty()
        log_box.text("\n".join(st.session_state.cmq_logs[-3000:]) or "尚未執行")

    def ui_log(msg):
        st.session_state.cmq_logs.append(str(msg))
        log_box.text("\n".join(st.session_state.cmq_logs[-3000:]))

    if run:
        st.session_state.cmq_logs = []
        st.session_state.cmq_rows = None
        try:
            if not start or not end:
                raise ValueError("請選擇完整的購買日期區間")
            _memo.set_env(env)
            _memo.set_runtime_credentials(backend_email, backend_password)
            with st.spinner("查詢中，請稍候…"):
                st.session_state.cmq_rows = search_customer_memo_orders(
                    start.strftime("%Y/%m/%d"), end.strftime("%Y/%m/%d"), ui_logger=ui_log,
                )
        except Exception as e:
            ui_log(f"❌ 查詢錯誤：{e}")
            st.error(str(e))

    rows = st.session_state.get("cmq_rows")
    if rows is not None:
        step("4", "查詢結果")
        if not rows:
            st.info("查無客人備註非空白的訂單")
        else:
            st.metric("筆數", len(rows))
            st.dataframe(rows, use_container_width=True, hide_index=True)
