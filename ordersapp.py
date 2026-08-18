# ============================================================
# 檔名：ordersapp.py
# 版本：v8.77
# 模組：服務訂單系統主畫面／統一功能選單
# 最後更新：2026-08-19
#
# v8.77
# - 新增「批次建單優化」：日期區間 × 複數時段批次查班及建單，不影響舊批次建單。
# - 新增「檸檬保留單建單」「檸檬保留單取消」正式選單入口。
# - memo 功能直接改走 function/memo_router.py。
# - VIP Calendar patch 改由單一 patch bundle 套用。
# ============================================================
# -*- coding: utf-8 -*-
__version__ = "8.77"

import streamlit as st
from datetime import date, timedelta

from env import GOOGLE_CALENDAR_MAP
from accounts import ACCOUNTS
from function.ui_common import step, info_panel
from function import consistency_check as _consistency_check_page
from function import calendar_check as _calendar_check_page
from function import cleaner_next_day_reminder as _cleaner_next_day_page
from function import weekend_reminder_page as _weekend_reminder_page
from function import no_line_link_search as _no_line_link_page
from function import bonus_note as _bonus_note_page
from function import order_creation as _order_creation_page
from function import line_notice_generator as _line_notice_page
from function import next_appointment_list as _next_appointment_page
from function import next_service_time_updater as _next_service_time_page
from function import member_preferences as _member_preferences_page
from function import batch_booking_optimized as _batch_booking_optimized_page
from function import reserve_menu as _reserve_menu_page
from function.memo_router import render as _render_memo

try:
    import quick_order
except Exception as e:
    st.error(f"quick_order.py 載入失敗：{type(e).__name__}: {e}")
    st.stop()

st.set_page_config(page_title="服務訂單系統", page_icon="🧹", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;700&family=Space+Grotesk:wght@500;700&display=swap');
:root {
    --lemon: #F5C518; --lemon-dark: #D4A017; --lemon-soft: #FFFBEA;
    --lemon-mid: #FFF3C4; --charcoal: #1C1C1E; --ink: #3A3A3C;
    --muted: #8E8E93; --border: #E5E5EA; --surface: #FFFFFF;
    --success: #34C759; --danger: #FF3B30; --radius: 14px;
}
html, body, [class*="css"] { font-family: 'Noto Sans TC', sans-serif; color: var(--charcoal); }
#MainMenu, footer, header { visibility: hidden; }
[data-testid="stAppViewContainer"] { background: #FAFAFA; }
.block-container { padding-top: 2rem !important; padding-bottom: 2rem !important; max-width: 1180px !important; }
.hero { background: linear-gradient(135deg, #FFFDF0 0%, #FFFBEA 100%); border: 1.5px solid var(--lemon-mid); border-radius: var(--radius); padding: 2rem 2.5rem 1.6rem; margin-bottom: 2rem; display: flex; align-items: center; gap: 1.2rem; box-shadow: 0 2px 12px rgba(245,197,24,0.10); }
.hero-emoji { font-size: 3rem; line-height: 1; }
.hero-title { font-family: 'Space Grotesk', sans-serif; font-size: 1.9rem; font-weight: 700; color: var(--charcoal); letter-spacing: -0.5px; }
.hero-sub { color: var(--ink); font-size: 0.92rem; margin-top: 0.3rem; opacity: 0.78; }
.step-pill { display: inline-flex; align-items: center; gap: 0.5rem; background: var(--lemon-mid); border: 1.5px solid var(--lemon); border-radius: 30px; padding: 0.28rem 0.9rem; font-size: 0.78rem; font-weight: 700; color: var(--charcoal); margin-bottom: 0.9rem; letter-spacing: 0.02em; }
.step-num { background: var(--lemon); border-radius: 50%; width: 20px; height: 20px; display: inline-flex; align-items: center; justify-content: center; font-size: 0.72rem; font-weight: 700; }
.sec-label { font-size: 12px; font-weight: 700; color: var(--muted); letter-spacing: .04em; margin-bottom: 8px; }
.hint-box { background: var(--lemon-soft); border-left: 4px solid var(--lemon); border-radius: 0 8px 8px 0; padding: 0.75rem 1rem; font-size: 0.9rem; color: var(--ink); margin-top: 0.6rem; }
[data-testid="stTextInput"] label, [data-testid="stNumberInput"] label, [data-testid="stSelectbox"] label, [data-testid="stMultiSelect"] label, [data-testid="stDateInput"] label, [data-testid="stRadio"] label { font-size: 13px !important; color: var(--ink) !important; font-weight: 700 !important; }
[data-testid="stTextInput"] input, [data-testid="stNumberInput"] input, [data-testid="stSelectbox"] > div > div, [data-testid="stMultiSelect"] > div > div, [data-testid="stDateInput"] input { border-radius: 10px !important; border: 1.5px solid var(--border) !important; background: white !important; font-size: 15px !important; }
[data-testid="stButton"] > button { background: var(--lemon) !important; color: var(--charcoal) !important; border: none !important; border-radius: 10px !important; font-size: 15px !important; font-weight: 700 !important; padding: 0.55rem 1.2rem !important; box-shadow: 0 2px 10px rgba(245,197,24,0.28) !important; }
[data-testid="stButton"] > button:hover { background: var(--lemon-dark) !important; transform: translateY(-1px) !important; }
[data-testid="stButton"] > button:disabled { background: #D1D5DB !important; color: #777 !important; }
[data-testid="stAlert"] { border-radius: 10px !important; font-size: 14px !important; }
hr { border-color: #e8e8e8 !important; margin: 1.4rem 0 !important; }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="hero">
  <div class="hero-emoji">🧹</div>
  <div>
    <div class="hero-title">服務訂單系統</div>
    <div class="hero-sub">支援批次建單、保留單、舊客／新客建單、LINE 通知、確認信與 Google 日曆同步。</div>
  </div>
</div>
""", unsafe_allow_html=True)

step("1", "登入與環境設定")
col_e, col_p, col_env = st.columns([3.2, 3.2, 1.2])
with col_e:
    backend_email = st.text_input("後台帳號")
with col_p:
    backend_password = st.text_input("後台密碼", type="password")
with col_env:
    env_label = st.selectbox("環境", ["prod（正式機 backend）", "dev（測試機 backend-dev）"], index=0)
    env = "dev" if env_label.startswith("dev") else "prod"

st.markdown("<hr>", unsafe_allow_html=True)
step("2", "功能選單")

FUNCTION_OPTIONS = [
    # ---------- A. 建單／成單流程 ----------
    ("批次建單：從 Google Sheet 逐列建立訂單、寄確認信、同步日曆。", "orders", "批次建單（Google Sheet）"),
    ("批次建單優化：會員一次選日期區間與多個時段，集中查班後批次建立訂單。", "orders", "批次建單優化"),
    ("檸檬保留單建單：依日期區間、時段與保留率分析班表並批次成立保留單。", "orders", "檸檬保留單建單"),
    ("建立舊客訂單：電話查會員、帶入歷史資料建單；需求搜尋整合在此流程內。", "orders", "建立舊客訂單"),
    ("建立新客訂單：貼上制式文字拆成欄位，供客服修改後建立訂單。", "orders", "建立新客訂單"),
    ("建立儲值金訂單：客人自行儲值／購買金額建單，付款方式與發票自動沿用會員最近一次設定。", "orders", "建立儲值金訂單"),
    ("訂單轉換：原單轉多筆新單，各建折價券，混合配班。", "orders", "訂單轉換"),
    ("儲值金補價差：兩段式流程，先建儲值金清零單，再建客付補差價單。", "orders", "儲值金補價差"),
    # ---------- B. 訂單附屬功能 ----------
    ("取消訂單：依電話、服務月份／日期區間與付款狀態搜尋訂單，處理退款與備註。", "orders", "取消訂單"),
    ("檸檬保留單取消：依期間、複選時段與客人備註安全篩選並批次取消保留單。", "orders", "檸檬保留單取消"),
    ("VIP 訂單／Google 日曆同步：同時查詢後台訂單與 Google 日曆，支援異動、取消、暫停與日曆更新。", "orders", "VIP 訂單／Google 日曆同步"),
    ("訂單客服備註：舊客回購備註回填、新成單提醒建立、客服備忘錄整理。", "memo", "訂單客服備註"),
    ("儲值獎金備註：搜尋儲值金訂單，依姓名把獎金專員名字加進客服備註。", "orders", "儲值獎金備註"),
    ("排班管理：排班匯入、檸檬人空檔查詢、清空排班。", "memo", "排班管理"),
    ("評估文字工具：貼入評估內容，自動產生含時數／移除時數兩種版本文字。", "memo", "評估文字工具"),
    # ---------- C. 稽核比對工具 ----------
    ("雙向訂單檢查：Google Sheet vs. 後台，針對已有訂單編號的工作表跟後台做雙向比對。", "orders", "雙向訂單檢查"),
    ("後台／Google 日曆雙向比對：後台 vs. Google 日曆，以事件時間與顏色做雙向比對。", "orders", "後台／Google 日曆雙向比對"),
    ("查詢無LINE連結訂單：搜尋訂購資訊裡沒有LINE連結的訂單。", "orders", "查詢無LINE連結訂單"),
    # ---------- D. LINE 通知／提醒 ----------
    ("LINE 通知產生器：用已成立訂單編號補產生通知訊息，支援多筆同時產生。", "orders", "LINE 通知產生器"),
    ("週末服務 LINE 提醒：篩選週末已付款訂單、產生提醒訊息並追蹤回覆。", "orders", "週末服務 LINE 提醒"),
    ("專員隔日上班提醒：依服務日期彙整每位專員班次與 LINE 聊天連結。", "orders", "專員隔日上班提醒"),
    # ---------- E. 會員／客戶管理 ----------
    ("會員喜好設定：輸入電話查會員，設定喜愛專員性別與喜愛／不喜愛專員。", "orders", "會員喜好設定"),
    ("整理預約下次服務：搜尋評價日期區間內有填預約下次服務的評價並整理名單。", "orders", "整理預約下次服務"),
    ("更新建議下次服務時間：依地址＋電話查後台最近3次服務日期並寫回 Sheet。", "orders", "更新建議下次服務時間"),
    # ---------- F. 財務功能 ----------
    ("台北/台中區對帳：ATM 待付款清單查詢、配對銀行明細、更新系統對帳。", "memo", "台北/台中區對帳"),
    ("桃園/新竹區對帳：依付款日期、付款狀態搜尋 ATM 訂單並比對銀行明細。", "memo", "桃園/新竹區對帳"),
    ("服務異動：車馬費／異動費、服務前後加減時、退款與客訴退款等分階段處理。", "memo", "服務異動"),
]

_MEMO_SECTION_MAP = {
    "訂單客服備註": "📋 客服作業",
    "排班管理": "📅 排班管理",
    "評估文字工具": "📐 評估文字工具",
    "台北/台中區對帳": "💰 財務對帳",
    "桃園/新竹區對帳": "💳 付款後5碼及星和診所比對",
    "服務異動": "🔄 服務異動",
}

_CATEGORY_HEADERS_BY_INDEX = {
    0: "A. 建單／成單流程",
    8: "B. 訂單附屬功能",
    15: "C. 稽核比對工具",
    18: "D. LINE 通知／提醒",
    21: "E. 會員／客戶管理",
    24: "F. 財務功能",
}
_menu_display_options = []
_menu_option_targets = []
_menu_counter = 0
for _opt_idx, _opt in enumerate(FUNCTION_OPTIONS):
    if _opt_idx in _CATEGORY_HEADERS_BY_INDEX:
        _menu_display_options.append(f"── {_CATEGORY_HEADERS_BY_INDEX[_opt_idx]} ──")
        _menu_option_targets.append(None)
    _menu_counter += 1
    _menu_display_options.append(f"{_menu_counter}. {_opt[0]}")
    _menu_option_targets.append(_opt_idx)

_menu_default_index = next(i for i, t in enumerate(_menu_option_targets) if t is not None)
selected_label = st.selectbox("功能選單", _menu_display_options, index=_menu_default_index, key="unified_function_select")
_selected_pos = _menu_display_options.index(selected_label)
_selected_target = _menu_option_targets[_selected_pos]
if _selected_target is None:
    st.info("這是分類標題，請改選下面的功能項目。")
    st.stop()
_selected_option = FUNCTION_OPTIONS[_selected_target]
_system_key, mode = _selected_option[1], _selected_option[2]

st.markdown("<hr>", unsafe_allow_html=True)

if _system_key == "memo":
    _render_memo(_MEMO_SECTION_MAP.get(mode, mode), backend_email, backend_password, env)
    st.stop()

if mode == "批次建單優化":
    _batch_booking_optimized_page.render(backend_email, backend_password, env)
    st.stop()

if mode == "檸檬保留單建單":
    _reserve_menu_page.render_create(backend_email, backend_password, env)
    st.stop()

if mode == "檸檬保留單取消":
    _reserve_menu_page.render_cancel(backend_email, backend_password, env)
    st.stop()

if mode == "取消訂單":
    from function.cancel_order import render_cancel_order
    step("3", "取消訂單")
    info_panel("功能說明", [
        "依手機號碼搜尋一般訂單，不限定 VIP。",
        "服務日期可用月份或日期區間查詢。",
        "付款狀態可選已付款或待付款。",
        "搜尋後可勾選一筆或多筆訂單處理取消、退款與備註。",
    ])
    render_cancel_order(backend_email.strip(), backend_password.strip(), env)
    st.stop()

if mode == "VIP 訂單／Google 日曆同步":
    import calendar as _calendar
    import function.vip_calendar_sync as _vcs
    from function.vip_calendar_patch_bundle import apply_all as _apply_vip_patches

    if not getattr(_vcs, "_ordersapp_vip_patches_applied", False):
        _apply_vip_patches(_vcs)
        _vcs._ordersapp_vip_patches_applied = True

    step("3", "VIP 訂單／Google 日曆同步")
    info_panel("功能說明", [
        "依 VIP 客戶手機號碼及月份／日期區間，同時查詢後台訂單與 Google 日曆。",
        "支援異動日期／時段、取消／暫停、新增或修改日曆事件。",
        "異動或新增訂單時會先確認後台該日期／時段可用。",
        "Google 日曆顏色：紫色＝未安排、黃色＝已安排、綠色＝暫停。",
    ])
    _query_mode = st.radio("查詢方式", ["月份", "日期區間"], horizontal=True, key="vipcal_query_mode")
    _today = date.today()
    if _query_mode == "月份":
        _year_options = list(range(_today.year - 1, _today.year + 3))
        _q1, _q2 = st.columns(2)
        with _q1:
            _query_year = st.selectbox("年份", _year_options, index=_year_options.index(_today.year), key="vipcal_query_year")
        with _q2:
            _query_month = st.selectbox("月份", list(range(1, 13)), index=_today.month - 1, format_func=lambda m: f"{m} 月", key="vipcal_query_month")
        _last_day = _calendar.monthrange(int(_query_year), int(_query_month))[1]
        _query_date_s = date(int(_query_year), int(_query_month), 1)
        _query_date_e = date(int(_query_year), int(_query_month), _last_day)
    else:
        _r1, _r2 = st.columns(2)
        with _r1:
            _query_date_s = st.date_input("查詢起日", value=_today - timedelta(days=30), key="vipcal_range_s")
        with _r2:
            _query_date_e = st.date_input("查詢迄日", value=_today + timedelta(days=90), key="vipcal_range_e")
        if _query_date_s > _query_date_e:
            st.error("查詢起日不可晚於查詢迄日")
            st.stop()
    st.session_state["vipcal_query_date_s"] = _query_date_s.isoformat()
    st.session_state["vipcal_query_date_e"] = _query_date_e.isoformat()
    st.caption(f"查詢範圍：{_query_date_s.isoformat()} ～ {_query_date_e.isoformat()}")
    _vcs.render_vip_calendar_sync(backend_email.strip(), backend_password.strip(), env)
    st.stop()

if mode == "批次建單（Google Sheet）":
    _order_creation_page.render_batch(backend_email, backend_password, env)
elif mode == "建立舊客訂單":
    _order_creation_page.render_old_customer(backend_email, backend_password, env)
elif mode == "建立新客訂單":
    _order_creation_page.render_new_customer(backend_email, backend_password, env)
elif mode == "建立儲值金訂單":
    _order_creation_page.render_stored_value_order(backend_email, backend_password, env)
elif mode == "訂單轉換":
    _order_creation_page.render_order_conversion(backend_email, backend_password, env)
elif mode == "儲值金補價差":
    _order_creation_page.render_topup_diff(backend_email, backend_password, env)
elif mode == "雙向訂單檢查":
    _consistency_check_page.render(backend_email, backend_password, env, ACCOUNTS)
elif mode == "後台／Google 日曆雙向比對":
    _calendar_check_page.render(backend_email, backend_password, env, GOOGLE_CALENDAR_MAP)
elif mode == "專員隔日上班提醒":
    _cleaner_next_day_page.render(backend_email, backend_password, env)
elif mode == "週末服務 LINE 提醒":
    _weekend_reminder_page.render(backend_email, backend_password, env)
elif mode == "查詢無LINE連結訂單":
    _no_line_link_page.render(backend_email, backend_password, env)
elif mode == "儲值獎金備註":
    _bonus_note_page.render(backend_email, backend_password, env)
elif mode == "LINE 通知產生器":
    _line_notice_page.render(backend_email, backend_password, env)
elif mode == "整理預約下次服務":
    _next_appointment_page.render(backend_email, backend_password, env)
elif mode == "更新建議下次服務時間":
    _next_service_time_page.render(backend_email, backend_password, env)
elif mode == "會員喜好設定":
    _member_preferences_page.render(backend_email, backend_password, env)
