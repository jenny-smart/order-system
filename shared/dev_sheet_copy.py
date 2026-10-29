# -*- coding: utf-8 -*-
"""測試機 dev 批次成單專用：執行前先複製工作表分頁，所有讀取與回填都在副本進行。

三個批次入口（批次建單／批次建單優化／批次建單優化＋雲端批次成單）共用：
- prod：完全不變，直接使用輸入的分頁。
- dev：第一次執行時把原分頁複製成「原名_devMMDD-HHMMSS」，之後同一個瀏覽器工作階段
  對同一原分頁一律沿用該副本（檢查筆數、重跑失敗列都在同一份），按「改用新的測試副本」才重建。
- dev：也可輸入先前建立的測試副本名稱，跨瀏覽器工作階段繼續使用同一分頁。
- dev 不提供「改 Google 日曆」，避免測試資料改到正式日曆。
- dev：原分頁（排程工作表）更新後，可「以最新排程更新此測試副本」：重新複製原分頁，
  把舊副本已成單（有訂單編號）的測試結果依日曆事件ID＋日期＋開始時間帶到新副本，副本名稱不變；
  只帶測試機後台付款狀態「已付款」的訂單，取消／退款／待付款的列留空可重新成單。
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

TAIPEI = timezone(timedelta(hours=8))
ALL_ACTIONS = ["建單", "寄確認信", "改 Google 日曆"]
DEV_ACTIONS = ["建單", "寄確認信"]
_STATE_KEY = "_dev_sheet_copies"


def is_dev(env) -> bool:
    return str(env or "").strip().lower() == "dev"


def action_options(env) -> list[str]:
    return list(DEV_ACTIONS) if is_dev(env) else list(ALL_ACTIONS)


def default_actions(env) -> list[str]:
    return ["建單"] if is_dev(env) else list(ALL_ACTIONS)


def copy_title(source: str, now: datetime | None = None) -> str:
    now = now or datetime.now(TAIPEI)
    return f"{source}_dev{now:%m%d-%H%M%S}"


def create_dev_copy(source: str) -> str:
    """在同一份 Google Sheet 內複製分頁，回傳副本名稱。"""
    import orders

    source = str(source or "").strip()
    if not source:
        raise ValueError("請輸入工作表名稱。")
    client = orders.build_gsheet_client()
    spreadsheet = client.open_by_key(orders.GOOGLE_SHEET_ID)
    try:
        worksheet = spreadsheet.worksheet(source)
    except Exception as exc:
        if type(exc).__name__ == "WorksheetNotFound":
            raise ValueError(f"找不到工作表分頁「{source}」，無法建立測試副本。") from exc
        raise
    title = copy_title(source)
    spreadsheet.duplicate_sheet(worksheet.id, new_sheet_name=title)
    return title


# 測試機成單會回填的欄位：I 狀態、K:AG 成單結果（訂單編號在 M）。
_STATUS_COL, _RESULT_START, _RESULT_END, _ORDER_COL = 8, 10, 33, 12
_EVENT_ID_HEADER = "日曆事件ID"


def _cell(row, index) -> str:
    return str(row[index]).strip() if index < len(row) and row[index] is not None else ""


def _row_key(row, event_col):
    """同一列的對應鍵：日曆事件ID（沒有時用 姓名＋電話＋地址）＋日期＋開始時間。

    日期或時段改了就不算同一列：測試訂單是依舊日期成立的，不能帶到新日期。
    """
    ymd = re.match(r"(\d{4})\D(\d{1,2})\D(\d{1,2})", _cell(row, 5))
    date = f"{ymd.group(1)}{int(ymd.group(2)):02d}{int(ymd.group(3)):02d}" if ymd else _cell(row, 5)
    slot = (date, _cell(row, 6).zfill(5))
    event_id = _cell(row, event_col) if event_col is not None else ""
    if event_id:
        return ("id", event_id) + slot
    digits = re.sub(r"\D", "", _cell(row, 3))
    return ("who", re.sub(r"\s+", "", _cell(row, 2)), digits[-9:], re.sub(r"\s+", "", _cell(row, 4))) + slot


def _event_col(header):
    matches = [i for i, name in enumerate(header) if str(name).strip() == _EVENT_ID_HEADER and i >= 30]
    return matches[-1] if matches else None


PAID = "已付款"


def carry_booked_rows(old_values, new_values, statuses=None):
    """舊副本已成單的列帶到新排程：回傳（儲存格更新, 要附加到最下方的列, 帶過去的列數, 未帶的訂單）。

    statuses＝{訂單編號: 後台付款狀態}；有提供時只帶「已付款」的訂單，其餘列在「未帶的訂單」。
    """
    old_header, new_header = (old_values or [[]])[0], (new_values or [[]])[0]
    old_event, new_event = _event_col(old_header), _event_col(new_header)
    new_rows = {}
    for row_num, row in enumerate(new_values[1:], 2):
        if any(_cell(row, i) for i in range(9)):
            new_rows.setdefault(_row_key(row, new_event), row_num)
    updates, appended, carried, dropped = [], [], 0, []
    for row in old_values[1:]:
        order_no = _cell(row, _ORDER_COL)
        if not order_no:
            continue
        if statuses is not None and statuses.get(order_no) != PAID:
            dropped.append((order_no, statuses.get(order_no) or "後台查無"))
            continue
        target = new_rows.get(_row_key(row, old_event))
        if target and not _cell(new_values[target - 1], _ORDER_COL):
            padded = list(row) + [""] * (_RESULT_END - len(row))
            updates.append({"range": f"I{target}", "values": [[padded[_STATUS_COL]]]})
            updates.append({"range": f"K{target}:AG{target}", "values": [padded[_RESULT_START:_RESULT_END]]})
            carried += 1
        elif not target:
            appended.append(list(row))
    return updates, appended, carried, dropped


def backend_order_statuses(order_nos, region="", credentials=("", "")) -> dict:
    """登入測試機後台，依訂單編號查付款狀態（已付款／待付款／取消訂單／已退款）；查無的不列入。"""
    import requests
    import orders
    from accounts import ACCOUNTS
    from shared.batch_booking_safety import _configure_runtime

    order_nos = list(dict.fromkeys(str(x).strip() for x in order_nos if str(x).strip()))
    if not order_nos:
        return {}
    account = ACCOUNTS.get(region) or {}
    email = str(account.get("email") or credentials[0] or "").strip()
    password = str(account.get("password") or credentials[1] or "").strip()
    if not email or not password:
        raise RuntimeError("查訂單付款狀態需要測試機後台帳號密碼，請先填寫後台帳號密碼。")
    _configure_runtime("dev")
    session = requests.Session()
    if not orders.login(session, email, password):
        raise RuntimeError("測試機後台登入失敗，無法確認訂單付款狀態。")
    statuses = {}
    for order_no in order_nos:
        params = dict(orders.PURCHASE_FILTER_PARAMS_TEMPLATE)
        params["orderNo"] = order_no
        resp = session.get(orders.PURCHASE_URL, params=params, headers=orders.HEADERS, allow_redirects=True)
        if resp.status_code != 200:
            raise RuntimeError(f"查詢訂單 {order_no} 失敗：HTTP {resp.status_code}")
        for card in orders.extract_order_cards_from_purchase_html(resp.text):
            if str(card.get("order_no") or "").strip() == order_no:
                lines = card.get("lines", [])
                status = orders.card_payment_status(lines)
                statuses[order_no] = (status if status != PAID else "已取消") if orders.is_void_card(lines) else status
                break
    if not statuses:
        raise RuntimeError("測試機後台查不到任何一筆副本內的訂單，請確認是用測試機帳號；原副本未變更。")
    return statuses


def refresh_dev_copy(source: str, copy_name: str, status_lookup=None) -> dict:
    """以原分頁最新內容重建測試副本（名稱不變），保留舊副本已成單（已付款）的測試結果。

    status_lookup(訂單編號清單) → {訂單編號: 付款狀態}；None＝不查後台，全部帶過去。
    """
    import orders

    source, copy_name = str(source or "").strip(), str(copy_name or "").strip()
    if not copy_name.startswith(f"{source}_dev"):
        raise ValueError(f"測試工作表名稱必須以「{source}_dev」開頭，以免改到正式分頁。")
    spreadsheet = orders.build_gsheet_client().open_by_key(orders.GOOGLE_SHEET_ID)
    original = spreadsheet.worksheet(source)
    old = spreadsheet.worksheet(copy_name)
    old_values = old.get_values(value_render_option="FORMULA")
    # 先查後台再複製，查詢失敗時不會留下做到一半的分頁。
    statuses = status_lookup([_cell(row, _ORDER_COL) for row in old_values[1:]]) if status_lookup else None
    fresh = spreadsheet.duplicate_sheet(original.id, insert_sheet_index=getattr(old, "index", None),
                                        new_sheet_name=f"{copy_name}_更新中")
    try:
        new_values = fresh.get_values(value_render_option="FORMULA")
        updates, appended, carried, dropped = carry_booked_rows(old_values, new_values, statuses)
        if appended:
            start = len(new_values) + 1
            end = start + len(appended) - 1
            if fresh.row_count < end:
                fresh.resize(rows=end + 10)
            width = max(len(row) for row in appended)
            updates.append({"range": f"A{start}", "values": [row + [""] * (width - len(row)) for row in appended]})
        if updates:
            fresh.batch_update(updates, value_input_option="USER_ENTERED")
        if appended:
            # 電話以文字寫入，避免開頭的 0 被試算表吃掉。
            fresh.batch_update([{"range": f"D{start + i}", "values": [[_cell(row, 3)]]}
                                for i, row in enumerate(appended)], value_input_option="RAW")
    except Exception:
        # 舊副本還沒動，刪掉做到一半的新分頁即可。
        spreadsheet.del_worksheet(fresh)
        raise
    spreadsheet.del_worksheet(old)
    fresh.update_title(copy_name)
    return {"carried": carried, "appended": len(appended), "dropped": dropped}


def _copies(st) -> dict:
    store = st.session_state.get(_STATE_KEY)
    if not isinstance(store, dict):
        store = {}
        st.session_state[_STATE_KEY] = store
    return store


def current_copy(st, env, sheet_name: str) -> str:
    """dev 已建立的副本名稱；尚未建立或非 dev 回傳空字串。"""
    if not is_dev(env):
        return ""
    return str(_copies(st).get(str(sheet_name or "").strip(), "") or "")


def use_existing_copy(st, env, sheet_name: str, copy_name: str) -> str:
    """dev 指定既有的系統測試副本；避免誤把正式原分頁當成測試分頁。"""
    source = str(sheet_name or "").strip()
    target = str(copy_name or "").strip()
    if not is_dev(env):
        raise ValueError("只有測試機 dev 可以沿用測試工作表。")
    if not source:
        raise ValueError("請先輸入原工作表名稱。")
    if not target:
        raise ValueError("請輸入既有測試工作表名稱。")
    if not target.startswith(f"{source}_dev"):
        raise ValueError(f"測試工作表名稱必須以「{source}_dev」開頭，以免誤寫正式分頁。")
    _copies(st)[source] = target
    return target


def read_sheet(st, env, sheet_name: str) -> str:
    """只讀用途（檢查筆數、篩選選項）：dev 已有副本就讀副本，否則讀原分頁。"""
    return current_copy(st, env, sheet_name) or str(sheet_name or "").strip()


def resolve_run_sheet(st, env, sheet_name: str, creator=None) -> str:
    """實際執行用：prod 回傳原分頁；dev 回傳副本（沒有就先建立）。"""
    source = str(sheet_name or "").strip()
    if not is_dev(env) or not source:
        return source
    store = _copies(st)
    if not store.get(source):
        store[source] = (creator or create_dev_copy)(source)
    return store[source]


def render_notice(st, env, sheet_name: str, key: str, region: str = "", credentials=("", "")) -> None:
    """dev 時顯示本次使用的測試副本：沿用既有副本、以最新排程更新、改用新副本。"""
    if not is_dev(env):
        return
    source = str(sheet_name or "").strip()
    if not source:
        st.caption("🧪 測試機：執行時會先複製工作表分頁，讀取與回填都在副本，原分頁不受影響。")
        return
    box = st.container(border=True)
    copy = current_copy(st, env, source)
    if not copy:
        box.markdown(f"🧪 **測試副本**：尚未指定，執行時自動把「{source}」複製一份。要接續先前的測試，請貼上副本名稱：")
        c1, c2 = box.columns([3, 1], vertical_alignment="bottom")
        existing = c1.text_input("既有測試副本名稱", placeholder=f"例如：{source}_dev1028-080000",
                                 key=f"{key}_dev_copy_existing", label_visibility="collapsed")
        if c2.button("沿用此副本", key=f"{key}_dev_copy_use", disabled=not str(existing or "").strip(),
                     use_container_width=True):
            try:
                use_existing_copy(st, env, source, existing)
            except ValueError as exc:
                box.error(str(exc))
            else:
                st.rerun()
        return
    box.markdown(f"🧪 **測試副本**：{copy}（原分頁「{source}」不受影響）")
    c1, c2 = box.columns(2)
    refresh = c1.button("以最新排程更新此副本", key=f"{key}_dev_copy_refresh", use_container_width=True,
                        help=f"「{source}」更新後使用：重新複製最新排程；日曆事件ID、日期、開始時間都相同，"
                             "且測試機後台「已付款」的列，保留訂單編號與結果，副本名稱不變。")
    if c2.button("改用新的測試副本", key=f"{key}_dev_copy_reset", use_container_width=True):
        _copies(st).pop(source, None)
        st.session_state.pop(f"{key}_dev_copy_existing", None)
        st.rerun()
    if refresh:
        try:
            result = refresh_dev_copy(source, copy, lambda nos: backend_order_statuses(nos, region, credentials))
        except Exception as exc:
            box.error(f"更新測試副本失敗：{exc}（原副本未變更）")
        else:
            box.success(f"已更新：保留已付款訂單 {result['carried']} 列"
                        + (f"；日期／時段已改的已付款訂單 {result['appended']} 列放在最下方" if result["appended"] else "") + "。")
            if result["dropped"]:
                box.info("非已付款、未帶入（該列可重新成單）："
                         + "、".join(f"{no}（{status}）" for no, status in result["dropped"]))
