# -*- coding: utf-8 -*-
"""測試機 dev 批次成單專用：執行前先複製工作表分頁，所有讀取與回填都在副本進行。

三個批次入口（批次建單／批次建單優化／批次建單優化＋雲端批次成單）共用：
- prod：完全不變，直接使用輸入的分頁。
- dev：第一次執行時把原分頁複製成「原名_devMMDD-HHMMSS」，之後同一個瀏覽器工作階段
  對同一原分頁一律沿用該副本（檢查筆數、重跑失敗列都在同一份），按「改用新的測試副本」才重建。
- dev：也可輸入先前建立的測試副本名稱，跨瀏覽器工作階段繼續使用同一分頁。
- dev 不提供「改 Google 日曆」，避免測試資料改到正式日曆。
"""
from __future__ import annotations

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


def render_notice(st, env, sheet_name: str, key: str) -> None:
    """dev 時顯示本次會使用的分頁，並提供改用新副本的按鈕。"""
    if not is_dev(env):
        return
    source = str(sheet_name or "").strip()
    if not source:
        st.info("🧪 測試機 dev：執行時會先複製輸入的工作表分頁，所有讀取與回填都在副本進行，原分頁不受影響。")
        return
    existing = st.text_input(
        "沿用既有測試工作表（選填，不另開新分頁）",
        placeholder=f"例如：{source}_dev1028-080000",
        key=f"{key}_dev_copy_existing",
        help="貼上先前由測試機建立的完整分頁名稱，再按「沿用此工作表」。",
    )
    if st.button("沿用此測試工作表", key=f"{key}_dev_copy_use", disabled=not str(existing or "").strip()):
        try:
            use_existing_copy(st, env, source, existing)
        except ValueError as exc:
            st.error(str(exc))
        else:
            st.rerun()
    copy = current_copy(st, env, source)
    if not copy:
        st.info(f"🧪 測試機 dev：按下執行時會先把「{source}」複製成測試副本，所有讀取與回填都在副本進行，原分頁不受影響。")
        return
    st.info(f"🧪 測試機 dev：沿用測試副本「{copy}」（原分頁「{source}」不受影響）。")
    if st.button("下次執行改用新的測試副本", key=f"{key}_dev_copy_reset"):
        _copies(st).pop(source, None)
        st.session_state.pop(f"{key}_dev_copy_existing", None)
        st.rerun()
