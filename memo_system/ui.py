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
    import re
    import importlib
    from datetime import date, timedelta
    from . import memo
    from . import shift
    from . import atm
    atm = importlib.reload(atm)
    from . import payment_match
    payment_match = importlib.reload(payment_match)
    from . import change_order

    def default_region_from_email(email_value):
        text = str(email_value or "").strip().lower()
        if ".tc@" in text or "+tc@" in text or text.startswith("jenny.tc@"):
            return "台中"
        return "台北"

    def region_selectbox(label, key, email_value=None):
        options = ["台北", "台中", "桃園", "新竹", "高雄"]
        default_region = default_region_from_email(email_value)
        marker_key = f"{key}_default_email"
        current_email = str(email_value or "").strip().lower()
        if st.session_state.get(marker_key) != current_email:
            st.session_state[key] = default_region
            st.session_state[marker_key] = current_email
        return st.selectbox(label, options, index=options.index(default_region), key=key)

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
    # ============================================================

    DEFAULT_RESULT = {
        "processed": 0, "success": 0, "failed": 0,
        "skipped": 0, "updated_orders": 0, "errors": [],
    }

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
    # Helpers
    # ============================================================

    def sec(title):
        st.markdown(f'<p class="sec-label">{title}</p>', unsafe_allow_html=True)

    def step(num, title):
        st.markdown(
            f'<div class="step-pill"><span class="step-num">{num}</span>{title}</div>',
            unsafe_allow_html=True
        )

    def normalize_result(r):
        base = DEFAULT_RESULT.copy()
        if isinstance(r, dict):
            base.update(r)
        if not isinstance(base.get("errors"), list):
            base["errors"] = []
        return base

    def render_result(result):
        r = normalize_result(result)
        with result_container:
            st.markdown("---")
            step("6", "執行結果")
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("執行筆數", r["processed"])
            c2.metric("成功", r["success"])
            c3.metric("失敗", r["failed"])
            c4.metric("略過", r["skipped"])
            c5.metric("回寫筆數", r["updated_orders"])
            if r["errors"]:
                with st.expander(f"⚠️ 錯誤明細（{len(r['errors'])} 筆）", expanded=True):
                    for i, err in enumerate(r["errors"], 1):
                        st.markdown(f"**{i}.** {err}")
            elif r["processed"] > 0:
                st.success(f"✅ 全部完成，共處理 {r['processed']} 筆，成功 {r['success']} 筆。")
            else:
                st.info("執行完成，無資料被處理。")

    def render_atm_result(result, container):
        r = normalize_result(result)
        with container:
            st.markdown("---")
            step("4", "執行結果")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("執行筆數", r["processed"])
            c2.metric("成功", r["success"])
            c3.metric("失敗", r["failed"])
            c4.metric("略過", r["skipped"])
            if r["errors"]:
                with st.expander(f"⚠️ 錯誤明細（{len(r['errors'])} 筆）", expanded=True):
                    for i, err in enumerate(r["errors"], 1):
                        st.markdown(f"**{i}.** {err}")
            elif r["processed"] > 0:
                st.success(f"✅ 全部完成，共處理 {r['processed']} 筆，成功 {r['success']} 筆。")
            else:
                st.info("執行完成，無資料被處理。")

    def ui_log(msg):
        st.session_state.logs.append(str(msg))
        try:
            log_box.text("\n".join(st.session_state.logs[-3000:]))
        except Exception:
            pass

    def safe_get(row, *keys, default=""):
        for k in keys:
            if k in row and row.get(k) is not None:
                return row.get(k)
        return default

    def clear_pick_states():
        for k in [k for k in st.session_state.keys() if k.startswith("pick_")]:
            del st.session_state[k]

    def reset_before_action(clear_preview=True, clear_selection=True):
        st.session_state.logs = []
        st.session_state.result = None
        if clear_preview:
            st.session_state.preview_rows = []
            st.session_state.sheet_summary = None
        if clear_selection:
            clear_pick_states()
        try:
            log_box.text("尚未執行")
        except Exception:
            pass

    def reset_before_execute_keep_preview():
        st.session_state.logs = []
        st.session_state.result = None
        try:
            log_box.text("尚未執行")
        except Exception:
            pass

    def reset_mode_state_if_changed(current_mode):
        if st.session_state.last_mode != current_mode:
            st.session_state.preview_rows = []
            st.session_state.sheet_summary = None
            clear_pick_states()
            st.session_state.last_mode = current_mode

    def get_session(ui_logger=None):
        desired_email = str(email or "").strip()
        desired_env = str(env_option or "prod").strip()
        if (st.session_state.auth_session is not None
                and (st.session_state.get("auth_email") != desired_email
                     or st.session_state.get("auth_env") != desired_env)):
            st.session_state.auth_session = None
            st.session_state.is_logged_in = False
        if st.session_state.auth_session is not None:
            return st.session_state.auth_session
        if not st.session_state.get("credentials_ready"):
            raise RuntimeError("請先在「登入」區塊輸入帳號密碼")
        session = memo.login(ui_logger=ui_logger)
        st.session_state.auth_session = session
        st.session_state.is_logged_in = True
        st.session_state.login_identity = desired_email
        st.session_state.auth_email = desired_email
        st.session_state.auth_env = desired_env
        return session

    # ============================================================
    # Preview blocks
    # ============================================================

    def render_preview_blocks(rows):
        step("4", "查詢結果預覽")
        if not rows:
            st.info("查無資料")
            return []

        can_rows = [r for r in rows if r.get("can_autofill")]
        no_rows  = [r for r in rows if not r.get("can_autofill")]

        m1, m2, m3 = st.columns(3)
        m1.metric("查詢總筆數", len(rows))
        m2.metric("可自動回填", len(can_rows))
        m3.metric("無可參照來源", len(no_rows))

        st.markdown(
            '<div class="info-strip">'
            '<b>預覽說明</b><ul>'
            '<li>目前訂單：要回填備註的目標訂單</li>'
            '<li>來源訂單：最近一筆可參照的歷史訂單</li>'
            '<li>新成單：沒有歷史來源時，會帶入預設提醒文字</li>'
            '</ul></div>',
            unsafe_allow_html=True
        )

        selected_ids = []

        def render_section(title, items, section_key, default_checked):
            st.markdown(f"### {title}")
            if not items:
                st.caption("沒有資料")
                return

            c1, c2, c3 = st.columns([1, 1, 4])
            with c1:
                if st.button("本區全選", key=f"sel_{section_key}", use_container_width=True):
                    for row in items:
                        oid = str(row.get("order_id", "")).strip()
                        if oid:
                            st.session_state[f"pick_{oid}"] = True
            with c2:
                if st.button("本區全不選", key=f"unsel_{section_key}", use_container_width=True):
                    for row in items:
                        oid = str(row.get("order_id", "")).strip()
                        if oid:
                            st.session_state[f"pick_{oid}"] = False
            with c3:
                st.caption(f"本區共 {len(items)} 筆")

            for row in items:
                order_id = str(row.get("order_id", "")).strip()
                checked = st.checkbox(
                    f"選取 {order_id}",
                    key=f"pick_{order_id}",
                    value=st.session_state.get(f"pick_{order_id}", default_checked),
                    label_visibility="collapsed"
                )

                card_cls = "preview-card preview-ok" if row.get("can_autofill") else "preview-card preview-ng"
                target_name          = row.get("customer_name", "")
                phone                = row.get("phone", "")
                address              = row.get("address", "")
                service_date         = row.get("service_date", "")
                purchase_status_name = row.get("purchase_status_name", "")
                source_order_id      = row.get("source_order_id", "")
                source_service_date  = row.get("source_service_date", "")
                source_purchase_status_name = row.get("source_purchase_status_name", "")
                source_status_name   = row.get("source_status_name", "")
                source_notice_preview = row.get("source_notice_preview", "")
                is_new_order         = row.get("is_new_order", False)
                can_autofill         = row.get("can_autofill", False)

                if is_new_order:
                    source_notice_display_html = "（請於下方欄位編輯要寫入後台的提醒文字）"
                    suggestion_text = "新成單，將帶入下方可編輯的提醒文字"
                elif can_autofill:
                    source_notice_display_html = source_notice_preview.replace("\n", "<br>") if source_notice_preview else ""
                    suggestion_text = "建議執行"
                else:
                    source_notice_display_html = source_notice_preview.replace("\n", "<br>") if source_notice_preview else ""
                    suggestion_text = "無可參照來源，請人工確認"

                st.markdown(f"""
                <div class="{card_cls}">
                    <div class="preview-title">目前訂單：{order_id}</div>
                    <div class="preview-sub">
                        <b>客戶 / 電話：</b>{target_name} / {phone}<br>
                        <b>地址：</b>{address}<br>
                        <b>目前服務日期：</b>{service_date}　
                        <b>目前付款狀態：</b>{purchase_status_name or "-"}
                    </div>
                    <hr style="margin:10px 0;">
                    <div class="preview-sub">
                        <b>來源訂單：</b>{source_order_id or "無"}<br>
                        <b>來源服務日期：</b>{source_service_date or "-"}　
                        <b>來源付款狀態：</b>{source_purchase_status_name or "-"}　
                        <b>來源服務狀態：</b>{source_status_name or "-"}<br>
                        <b>來源備註：</b>{source_notice_display_html or "無"}
                    </div>
                    <div class="preview-sub" style="margin-top:8px;">
                        <b>建議：</b>{suggestion_text}
                    </div>
                </div>
                """, unsafe_allow_html=True)

                if is_new_order:
                    st.text_area(
                        f"✏️ 新成單提醒文字（{order_id}，可自行編輯，將寫入後台備註）",
                        value=st.session_state.get(f"new_notice_{order_id}", memo.DEFAULT_NEW_ORDER_NOTICE),
                        key=f"new_notice_{order_id}",
                        height=130,
                    )

                if checked and order_id:
                    selected_ids.append(order_id)

        render_section("可自動回填", can_rows, "can_autofill", True)
        render_section("無可參照來源", no_rows, "no_source", False)

        st.markdown("---")
        step("5", "執行確認")
        st.metric("目前勾選", len(selected_ids))
        st.caption("執行後會把來源客服備註（或新成單固定提醒文字）寫入目標訂單，並把目標訂單服務狀態改為已處理。")
        return selected_ids

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

    shift_sub_section = None

    if main_section == "📅 排班管理":
        step("3", "選擇排班子功能")
        shift_sub_section = st.radio(
            "排班子功能",
            ["📥 排班匯入", "🍋 檸檬人勾班", "🧹 清空排班"],
            horizontal=True,
            label_visibility="collapsed",
            key="shift_sub_section",
        )
        SHIFT_SUB_HELP = {
            "📥 排班匯入": '<div class="info-strip"><b>操作流程</b><ol><li>上傳 Excel / CSV</li><li>執行 Dry Run 預覽</li><li>確認合併結果</li><li>正式儲存</li></ol></div>',
            "🍋 檸檬人勾班": '<div class="info-strip"><b>操作流程</b><ol><li>輸入檸檬人名單</li><li>選擇起迄日期</li><li>選擇要勾的班別</li><li>批次勾班</li></ol></div>',
            "🧹 清空排班": '<div class="warn-strip"><b>危險操作</b><ul><li>會直接修改後台排班</li><li>沒有逐筆預覽機制</li><li>請確認人員與日期後再執行</li></ul></div>',
        }
        st.markdown(SHIFT_SUB_HELP.get(shift_sub_section, ""), unsafe_allow_html=True)

    st.markdown("---")

    # ============================================================
    # 功能一：Memo 自動回填
    # ============================================================

    def render_memo_section():
        step("3", "設定查詢條件")

        mode = st.radio(
            "",
            ["By Google Sheet", "By 電話", "By 搜尋條件"],
            horizontal=True,
            label_visibility="collapsed",
            key="memo_mode",
        )
        reset_mode_state_if_changed(mode)

        row_spec = ""; force = False; sheet_run_mode = "指定列號"; sheet_limit = 5
        phone_text = ""; date_mode = "服務日期"; purchase_status_name = "全部"
        start_date = None; end_date = None
        sheet_summary_btn = False; search_btn = False; execute_btn = False

        if mode == "By Google Sheet":
            sheet_run_mode = st.radio("處理方式", ["指定列號", "依剩餘筆數處理"], horizontal=True)
            if sheet_run_mode == "指定列號":
                st.markdown('<div class="info-strip"><b>列號格式</b><ul><li>單列：<code>2</code></li><li>多列：<code>2,3,5</code></li><li>區間：<code>2,3,5-7</code></li></ul></div>', unsafe_allow_html=True)
                c1, c2 = st.columns([5, 1])
                with c1:
                    row_spec = st.text_input("列號")
                with c2:
                    st.markdown("<div style='height:26px'></div>", unsafe_allow_html=True)
                    force = st.checkbox("強制重跑")
                execute_btn = st.button("🚀 執行", use_container_width=True, disabled=not st.session_state.credentials_ready)
            else:
                c1, c2 = st.columns(2)
                with c1:
                    sheet_summary_btn = st.button("🔍 查詢目前筆數", use_container_width=True, disabled=not st.session_state.credentials_ready)
                with c2:
                    sheet_limit = st.number_input("本次處理筆數", min_value=1, value=5)
                if st.session_state.sheet_summary:
                    s = st.session_state.sheet_summary
                    m1, m2, m3 = st.columns(3)
                    m1.metric("總筆數", s.get("total_rows", 0))
                    m2.metric("未處理筆數", s.get("pending_rows", 0))
                    m3.metric("已處理筆數", s.get("done_rows", 0))
                execute_btn = st.button("🚀 執行前 N 筆未處理資料", use_container_width=True, disabled=not st.session_state.credentials_ready)

        elif mode == "By 電話":
            phone_text = st.text_area("電話號碼", placeholder="可輸入多支，以逗號或換行分隔，例：0912345678,0922345678")
            st.caption("會先找出「目標訂單」，再比對最近一筆可參照的來源訂單。")
            c1, c2 = st.columns(2)
            with c1:
                search_btn = st.button("🔍 查詢列表", use_container_width=True, disabled=not st.session_state.credentials_ready)
            with c2:
                execute_btn = st.button("🚀 執行勾選項目", use_container_width=True, disabled=not st.session_state.credentials_ready)

        else:
            c1, c2 = st.columns(2)
            with c1:
                date_mode = st.selectbox("日期條件", ["服務日期", "購買日期"])
            with c2:
                purchase_status_name = st.selectbox("付款狀態", ["全部", "已付款", "未付款"], index=0)
            c3, c4 = st.columns(2)
            with c3:
                start_date = st.date_input("開始日期", value=None)
            with c4:
                end_date = st.date_input("結束日期", value=None)
            st.caption("搜尋條件固定只撈服務狀態＝未處理的目標訂單，再比對最近的可參照來源。")
            c5, c6 = st.columns(2)
            with c5:
                search_btn = st.button("🔍 查詢列表", use_container_width=True, disabled=not st.session_state.credentials_ready)
            with c6:
                execute_btn = st.button("🚀 執行勾選項目", use_container_width=True, disabled=not st.session_state.credentials_ready)

        global log_box, result_container
        with st.expander("執行 LOG", expanded=True):
            log_box = st.empty()
            log_box.text("\n".join(st.session_state.logs[-3000:]) if st.session_state.logs else "尚未執行")

        result_container = st.container()
        if st.session_state.result is not None:
            render_result(st.session_state.result)

        if sheet_summary_btn:
            try:
                st.session_state.is_running = True
                reset_before_action(clear_preview=True, clear_selection=True)
                ui_log("===== 查詢目前筆數 =====")
                with st.spinner("查詢中，請稍候…"):
                    st.session_state.sheet_summary = memo.get_sheet_summary(ui_logger=ui_log)
                ui_log("✅ 查詢完成")
            except Exception as e:
                ui_log(f"❌ 查詢失敗：{e}")
                st.error(str(e))
            finally:
                st.session_state.is_running = False

        if search_btn:
            try:
                st.session_state.is_running = True
                reset_before_action(clear_preview=True, clear_selection=True)
                ui_log("===== 開始查詢 =====")
                with st.spinner("查詢中，請稍候…"):
                    session = get_session(ui_logger=ui_log)
                    if mode == "By 電話":
                        if not phone_text.strip():
                            raise ValueError("請輸入至少一支電話")
                        preview_rows = memo.preview_by_phone_multi(phone_text=phone_text.strip(), ui_logger=ui_log, session=session)
                    else:
                        start_text = start_date.strftime("%Y/%m/%d") if start_date else ""
                        end_text   = end_date.strftime("%Y/%m/%d") if end_date else ""
                        preview_rows = memo.preview_by_conditions(
                            date_mode=date_mode, date_start=start_text, date_end=end_text,
                            purchase_status_name=purchase_status_name, ui_logger=ui_log, session=session,
                        )
                st.session_state.preview_rows = preview_rows or []
                ui_log(f"✅ 查詢完成，共 {len(st.session_state.preview_rows)} 筆")
                st.rerun()
            except Exception as e:
                ui_log(f"❌ 查詢錯誤：{e}")
                st.error(str(e))
            finally:
                st.session_state.is_running = False

        if mode in ["By 電話", "By 搜尋條件"] and st.session_state.preview_rows:
            st.markdown("---")
            render_preview_blocks(st.session_state.preview_rows)

        if execute_btn:
            try:
                st.session_state.is_running = True
                reset_before_execute_keep_preview()

                if mode == "By Google Sheet":
                    ui_log("===== 開始執行 =====")
                    with st.spinner("執行中，請稍候…"):
                        session = get_session(ui_logger=ui_log)
                        if sheet_run_mode == "指定列號":
                            result = memo.main(row_spec=row_spec, force=force, ui_logger=ui_log, session=session)
                        else:
                            result = memo.main_first_n_pending(limit=int(sheet_limit), ui_logger=ui_log, session=session)
                else:
                    if not st.session_state.preview_rows:
                        raise RuntimeError("請先查詢列表")
                    current_selected_ids = []
                    custom_notices = {}
                    for row in st.session_state.preview_rows:
                        oid = str(safe_get(row, "order_id", default="")).strip()
                        if oid and st.session_state.get(f"pick_{oid}", False):
                            current_selected_ids.append(oid)
                            if row.get("is_new_order"):
                                custom_notices[oid] = st.session_state.get(f"new_notice_{oid}", memo.DEFAULT_NEW_ORDER_NOTICE)
                    if not current_selected_ids:
                        raise RuntimeError("請先勾選要執行的資料")
                    ui_log("===== 開始執行勾選項目 =====")
                    ui_log(f"勾選筆數：{len(current_selected_ids)}")
                    with st.spinner("執行中，請稍候…"):
                        session = get_session(ui_logger=ui_log)
                        result = memo.main_by_selected_order_ids(
                            order_ids=current_selected_ids, ui_logger=ui_log,
                            session=session, custom_notices=custom_notices,
                        )

                ui_log("===== 執行完成 =====")
                st.session_state.result = result
                render_result(result)
            except Exception as e:
                ui_log(f"❌ 執行錯誤：{e}")
                st.session_state.result = {**DEFAULT_RESULT, "failed": 1, "errors": [str(e)]}
                render_result(st.session_state.result)
            finally:
                st.session_state.is_running = False

    # ============================================================
    # 功能二：排班匯入
    # ============================================================

    def render_shift_import_section():
        step("3", "上傳排班匯入檔")
        st.markdown('<div class="info-strip"><b>檔案欄位</b><ul><li>地區、日期、類型、時段、名稱</li></ul><b>支援類型</b><ul><li>全6、全8、上4、上3、上2、下4、下3、下2、晚2、清</li></ul></div>', unsafe_allow_html=True)
        st.markdown('<div class="warn-strip"><b>注意</b><ul><li>正式儲存會直接修改後台排班</li><li>請先用 Dry Run 確認結果</li></ul></div>', unsafe_allow_html=True)

        uploaded_file = st.file_uploader("選擇 Excel / CSV 檔案", type=["xlsx", "xls", "csv"])
        c1, c2 = st.columns(2)
        with c1:
            dry_run_btn = st.button("🔍 Dry Run 預覽（不會寫入）", use_container_width=True, disabled=not (st.session_state.credentials_ready and uploaded_file is not None))
        with c2:
            execute_btn = st.button("🚀 正式儲存", use_container_width=True, disabled=not (st.session_state.credentials_ready and st.session_state.shift_dry_run_result is not None))

        with st.expander("執行 LOG", expanded=True):
            log_box_local = st.empty()
            log_box_local.text("\n".join(st.session_state.logs[-3000:]) if st.session_state.logs else "尚未執行")

        def shift_ui_log(msg):
            st.session_state.logs.append(str(msg))
            try: log_box_local.text("\n".join(st.session_state.logs[-3000:]))
            except: pass

        if dry_run_btn and uploaded_file is not None:
            try:
                st.session_state.logs = []; st.session_state.shift_dry_run_result = None
                shift_ui_log("===== 開始解析匯入檔 =====")
                rows = shift.parse_import_file(uploaded_file, uploaded_file.name)
                shift_ui_log(f"解析完成，共 {len(rows)} 筆有效資料")
                st.session_state.shift_import_rows = rows
                with st.spinner("Dry Run 中，請稍候…"):
                    session = get_session(ui_logger=shift_ui_log)
                    result = shift.process_import_file(rows, dry_run=True, ui_logger=shift_ui_log, session=session)
                st.session_state.shift_dry_run_result = result
                shift_ui_log("===== Dry Run 完成 =====")
            except Exception as e:
                shift_ui_log(f"❌ Dry Run 失敗：{e}"); st.error(str(e))

        if st.session_state.shift_dry_run_result:
            result = st.session_state.shift_dry_run_result
            st.markdown("---"); step("4", "Dry Run 結果預覽")
            m1, m2, m3 = st.columns(3)
            m1.metric("處理人數", result.get("processed_people", 0))
            m2.metric("處理月份數", result.get("processed_months", 0))
            m3.metric("略過人數", len(result.get("skipped", [])))
            if result.get("errors"):
                with st.expander(f"⚠️ 訊息（{len(result['errors'])} 筆）", expanded=True):
                    for i, err in enumerate(result["errors"], 1): st.markdown(f"**{i}.** {err}")
            for name, month, merged in result.get("dry_run_payloads", []):
                with st.expander(f"{name} — {month}（合併後共 {len(merged)} 筆勾選）", expanded=False):
                    if merged: st.text("\n".join(f"{k} = {v}" for k, v in sorted(merged.items())))
                    else: st.caption("這個月份合併後沒有任何勾選（可能是被「清」全部清空了）")
            st.caption("確認上面合併後的結果沒有問題，再按「正式儲存」送出。")

        if execute_btn:
            try:
                st.session_state.logs = []; ui_log("===== 開始正式儲存 =====")
                rows = st.session_state.shift_import_rows
                with st.spinner("儲存中，請稍候…"):
                    session = get_session(ui_logger=ui_log)
                    result = shift.process_import_file(rows, dry_run=False, ui_logger=ui_log, session=session)
                ui_log("===== 儲存完成 =====")
                st.success(f"✅ 完成，共儲存 {result.get('saved', 0)} 個人/月份")
                if result.get("errors"): st.error("\n".join(result["errors"][:20]))
                st.session_state.shift_dry_run_result = None
            except Exception as e:
                ui_log(f"❌ 儲存失敗：{e}"); st.error(str(e))

    # ============================================================
    # 功能三：檸檬人勾班
    # ============================================================

    def render_lemon_assign_section():
        step("3", "設定檸檬人勾班條件")
        st.markdown("""
        <div class="warn-strip">
        <b>注意</b>
        <ul>
        <li>會直接修改後台排班</li>
        <li>指定日期內原本已勾選的全日/上午/下午/晚上，會先清掉再套用本次選擇的班別</li>
        <li>請確認檸檬人名單、日期區間與班別後再執行</li>
        <li>多人請用逗號分隔，例如：<code>檸檬人1,檸檬人2,檸檬人3,檸檬人4,檸檬人5,檸檬人6,檸檬人7,檸檬人8,檸檬人9,檸檬人10,檸檬人11,檸檬人12</code></li>
        </ul>
        </div>
        """, unsafe_allow_html=True)

        c1, c2, c3 = st.columns([2, 1.3, 1.3])
        with c1:
            lemon_names_raw = st.text_input("檸檬人名單", placeholder="檸檬人1,檸檬人2,檸檬人3", key="lemon_assign_names")
        with c2:
            assign_start = st.date_input("開始日期", key="lemon_assign_start")
        with c3:
            assign_end = st.date_input("結束日期", key="lemon_assign_end")

        assign_types = st.multiselect(
            "要勾選的班別",
            [k for k in shift.TYPE_MAP.keys() if k != shift.CLEAR_TYPE],
            default=["全8"],
            key="lemon_assign_types",
        )

        lemon_names = [n.strip() for n in re.split(r"[,，]", lemon_names_raw) if n.strip()]
        if lemon_names:
            st.caption(f"將處理 {len(lemon_names)} 人：{'、'.join(lemon_names)}")
        if assign_types:
            st.caption(f"將勾選班別：{'、'.join(assign_types)}")

        execute_btn = st.button(
            "🚀 執行檸檬人勾班",
            use_container_width=True,
            type="primary",
            disabled=not (st.session_state.credentials_ready and bool(lemon_names) and bool(assign_types)),
        )

        with st.expander("執行 LOG", expanded=True):
            log_box_local = st.empty()
            log_box_local.text("\n".join(st.session_state.logs[-3000:]) if st.session_state.logs else "尚未執行")

        def lemon_assign_log(msg):
            st.session_state.logs.append(str(msg))
            try:
                log_box_local.text("\n".join(st.session_state.logs[-3000:]))
            except Exception:
                pass

        if execute_btn:
            try:
                st.session_state.logs = []
                st.session_state.lemon_assign_result = None
                lemon_assign_log(
                    f"===== 開始檸檬人勾班：{len(lemon_names)} 人，"
                    f"{assign_start.strftime('%Y-%m-%d')} ~ {assign_end.strftime('%Y-%m-%d')}，"
                    f"班別：{'、'.join(assign_types)} ====="
                )
                with st.spinner("勾班中，請稍候…"):
                    session = get_session(ui_logger=lemon_assign_log)
                    result = shift.assign_person_shift_range(
                        session=session,
                        names=lemon_names,
                        date_start=assign_start.strftime("%Y-%m-%d"),
                        date_end=assign_end.strftime("%Y-%m-%d"),
                        type_values=assign_types,
                        ui_logger=lemon_assign_log,
                    )
                st.session_state.lemon_assign_result = result
                lemon_assign_log("===== 檸檬人勾班完成 =====")
                st.rerun()
            except Exception as e:
                lemon_assign_log(f"❌ 勾班失敗：{e}")
                st.error(str(e))

        result = st.session_state.get("lemon_assign_result")
        if result is not None:
            st.markdown("---")
            step("4", "勾班結果")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("處理人數", result.get("processed_people", 0))
            c2.metric("處理月份數", result.get("processed_months", 0))
            c3.metric("儲存次數", result.get("saved", 0))
            c4.metric("錯誤數", len(result.get("errors", [])))

            if result.get("warnings"):
                with st.expander(f"⚠️ 衝突提醒（{len(result['warnings'])} 筆）", expanded=True):
                    for w in result["warnings"]:
                        st.warning(w)

            if result.get("errors"):
                with st.expander(f"❌ 錯誤明細（{len(result['errors'])} 筆）", expanded=True):
                    for err in result["errors"]:
                        st.error(err)
            else:
                st.success("✅ 檸檬人勾班完成")

    # ============================================================
    # 功能四：ATM 對帳
    # ============================================================

    def render_atm_section():
        step("3", "選擇 ATM 對帳步驟")
        atm_mode = st.radio("", ["① 待付款清單查詢", "② 配對銀行明細", "③ 更新系統對帳"], horizontal=True, label_visibility="collapsed", key="atm_mode")
        if "待付款" in atm_mode:
            render_atm_list_mode()
        elif "配對" in atm_mode:
            render_atm_auto_match_mode()
        else:
            render_atm_reconcile_mode()

    def render_payment_match_mode():
        step("3", "付款後5碼及星和診所比對（獨立功能）")
        st.caption("固定付款方式 ATM；查詢結果寫入 K:S，不使用原 ATM 待付款清單。")
        today = date.today()
        c1, c2, c3, c4 = st.columns(4)
        with c1: region = st.selectbox("地區", ["台北", "台中", "桃園", "新竹", "高雄"], key="payment_match_region")
        with c2: paid_start = st.date_input("付款日期-起", value=today.replace(day=1), key="payment_match_start")
        with c3: paid_end = st.date_input("付款日期-迄", value=today, key="payment_match_end")
        with c4: status_label = st.selectbox("付款狀態", ["已付款", "待付款"], key="payment_match_status")

        search_btn = st.button("🔍 搜尋付款訂單", use_container_width=True, disabled=not st.session_state.credentials_ready, key="payment_match_search")
        log_box_local = st.empty()

        def payment_log(msg):
            st.session_state.logs.append(str(msg))
            try: log_box_local.text("\n".join(st.session_state.logs[-2000:]))
            except Exception: pass

        current_context = (region, str(email or "").strip().lower())
        if st.session_state.get("payment_match_context") != current_context:
            st.session_state.payment_match_rows = None

        if search_btn:
            try:
                st.session_state.logs = []
                session = get_session(ui_logger=payment_log)
                st.session_state.payment_match_rows = payment_match.search_orders(
                    session, paid_start.strftime("%Y-%m-%d"), paid_end.strftime("%Y-%m-%d"),
                    "1" if status_label == "已付款" else "0",
                    region=region, login_email=email, ui_logger=payment_log,
                )
                st.session_state.payment_match_context = current_context
            except Exception as exc:
                payment_log(f"❌ 查詢失敗：{exc}")
                st.error(str(exc))

        rows = st.session_state.get("payment_match_rows")
        if rows is not None:
            st.metric("查到筆數", len(rows))
            if rows:
                st.dataframe(rows, use_container_width=True, hide_index=True)
                if st.button("📥 貼到 K:S 待比對區", type="primary", use_container_width=True, key="payment_match_paste"):
                    try:
                        result = payment_match.paste_orders(region, rows, ui_logger=payment_log)
                        st.success(f"已從第 {result['start_row']} 列貼上 {result['pasted']} 筆。")
                    except Exception as exc:
                        st.error(f"貼上失敗：{exc}")

        if st.button("🔗 比對銀行 B:H 與訂單 K:S", use_container_width=True, key="payment_match_run"):
            try:
                result = payment_match.match_bank_rows(region, ui_logger=payment_log)
                st.success(f"完成：配對 {result['matched_orders']} 筆訂單；待人工確認 {result['review']} 列。")
            except Exception as exc:
                st.error(f"比對失敗：{exc}")

    def render_atm_list_mode():
        step("3", "待付款清單查詢")
        c1, c2 = st.columns([1, 2])
        with c1: region = region_selectbox("要貼到哪個地區的工作表", "atm_list_region", email)
        with c2: date_until = st.date_input("訂購日期-迄（預設為前一天）", value=date.fromisoformat(atm.default_date_until_tw()), key="atm_list_date_until")

        search_btn = st.button("🔍 查詢待付款 ATM 名單", use_container_width=True, disabled=not st.session_state.credentials_ready)

        with st.expander("執行 LOG", expanded=True):
            log_box_local = st.empty()
            log_box_local.text("\n".join(st.session_state.logs[-3000:]) if st.session_state.logs else "尚未執行")

        def atm_list_ui_log(msg):
            st.session_state.logs.append(str(msg))
            try: log_box_local.text("\n".join(st.session_state.logs[-3000:]))
            except: pass

        if search_btn:
            try:
                st.session_state.logs = []; st.session_state.atm_list_rows = None; st.session_state.atm_list_paste_result = None
                atm_list_ui_log("===== 開始查詢 ATM 待付款名單 =====")
                with st.spinner("查詢中，請稍候…"):
                    session = get_session(ui_logger=atm_list_ui_log)
                    rows = atm.search_atm_unpaid_orders(session=session, date_until=date_until.strftime("%Y-%m-%d"), ui_logger=atm_list_ui_log)
                st.session_state.atm_list_rows = rows
                atm_list_ui_log("===== 查詢完成 =====")
                st.rerun()
            except Exception as e:
                atm_list_ui_log(f"❌ 查詢失敗：{e}"); st.error(str(e))

        rows = st.session_state.get("atm_list_rows")
        if rows is not None:
            st.markdown("---"); step("4", "查詢結果")
            if not rows:
                st.info("查無符合條件的待付款 ATM 訂單。")
            else:
                st.metric("查到筆數", len(rows))
                st.text("\n".join(f"{r['year_month']}　{r['order_no']}　{r['name']}　${r['net_amount']}" for r in rows))
                st.markdown(f'<div class="warn-strip">⚠️ 確認貼上後，會把以上 {len(rows)} 筆資料寫入「{region}」ATM 對帳工作表的 I~L 欄。</div>', unsafe_allow_html=True)
                if st.button(f"🚀 貼上到「{region}」ATM 對帳工作表", type="primary", use_container_width=True):
                    try:
                        atm_list_ui_log(f"===== 開始貼上到「{region}」ATM 對帳工作表 =====")
                        with st.spinner("貼上中，請稍候…"):
                            paste_result = atm.paste_atm_unpaid_list(region=region, rows=rows, ui_logger=atm_list_ui_log)
                        st.session_state.atm_list_paste_result = paste_result
                        atm_list_ui_log("===== 貼上完成 =====")
                        st.rerun()
                    except Exception as e:
                        atm_list_ui_log(f"❌ 貼上失敗：{e}"); st.error(str(e))

        if st.session_state.get("atm_list_paste_result") is not None:
            st.markdown("---"); step("5", "貼上結果")
            pr = st.session_state.get("atm_list_paste_result")
            if pr.get("errors"): st.error("；".join(pr["errors"]))
            else: st.success(f"✅ 已從第 {pr.get('start_row')} 列開始，貼上 {pr.get('pasted', 0)} 筆資料到 I~L 欄。")

    def render_atm_auto_match_mode():
        step("4", "配對銀行明細")
        st.markdown('<div class="info-strip"><b>配對依據</b><ul><li>金額 + 末碼</li><li>金額 + 姓名</li><li>金額 + 備註或時間</li><li>一筆收入可配對 2～5 筆訂單加總；須有末碼/姓名依據且組合唯一</li></ul></div>', unsafe_allow_html=True)
        st.markdown('<div class="warn-strip"><b>配對限制</b><ul><li>只靠金額不會自動配對</li><li>必須有末碼、姓名、備註或時間依據</li></ul></div>', unsafe_allow_html=True)

        row_spec = st.text_input("指定銀行列號", placeholder="例如：762-764,767-771")
        c1, c2, c3, c4 = st.columns([1, 1, 1, 1])
        with c1: region = region_selectbox("地區", "atm_match_region", email)
        with c2: default_service_type = st.text_input("預設服務類別", value="清潔", key="atm_match_service_type")
        with c3: default_fee_type = st.text_input("預設費用類別", value="服務費用", key="atm_match_fee_type")
        with c4:
            st.markdown("<div style='height:26px'></div>", unsafe_allow_html=True)
            overwrite_existing = st.checkbox("覆蓋已配對列", value=False, key="atm_match_overwrite")
        allow_review_prefill = st.checkbox("允許需確認候選預填", value=True, key="atm_match_allow_review_prefill")

        execute_btn = st.button("🚀 配對銀行明細", use_container_width=True, disabled=not st.session_state.credentials_ready)

        with st.expander("執行 LOG", expanded=True):
            log_box_local = st.empty()
            log_box_local.text("\n".join(st.session_state.logs[-3000:]) if st.session_state.logs else "尚未執行")

        def atm_match_ui_log(msg):
            st.session_state.logs.append(str(msg))
            try: log_box_local.text("\n".join(st.session_state.logs[-3000:]))
            except: pass

        result_container_local = st.container()
        if st.session_state.get("atm_match_result") is not None:
            render_atm_result(st.session_state.atm_match_result, result_container_local)

        if execute_btn:
            try:
                st.session_state.logs = []; st.session_state.atm_match_result = None
                atm_match_ui_log(f"===== 開始配對銀行明細（{region}）=====")
                with st.spinner("配對中，請稍候…"):
                    result = atm.auto_match_bank_rows(region=region, row_spec=row_spec.strip(), overwrite_existing=overwrite_existing, default_service_type=default_service_type.strip() or "清潔", default_fee_type=default_fee_type.strip() or "服務費用", allow_review_prefill=allow_review_prefill, ui_logger=atm_match_ui_log)
                atm_match_ui_log("===== 配對銀行明細完成 =====")
                st.session_state.atm_match_result = result
                render_atm_result(result, result_container_local)
            except Exception as e:
                atm_match_ui_log(f"❌ 自動配對失敗：{e}")
                st.session_state.atm_match_result = {**DEFAULT_RESULT, "failed": 1, "errors": [str(e)]}
                render_atm_result(st.session_state.atm_match_result, result_container_local)

    def render_atm_reconcile_mode():
        step("5", "更新系統對帳")
        st.markdown('<div class="warn-strip"><b>注意</b><ul><li>執行後會立即更新系統</li><li>發確認信會直接寄出</li><li>請確認列號正確後再執行</li></ul></div>', unsafe_allow_html=True)
        c1, c2 = st.columns([1, 3])
        with c1: region = region_selectbox("地區", "atm_reconcile_region", email)
        with c2: row_spec = st.text_input("列號", placeholder="支援：單列 2、逗號分隔 2,3,5、區間 2,3,5-7")
        c3, c4, c5 = st.columns(3)
        with c3: do_mark_paid = st.checkbox("按已付款", value=True)
        with c4: do_issue_invoice = st.checkbox("開立發票", value=True)
        with c5: do_send_mail = st.checkbox("發確認信", value=True)
        execute_btn = st.button("🚀 執行", use_container_width=True, disabled=not (st.session_state.credentials_ready and bool(row_spec.strip())))

        with st.expander("執行 LOG", expanded=True):
            log_box_local = st.empty()
            log_box_local.text("\n".join(st.session_state.logs[-3000:]) if st.session_state.logs else "尚未執行")

        def atm_ui_log(msg):
            st.session_state.logs.append(str(msg))
            try: log_box_local.text("\n".join(st.session_state.logs[-3000:]))
            except: pass

        atm_result_container = st.container()
        if st.session_state.get("atm_result") is not None:
            render_atm_result(st.session_state.atm_result, atm_result_container)

        if execute_btn:
            try:
                st.session_state.logs = []; st.session_state.atm_result = None
                atm_ui_log(f"===== 開始更新系統對帳（{region}）=====")
                if not (do_mark_paid or do_issue_invoice or do_send_mail):
                    raise ValueError("請至少勾選一項要執行的動作")
                with st.spinner("執行中，請稍候…"):
                    session = get_session(ui_logger=atm_ui_log)
                    result = atm.process_atm_rows(region=region, row_spec=row_spec, do_mark_paid=do_mark_paid, do_issue_invoice=do_issue_invoice, do_send_mail=do_send_mail, ui_logger=atm_ui_log, session=session)
                atm_ui_log("===== 執行完成 =====")
                st.session_state.atm_result = result
                render_atm_result(result, atm_result_container)
            except Exception as e:
                atm_ui_log(f"❌ 執行錯誤：{e}")
                st.session_state.atm_result = {**DEFAULT_RESULT, "failed": 1, "errors": [str(e)]}
                render_atm_result(st.session_state.atm_result, atm_result_container)

    # ============================================================
    # 功能五：清空排班
    # ============================================================

    def render_clear_shift_section():
        clear_mode = st.radio("", ["手動清空（某人 / 某段期間）", "自動清除候補檸檬人（從未配班清單）"], horizontal=True, label_visibility="collapsed", key="clear_shift_mode")

        if clear_mode == "手動清空（某人 / 某段期間）":
            step("3", "設定要清空的人員與期間")
            st.markdown('<div class="warn-strip"><b>注意</b><ul><li>會直接覆寫後台排班</li><li>沒有預覽機制</li><li>請確認姓名與日期區間</li><li>多人範例：<code>檸檬人1,檸檬人2,檸檬人3,檸檬人4,檸檬人5,檸檬人6,檸檬人7,檸檬人8,檸檬人9,檸檬人10,檸檬人11,檸檬人12,檸檬人13</code></li></ul></div>', unsafe_allow_html=True)
            c1, c2, c3 = st.columns([2, 1.3, 1.3])
            with c1: target_names_raw = st.text_input("人員姓名", placeholder="例如：蔡立娟 或 檸檬人3，多人用逗號分隔：檸檬人2,檸檬人4")
            with c2: range_start = st.date_input("開始日期", key="clear_range_start")
            with c3: range_end = st.date_input("結束日期", key="clear_range_end")
            target_names = [n.strip() for n in re.split(r"[,，]", target_names_raw) if n.strip()]
            if len(target_names) > 1: st.caption(f"將清空 {len(target_names)} 人：{'、'.join(target_names)}")
            execute_btn = st.button("🚀 執行清空", use_container_width=True, disabled=not (st.session_state.credentials_ready and bool(target_names)))

            with st.expander("執行 LOG", expanded=True):
                log_box_local = st.empty()
                log_box_local.text("\n".join(st.session_state.logs[-3000:]) if st.session_state.logs else "尚未執行")

            def clear_ui_log(msg):
                st.session_state.logs.append(str(msg))
                try: log_box_local.text("\n".join(st.session_state.logs[-3000:]))
                except: pass

            if st.session_state.clear_person_result is not None:
                results = st.session_state.clear_person_result
                if isinstance(results, dict): results = [results]
                st.markdown("---"); step("4", "執行結果")
                c1, c2, c3 = st.columns(3)
                c1.metric("清到資料的天數", sum(len(r.get("cleared_dates", [])) for r in results))
                c2.metric("原本就沒勾選的天數", sum(len(r.get("untouched_dates", [])) for r in results))
                c3.metric("移除的勾選筆數", sum(r.get("cleared_slot_count", 0) for r in results))
                for r in results:
                    if r.get("errors"):
                        with st.expander(f"⚠️ 「{r.get('name', '')}」錯誤明細（{len(r['errors'])} 筆）", expanded=True):
                            for i, err in enumerate(r["errors"], 1): st.markdown(f"**{i}.** {err}")
                    else:
                        st.success(f"✅ 已清空「{r.get('name', '')}」指定期間的排班（{len(r.get('cleared_dates', []))} 天有清到資料）。")

            if execute_btn:
                try:
                    st.session_state.logs = []; st.session_state.clear_person_result = None
                    clear_ui_log(f"===== 開始清空 {len(target_names)} 人的排班：{'、'.join(target_names)} =====")
                    results = []
                    with st.spinner("執行中，請稍候…"):
                        session = get_session(ui_logger=clear_ui_log)
                        for n in target_names:
                            clear_ui_log(f"\n----- 清空「{n}」-----")
                            results.append(shift.clear_person_shift_range(session=session, name=n, date_start=range_start.strftime("%Y-%m-%d"), date_end=range_end.strftime("%Y-%m-%d"), ui_logger=clear_ui_log))
                    clear_ui_log("===== 執行完成 =====")
                    st.session_state.clear_person_result = results
                    st.rerun()
                except Exception as e:
                    clear_ui_log(f"❌ 執行錯誤：{e}"); st.error(str(e))

        else:
            step("3", "設定要掃描並清空的日期區間")
            c1, c2 = st.columns(2)
            with c1: scan_start = st.date_input("開始日期", key="lemon_scan_start")
            with c2: scan_end = st.date_input("結束日期", key="lemon_scan_end")
            scan_btn = st.button("🔍 掃描並清空未配班清單", use_container_width=True, disabled=not st.session_state.credentials_ready)

            with st.expander("執行 LOG", expanded=True):
                log_box_local = st.empty()
                log_box_local.text("\n".join(st.session_state.logs[-3000:]) if st.session_state.logs else "尚未執行")

            def clear_ui_log(msg):
                st.session_state.logs.append(str(msg))
                try: log_box_local.text("\n".join(st.session_state.logs[-3000:]))
                except: pass

            if scan_btn:
                try:
                    st.session_state.logs = []; st.session_state.lemon_scan_entries = None; st.session_state.lemon_clear_results = None
                    clear_ui_log("===== 開始掃描未配班清單中的檸檬人 =====")
                    with st.spinner("掃描並清空中，請稍候…"):
                        session = get_session(ui_logger=clear_ui_log)
                        entries = shift.find_unassigned_lemon_bookings_range(
                            session=session,
                            date_start=scan_start.strftime("%Y-%m-%d"),
                            date_end=scan_end.strftime("%Y-%m-%d"),
                            ui_logger=clear_ui_log,
                        )
                        st.session_state.lemon_scan_entries = entries
                        if entries:
                            clear_ui_log("===== 開始清空候補檸檬人佔用的時段 =====")
                            results = shift.clear_unassigned_lemon_bookings(session=session, entries=entries, ui_logger=clear_ui_log)
                            st.session_state.lemon_clear_results = results
                            clear_ui_log("===== 清空完成，請重新整理後台班表確認 =====")
                        else:
                            st.session_state.lemon_clear_results = []
                            clear_ui_log("===== 掃描完成，沒有需要清空的檸檬人 =====")
                    st.rerun()
                except Exception as e:
                    clear_ui_log(f"❌ 掃描/清空失敗：{e}"); st.error(str(e))

            entries = st.session_state.lemon_scan_entries
            if entries is not None:
                st.markdown("---"); step("4", "掃描結果")
                if not entries:
                    st.info("這個日期區間的未配班清單裡沒有發現檸檬人。")
                else:
                    by_name = {}
                    for e in entries: by_name.setdefault(e["name"], []).append(e["date"])
                    st.metric("發現的檸檬人數", len(by_name))
                    for name, dates in by_name.items():
                        st.markdown(f'<div class="preview-card preview-ok"><div class="preview-title">{name}</div><div class="preview-sub"><b>佔用日期：</b>{"、".join(sorted(set(dates)))}</div></div>', unsafe_allow_html=True)
                    st.markdown('<div class="warn-strip"><b>已自動執行清空</b><ul><li>請重新整理後台班表確認結果</li><li>若仍顯示，請確認是否是未配班訂單本身尚未重新整理</li></ul></div>', unsafe_allow_html=True)

            if st.session_state.lemon_clear_results is not None:
                st.markdown("---"); step("5", "清空結果")
                for r in st.session_state.lemon_clear_results:
                    if r.get("errors"): st.error(f"❌ {r['name']}：{'；'.join(r['errors'])}")
                    else: st.success(f"✅ {r['name']}：清空 {len(r.get('cleared_dates', []))} 天，移除 {r.get('cleared_slot_count', 0)} 筆勾選")

    # ============================================================
    # 功能六：服務異動
    # ============================================================

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

    def render_change_order_section():
        step("3", "選擇服務異動步驟")
        co_mode = st.radio("", ["階段 A：查詢試算（寫入清潔異動工作表）", "階段 B：回填系統（讀工作表寫回後台）"], horizontal=True, label_visibility="collapsed", key="change_order_mode")
        if co_mode.startswith("階段 A"):
            render_change_order_stage_a()
        else:
            render_change_order_stage_b()

    def render_change_order_stage_a():
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
                    session = get_session(ui_logger=co_log)
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

    def render_change_order_stage_b():
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
                        session = get_session(ui_logger=co_log)
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

    # ============================================================
    # 功能七：評估文字工具
    # ============================================================

    def render_assessment_section():
        step("3", "貼入原始評估內容")
        st.markdown(
            '<div class="info-strip">'
            '自動從「建議M人N小時」解析人數與時數，計算平日（×600）與週末（×700）金額，'
            '產生兩個版本供複製使用。不需登入。'
            '</div>',
            unsafe_allow_html=True
        )

        raw = st.text_area("原始評估內容", height=300,
                            placeholder="Alan(台北)\n建議2人6保留加時可能\n10p以下0.5\n...")

        if st.button("產生兩版文字", use_container_width=True):
            if not raw.strip():
                st.warning("請先貼入評估內容")
                st.stop()

            lines = raw.strip().split("\n")
            header_line = ""; recommend_line = ""
            item_lines = []; note_lines = []; sum_line = ""
            phase = "header"

            for i, line in enumerate(lines):
                trimmed = line.strip()
                if not trimmed: continue
                if phase == "header" and i == 0:
                    header_line = trimmed; phase = "recommend"; continue
                if phase == "recommend":
                    if "建議" in trimmed:
                        # 建議可能夾在長句後半（如「...，建議3人8保留加時可能」），
                        # 從「建議」開始截取，丟掉前面的說明文字
                        idx = trimmed.index("建議")
                        recommend_line = trimmed[idx:]
                        phase = "items"
                    # 其他行（@Jenny、說明文字等）在 recommend 階段直接略過
                    continue
                if phase == "items":
                    if re.match(r"^[\d.+\s]+=", trimmed):
                        sum_line = trimmed; phase = "notes"; continue
                    item_lines.append(trimmed); continue
                if phase == "notes":
                    note_lines.append(line)

            m = re.search(r"建議\s*(\d+)\s*人\s*(\d+(?:\.\d+)?)", recommend_line)
            extra_lines = []
            if m:
                people = float(m.group(1))
                hours  = float(m.group(2))
                wd_price = int(round(people * hours * 600))
                wk_price = int(round(people * hours * 700))

                # 服務金額（含稅）
                amount_line = f"服務金額：平日 ${wd_price}（含稅）；週末 ${wk_price}（含稅）"

                # 服務時間：依時數規則
                M = int(people)
                N = hours
                hrs_label = int(N) if N == int(N) else N
                time_label = f"{M}人{hrs_label}小時"

                if N <= 3:
                    # 短班：AM 09 開始，PM 14 開始，各 N 小時
                    am_end = int(9 + N)
                    pm_end = int(14 + N)
                    time_range = f"09-{am_end:02d}點 或 14-{pm_end:02d}點"
                elif N == 4:
                    # 4 小時：AM 08:30 起，PM 14:00 起
                    time_range = "08:30-12:30 或 14:00-18:00"
                else:
                    # 5 小時以上：09 開始，加 1 小時休息
                    end_raw = 9 + N + 1
                    end_h   = int(end_raw)
                    end_m   = int(round((end_raw - end_h) * 60))
                    end_str = f"{end_h:02d}" if end_m == 0 else f"{end_h:02d}:{end_m:02d}"
                    time_range = f"09-{end_str}點，中間休息1小時"

                time_line = f"服務時間：{time_label}--{time_range}"
                extra_lines = [amount_line, time_line]

                st.success(
                    f"解析：{M} 人 × {hrs_label} 小時 → "
                    f"平日 ${wd_price}（含稅）、週末 ${wk_price}（含稅）｜{time_range}"
                )
            else:
                st.warning("未能從建議行解析到「M人N小時」，服務金額與時間欄位略過")

            rec_line = re.sub(
                r"(建議\s*\d+\s*人\s*)(\d+(?:\.\d+)?)(?!小時)",
                lambda mo: mo.group(1) + mo.group(2) + "小時",
                recommend_line
            )

            # 版本一：header + 建議 + 服務金額 + 服務時間 + 空行 + 評估內容: + 項目（含時數）+ 加總
            v1_lines = [header_line, rec_line] + extra_lines + ["", "評估內容："] + item_lines
            if sum_line: v1_lines.append(sum_line)

            # 版本二：header + 建議 + 服務金額 + 服務時間 + 空行 + 評估內容: + 項目（去時數）+ 注意事項（不含加總）
            v2_item_lines = [re.sub(r"[\d.]+\s*$", "", l).rstrip() for l in item_lines]
            v2_lines = [header_line, rec_line] + extra_lines + ["", "評估內容："] + v2_item_lines
            if note_lines:
                v2_lines.append("")
                v2_lines.extend(note_lines)

            st.session_state["assess_v1"] = "\n".join(v1_lines)
            st.session_state["assess_v2"] = "\n".join(v2_lines)

        if st.session_state.get("assess_v1"):
            import html as _html
            import streamlit.components.v1 as _components

            def _copyable_editor(label, content, key_suffix, height):
                safe = _html.escape(content)
                lines = content.count("\n") + 1
                ta_height = max(height, lines * 26 + 60)
                _components.html(f"""
    <html><body style="margin:0;padding:0;background:transparent;">
    <p style="margin:0 0 4px 0;font-size:14px;font-weight:700;
       font-family:'Noto Sans TC',sans-serif;color:#1C1C1E;">{_html.escape(label)}</p>
    <textarea id="ta_{key_suffix}"
      style="width:100%;height:{ta_height}px;box-sizing:border-box;
             border-radius:12px;border:1.5px solid #E8E8EC;
             font-size:14px;line-height:1.6;padding:10px;
             font-family:'Noto Sans TC',sans-serif;resize:vertical;">{safe}</textarea>
    <button id="btn_{key_suffix}"
      onclick="navigator.clipboard.writeText(document.getElementById('ta_{key_suffix}').value)
               .then(function(){{
                   document.getElementById('btn_{key_suffix}').textContent='✅ 已複製！';
                   setTimeout(function(){{
                       document.getElementById('btn_{key_suffix}').textContent='複製';
                   }}, 1500);
               }});"
      style="background:#F5C518;border:none;border-radius:12px;padding:9px 16px;
             font-weight:700;cursor:pointer;width:100%;margin-top:8px;font-size:15px;
             font-family:'Noto Sans TC',sans-serif;">
      複製
    </button>
    </body></html>
    """, height=ta_height + 80)

            st.markdown("---")
            step("4", "版本一 — 含時數（至加總）")
            _copyable_editor("版本一", st.session_state["assess_v1"], "v1", 260)

            st.markdown("<div style='margin-top:1.2rem'></div>", unsafe_allow_html=True)
            step("5", "版本二 — 移除時數（含注意事項）")
            _copyable_editor("版本二", st.session_state["assess_v2"], "v2", 600)

    # ============================================================
    # 路由
    # ============================================================

    if main_section == "📋 客服作業":
        render_memo_section()

    elif main_section == "📅 排班管理":
        if shift_sub_section == "📥 排班匯入":
            render_shift_import_section()
        elif shift_sub_section == "🍋 檸檬人勾班":
            render_lemon_assign_section()
        else:
            render_clear_shift_section()

    elif main_section == "💰 財務對帳":
        render_atm_section()

    elif main_section == "💳 付款後5碼及星和診所比對":
        render_payment_match_mode()

    elif main_section == "🔄 服務異動":
        render_change_order_section()

    elif main_section == "📐 評估文字工具":
        render_assessment_section()
