# ============================================================
# 檔名：tools/memo_system/ui.py（原 memo-system/memoapp.py）
# 說明：整併進 tool-system，包成 render_memo_system() 供
#       pages/訂單系統.py 呼叫。
# 更新記錄：
# 2026-07-15（二）
# - 清潔異動階段 B 掃描說明補上專員服務時間異動、車馬費發票、VIP券與儲值金
#   扣返等特殊 B 欄狀態。
# 2026-07-15
# - 清潔異動階段 A/B 地區下拉新增桃園／新竹／高雄，對應 change_order.py
#   v2.3 新增的清潔異動 Google Sheet。
# 2026-07-13
# - ATM 對帳地區預設改由登入帳號判斷；jenny.tc 等台中帳號預設台中，
#   避免台中登入卻查詢/貼到台北工作表。
# 2026-07-08
# - ATM 待付款清單的預設訂購日期迄改用 atm.default_date_until_tw()，避免
#   Streamlit Cloud UTC 日期造成前一天判斷錯誤。
# - 清潔異動加時/減時發生時間改為「服務前／專員回報」，移除「服務後」。
# - 清潔異動階段 B 畫面文案改為待加收/已加收，對應 change_order.py v1.9。
# ============================================================
def render_memo_system(forced_main_section=None, shared_backend_email=None, shared_backend_password=None, shared_env=None):
    # memoapp.py
    # -*- coding: utf-8 -*-
    import streamlit as st
    from . import memo
    from . import change_order

    from function.ui_common import step
    from function import memo_customer_service as _memo_customer_service_page
    from function import shift_management as _shift_management_page
    from function import atm_reconciliation as _atm_reconciliation_page
    from function import payment_match_page as _payment_match_page
    from function import change_order_page as _change_order_page
    from function import assessment_tool as _assessment_tool_page

    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;700;900&family=Space+Grotesk:wght@500;700&display=swap');

    :root {
        --lemon:       #F5C518;
        --lemon-dark:  #D4A017;
        --lemon-soft:  #FFFCF2;
        --lemon-mid:   #FFF3C4;
        --charcoal:    #1C1C1E;
        --ink:         #3A3A3C;
        --muted:       #8E8E93;
        --border:      #E8E8EC;
        --surface:     #FFFFFF;
        --success:     #34C759;
        --danger:      #FF3B30;
        --radius:      16px;
        --shadow:      0 2px 14px rgba(0,0,0,0.05);
    }

    html, body, [class*="css"] {
        font-family: 'Noto Sans TC', sans-serif;
        color: var(--charcoal);
    }

    #MainMenu, footer, header { visibility: hidden; }

    [data-testid="stAppViewContainer"] { background: #FAFAFA; }

    .block-container {
        padding-top: 2.2rem !important;
        padding-bottom: 2.5rem !important;
        max-width: 1180px !important;
    }

    .hero {
        background: linear-gradient(135deg, #FFFDF5 0%, #FFFBEA 100%);
        border: 1.5px solid var(--lemon-mid);
        border-radius: var(--radius);
        padding: 2.1rem 2.6rem;
        margin-bottom: 2.2rem;
        display: flex;
        align-items: center;
        gap: 1.3rem;
        box-shadow: 0 2px 14px rgba(245,197,24,0.08);
    }
    .hero-emoji { font-size: 3.1rem; line-height: 1; }
    .hero-title {
        font-family: 'Space Grotesk', sans-serif;
        font-size: 2rem;
        font-weight: 700;
        color: var(--charcoal);
        margin: 0;
        letter-spacing: -0.5px;
    }
    .hero-sub {
        color: var(--ink);
        font-size: 0.94rem;
        margin-top: 0.35rem;
        opacity: 0.75;
        line-height: 1.6;
    }

    .step-pill {
        display: inline-flex;
        align-items: center;
        gap: 0.6rem;
        background: var(--surface);
        border: 1.5px solid var(--lemon-mid);
        border-radius: 30px;
        padding: 0.4rem 1.1rem 0.4rem 0.5rem;
        font-size: 0.98rem;
        font-weight: 900;
        color: var(--charcoal);
        margin-bottom: 1.1rem;
        box-shadow: 0 2px 8px rgba(245,197,24,0.10);
    }
    .step-num {
        background: var(--lemon);
        border-radius: 50%;
        width: 26px; height: 26px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        font-size: 0.85rem;
        font-weight: 900;
        box-shadow: 0 1px 4px rgba(212,160,23,0.4);
    }

    .sec-label {
        font-size: 12px;
        font-weight: 700;
        color: var(--muted);
        letter-spacing: .04em;
        margin-bottom: 8px;
    }

    .info-strip {
        background: var(--lemon-soft);
        border-left: 4px solid var(--lemon);
        border-radius: 0 10px 10px 0;
        padding: 0.75rem 1.1rem;
        font-size: 0.9rem;
        color: var(--ink);
        margin-bottom: 1rem;
    }
    .info-strip code {
        background: var(--lemon-mid);
        color: var(--charcoal);
        padding: 1px 6px;
        border-radius: 5px;
        font-weight: 700;
    }

    .warn-strip {
        background: #FFF4E5;
        border-left: 4px solid #FF9500;
        border-radius: 0 10px 10px 0;
        padding: 0.75rem 1.1rem;
        font-size: 0.9rem;
        color: var(--ink);
        margin-bottom: 1rem;
    }

    .stTextInput label, .stSelectbox label, .stDateInput label,
    .stNumberInput label, .stRadio label, .stTextArea label,
    .stFileUploader label {
        font-weight: 700 !important;
        font-size: 14.5px !important;
        color: var(--charcoal) !important;
    }

    .stButton > button {
        background: var(--lemon) !important;
        color: var(--charcoal) !important;
        border: none !important;
        border-radius: 12px !important;
        font-weight: 700 !important;
        font-family: 'Noto Sans TC', sans-serif !important;
        font-size: 15px !important;
        padding: 0.6rem 1.2rem !important;
        transition: background 0.18s, transform 0.12s, box-shadow 0.18s !important;
        box-shadow: 0 3px 12px rgba(245,197,24,0.30) !important;
    }
    .stButton > button:hover {
        background: var(--lemon-dark) !important;
        transform: translateY(-1px) !important;
        box-shadow: 0 4px 16px rgba(245,197,24,0.40) !important;
    }
    .stButton > button[kind="primary"] {
        background: var(--charcoal) !important;
        color: var(--lemon) !important;
        box-shadow: 0 3px 14px rgba(28,28,30,0.25) !important;
    }
    .stButton > button[kind="primary"]:hover { background: #2C2C2E !important; }

    button[kind="secondary"] {
        background: var(--surface) !important;
        color: var(--charcoal) !important;
        border: 1.5px solid var(--border) !important;
        box-shadow: none !important;
    }

    .stTextInput input, .stSelectbox > div > div,
    .stDateInput input, .stNumberInput input, .stTextArea textarea {
        border-radius: 12px !important;
        border: 1.5px solid var(--border) !important;
        background: white !important;
        font-size: 15px !important;
    }
    .stTextInput input:focus, .stNumberInput input:focus, .stTextArea textarea:focus {
        border-color: var(--lemon) !important;
        box-shadow: 0 0 0 3px rgba(245,197,24,0.18) !important;
    }
    .stCheckbox label, .stRadio > div { font-weight: 600 !important; }
    div[role="radiogroup"] { gap: 0.4rem; }

    [data-testid="stMetric"] {
        background: white;
        border: 1px solid var(--border);
        border-radius: var(--radius);
        padding: 16px;
        box-shadow: var(--shadow);
    }
    [data-testid="stMetricValue"] { font-family: 'Space Grotesk', sans-serif; font-weight: 700; }
    [data-testid="stMetricLabel"] { font-weight: 600; color: var(--muted); }

    .preview-card {
        border: 1px solid var(--border);
        border-radius: var(--radius);
        padding: 16px 18px;
        margin-bottom: 12px;
        background: white;
        box-shadow: var(--shadow);
    }
    .preview-ok  { border-left: 6px solid var(--success); }
    .preview-ng  { border-left: 6px solid #d4d4d8; }
    .preview-title { font-size: 16px; font-weight: 700; margin-bottom: 8px; }
    .preview-sub   { color: #444; font-size: 14px; line-height: 1.7; }

    [data-testid="stCode"] { border-radius: 12px !important; font-size: 13px !important; background:white !important; color:#1C1C1E !important; min-height:auto !important; }
    .streamlit-expanderHeader { font-weight: 700 !important; font-size: 0.95rem !important; }
    .streamlit-expander { border-radius: var(--radius) !important; border: 1px solid var(--border) !important; }
    hr { border-color: #ececec !important; margin: 1.6rem 0 !important; }
    </style>
    """, unsafe_allow_html=True)

    # ============================================================
    # Session state
    DEFAULT_STATE = {
        "logs": [], "result": None, "is_running": False,
        "is_logged_in": False, "preview_rows": [], "last_mode": "",
        "login_identity": "", "sheet_summary": None,
        "shift_import_rows": [], "shift_dry_run_result": None,
        "lemon_candidate": None, "lemon_assign_result": None,
        "atm_result": None, "atm_match_result": None,
        "atm_list_rows": None, "atm_list_paste_result": None,
        "clear_person_result": None,
        "lemon_scan_entries": None, "lemon_clear_results": None,
        "co_calc_rows": [], "co_pending_rows": [],
        "co_phone_orders": [], "co_selected_order_no": "",
        "co_selected_order_detail": None,
        "auth_session": None, "auth_env": "", "auth_email": "", "credentials_ready": False,
        "assess_v1": "", "assess_v2": "",
    }

    for k, v in DEFAULT_STATE.items():
        if k not in st.session_state:
            st.session_state[k] = v

    st.session_state.is_running = False

    # ============================================================
    # Hero
    # ============================================================

    if shared_backend_email is None:
        st.markdown("""
        <div class="hero">
          <div class="hero-emoji">🍋</div>
          <div>
            <div class="hero-title">檸檬營運自動化工具</div>
            <div class="hero-sub">客服・排班・財務・服務異動作業平台</div>
          </div>
        </div>
        """, unsafe_allow_html=True)

    # ============================================================
    # Step 1：登入
    # ============================================================

    if shared_backend_email is not None:
        # 由整合頁面（pages/訂單系統.py）統一提供帳密/環境，這裡不再重複顯示登入欄位。
        email, password, env_option = shared_backend_email, shared_backend_password, shared_env
        memo.set_env(env_option)
        change_order.set_env(env_option)
        memo.set_runtime_credentials(email, password)
        st.session_state.credentials_ready = bool((email or "").strip()) and bool((password or "").strip())

        if (st.session_state.is_logged_in
                and ((st.session_state.auth_env and st.session_state.auth_env != env_option)
                     or (st.session_state.auth_email and st.session_state.auth_email != (email or "").strip()))):
            st.session_state.auth_session = None
            st.session_state.is_logged_in = False
    else:
        step("1", "登入與環境設定")
        login_expanded = not st.session_state.is_logged_in

        with st.expander(
            f"✅ 已登入：{st.session_state.login_identity}" if st.session_state.is_logged_in else "🔐 尚未登入，請輸入帳密",
            expanded=login_expanded,
        ):
            col_e, col_p, col_env = st.columns([2.4, 2.4, 1.2])
            with col_e:
                email = st.text_input("後台帳號", placeholder="jenny@lemonclean.com.tw", key="login_email")
            with col_p:
                password = st.text_input("後台密碼", type="password", key="login_password")
            with col_env:
                env_option = st.selectbox("環境", ["prod", "dev"], index=0, key="login_env")

            memo.set_env(env_option)
            change_order.set_env(env_option)
            memo.set_runtime_credentials(email, password)
            st.session_state.credentials_ready = bool(email.strip()) and bool(password.strip())

            if st.button("解除鎖定 / 重新登入", use_container_width=True):
                st.session_state.is_running = False
                st.session_state.logs = []
                st.session_state.auth_session = None
                st.session_state.is_logged_in = False
                st.success("已解除鎖定，下次執行任何功能時會自動重新登入。")
                st.rerun()

            if (st.session_state.is_logged_in
                    and ((st.session_state.auth_env and st.session_state.auth_env != env_option)
                         or (st.session_state.auth_email and st.session_state.auth_email != email.strip()))):
                st.session_state.auth_session = None
                st.session_state.is_logged_in = False
                st.warning("帳號或環境已切換，下次執行功能時會自動重新登入。")

        if not st.session_state.credentials_ready:
            st.markdown(
                '<div class="info-strip"><b>開始前</b><ul>'
                '<li>請先輸入後台帳號與密碼</li>'
                '<li>執行功能時會自動登入，不用另外按 Login</li>'
                '<li>評估文字工具不需登入，可直接使用</li>'
                '</ul></div>',
                unsafe_allow_html=True
            )
        elif not st.session_state.is_logged_in:
            st.markdown(
                '<div class="info-strip"><b>帳密已就緒</b><ul>'
                '<li>第一次執行功能時會自動登入</li>'
                '<li>登入後各功能共用同一組 Session</li>'
                '</ul></div>',
                unsafe_allow_html=True
            )

        st.markdown("---")

    # ============================================================
    # Step 2：選擇功能
    # ============================================================

    if forced_main_section is not None:
        main_section = forced_main_section
    else:
        step("2", "選擇功能")

        main_section = st.selectbox(
            "功能",
            [
                "📋 客服作業",
                "📅 排班管理",
                "💰 財務對帳",
                "💳 付款後5碼及星和診所比對",
                "🔄 服務異動",
                "📐 評估文字工具",
            ],
            label_visibility="collapsed",
            key="main_section",
        )

    MAIN_SECTION_HELP = {
        "📋 客服作業": """
        <div class="info-strip"><b>用途</b><ul>
        <li>舊客回購備註回填</li><li>新成單提醒建立</li><li>客服備忘錄整理</li>
        </ul><b>流程</b><ol>
        <li>選擇查詢方式</li><li>查詢並預覽</li><li>勾選訂單</li><li>執行回填</li>
        </ol></div>""",
        "📅 排班管理": """
        <div class="info-strip"><b>可執行項目</b><ul>
        <li>排班匯入</li><li>檸檬人勾班</li><li>清空排班</li>
        </ul><b>下一步</b><ul><li>請選擇下方排班子功能</li></ul></div>""",
        "💰 財務對帳": """
        <div class="info-strip"><b>建議順序</b><ol>
        <li>待付款清單查詢</li><li>配對銀行明細</li><li>更新系統對帳</li>
        </ol><b>用途</b><ul>
        <li>每日 ATM 對帳</li><li>補款確認</li><li>發票與確認信處理</li>
        </ul></div>""",
        "💳 付款後5碼及星和診所比對": """
        <div class="info-strip"><b>獨立對帳功能</b><ul>
        <li>依付款日期、付款狀態搜尋 ATM 訂單</li>
        <li>訂單資料寫入 K～S；比對銀行 B～H</li>
        <li>支援一筆匯款對多筆訂單及星和診所</li>
        </ul><b>安全範圍</b><ul><li>不會更新後台付款狀態、發票或寄信</li></ul></div>""",
        "🔄 服務異動": """
        <div class="info-strip"><b>支援項目</b><ul>
        <li>車馬費、異動費</li><li>服務前加時、服務前減時</li>
        <li>專員回報加時、專員回報減時</li><li>退款、客訴退款、物損退款</li>
        </ul><b>建議流程</b><ol>
        <li>階段 A：查詢試算</li><li>確認後寫入工作表</li><li>階段 B：同步回後台</li>
        </ol></div>""",
        "📐 評估文字工具": """
        <div class="info-strip"><b>用途</b><ul>
        <li>貼入評估內容，自動產生兩版文字</li>
        <li>版本一：含各項時數與加總</li>
        <li>版本二：移除時數，含注意事項</li>
        </ul><b>金額自動計算</b><ul>
        <li>從「建議M人N小時」解析</li>
        <li>平日 M×N×600</li>
        <li>週末 M×N×700</li>
        </ul><b>不需登入，可直接使用</b></div>""",
    }

    st.markdown(MAIN_SECTION_HELP.get(main_section, ""), unsafe_allow_html=True)


    st.markdown("---")

    # ============================================================
    # 路由
    # ============================================================

    if main_section == "📋 客服作業":
        _memo_customer_service_page.render(email, password, env_option)

    elif main_section == "📅 排班管理":
        _shift_management_page.render(email, password, env_option)

    elif main_section == "💰 財務對帳":
        _atm_reconciliation_page.render(email, password, env_option)

    elif main_section == "💳 付款後5碼及星和診所比對":
        _payment_match_page.render(email, password, env_option)

    elif main_section == "🔄 服務異動":
        _change_order_page.render(email, password, env_option)

    elif main_section == "📐 評估文字工具":
        _assessment_tool_page.render(email, password, env_option)
