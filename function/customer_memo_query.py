# -*- coding: utf-8 -*-
# ============================================================
# 檔名：function/customer_memo_query.py
# 功能：客人備註查詢（獨立功能，不屬於訂單客服備註）
#   依購買日期區間＋全部付款狀態查詢訂單，排除代客預訂，
#   列出客人備註非空白的訂單：訂單號碼／客人姓名／電話／地址／
#   付款狀態／客人備註／客服備註。只查詢，不修改後台。
# 更新記錄：
# 2026-11-10
# - ② 客服備註需註記：「註記」欄放最前方（與排程「客服備註」分頁相同）。
# - 頁面：電話改為後台訂單管理電話搜尋連結；查詢結果分兩區，與每日 08:30 排程相同：
#   ① 客人備註非空白　② 客服備註需註記（標示 VIP 但非儲值金付款、**N- 但已非首次服務）。
# - 新增 created_from／created_to：依訂購時間（列表卡片的 YYYY-MM-DD HH:MM:SS）
#   篩選時間區間，給每日 08:30 排程（shared/customer_memo_schedule.py）使用。
# - 結果新增「服務日期」欄。
# - 抽出 fetch_window_orders（查列表＋篩選＋讀明細）；新增 find_notice_flag_orders：
#   客服備註標示 **VIP** 但付款方式不是儲值金、或有 **N-XXX** 但已非首次服務的訂單，
#   給排程貼「客服備註」分頁。
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


def fetch_window_orders(date_start: str, date_end: str, log, session,
                        created_from: Optional[datetime] = None,
                        created_to: Optional[datetime] = None) -> List[Dict]:
    """購買日期區間（＋訂購時間區間）全部付款狀態、排除代客預訂的訂單，已讀取明細。"""
    if not date_start or not date_end:
        raise RuntimeError("請選擇完整的購買日期區間")
    start_dt, end_dt = _memo.parse_date(date_start), _memo.parse_date(date_end)
    if start_dt and end_dt and start_dt > end_dt:
        raise RuntimeError("開始日期不可晚於結束日期")

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
    return _memo.enrich_items_from_detail(session, candidates, log=log, context_label="讀取訂單明細")


def customer_memo_rows(candidates: List[Dict]) -> List[Dict]:
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
    return result


def _order_number(order_no: str) -> int:
    digits = re.sub(r"\D", "", str(order_no or ""))
    return int(digits) if digits else 0


def is_returning_customer(session, item: Dict, history_cache: Dict) -> bool:
    """同電話＋同地址有更早的其他訂單（排除取消訂單／已退款）→ 已非首次服務。"""
    phone = _memo.normalize_phone(item.get("phone", ""))
    if not phone:
        return False
    if phone not in history_cache:
        history_cache[phone] = _memo.search_all_orders_by_phone(session, phone)
    me = _order_number(item.get("order_no", ""))
    for x in history_cache[phone]:
        if x.get("order_no") == item.get("order_no") or x.get("purchase_status") in ("2", "3"):
            continue
        if not _memo.same_address(x.get("address", ""), item.get("address", "")):
            continue
        if _order_number(x.get("order_no", "")) < me:
            return True
    return False


def find_notice_flag_orders(candidates: List[Dict], session, log=None) -> List[Dict]:
    """
    客服備註本來就有資料，但：
    - 標示 **VIP** 而本次付款方式不是儲值金
    - 有 **N-XXX** 但已非首次服務
    回傳要貼「客服備註」分頁的列（註記文字與訂單客服備註頁面相同）。
    """
    log = log or (lambda m: None)
    history_cache: Dict = {}
    result = []
    for x in candidates:
        own = _memo.strip_change_block(x.get("notice", ""))
        if not own:
            continue
        has_vip = _memo.VIP_TAG in own
        has_n = bool(_memo.N_TAG_RE.search(own))
        if not has_vip and not has_n:
            continue
        returning = is_returning_customer(session, x, history_cache) if has_n else False
        note = _memo.service_change_text({}, {"notice": own, "payway": x.get("payway", "")}, returning)
        if not note:
            continue
        result.append({
            "註記": note.replace("\n", "；"),
            "訂單號碼": x.get("order_no", ""),
            "客人姓名": x.get("name", ""),
            "電話": x.get("phone", ""),
            "服務日期": _memo.display_service_date(x),
            "付款方式": x.get("payway", ""),
            "客服備註": own,
        })
    result.sort(key=lambda r: r["訂單號碼"])
    log(f"✅ 客服備註需註記共 {len(result)} 筆")
    return result


def search_customer_memo_orders(date_start: str, date_end: str, ui_logger=None, session=None,
                                created_from: Optional[datetime] = None,
                                created_to: Optional[datetime] = None) -> List[Dict]:
    """
    購買日期區間＋全部付款狀態，排除代客預訂，只留客人備註非空白的訂單。
    有給 created_from／created_to（naive，台北時間）時，再依訂購時間篩選 [created_from, created_to)。
    """
    log = ui_logger or (lambda m: None)
    log("===== 客人備註查詢 =====")
    log(f"購買日期區間: {date_start} ~ {date_end}")
    log("付款狀態: 全部｜排除代客預訂｜只列客人備註非空白")
    session = session or _memo.login(ui_logger=ui_logger)
    candidates = fetch_window_orders(date_start, date_end, log, session, created_from, created_to)
    result = customer_memo_rows(candidates)
    log(f"✅ 客人備註非空白共 {len(result)} 筆")
    return result


def phone_search_url(phone: str) -> str:
    """後台訂單管理用電話搜尋的結果頁（依目前環境）。"""
    from urllib.parse import urlencode

    digits = re.sub(r"\D", "", str(phone or ""))
    if not digits:
        return ""
    params = _memo.blank_list_params()
    params["phone"] = digits
    return f"{_memo.PURCHASE_URL}?{urlencode(params)}"


def _show_table(rows: List[Dict]):
    data = [{**r, "電話": phone_search_url(r.get("電話", ""))} for r in rows]
    st.dataframe(
        data, use_container_width=True, hide_index=True,
        column_config={"電話": st.column_config.LinkColumn("電話", display_text=r"phone=(\d+)")},
    )


def render(backend_email, backend_password, env):
    step("3", "客人備註查詢")
    info_panel("功能說明", [
        "依購買日期區間查詢，付款狀態為全部（含取消／退款），排除代客預訂（含代客保留、系統保留單）。",
        "① 客人備註非空白的訂單，並顯示客服備註。",
        "② 客服備註需註記：客服備註標示 **VIP** 但付款方式不是儲值金，或有 **N-** 但已非首次服務。",
        "電話可直接點開後台訂單管理的電話搜尋結果。只查詢，不會修改後台。",
        "每日 08:30 排程（上班日，區間截到 08:00）會用相同規則貼到台北／台中內勤工作表單的「客人備註」「客服備註」分頁。",
    ])

    c1, c2 = st.columns(2)
    with c1:
        start = st.date_input("購買日期（開始）", value=None, key="cmq_start")
    with c2:
        end = st.date_input("購買日期（結束）", value=None, key="cmq_end")

    ready = bool(str(backend_email or "").strip()) and bool(str(backend_password or "").strip())
    run = st.button("🔍 查詢", use_container_width=True, disabled=not ready, key="cmq_run")

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
        st.session_state.cmq_notice_rows = None
        try:
            if not start or not end:
                raise ValueError("請選擇完整的購買日期區間")
            _memo.set_env(env)
            _memo.set_runtime_credentials(backend_email, backend_password)
            with st.spinner("查詢中，請稍候…"):
                ui_log("===== 客人備註／客服備註查詢 =====")
                ui_log(f"購買日期區間: {start:%Y/%m/%d} ~ {end:%Y/%m/%d}｜付款狀態全部｜排除代客預訂")
                session = _memo.login(ui_logger=ui_log)
                candidates = fetch_window_orders(start.strftime("%Y/%m/%d"), end.strftime("%Y/%m/%d"), ui_log, session)
                st.session_state.cmq_rows = customer_memo_rows(candidates)
                ui_log(f"✅ 客人備註非空白共 {len(st.session_state.cmq_rows)} 筆")
                ui_log("[客服備註] 檢查 VIP 非儲值金、N- 已非首次服務")
                st.session_state.cmq_notice_rows = find_notice_flag_orders(candidates, session, log=ui_log)
        except Exception as e:
            ui_log(f"❌ 查詢錯誤：{e}")
            st.error(str(e))

    rows = st.session_state.get("cmq_rows")
    notice_rows = st.session_state.get("cmq_notice_rows")
    if rows is not None:
        step("4", "查詢結果")
        st.markdown(f"### ① 客人備註非空白（{len(rows)} 筆）")
        if rows:
            _show_table(rows)
        else:
            st.info("查無客人備註非空白的訂單")
        if notice_rows is not None:
            st.markdown(f"### ② 客服備註需註記（{len(notice_rows)} 筆）")
            if notice_rows:
                _show_table(notice_rows)
            else:
                st.info("查無需要註記的客服備註")
